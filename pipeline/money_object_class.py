"""Where every ICE and CBP dollar went, by kind of spending (payroll, contracts, buildings, grants), from USAspending's account data.

Usage:  python pipeline/money_object_class.py      (run by the refresh, step "accounts")
Source: USAspending Spending Explorer (agency account reports, the same data agencies file with the Treasury each quarter).
Writes, in data/reference/ (all "|" separated):
  agency_object_class.csv    fy|agency|account|object_class|musd     obligations, in millions, for each ICE and CBP account
  agency_object_class_meta.json  the fiscal years and reporting period each year was read through, and the day read
  agency_object_class_minor.csv  fy|agency|code|name|musd        the same money in the finer federal categories (11.1 full-time pay,
                                                                 25.4 running facilities, 21.0 moving people, 25.3 payments to other agencies...)
  agency_award_linked.csv    fy|agency|object_class|linked_musd|total_musd   how much of each kind is tied to a published award (a
                                                                 contract or grant with a named recipient); the rest has no payee in public records
  ice_spending_by_state.csv  state|musd                          ICE-funded contract money by the state where the work is done, for the
                                                                 same three fiscal years as the contract pages (headquarters services show up in DC and Virginia)

Contract data (what the rest of the page counts) shows who was paid; these account reports show everything, payroll included,
so the two do not match line for line: contract money appears here inside "Contractual services and supplies".
"""
import csv, datetime as dt, json, time
from pathlib import Path
from identity import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://api.usaspending.gov/api/v2/spending/"
DHS = 766                                            # USAspending's id for the Department of Homeland Security
ROOT_API = "https://api.usaspending.gov/api/v2"


def fy_dates(fy, period):
    """Fiscal year fy through reporting period (12 = September) -> (start, end) dates."""
    end_month = {3: "12-31", 6: "03-31", 9: "06-30", 12: "09-30"}[period]
    return f"{fy - 1}-10-01", f"{fy if period > 3 else fy - 1}-{end_month}"
AGENCIES = {"ICE": "Immigration and Customs Enforcement", "CBP": "Customs and Border Protection"}


def fiscal_years(today):
    fy = today.year + (1 if today.month >= 10 else 0)
    return list(range(fy - 4, fy))                  # the last four finished or nearly finished years


def main():
    import requests
    s = requests.Session(); s.headers["User-Agent"] = USER_AGENT
    def post(body, tries=4):
        for i in range(tries):
            try:
                r = s.post(API, json=body, timeout=120)
                if r.status_code == 200: time.sleep(0.4); return r.json()
                if r.status_code == 400 and "submission period" in r.text: return {}      # that quarter has not been reported yet
                err = f"{r.status_code} {r.text[:150]}"
            except Exception as e: err = str(e)[:150]
            time.sleep(5 * (i + 1))
        raise RuntimeError(f"USAspending did not answer: {err}")
    rows, minor, linked, meta = [], [], [], {"read": dt.date.today().isoformat(), "years": {}}
    for fy in fiscal_years(dt.date.today()):
        got = None
        for period in (12, 9, 6, 3):                 # the newest quarter that has been reported
            j = post({"type": "federal_account", "filters": {"fy": str(fy), "period": str(period), "agency": DHS}})
            if j.get("results"): got = (period, j["results"]); break
        if not got: print(f"FY{fy}: no account data yet", flush=True); continue
        period, accts = got; meta["years"][fy] = period
        for a in accts:
            ag = next((k for k, v in AGENCIES.items() if v in a["name"]), None)
            if not ag: continue
            oc = post({"type": "object_class", "filters": {"fy": str(fy), "period": str(period), "agency": DHS, "federal_account": int(a["id"])}})
            tot = sum(x["amount"] for x in oc.get("results", []))
            if abs(tot - a["amount"]) > max(1e6, 0.001 * abs(a["amount"])): raise SystemExit(f"FY{fy} {a['account_number']}: object classes add to {tot:,.0f}, account says {a['amount']:,.0f}. Nothing written.")
            for x in oc.get("results", []):
                if x["amount"]: rows.append([fy, ag, f"{a['account_number']} {a['name']}", x["name"], round(x["amount"] / 1e6, 1)])
                if x["amount"]:                       # the part of this kind of spending tied to a published award
                    rc = post({"type": "recipient", "filters": {"fy": str(fy), "period": str(period), "agency": DHS, "federal_account": int(a["id"]), "object_class": str(x["id"])}})
                    linked.append([fy, ag, x["name"], round((rc.get("total") or 0) / 1e6, 1), round(x["amount"] / 1e6, 1)])
            b0, b1 = fy_dates(fy, period)
            r = s.post(f"{ROOT_API}/federal_accounts/{a['account_number']}/object_classes/total/", json={"filters": {"time_period": [{"start_date": b0, "end_date": b1}]}, "limit": 100}, timeout=120)
            if r.status_code == 200:
                mi = r.json().get("results", []); mt = sum(x["obligations"] for x in mi)
                if mi and abs(mt - a["amount"]) <= max(1e6, 0.002 * abs(a["amount"])): minor += [[fy, ag, x["code"], x["name"], round(x["obligations"] / 1e6, 1)] for x in mi if x["obligations"]]
                elif mi: print(f"FY{fy} {a['account_number']}: finer categories add to {mt:,.0f}, account says {a['amount']:,.0f}; left out", flush=True)
            time.sleep(0.4)
        print(f"FY{fy} (through period {period}): {sum(1 for r in rows if r[0] == fy)} lines", flush=True)
    if not any(r[1] == "ICE" for r in rows): raise SystemExit("No ICE accounts found. Nothing written.")
    with open(REF / "agency_object_class.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|"); w.writerow(["fy", "agency", "account", "object_class", "musd"]); w.writerows(rows)
    (REF / "agency_object_class_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    agg = {}
    for fy, ag, code, name, m in minor: k = (fy, ag, code, name); agg[k] = round(agg.get(k, 0) + m, 1)
    with open(REF / "agency_object_class_minor.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|"); w.writerow(["fy", "agency", "code", "name", "musd"]); w.writerows([[*k, v] for k, v in sorted(agg.items())])
    la = {}
    for fy, ag, oc, l, t in linked: k = (fy, ag, oc); v = la.get(k, [0, 0]); la[k] = [round(v[0] + l, 1), round(v[1] + t, 1)]
    with open(REF / "agency_award_linked.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|"); w.writerow(["fy", "agency", "object_class", "linked_musd", "total_musd"]); w.writerows([[*k, *v] for k, v in sorted(la.items())])
    # ICE-funded contract money by the state where the work is done (same window as the contract pages)
    fys = sorted(meta["years"]); fys = [y for y in fys if y >= fys[-1] - 2]
    g = s.post(f"{ROOT_API}/search/spending_by_geography/", json={"scope": "place_of_performance", "geo_layer": "state", "filters": {"award_type_codes": ["A", "B", "C", "D"],
        "agencies": [{"type": "funding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}],
        "time_period": [{"start_date": f"{fys[0] - 1}-10-01", "end_date": f"{fys[-1]}-09-30"}]}}, timeout=180)
    if g.status_code == 200 and g.json().get("results"):
        with open(REF / "ice_spending_by_state.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter="|"); w.writerow(["state", "musd"]); w.writerows(sorted([[x["shape_code"], round(x["aggregated_amount"] / 1e6, 1)] for x in g.json()["results"] if x.get("shape_code")], key=lambda r: -r[1]))
        meta["by_state_window"] = [f"{fys[0] - 1}-10-01", f"{fys[-1]}-09-30"]; (REF / "agency_object_class_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


if __name__ == "__main__": main()
