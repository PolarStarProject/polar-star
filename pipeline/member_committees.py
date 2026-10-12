"""Every member of Congress's own FEC committees: campaign committees, joint fundraisers the campaign belongs to, and
leadership funds the member sponsors. Used to tie joint fundraisers that took detention-contractor money to the members
who share in them, on each member's scorecard.

Usage:  python pipeline/member_committees.py      (needs FEC_API_KEY; run in GitHub Actions)
Reads data/reference/members.csv and the public-domain congress-legislators files for each member's FEC candidate ids.
Writes data/reference/member_committees.csv ("|" separated): bioguide | committee_id | name | designation
designation: P principal campaign committee, A other authorized committee, J joint fundraiser, D leadership fund.
Without a key it stops and changes nothing. Organizations and officials only: no private person is read or written.
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://api.open.fec.gov/v1"
SRC = "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/"


def rows_for(bg, authorized, sponsored):
    """FEC committee records for one member -> rows, one per committee, leadership funds marked D whatever the FEC designation."""
    out = {}
    for c in authorized:
        d = c.get("designation") or ""
        if d in ("P", "A", "J") and c.get("committee_id"): out[c["committee_id"]] = (" ".join((c.get("name") or "").split()), d)
    for c in sponsored:
        if c.get("committee_id"): out[c["committee_id"]] = (" ".join((c.get("name") or "").split()), "D")
    return [{"bioguide": bg, "committee_id": k, "name": n.replace("|", "/"), "designation": d} for k, (n, d) in sorted(out.items())]


def main():
    key = os.environ.get("FEC_API_KEY", "").strip()
    if not key: print("FEC_API_KEY is not set: member committees were left as they were."); return
    def call(path, **q):
        url = f"{API}{path}?" + urllib.parse.urlencode(dict(q, api_key=key, per_page=100), doseq=True)
        for i in range(40):                                 # the key allows 1,000 calls an hour; on "too many" wait out the hour
            try:
                with urllib.request.urlopen(url, timeout=90) as r: time.sleep(1); return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                err = str(e)[:120]
                if "429" not in err and i >= 5: break
                time.sleep(120 if "429" in err else 6)
        raise SystemExit(f"FEC did not answer {path}: {err}. Nothing written.")
    def every(path, **q):                                   # all pages of a filtered committee list
        out, page = [], 1
        while True:
            j = call(path, page=page, **q); out += j.get("results") or []
            if page >= (j.get("pagination") or {}).get("pages", 1): return out
            page += 1
    mem = [r["bioguide"] for r in csv.DictReader(open(REF / "members.csv", encoding="utf-8"), delimiter="|")]
    legs = {l["id"]["bioguide"]: l for f in ("legislators-current.json", "legislators-historical.json") for l in json.load(urllib.request.urlopen(SRC + f))}
    ids = {bg: (legs.get(bg) or {}).get("id", {}).get("fec", []) for bg in mem}
    allids = sorted({c for v in ids.values() for c in v}); auth, spon = [], []
    for i in range(0, len(allids), 40):                     # forty candidates per request keeps the whole run to a few dozen calls
        chunk = allids[i:i + 40]
        auth += every("/committees/", candidate_id=chunk); spon += every("/committees/", sponsor_candidate_id=chunk)
    rows, none = [], sum(1 for v in ids.values() if not v)
    for bg in mem:
        mine = set(ids[bg])
        if not mine: continue
        rows += rows_for(bg, [c for c in auth if mine & set(c.get("candidate_ids") or [])], [c for c in spon if mine & set(c.get("sponsor_candidate_ids") or [])])
    if len({r["bioguide"] for r in rows}) < 400: raise SystemExit(f"Implausible: committees for only {len({r['bioguide'] for r in rows})} members. Nothing written.")
    with open(REF / "member_committees.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bioguide", "committee_id", "name", "designation"], delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} committees for {len({r['bioguide'] for r in rows})} members; {none} members with no FEC id", file=sys.stderr)


if __name__ == "__main__": main()
