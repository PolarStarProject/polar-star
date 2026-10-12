"""Each ICE contract of $1 million or more, from USAspending.gov: one row per award, so a company's total can be opened into the
contracts behind it.

Usage:  python pipeline/money_awards.py
Window: awards with any activity in the same three fiscal years as money_usaspending.py.
Writes data/reference/ice_awards.csv ("|" separated) and ice_awards_meta.json.

UNITS AND MEANING, read before using: amount_usd is WHOLE DOLLARS and is what has been committed over the WHOLE LIFE of the
award so far (the source's "Award Amount"), not what was committed inside the window. An award that began in 2019 carries its
2019-2023 dollars too. So a company's rows here do NOT add up to its three-year total in ice_contract_recipients.csv (which is in
MILLIONS and window-only), and the two must never be added or compared as if they were the same measure.

Each award is then opened once more for four things the search does not give (added 7 October 2026):
  window_usd   WHOLE DOLLARS committed INSIDE the window: the award's own transactions with an action date in the window, added
               up. Can be negative (money taken back). Blank = that award's detail could not be read; blank is not zero.
  competed     "C" competed, "N" not competed, "" not recorded, from the award's extent-competed code (same grouping as
               money_usaspending.COMPETED)
  extent       the source's own extent-competed code, unchanged (A, B, C, D, E, F, G, CDO, NDO): "competed" above is a grouping of it
  offers       how many offers were received, as recorded (blank = not recorded). 1 on a competed award means it was opened to
               competition and one company bid.
  reason       for an award that was not fully competed, the reason the record gives, in the source's words (the "other than
               full and open" reason, or for an order under an existing contract the "fair opportunity limited" reason)
  psc          the product/service code (S206 = guard services, the code used for running detention sites)
  pop_city, pop_state, pop_zip   where the work is performed, as the award records it. A place, never a person.
The window amounts are checked against money_meta.json: together they must be between half of and just over ICE's window total,
or nothing is written. Up to 2% of awards may fail to open; more than that and nothing is written.

Nothing is written unless the source answers every page and the result is plausible. Contracts only (award types A, B, C, D);
recipients are companies and organisations. The source itself masks any individual as a recipient; a row whose recipient is
blank or masked is dropped rather than shown.
"""
import csv, datetime as dt, json, pathlib, re, sys, time
from identity import USER_AGENT

ROOT = pathlib.Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://api.usaspending.gov"
FLOOR = 1_000_000
FIELDS = ["Award ID", "Recipient Name", "Award Amount", "Start Date", "End Date", "Description", "Contract Award Type"]
MASKED = re.compile(r"redacted|multiple recipients|individual|miscellaneous foreign|^\s*$", re.I)


def clean_rows(results):
    """Source rows -> output rows. Drops a row with no id, no recipient, a masked recipient, or an amount under the floor;
    two rows for the same award keep the larger amount. Largest first."""
    out = {}
    for x in results:
        uid, name, amt = x.get("generated_internal_id"), (x.get("Recipient Name") or "").strip(), x.get("Award Amount")
        if not uid or MASKED.search(name) or not isinstance(amt, (int, float)) or amt < FLOOR: continue
        row = {"award_id": (x.get("Award ID") or "").strip(), "recipient": name, "amount_usd": int(round(amt)), "start": (x.get("Start Date") or "")[:10], "end": (x.get("End Date") or "")[:10],
               "type": (x.get("Contract Award Type") or "").strip(), "what": " ".join((x.get("Description") or "").split())[:140].replace("|", "/"), "uid": uid}
        if uid not in out or row["amount_usd"] > out[uid]["amount_usd"]: out[uid] = row
    return sorted(out.values(), key=lambda r: (-r["amount_usd"], r["uid"]))


def window_sum(txs, start, end):
    """Dollars committed by one award's transactions whose action date is inside start..end (ISO dates, inclusive)."""
    return int(round(sum((t.get("federal_action_obligation") or 0) for t in txs if start <= (t.get("action_date") or "")[:10] <= end)))


def offers_int(v):
    """The recorded number of offers as an int, or "" when it is missing or not a whole number of 0 or more."""
    try: n = int(str(v).strip())
    except (TypeError, ValueError): return ""
    return n if 0 <= n < 100000 else ""


def competed_code(code, groups):
    """'C', 'N' or '' from an extent-competed code and money_usaspending.COMPETED."""
    return "C" if code in groups["competed"] else "N" if code in groups["not_competed"] else ""


