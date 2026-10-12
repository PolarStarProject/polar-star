"""Contributions by detention contractors' political committees to other committees, from the FEC API.

Usage:  python pipeline/money_fec.py        (needs the environment variable FEC_API_KEY, a free key from api.data.gov)
Committees: GEO Group (C00382150), CoreCivic (C00366468), Management & Training Corporation (C00208322).
Election cycles: the current one and the one before.
Writes data/reference/fec_pac_recipients.csv ("|" separated: pac | cycle_<earlier> | cycle_<current> | recipient | type | party | state | gifts,
the number of separate contributions the FEC counts behind the total)
fec_committee_detail.csv (for "other" committees only: whether each is a leadership fund or a joint fundraiser, the politician the
FEC lists as its sponsor, and the committees a joint fundraiser shares its money with), and fec_meta.json with the cycles, the day read and the FEC's own total, which build_site.py checks the rows against.
Rows are recipient COMMITTEES, never people. Without a key the script stops and changes nothing.
"""
import csv, datetime as dt, json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://api.open.fec.gov/v1"
PACS = {"G": "C00382150", "C": "C00366468", "M": "C00208322"}
TYPE = {"H": "H", "S": "S", "P": "P", "X": "P", "Y": "P", "Z": "P"}       # House, Senate, presidential and party committees; everything else is "Q", another committee


def cycles(today):
    cur = today.year + today.year % 2; return [cur - 2, cur]


def merge(per_cycle, info, cyc):
    """per_cycle: {(pac, recipient_id): {cycle: dollars, 'name': ...}}; info: {recipient_id: (type, party, state)} -> rows, total."""
    rows, total = [], 0
    for (pac, rid), v in per_cycle.items():
        a, b = int(round(v.get(cyc[0], 0))), int(round(v.get(cyc[1], 0)))
        if not a and not b: continue
        t, party, state = info.get(rid, ("Q", "", "")); total += a + b
        rows.append({"pac": pac, f"cycle_{cyc[0]}": a, f"cycle_{cyc[1]}": b, "recipient": v["name"].replace("|", "/"), "type": t, "party": party or "", "state": state or "", "gifts": int(v.get("n") or 0), "recipient_id": rid})
    return sorted(rows, key=lambda r: (r["pac"], -(r[f"cycle_{cyc[0]}"] + r[f"cycle_{cyc[1]}"]), r["recipient"])), total


def detail(rec):
    """One FEC committee record -> (kind, [sponsor candidate ids], [committees a joint fundraiser shares with]).
    kind: D = leadership fund (a politician's own committee), J = joint fundraiser, "" = anything else."""
    kind = rec.get("designation") if rec.get("designation") in ("D", "J") else ""
    if not kind and rec.get("leadership_pac"): kind = "D"
    shares = [" ".join((x.get("joint_committee_name") or "").split()) for x in rec.get("jfc_committee") or []]
    return kind, [c for c in rec.get("sponsor_candidate_ids") or [] if c], sorted({x for x in shares if x})


def timeline(pac, reports):
    """A committee's periodic reports -> [{pac, quarter, usd}], by the quarter each report's period ends in. Uses the form's own
    line for contributions to federal candidates and committees. Where a period was reported more than once (an amendment),
    only the newest version counts."""
    newest = {}
    for r in reports:
        k = (r.get("coverage_start_date") or "")[:10], (r.get("coverage_end_date") or "")[:10]
        if not k[1] or r.get("fed_candidate_committee_contributions_period") is None: continue
        stamp = (r.get("receipt_date") or "", r.get("file_number") or 0)
        if k not in newest or stamp > newest[k][0]: newest[k] = (stamp, r)
    q = {}
    for (_, end), (_, r) in newest.items():
        key = f"{end[:4]} Q{(int(end[5:7]) - 1) // 3 + 1}"; q[key] = q.get(key, 0) + int(round(r["fed_candidate_committee_contributions_period"] or 0))
    return [{"pac": pac, "quarter": k, "usd": v} for k, v in sorted(q.items())]


