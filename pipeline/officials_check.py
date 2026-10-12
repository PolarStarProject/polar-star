"""State and local officials, each checked against an official government page every week. Nothing is approved by hand.

Usage:  python pipeline/officials_check.py        (needs internet; runs in GitHub Actions)

Local jails that hold people for ICE (data/reference/local_officials.csv): the sheriff, jailer or corrections head
named for each jail. A row is shown only while its official source page (a county, sheriff's office or agency site)
still names that person. A row with no official page is kept on file but not shown.

Governors: the current governor of each state, from Wikidata (the person holding the office with no end date), or,
where Wikidata does not settle it, from data/reference/governors_ref.csv (kept by hand). Either way a governor is shown
only when the governor's own official website names them. Wikidata gives the start date when it has one.

A page that cannot be reached keeps a row that passed within the last 21 days; if most fetches fail, nothing is
written. Writes data/reference/local_officials_checked.csv, governors.csv and officials_meta.json.
"""
import csv, datetime as dt, html, json, re, sys, urllib.parse
from pathlib import Path
from social_check import fetcher

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
GRACE_DAYS = 21
SPARQL = """SELECT ?iso ?person ?personLabel ?start ?partyLabel ?site WHERE {
  ?state wdt:P31 wd:Q35657; wdt:P300 ?iso; wdt:P1313 ?office.
  ?person p:P39 ?st. ?st ps:P39 ?office. FILTER NOT EXISTS { ?st pq:P582 ?end }
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?person p:P102 ?ps. ?ps ps:P102 ?party. FILTER NOT EXISTS { ?ps pq:P582 ?pend } }
  OPTIONAL { ?office wdt:P856 ?site }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }"""
PARTY = {"Republican Party": "R", "Democratic Party": "D"}


def page_names(page, name):
    """True when the page's text has the person's first and last name (middle initials and Jr./Sr. not required)."""
    if not page: return False
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).lower()
    words = [w for w in re.sub(r"[.,]", " ", name).split() if len(w) > 1 and w.lower() not in ("jr", "sr", "ii", "iii", "iv")]
    if len(words) < 2: return False
    first, last = words[0].lower(), words[-1].lower()
    return re.search(r"\b" + re.escape(first) + r"\b", text) is not None and re.search(r"\b" + re.escape(last) + r"\b", text) is not None


def check_rows(rows, prev, today, get_text, keyf, namef, urlf):
    out, errors = [], 0
    for r in rows:
        k = keyf(r); p = prev.get(k, {}); res = dict(r, ok="0", checked=str(today), last_ok=p.get("last_ok", ""))
        u = urlf(r)
        if not u: res["reason"] = "no official page to check"; out.append(res); continue
        page = get_text(u)
        if page is None:
            errors += 1; res["reason"] = "official page could not be reached"
            if p.get("last_ok") and (today - dt.date.fromisoformat(p["last_ok"])).days <= GRACE_DAYS: res["ok"] = "1"
        elif page_names(page, namef(r)): res["ok"], res["last_ok"], res["reason"] = "1", str(today), ""
        else: res["reason"] = "the official page does not name this person"
        out.append(res)
    return out, errors


def wikidata(query):
    import time, urllib.request
    from identity import USER_AGENT
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": query, "format": "json"})
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"}), timeout=120) as r: return json.loads(r.read().decode("utf-8"))
        except Exception: time.sleep(20)
    return None


def governors(get_json=None):
    """One row per state with exactly one current governor in Wikidata, or none for that state."""
    j = (get_json or (lambda q: wikidata(q)))(SPARQL)
    by = {}
    for b in (j or {}).get("results", {}).get("bindings", []):
        v = {k: x["value"] for k, x in b.items()}
        st = v["iso"].split("-")[-1]
        g = by.setdefault(st, {})
        g.setdefault(v["person"], {"state": st, "name": v.get("personLabel", ""), "start": v.get("start", "")[:10], "parties": set(), "site": v.get("site", "")})
        if v.get("partyLabel"): g[v["person"]]["parties"].add(v["partyLabel"])
        if v.get("site") and not g[v["person"]]["site"]: g[v["person"]]["site"] = v["site"]
    out = []
    for st, people in sorted(by.items()):
        # Past governors often lack an end date in Wikidata, so several look "current": take the one who started last, and
        # skip the state when that is not clear-cut (no start date, or a tie). The official-site check follows.
        P = sorted(people.values(), key=lambda g: g["start"], reverse=True)
        if not P[0]["start"] or (len(P) > 1 and P[1]["start"] == P[0]["start"]): continue
        g = P[0]
        ps = sorted(g["parties"])
        g["party"] = PARTY.get(ps[0], "I" if ps else "") if len(ps) == 1 else ""
        out.append({"state": st, "name": g["name"], "party": g["party"], "start": g["start"], "site": g["site"]})
    return out


def write(name, rows, fields):
    with open(REF / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n", extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def main():
    get_text, get_json = fetcher()
    today = dt.date.today()
    rd = lambda n: list(csv.DictReader(open(REF / n, encoding="utf-8"), delimiter="|")) if (REF / n).exists() else []
    loc = rd("local_officials.csv")
    prev = {(r["facility_name"], r["state"]): r for r in rd("local_officials_checked.csv")}
    lout, lerr = check_rows(loc, prev, today, get_text, lambda r: (r["facility_name"], r["state"]), lambda r: r["official"], lambda r: r["source_url"])
    tried = sum(1 for r in loc if r["source_url"])
    if tried and lerr > tried / 2: raise SystemExit(f"{lerr} of {tried} official pages could not be reached: left the lists as they were.")
    write("local_officials_checked.csv", lout, ["facility_name", "state", "official", "title", "office", "source_url", "ok", "reason", "checked", "last_ok"])
    gov = {g["state"]: g for g in governors()}
    print(f"Wikidata: a current governor for {len(gov)} states", file=sys.stderr)
    for r in rd("governors_ref.csv"):                   # the list kept by hand fills any state Wikidata does not settle; every name is still checked
        if r["state"] not in gov: gov[r["state"]] = {"state": r["state"], "name": r["name"], "party": r["party"], "start": "", "site": r["site"]}
        elif not gov[r["state"]]["site"]: gov[r["state"]]["site"] = r["site"]
    gov = [gov[k] for k in sorted(gov)]
    if len(gov) < 40: raise SystemExit(f"Governors for only {len(gov)} states: left as they were.")
    gprev = {r["state"]: r for r in rd("governors.csv")}
    gout, gerr = check_rows(gov, gprev, today, get_text, lambda r: r["state"], lambda r: r["name"], lambda r: r["site"])
    write("governors.csv", gout, ["state", "name", "party", "start", "site", "ok", "reason", "checked", "last_ok"])
    meta = {"checked": str(today), "local_shown": sum(r["ok"] == "1" for r in lout), "local_candidates": len(loc), "governors_shown": sum(r["ok"] == "1" for r in gout)}
    (REF / "officials_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    for r in lout + gout:
        if r["ok"] != "1": print(f"hidden: {r.get('facility_name') or r['state']} {r.get('official') or r.get('name')}: {r['reason']}", file=sys.stderr)
    print(json.dumps(meta), file=sys.stderr)


if __name__ == "__main__": main()
