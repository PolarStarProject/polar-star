"""Profiles of the lobbying firms that work for detention and ICE flight companies, from the Senate's Lobbying Disclosure
Act records (lda.gov API).

Usage:  python pipeline/firm_profiles.py        (needs internet; runs in GitHub Actions)

The firms are the ones in lobbying_firms.csv (hired by GEO, CoreCivic, MTC or CSI Aviation). For each firm, for the last
two calendar years, from its own filings:
  clients      every client on its quarterly reports (the latest version per client and quarter): what it reported
               being paid, how many reports, and whether a report listed ICE or the Department of Homeland Security among
               the agencies contacted or "Immigration" among the issues
  money        its semiannual LD-203 reports: political contributions reported by the firm and by its registered
               lobbyists, added up by the official or committee they went to, and by kind (to a campaign or committee,
               or paying for an event that honored an official). Contributors are never named: a lobbyist's personal
               gift is reported under the firm's name here.
  former       lobbyists on its reports who list a past government post ("covered position"), named only for that post,
               as they filed it (the same rule as lobbying_former_officials.csv)
A firm with very many filings is read up to PAGE_CAP pages a year, and the profile says so ("partial").
Writes data/reference/firm_clients.csv, firm_money.csv, firm_former.csv and firm_meta.json. Nothing is written unless
most requests succeed.
"""
import csv, datetime as dt, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from identity import USER_AGENT

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://lda.gov/api/v1/"
YEARS_BACK, PAGE_CAP = 1, 40           # this year and last year; at most 40 pages (1,000 reports) a firm a year
SUFFIX = {"INC", "INCORPORATED", "LLC", "L", "C", "LLP", "LP", "PLLC", "PC", "P", "CORP", "CORPORATION", "CO", "COMPANY", "THE", "LTD", "PLC", "DC", "D"}
QUARTER = {"first_quarter": "Q1", "second_quarter": "Q2", "third_quarter": "Q3", "fourth_quarter": "Q4", "mid_year": "H1", "year_end": "H2"}
EVENT = {"he": "honorary", "me": "meeting", "ple": "library", "pic": "inaugural"}


def core(name):
    """The words that name a firm, without legal suffixes or a "d/b/a" tail: "Capitol Counsel, LLC" -> "CAPITOL COUNSEL"."""
    n = re.split(r"\b(?:D/B/A|DBA|F/K/A|FKA|FORMERLY)\b", (name or "").upper())[0]
    return " ".join(w for w in re.sub(r"[^A-Z0-9 ]+", " ", re.sub(r"\(.*?\)", " ", n)).split() if w not in SUFFIX)


def qname(name):
    """The name to search lda.gov with: the firm's name without a legal suffix, keeping "&" ("Holland & Knight LLP" ->
    "Holland & Knight"). lda.gov matches part of a name, so the search is wide; core() then keeps only this firm's filings."""
    w = re.sub(r"\(.*?\)", " ", re.split(r"(?i)\b(?:d/b/a|dba)\b", name or "")[0]).replace(",", " ").replace(".", " ").split()
    while len(w) > 1 and w[-1].upper() in SUFFIX: w.pop()
    return " ".join(w)


TITLE = re.compile(r"^(?:the\s+)?(?:hon(?:orable)?\.?\s+|rep(?:resentative)?\.?\s+|congress(?:wo)?man\s+|sen(?:ator)?\.?\s+|mr\.?\s+|ms\.?\s+|mrs\.?\s+|dr\.?\s+|gov(?:ernor)?\.?\s+|leader\s+|speaker\s+|whip\s+)+", re.I)


def recipient(name):
    """One spelling per official: titles dropped ("Senator John Cornyn" -> "John Cornyn"), spaces and case tidied."""
    n = TITLE.sub("", re.sub(r"\s+", " ", (name or "")).strip().strip(",;. "))
    return n.title() if n.isupper() or n.islower() else n


def clients_of(filings, key):
    """A firm's filings -> {client: {usd, filings, ice, dhs, imm, first, last}}. Only filings the firm itself filed (its
    name, without suffixes, is the firm's), the latest version per client and quarter, registrations left out."""
    keep = {}
    for f in filings:
        if core((f.get("registrant") or {}).get("name")) != key or re.fullmatch(r"R[RA]", f.get("filing_type") or ""): continue
        c = f.get("client") or {}
        k = (c.get("id"), f.get("filing_year"), f.get("filing_period"))
        if k not in keep or (f.get("dt_posted") or "") > (keep[k].get("dt_posted") or ""): keep[k] = f
    out = {}
    for f in keep.values():
        name = re.sub(r"\s+", " ", ((f.get("client") or {}).get("name") or "")).strip()
        if not name: continue
        acts = f.get("lobbying_activities") or []
        ents = {g.get("name") or "" for a in acts for g in a.get("government_entities") or []}
        q = f"{f.get('filing_year')} {QUARTER.get(f.get('filing_period'), '')}".strip()
        o = out.setdefault(name, {"usd": 0, "filings": 0, "ice": 0, "dhs": 0, "imm": 0, "first": q, "last": q})
        o["usd"] += int(float(f.get("income") or 0)); o["filings"] += 1
        o["ice"] += any("Immigration & Customs Enforcement" in e for e in ents)
        o["dhs"] += any(e.startswith("Homeland Security") for e in ents)
        o["imm"] += any((a.get("general_issue_code") or "") == "IMM" for a in acts)
        o["first"], o["last"] = min(o["first"], q), max(o["last"], q)
    return out