def main():
    key = os.environ.get("FEC_API_KEY", "").strip()
    if not key: print("FEC_API_KEY is not set: the political committee figures were left as they were."); return
    def call(path, **q):
        url = f"{API}{path}?" + urllib.parse.urlencode(dict(q, api_key=key, per_page=100), doseq=True)
        for i in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as r: time.sleep(0.5); return json.loads(r.read().decode("utf-8"))
            except Exception as e: err = str(e)[:100]; time.sleep(20 if "429" in err else 5)
        raise SystemExit(f"FEC did not answer {path}: {err}. Nothing written.")
    cyc = cycles(dt.date.today()); per = {}
    for pac, cid in PACS.items():
        for c in cyc:
            page = 1
            while True:
                j = call("/schedules/schedule_b/by_recipient_id/", committee_id=cid, cycle=c, page=page)
                for x in j["results"]:
                    if not x.get("recipient_id"): continue
                    d = per.setdefault((pac, x["recipient_id"]), {"name": x.get("recipient_name") or x["recipient_id"]}); d[c] = d.get(c, 0) + (x["total"] or 0); d["n"] = d.get("n", 0) + (x.get("count") or 0)
                if page >= (j.get("pagination") or {}).get("pages", 1): break
                page += 1
    info, more, official, reg = {}, {}, {}, {}
    for rid in sorted({rid for _, rid in per}):                       # what kind of committee each recipient is, from its own FEC record
        res = call(f"/committee/{rid}/").get("results") or [{}]
        info[rid] = (TYPE.get(res[0].get("committee_type") or "", "Q"), res[0].get("party") if res[0].get("party") in ("REP", "DEM") else "", res[0].get("state") or "")
        if res[0].get("name"): official[rid] = " ".join(res[0]["name"].split())
        if info[rid][0] == "Q":
            more[rid] = detail(res[0])
            if more[rid][0] == "J":                                # who a joint fundraiser shares with is only in the committee's history, one record per cycle
                hist = call(f"/committee/{rid}/history/").get("results") or []
                pick = lambda hs: sorted({" ".join((x.get("joint_committee_name") or "").split()) for h in hs for x in h.get("jfc_committee") or []} - {""})
                shares = pick([h for h in hist if h.get("cycle") in cyc])
                if not shares:                                      # not restated for these cycles: the latest registration that lists them
                    for h in sorted(hist, key=lambda h: -(h.get("cycle") or 0)):
                        shares = pick([h])
                        if shares: break
                more[rid] = (more[rid][0], more[rid][1], shares)
            if more[rid][0] == "D" and not more[rid][1]:           # no sponsor on the current record: an earlier record's sponsor, else the name the committee itself registered as connected to it
                hist = call(f"/committee/{rid}/history/").get("results") or []
                sp = next((h.get("sponsor_candidate_ids") for h in sorted(hist, key=lambda h: -(h.get("cycle") or 0)) if h.get("sponsor_candidate_ids")), None)
                if sp: more[rid] = (more[rid][0], [c for c in sp if c], more[rid][2])
                elif (res[0].get("affiliated_committee_name") or "").strip() not in ("", "NONE", "N/A"):
                    reg[rid] = re.sub(r"\b(Ii|Iii|Iv)\b", lambda m: m.group(1).upper(), " ".join(res[0]["affiliated_committee_name"].split()).title())
    cand = {}                                                          # the politician behind each leadership fund, as the FEC names them
    for cid in sorted({c for _, sp, _ in more.values() for c in sp}):
        r0 = (call(f"/candidate/{cid}/").get("results") or [{}])[0]
        if r0.get("name"): cand[cid] = f'{r0["name"].title()} ({ {"H": "House", "S": "Senate", "P": "presidential candidate"}.get(r0.get("office"), "office not listed") }{", " + r0["state"] if r0.get("state") and r0.get("office") != "P" else ""})'
    for (_, rid), v in per.items():                                 # a contribution record with no name shows the bare id: use the committee's own name
        if v["name"] == rid and official.get(rid): v["name"] = official[rid]
    names = {rid: v["name"].replace("|", "/") for (_, rid), v in per.items()}
    drows = [{"recipient": names[rid], "committee_id": rid, "kind": k, "sponsors": "; ".join(cand[c] for c in sp if c in cand) or (f"none listed; its FEC registration names {reg[rid]} as a connected committee" if rid in reg else ""), "shares_with": "; ".join(x.replace("|", "/") for x in sh)}
             for rid, (k, sp, sh) in sorted(more.items(), key=lambda kv: names[kv[0]]) if k or sp or sh]
    rows, total = merge(per, info, cyc)
    # when the money was given: each committee's own periodic reports give its contributions to other federal committees per period
    trows = []
    for pac, cid in PACS.items():
        reps, page = [], 1
        while True:
            j = call(f"/committee/{cid}/reports/", cycle=cyc, page=page, sort="-coverage_end_date")
            reps += j["results"]
            if page >= (j.get("pagination") or {}).get("pages", 1): break
            page += 1
        trows += timeline(pac, reps)
    tsum = sum(r["usd"] for r in trows)
    timeline_ok = bool(trows) and abs(tsum - total) <= 0.1 * total
    print(f"timeline: {len(trows)} quarters adding to {tsum:,} against {total:,} by recipient: {'kept' if timeline_ok else 'NOT kept, the two disagree'}")
    if len(rows) < 50 or total < 200000: raise SystemExit(f"Implausible result ({len(rows)} recipients, {total:,} dollars). Nothing written.")
    with open(REF / "fec_pac_recipients.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pac", f"cycle_{cyc[0]}", f"cycle_{cyc[1]}", "recipient", "type", "party", "state", "gifts", "recipient_id"], delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    with open(REF / "fec_committee_detail.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recipient", "committee_id", "kind", "sponsors", "shares_with"], delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(drows)
    if timeline_ok:
        with open(REF / "fec_by_quarter.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pac", "quarter", "usd"], delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(trows)
    (REF / "fec_meta.json").write_text(json.dumps({"read": str(dt.date.today()), "cycles": cyc, "total": total}, indent=1), encoding="utf-8")
    print(f"{len(rows)} recipient committees, {total:,} dollars, cycles {cyc[0]} and {cyc[1]}")


if __name__ == "__main__": main()
