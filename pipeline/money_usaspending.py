"""ICE contract spending from USAspending.gov: who is paid, for what, the budget, and reported subcontracts.

Usage:  python pipeline/money_usaspending.py
Window: the three most recently completed federal fiscal years (a fiscal year ends 30 September). Three, so the window reaches
back to fiscal year 2024, the last full fiscal year before the change of administration in January 2025; money_meta.json keeps the
total for each fiscal year so the years can be compared.
Writes, in data/reference/ ("|" separated, MILLIONS of dollars, obligations not payments):
  ice_contract_recipients.csv   the 60 largest recipients; detention_guard_musd = same query limited to NAICS 561612 and 561210
  ice_money_flow.csv            obligations grouped by product/service code, with the largest recipients in each group
  ice_spending_by_year.csv      each spending group and each of the 60 largest recipients, per fiscal year ("checked" = no where the
                                per-year search did not add up to the recipient's total; those rows carry no yearly figures)
  ice_competition.csv           dollars per fiscal year by how the contract was awarded (competed, not competed, not recorded)
  ice_not_competed_top.csv      the recipients of the most not-competed dollars over the whole window
  ice_money_other.csv           the codes inside "everything else", largest first; the last row is all the small codes together
  ice_budget_totals.csv, ice_budget_accounts.csv    ICE's budget for those years, and its five largest accounts
  ice_subawards.csv             every reported subcontract, added up by prime contractor and subcontractor
  money_meta.json               the window, the day read, and the source's own totals. build_site.py checks the files against these.
Nothing is written unless every request succeeds and the parts add up, so a half-read never replaces a good file.
"""
import re, csv, datetime as dt, json, sys, time
from pathlib import Path
from identity import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://api.usaspending.gov"
GROUPS = [("GUARD", ["S206"]), ("AIR", ["V211"]), ("SUPPORT", ["R408", "R706", "R499", "R799", "R699", "R615", "R701", "R608", "B513"]),
          ("IT", ["DA01", "DA10", "DH01", "7A21", "7E20", "DJ01", "7G21", "DG01", "7B22", "DF01", "7E21", "7B20"]),
          ("EQUIP", ["5820", "8470", "8415", "5836", "7110"]), ("MEDICAL", ["Q201"]), ("BUILD", ["Y1JZ"])]



ACRONYMS = {"it", "itsm", "pm", "hw", "av", "ict", "hvac", "us", "dhs", "ice", "cbp", "sw", "r&d", "a&e"}


def psc_name(n):
    """USAspending's upper-case category names -> sentence case, keeping abbreviations (IT, ITSM, HW...) upper case."""
    s = " ".join((n or "").split()).capitalize().replace("|", "/")
    return re.sub(r"(?<![\w&])([a-z&]+)(?![\w&])", lambda m: m.group(1).upper() if m.group(1).lower() in ACRONYMS else m.group(1), s, flags=re.I)

def window(today):
    """The three fiscal years completed by today: (start, end, [FY numbers])."""
    end_year = today.year if (today.month, today.day) > (9, 30) else today.year - 1
    return f"{end_year - 3}-10-01", f"{end_year}-09-30", [end_year - 2, end_year - 1, end_year]


def musd(x): return int(round(x / 1e6))


def other_codes(all_codes, other_musd, floor=3e6, most=40):
    """What "everything else" is made of. all_codes: [(code, name, dollars)] for every product/service code ICE used.
    Returns ([codes outside GROUPS], rows for ice_money_other.csv). Codes under the floor are added into one last row, whose
    amount is whatever is left of other_musd (the group total, in millions, exactly as ice_money_flow.csv has it), so the rows always add up to the group and cancelled awards are not lost."""
    mine = {c for _, cs in GROUPS for c in cs}
    rest = sorted(((c, n, a) for c, n, a in all_codes if c and c not in mine), key=lambda x: -x[2])
    big = [x for x in rest if x[2] >= floor][:most]
    rows = [{"code": c, "name": psc_name(n), "musd": musd(a), "n_codes": 1} for c, n, a in big]
    rows.append({"code": "", "name": "", "musd": other_musd - sum(r["musd"] for r in rows), "n_codes": len(rest) - len(big)})
    return [c for c, _, _ in rest], rows