def money_of(reports, key):
    """LD-203 reports by a firm and its lobbyists -> {(recipient, kind): [usd, gifts]}. The recipient is the honoree when
    one is named (the official), else the payee (the committee). kind is "campaign" for a contribution to a candidate or
    committee, or the kind of event paid for. No contributor is kept."""
    out, seen = {}, set()
    for r in reports:
        if core((r.get("registrant") or {}).get("name")) != key: continue
        rid = r.get("filing_uuid") or r.get("url") or id(r)
        if rid in seen: continue
        seen.add(rid)
        for it in r.get("contribution_items") or []:
            kind = "campaign" if (it.get("contribution_type") or "").lower() == "feca" else EVENT.get((it.get("contribution_type") or "").lower(), "other")
            to = recipient(it.get("honoree_name") or it.get("payee_name"))
            try: usd = float(it.get("amount") or 0)
            except (TypeError, ValueError): usd = 0
            if not to or usd <= 0: continue
            o = out.setdefault((to, kind), [0.0, 0]); o[0] += usd; o[1] += 1
    return out


def former_of(filings, key):
    """Lobbyists on the firm's reports who list a past government post, with that post as they filed it."""
    out = {}
    for f in filings:
        if core((f.get("registrant") or {}).get("name")) != key: continue
        for a in f.get("lobbying_activities") or []:
            for l in a.get("lobbyists") or []:
                cp = re.sub(r"\s+", " ", (l.get("covered_position") or "")).strip()
                if not cp or cp.upper().strip(". ") in ("N/A", "NA", "NONE", "N A", "NOT APPLICABLE"): continue
                p = l.get("lobbyist") or {}
                name = " ".join(x for x in [p.get("first_name"), p.get("middle_name"), p.get("last_name"), p.get("suffix")] if x).strip().title()
                if name and len(cp) > len(out.get(name, "")): out[name] = cp
    return out


def main():
    asked = failed = 0
    def fetch(url):
        nonlocal asked, failed
        asked += 1
        for i in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}), timeout=90) as r:
                    time.sleep(4.2); return json.loads(r.read().decode("utf-8"))      # about 15 requests a minute without a key
            except Exception as e:
                err = str(e); time.sleep(30 if "429" in err else 8)
        failed += 1; return None
    def pages(endpoint, q):
        url, out, n, full = API + endpoint + "/?" + urllib.parse.urlencode(dict(q, page_size=25)), [], 0, True
        while url:
            if n >= PAGE_CAP: full = False; break
            j = fetch(url); n += 1
            if j is None: break
            out += j.get("results") or []; url = j.get("next")
        return out, full
    firms = sorted({r["firm"] for r in csv.DictReader(open(REF / "lobbying_firms.csv", encoding="utf-8"), delimiter="|") if "personal name" not in r["firm"]})
    this = dt.date.today().year
    rows_c, rows_m, rows_f, meta = [], [], [], {"read": str(dt.date.today()), "years": [this - YEARS_BACK, this], "firms": {}}
    for firm in firms:
        key = core(firm); cl, mo, fo, partial = {}, {}, {}, False
        for y in range(this - YEARS_BACK, this + 1):
            fl, full = pages("filings", {"registrant_name": qname(firm), "filing_year": y}); partial |= not full
            for k, v in clients_of(fl, key).items():
                o = cl.setdefault(k, {"usd": 0, "filings": 0, "ice": 0, "dhs": 0, "imm": 0, "first": v["first"], "last": v["last"]})
                for f in ("usd", "filings", "ice", "dhs", "imm"): o[f] += v[f]
                o["first"], o["last"] = min(o["first"], v["first"]), max(o["last"], v["last"])
            for k, v in former_of(fl, key).items():
                if len(v) > len(fo.get(k, "")): fo[k] = v
            rp, full = pages("contributions", {"registrant_name": qname(firm), "filing_year": y}); partial |= not full
            for k, (usd, n) in money_of(rp, key).items():
                o = mo.setdefault(k, [0.0, 0]); o[0] += usd; o[1] += n
        rows_c += [{"firm": firm, "client": k, **v} for k, v in sorted(cl.items(), key=lambda kv: -kv[1]["usd"])]
        rows_m += [{"firm": firm, "recipient": k[0], "kind": k[1], "usd": round(v[0]), "gifts": v[1]} for k, v in sorted(mo.items(), key=lambda kv: -kv[1][0])]
        rows_f += [{"firm": firm, "lobbyist": k, "covered_position": v} for k, v in sorted(fo.items())]
        meta["firms"][firm] = {"clients": len(cl), "partial": partial}
        print(f"  {firm}: {len(cl)} clients, {len(mo)} recipients, {len(fo)} former officials{' (partial)' if partial else ''}", file=sys.stderr)
    if not asked or failed > asked / 4: raise SystemExit(f"{failed} of {asked} lda.gov requests failed: left the profiles as they were.")
    def write(n, rows, fields):
        with open(REF / n, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n", extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    write("firm_clients.csv", rows_c, ["firm", "client", "usd", "filings", "ice", "dhs", "imm", "first", "last"])
    write("firm_money.csv", rows_m, ["firm", "recipient", "kind", "usd", "gifts"])
    write("firm_former.csv", rows_f, ["firm", "lobbyist", "covered_position"])
    (REF / "firm_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{len(firms)} firms profiled", file=sys.stderr)


if __name__ == "__main__": main()
