"""Where the joint fundraisers that took detention-contractor money sent what they raised, from the FEC API.

Usage:  python pipeline/jfc_flows.py        (needs FEC_API_KEY; runs in GitHub Actions)

A joint fundraising committee raises money once and splits it among its participants (candidates' campaigns, party
committees, leadership PACs) by a formula they agree. fec_committee_detail.csv lists the ones that took money from a
detention contractor's committee (fec_pac_recipients.csv). For each, in the same election cycles:
  receipts      what it took in overall (the FEC's own totals)
  contractor    what the contractor committees gave it (from fec_pac_recipients.csv)
  transfers     every payment it reported to another political committee (its own Schedule B), by recipient committee,
                with the FEC's party, committee type and designation for the recipient
Money is not labelled once it is pooled, so the page shows where each fundraiser's money went and, as an estimate, the
contractor share of it if the contractor gifts were split the same way as everything else (contractor / receipts x
transfer). That estimate is labelled as one; it is not a traced dollar.
Writes data/reference/jfc_flows.csv, jfc_totals.csv and jfc_meta.json. Nothing is written unless every fundraiser answers.
"""
import csv, datetime as dt, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://api.open.fec.gov/v1"


def main():
    key = os.environ.get("FEC_API_KEY", "").strip()
    if not key: print("FEC_API_KEY is not set: left as it was."); return
    def call(path, **q):
        url = f"{API}{path}?" + urllib.parse.urlencode(dict(q, api_key=key), doseq=True); err = ""
        for i in range(30):
            try:
                with urllib.request.urlopen(url, timeout=120) as r: time.sleep(0.6); return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                err = str(e)[:160]
                if "422" in err or "404" in err: break      # a missing record is not worth waiting on
                time.sleep(120 if "429" in err else 30)
        raise SystemExit(f"FEC did not answer {path}: {err}. Nothing written.")
    rd = lambda n: list(csv.DictReader(open(REF / n, encoding="utf-8"), delimiter="|")) if (REF / n).exists() else []
    meta = json.loads((REF / "fec_meta.json").read_text(encoding="utf-8")) if (REF / "fec_meta.json").exists() else {}
    cyc = meta.get("cycles") or [dt.date.today().year + dt.date.today().year % 2 - 2, dt.date.today().year + dt.date.today().year % 2]
    jfc = {r["committee_id"]: r["recipient"] for r in rd("fec_committee_detail.csv") if r["kind"] == "J" and r["committee_id"]}
    got = {}
    for r in rd("fec_pac_recipients.csv"):
        rid = r.get("recipient_id")
        if rid in jfc:
            for c in cyc: got[(rid, c)] = got.get((rid, c), 0) + int(r.get(f"cycle_{c}") or 0)
    flows, totals = [], []
    for cid, name in sorted(jfc.items()):
        for c in cyc:
            if not got.get((cid, c)): continue
            try: t = (call(f"/committee/{cid}/totals/", cycle=c).get("results") or [{}])[0]
            except SystemExit: t = {}            # some committees have no totals record for a cycle: receipts unknown, so no estimate
            totals.append({"jfc_id": cid, "jfc": name, "cycle": c, "receipts": int(round(t.get("receipts") or 0)), "contractor": got[(cid, c)]})
            by, last = {}, {}
            while True:
                try: j = call("/schedules/schedule_b/", committee_id=cid, two_year_transaction_period=c, per_page=100, sort="disbursement_date", **last)
                except SystemExit as e:
                    if "404" in str(e) or "422" in str(e): print(f"  {name} {c}: no disbursement records ({e})", file=sys.stderr); break
                    raise
                res = j.get("results") or []
                for x in res:
                    rid = x.get("recipient_committee_id")
                    if not rid or (x.get("memo_code") or "").upper() == "X": continue
                    rc = x.get("recipient_committee") or {}
                    o = by.setdefault(rid, [x.get("recipient_name") or rid, 0.0, rc.get("party") or "", rc.get("committee_type") or "", rc.get("designation") or ""])
                    o[1] += x.get("disbursement_amount") or 0
                li = (j.get("pagination") or {}).get("last_indexes")
                if not res or not li: break
                last = {k: v for k, v in li.items() if v is not None}
            for rid, (rn, usd, pty, ctype, dsg) in by.items():
                if usd > 0: flows.append({"jfc_id": cid, "cycle": c, "recipient_id": rid, "recipient": rn.replace("|", "/"), "usd": int(round(usd)), "party": pty, "ctype": ctype, "designation": dsg})
            print(f"  {name} {c}: {len(by)} recipients", file=sys.stderr)
    if not totals: raise SystemExit("No joint fundraiser with contractor money: left as it was.")
    def write(n, rows, fields):
        with open(REF / n, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    write("jfc_totals.csv", totals, ["jfc_id", "jfc", "cycle", "receipts", "contractor"])
    write("jfc_flows.csv", sorted(flows, key=lambda r: (r["jfc_id"], r["cycle"], -r["usd"])), ["jfc_id", "cycle", "recipient_id", "recipient", "usd", "party", "ctype", "designation"])
    (REF / "jfc_meta.json").write_text(json.dumps({"read": str(dt.date.today()), "cycles": cyc, "fundraisers": len({t["jfc_id"] for t in totals})}, indent=1), encoding="utf-8")
    print(f"{len(totals)} fundraiser-cycles, {len(flows)} transfers", file=sys.stderr)


if __name__ == "__main__": main()