# The government's "extent competed" codes. Competed: open to bidders. Not competed: awarded without competition, including a
# follow-on to an earlier competed contract and orders placed non-competitively under an existing contract.
COMPETED = {"competed": ["A", "D", "F", "CDO"], "not_competed": ["B", "C", "E", "G", "NDO"]}


def year_row(name, total, yearly, fys):
    """One recipient's dollars per fiscal year. The per-year search matches the name as text, so it can pick up a different
    company with a similar name: the years are kept only if they add up to the recipient's own total (within 2%)."""
    got = sum(yearly.get(fy, 0) for fy in fys); ok = abs(got - total) <= 0.02 * abs(total) + 5e5
    return {"kind": "recipient", "name": name, **{f"fy{fy}": musd(yearly.get(fy, 0)) if ok else "" for fy in fys}, "checked": "yes" if ok else "no"}


def flow_rows(total, groups, other_recips=()):
    """groups: [(name, codes, group dollars, [(recipient, dollars)])] -> rows for ice_money_flow.csv. OTHER is the remainder;
    other_recips are the largest recipients under the codes outside every group."""
    rows, used = [], 0
    for name, codes, amount, recips in groups:
        g = musd(amount); used += g
        keep = [(n, a) for n, a in recips if a >= 5e6 and a >= 0.015 * amount][:14]
        for n, a in keep or [("", 0)]:
            rows.append({"group": name, "group_total_musd": g, "psc_codes": " ".join(codes), "recipient": n, "musd": musd(a) if n else ""})
    other = musd(total) - used
    if other < 0: raise ValueError(f"groups add to {used}M, more than the total {musd(total)}M")
    keep = [(n, a) for n, a in other_recips if a >= 5e6][:14]
    for n, a in keep or [("", 0)]:
        rows.append({"group": "OTHER", "group_total_musd": other, "psc_codes": "", "recipient": n, "musd": musd(a) if n else ""})
    return rows


def sub_rows(records, old_for):
    """Subaward records -> one row per prime and subcontractor, largest first. old_for keeps hand-written descriptions."""
    agg = {}
    for r in records:
        k = (r["Prime Recipient Name"] or "").strip(), (r["Sub-Awardee Name"] or "").strip()
        a = agg.setdefault(k, [0.0, 0, ""]); a[0] += float(r["Sub-Award Amount"] or 0); a[1] += 1
        if not a[2]: a[2] = " ".join((r.get("Sub-Award Description") or "").split())[:90].capitalize()
    return [{"prime": p, "sub": s, "musd": f"{a / 1e6:.3f}", "for": (old_for.get((p, s)) or d).replace("|", "/"), "n": n} for (p, s), (a, n, d) in sorted(agg.items(), key=lambda kv: -kv[1][0])]


