"""Each current member's largest political-committee donors and the largest outside spending for or against them, from any
cause, in the current election cycle (FEC). Shown on every scorecard beside the detention money, so a reader sees who funds a
member without the page choosing which causes to show.

Usage:  python pipeline/member_top_donors.py      (needs FEC_API_KEY; run in GitHub Actions)
Reads data/reference/members.csv and member_committees.csv (from member_committees.py).

  gave   Schedule A, line 11C of the member's own committees' reports: contributions from other political committees (PACs,
         other members' leadership funds, party-affiliated PACs). Party committees (line 11B) and transfers from joint
         fundraisers (line 12) are not included. Grouped by the giving committee's FEC id.
  spent  Schedule E independent expenditures by candidate: money outside groups (super PACs and others) reported spending to
         support or oppose the member, grouped by the spending committee and whether it supported or opposed.

Writes data/reference/member_top_donors.csv ("|" separated): bioguide | kind (G gave, S supported, O opposed) | committee_id |
name | usd | count, the twenty largest of each kind per member (a tie at twentieth place is shown in full when that keeps the list
at thirty or fewer, otherwise as one row of kind TG/TS/TO giving the tied amount and how many committees share it), and member_top_donors_meta.json. Organizations only: individual
donors to members are not read. Without a key it stops and changes nothing.
"""
import csv, datetime as dt, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://api.open.fec.gov/v1"
SRC = "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/"
TOP = 20


def cycle(today):
    return today.year + today.year % 2


def top(groups, n=TOP):
    """{(bg, kind, cid): [name, usd, count]} -> rows, the n largest per member and kind, positive totals only."""
    by = {}
    for (bg, kind, cid), (name, usd, cnt) in groups.items():
        if usd > 0: by.setdefault((bg, kind), []).append({"bioguide": bg, "kind": kind, "committee_id": cid, "name": " ".join(name.split()).replace("|", "/"), "usd": round(usd), "count": cnt})
    out = []
    for (bg, kind), L in sorted(by.items()):
        L.sort(key=lambda r: -r["usd"])
        if len(L) <= n: out += L; continue
        cut = L[n - 1]["usd"]; above = [r for r in L if r["usd"] > cut]; at = [r for r in L if r["usd"] == cut]
        # Many committees give the legal maximum, so the tenth place is often a tie. Never break a tie by name (that would favour
        # names early in the alphabet): show everyone at the cut-off amount when that keeps the list short, otherwise count them.
        if len(above) + len(at) <= n + 10: out += above + sorted(at, key=lambda r: r["committee_id"])
        else: out += above + [{"bioguide": bg, "kind": "T" + kind, "committee_id": "", "name": "", "usd": cut, "count": len(at)}]
    return out


def add(groups, bg, kind, cid, name, usd, cnt=1):
    g = groups.setdefault((bg, kind, cid), [name, 0.0, 0]); g[1] += usd or 0; g[2] += cnt
    if name and not g[0]: g[0] = name


def main():
    key = os.environ.get("FEC_API_KEY", "").strip()
    if not key: print("FEC_API_KEY is not set: top donors were left as they were."); return
    def call(path, **q):
        url = f"{API}{path}?" + urllib.parse.urlencode(dict(q, api_key=key), doseq=True)
        for i in range(60):                                 # 1,000 calls an hour: on "too many", wait out the hour
            try:
                with urllib.request.urlopen(url, timeout=120) as r: time.sleep(0.6); return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                err = str(e)[:120] + (" " + e.read().decode("utf-8", "replace")[:300] if hasattr(e, "read") else "")
                if "429" not in err and (i >= 6 or "422" in err): break
                time.sleep(120 if "429" in err else 8)
        raise SystemExit(f"FEC did not answer {path}: {err}. Nothing written.")
    cyc = cycle(dt.date.today())
    cur = {r["bioguide"] for r in csv.DictReader(open(REF / "members.csv", encoding="utf-8"), delimiter="|") if r["current"]}
    own = {}
    for r in csv.DictReader(open(REF / "member_committees.csv", encoding="utf-8"), delimiter="|"):
        if r["bioguide"] in cur and r["designation"] in ("P", "A"): own[r["committee_id"]] = r["bioguide"]
    groups, rows_read = {}, 0
    ids = sorted(own)
    for i in range(0, len(ids), 10):                        # ten committees per request (the API caps list filters); keyset paging through every 11C line
        chunk, last = ids[i:i + 10], {}
        while True:
            j = call("/schedules/schedule_a/", committee_id=chunk, two_year_transaction_period=cyc, line_number="F3-11C", per_page=100, sort="contribution_receipt_date", **last)
            res = j.get("results") or []
            for r in res:
                if (r.get("memo_code") or "").upper() == "X": continue
                bg = own.get(r.get("committee_id"))
                if bg: add(groups, bg, "G", r.get("contributor_id") or r.get("contributor_name") or "", r.get("contributor_name") or "", r.get("contribution_receipt_amount"))
            rows_read += len(res); li = (j.get("pagination") or {}).get("last_indexes")
            if not res or not li: break
            last = {k: v for k, v in li.items() if v is not None}
        print(f"gave: {i + len(chunk)} of {len(ids)} committees, {rows_read} lines", file=sys.stderr)
    legs = {l["id"]["bioguide"]: l for f in ("legislators-current.json",) for l in json.load(urllib.request.urlopen(SRC + f))}
    cand = {c: bg for bg in cur for c in (legs.get(bg) or {}).get("id", {}).get("fec", [])}
    cids = sorted(cand)
    for i in range(0, len(cids), 10):
        page = 1
        while True:
            j = call("/schedules/schedule_e/by_candidate/", candidate_id=cids[i:i + 10], cycle=cyc, per_page=100, page=page)
            for r in j.get("results") or []:
                bg = cand.get(r.get("candidate_id")); kind = {"S": "S", "O": "O"}.get(r.get("support_oppose_indicator"))
                if bg and kind: add(groups, bg, kind, r.get("committee_id") or "", r.get("committee_name") or "", r.get("total"), r.get("count") or 0)
            if page >= (j.get("pagination") or {}).get("pages", 1): break
            page += 1
    rows = top(groups)
    if len({r["bioguide"] for r in rows if r["kind"] == "G"}) < 300: raise SystemExit(f"Implausible: PAC donors for only {len({r['bioguide'] for r in rows if r['kind'] == 'G'})} members. Nothing written.")
    with open(REF / "member_top_donors.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bioguide", "kind", "committee_id", "name", "usd", "count"], delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    (REF / "member_top_donors_meta.json").write_text(json.dumps({"read": str(dt.date.today()), "cycle": cyc, "lines_read": rows_read}, indent=1), encoding="utf-8")
    print(f"{len(rows)} rows for {len({r['bioguide'] for r in rows})} members", file=sys.stderr)


if __name__ == "__main__": main()