def main():
    import requests
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from money_usaspending import window, COMPETED
    s = requests.Session(); s.headers["User-Agent"] = USER_AGENT
    start, end, fys = window(dt.date.today())
    filters = {"time_period": [{"start_date": start, "end_date": end}], "award_type_codes": ["A", "B", "C", "D"], "award_amounts": [{"lower_bound": FLOOR}],
               "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement"}]}
    res, page, err = [], 1, ""
    while True:
        body = {"filters": filters, "fields": FIELDS, "limit": 100, "page": page, "sort": "Award Amount", "order": "desc", "subawards": False}
        for i in range(4):
            try:
                r = s.post(API + "/api/v2/search/spending_by_award/", json=body, timeout=90)
                if r.status_code == 200: j = r.json(); time.sleep(0.4); break
                err = f"{r.status_code} {r.text[:200]}"
            except Exception as e: err = str(e)[:200]
            time.sleep(5 * (i + 1))
        else: raise SystemExit(f"USAspending did not answer page {page}: {err}. Nothing written.")
        res += j["results"]
        if not j.get("page_metadata", {}).get("hasNext"): break
        page += 1
        if page > 80: raise SystemExit("More than 8,000 awards over the floor: not plausible for ICE. Nothing written.")
    rows = clean_rows(res)
    if len(rows) < 100 or not 1e8 < rows[0]["amount_usd"] < 5e10: raise SystemExit(f"Implausible result ({len(rows)} awards, largest {rows[0]['amount_usd'] if rows else 0:,}). Nothing written.")
    def get(path, body=None):
        for i in range(3):
            try:
                r = s.post(API + path, json=body, timeout=60) if body is not None else s.get(API + path, timeout=60)
                if r.status_code == 200: time.sleep(0.15); return r.json()
            except Exception: pass
            time.sleep(3 * (i + 1))
        return None
    def open_award(r):
        """Fills one row from the award's own record and its transactions. False if the source did not answer."""
        d = get(f"/api/v2/awards/{r['uid']}/"); txs, page = [], 1
        if d is None: return False
        while True:
            j = get("/api/v2/transactions/", {"award_id": r["uid"], "limit": 5000, "page": page})
            if j is None: return False
            txs += j.get("results") or []
            if not (j.get("page_metadata") or {}).get("hasNext"): break
            page += 1
        c, pop = d.get("latest_transaction_contract_data") or {}, d.get("place_of_performance") or {}
        r.update({"window_usd": window_sum(txs, start, end), "competed": competed_code(c.get("extent_competed"), COMPETED), "psc": (c.get("product_or_service_code") or "").strip(),
                  "extent": (c.get("extent_competed") or "").strip(), "offers": offers_int(c.get("number_of_offers_received")), "reason": " ".join((c.get("other_than_full_and_open_description") or c.get("fair_opportunity_limited_description") or "").split())[:120].replace("|", "/"),
                  "pop_city": (pop.get("city_name") or "").strip().upper().replace("|", "/"), "pop_state": (pop.get("state_code") or "").strip().upper(), "pop_zip": (pop.get("zip5") or "").strip()})
        return True
    again = []
    for n, r in enumerate(rows):
        r.update({"window_usd": "", "competed": "", "psc": "", "extent": "", "offers": "", "reason": "", "pop_city": "", "pop_state": "", "pop_zip": ""})
        if not open_award(r): again.append(r)
        if n % 100 == 0: print(f"  opened {n} of {len(rows)} awards ({len(again)} to retry)", flush=True)
    for wait in (60, 180):                     # the source has short outages: go back for the ones that failed, twice, after a pause
        if not again: break
        time.sleep(wait); again = [r for r in again if not (time.sleep(1.5) or open_award(r))]
    failed = len(again)
    if failed > 0.02 * len(rows): raise SystemExit(f"{failed} of {len(rows)} awards could not be opened. Nothing written.")
    wsum = sum(r["window_usd"] for r in rows if r["window_usd"] != "")
    mm = json.loads((REF / "money_meta.json").read_text(encoding="utf-8")) if (REF / "money_meta.json").exists() else None
    if mm and (mm["from"], mm["to"]) == (start, end) and not 0.5 * mm["total_musd"] * 1e6 <= wsum <= 1.02 * mm["total_musd"] * 1e6:
        raise SystemExit(f"Window amounts add to {wsum:,}, against ICE's window total of {mm['total_musd']:,} million: units or dates are wrong. Nothing written.")
    with open(REF / "ice_awards.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    (REF / "ice_awards_meta.json").write_text(json.dumps({"from": start, "to": end, "read": str(dt.date.today()), "floor_usd": FLOOR, "awards": len(rows), "source_rows": len(res), "recipients": len({r["recipient"] for r in rows}), "not_opened": failed, "window_usd_total": wsum}, indent=1), encoding="utf-8")
    print(f"ICE awards of ${FLOOR:,} or more active {start} to {end}: {len(rows)} awards to {len({r['recipient'] for r in rows})} recipients (largest {rows[0]['amount_usd']:,})")


if __name__ == "__main__": main()