def main():
    import requests
    s = requests.Session(); s.headers["User-Agent"] = USER_AGENT
    def call(path, body=None, tries=4):
        for i in range(tries):
            try:
                r = s.post(API + path, json=body, timeout=90) if body is not None else s.get(API + path, timeout=90)
                if r.status_code == 200: time.sleep(0.4); return r.json()
                err = f"{r.status_code} {r.text[:150]}"
            except Exception as e: err = str(e)[:150]
            time.sleep(5 * (i + 1))
        raise SystemExit(f"USAspending did not answer {path}: {err}. Nothing written.")
    start, end, fys = window(dt.date.today())
    F = lambda **extra: dict({"time_period": [{"start_date": start, "end_date": end}], "award_type_codes": ["A", "B", "C", "D"],
                              "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement"}]}, **extra)
    over = lambda **extra: sum(x["aggregated_amount"] or 0 for x in call("/api/v2/search/spending_over_time/", {"group": "fiscal_year", "filters": F(**extra)})["results"])
    rid = {}                                                             # recipient name -> the source's own id for that recipient
    def top(n, **extra):
        res = [x for x in call("/api/v2/search/spending_by_category/recipient/", {"filters": F(**extra), "limit": n, "page": 1})["results"] if x.get("name")]
        for x in res:
            if x.get("recipient_id"): rid.setdefault(x["name"], x["recipient_id"])
        return [(x["name"], x["amount"]) for x in res]
    yearly = call("/api/v2/search/spending_over_time/", {"group": "fiscal_year", "filters": F()})["results"]
    by_fy = {int(x["time_period"]["fiscal_year"]): x["aggregated_amount"] or 0 for x in yearly}
    total = sum(by_fy.values())
    if sorted(by_fy) != fys: raise SystemExit(f"Expected fiscal years {fys}, the source gave {sorted(by_fy)}. Nothing written.")
    if not 2e9 < total < 2e11: raise SystemExit(f"Implausible total ({total:,.0f}). Nothing written.")
    recips = top(60); guard = dict(top(100, naics_codes=["561612", "561210"]))
    groups = [(name, codes, over(psc_codes=codes), top(20, psc_codes=codes)) for name, codes in GROUPS]
    codes, page = [], 1                                   # every product/service code ICE used, to say what "everything else" is
    while True:
        j = call("/api/v2/search/spending_by_category/psc/", {"filters": F(), "limit": 100, "page": page})
        codes += [(x.get("code"), x.get("name"), x.get("amount") or 0) for x in j["results"]]
        if not j.get("page_metadata", {}).get("hasNext") or page > 40: break
        page += 1
    if abs(sum(a for _, _, a in codes) - total) > 0.02 * total: raise SystemExit(f"Product codes add to {sum(a for _, _, a in codes):,.0f}, not the total {total:,.0f}. Nothing written.")
    rest_codes, other = other_codes(codes, musd(total) - sum(musd(g[2]) for g in groups))
    flow = flow_rows(total, groups, top(20, psc_codes=rest_codes[:190]) if rest_codes else [])     # the search takes at most 200 codes; rest_codes is largest first, so the 190 biggest
    # each year on its own: every spending group, then every one of the largest recipients
    yearly_of = lambda **extra: {int(x["time_period"]["fiscal_year"]): x["aggregated_amount"] or 0 for x in call("/api/v2/search/spending_over_time/", {"group": "fiscal_year", "filters": F(**extra)})["results"]}
    year_rows = [{"kind": "group", "name": name, **{f"fy{fy}": musd(yearly_of(psc_codes=codes).get(fy, 0)) for fy in fys}, "checked": "yes"} for name, codes in GROUPS]
    year_rows.append({"kind": "group", "name": "OTHER", **{f"fy{fy}": musd(by_fy[fy]) - sum(r[f"fy{fy}"] for r in year_rows) for fy in fys}, "checked": "yes"})
    for name, amount in recips:
        row = year_row(name, amount, yearly_of(recipient_id=rid[name]), fys) if rid.get(name) else None      # by the recipient's id first: exact
        if not row or row["checked"] != "yes": row = year_row(name, amount, yearly_of(recipient_search_text=[name]), fys)   # else by name, kept only if it adds up
        year_rows.append(row)
    # how the contracts were awarded, by the government's own "extent competed" code on each one
    comp_rows = []
    for label, codes in COMPETED.items():
        y = yearly_of(extent_competed_type_codes=codes)
        comp_rows.append({"how": label, **{f"fy{fy}": musd(y.get(fy, 0)) for fy in fys}})
    comp_rows.append({"how": "not_recorded", **{f"fy{fy}": musd(by_fy[fy]) - sum(r[f"fy{fy}"] for r in comp_rows) for fy in fys}})
    nc_top = [{"recipient": n, "musd": musd(a)} for n, a in top(15, extent_competed_type_codes=COMPETED["not_competed"]) if a >= 5e6]

    # budget
    tot_rows, acc_rows = [], []
    oldacc = {r["code"]: r["account"] for r in csv.DictReader(open(REF / "ice_budget_accounts.csv", encoding="utf-8"), delimiter="|")} if (REF / "ice_budget_accounts.csv").exists() else {}
    for fy in fys:
        subs = call(f"/api/v2/agency/070/sub_components/?fiscal_year={fy}&limit=100")["results"]
        ice = next((x for x in subs if "immigration and customs" in x["name"].lower()), None)
        if not ice: raise SystemExit(f"ICE not found among Homeland Security's components for FY{fy}. Nothing written.")
        tot_rows.append({"fiscal_year": fy, "obligated_musd": musd(ice["total_obligations"]), "paid_out_musd": musd(ice["total_outlays"]), "available_musd": musd(ice["total_budgetary_resources"])})
        acc = call(f"/api/v2/agency/070/sub_components/{ice['id']}/?fiscal_year={fy}&limit=100")["results"]
        for a in sorted(acc, key=lambda a: -(a["total_obligations"] or 0))[:5]:
            acc_rows.append({"fiscal_year": fy, "account": oldacc.get(a["id"]) or a["name"].split(", U.S. Immigration")[0], "code": a["id"], "obligated_musd": musd(a["total_obligations"] or 0), "available_musd": musd(a["total_budgetary_resources"] or 0)})
    # subcontracts: every page
    recs, page = [], 1
    while True:
        j = call("/api/v2/search/spending_by_award/", {"filters": F(), "fields": ["Sub-Award ID", "Sub-Awardee Name", "Sub-Award Amount", "Prime Recipient Name", "Prime Award ID", "Sub-Award Description"],
                                                       "limit": 100, "page": page, "sort": "Sub-Award Amount", "order": "desc", "subawards": True, "spending_level": "subawards"})
        recs += j["results"]
        if not j.get("page_metadata", {}).get("hasNext") or page > 60: break
        page += 1
    old_for = {(r["prime"], r["sub"]): r["for"] for r in csv.DictReader(open(REF / "ice_subawards.csv", encoding="utf-8"), delimiter="|")} if (REF / "ice_subawards.csv").exists() else {}
    subs = sub_rows(recs, old_for); subs_total = round(sum(float(r["musd"]) for r in subs), 3)

    def write(name, rows, fields):
        with open(REF / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    write("ice_contract_recipients.csv", [{"recipient": n, "obligated_musd": musd(a), "detention_guard_musd": musd(guard[n]) if guard.get(n, 0) >= 5e5 else ""} for n, a in recips], ["recipient", "obligated_musd", "detention_guard_musd"])
    write("ice_money_flow.csv", flow, ["group", "group_total_musd", "psc_codes", "recipient", "musd"])
    write("ice_money_other.csv", other, ["code", "name", "musd", "n_codes"])
    write("ice_spending_by_year.csv", year_rows, ["kind", "name", *[f"fy{fy}" for fy in fys], "checked"])
    write("ice_competition.csv", comp_rows, ["how", *[f"fy{fy}" for fy in fys]])
    write("ice_not_competed_top.csv", nc_top, ["recipient", "musd"])
    write("ice_budget_totals.csv", tot_rows, ["fiscal_year", "obligated_musd", "paid_out_musd", "available_musd"])
    write("ice_budget_accounts.csv", acc_rows, ["fiscal_year", "account", "code", "obligated_musd", "available_musd"])
    write("ice_subawards.csv", subs, ["prime", "sub", "musd", "for", "n"])
    (REF / "money_meta.json").write_text(json.dumps({"from": start, "to": end, "read": str(dt.date.today()), "total_musd": musd(total), "by_fy_musd": [[fy, musd(by_fy[fy])] for fy in fys], "subs_total_musd": subs_total, "subs_records": len(recs)}, indent=1), encoding="utf-8")
    print(f"ICE contracts {start} to {end}: {musd(total):,}M total, {len(recips)} recipients, {len(subs)} subcontract lines ({subs_total:,.3f}M from {len(recs)} records)")


if __name__ == "__main__": main()
