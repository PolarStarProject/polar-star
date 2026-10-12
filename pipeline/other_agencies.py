"""Agencies other than ICE that hold, move or pay for people facing removal: what their own records say.

Usage:  python pipeline/other_agencies.py
Writes, in data/reference/ ("|" separated):
  cbp_encounters_by_month.csv  month|fy|total|southwest|northern|other|title42|uac    CBP encounters, nationwide. EVENTS, not people:
                               one person caught three times counts three times. From CBP's own monthly file.
  cbp_custody_by_month.csv     month|usbp_apprehended|usbp_in_custody|usbp_to_federal|ofo_sw_in_custody    from CBP's custody and
                               transfer tables. The page shows only the current fiscal year, so earlier months are kept from the old file.
  ohss_repatriations.csv       fy|removals|enforcement_returns|administrative_returns|expulsions|total     all of DHS, from Yearbook
                               table 39, rounded to the nearest 10 by the source. Ends where the source ends (no figure is estimated).
  other_money.csv              agency|program|recipient|musd     obligations in the window, by recipient. The last row of each program
                               (recipient blank) is everything not listed, so a program's rows add up to its total.
  other_money_payees.csv       every payee of $1 million or more (paid or taken back) in each program, private people left out, for
                               finding companies paid by more than one agency.
  other_money_meta.json        the window, the day read, each program's total, and how many payees were left out as private people.
  cbp_notices_seen.csv         url|title|first_seen     CBP death notices listed on its accountability page, for a person to review.
                               Nothing here reaches the page until it is added by hand to cbp_death_notices.csv.
Each part is written only when it reads cleanly. A part that fails leaves its old file as it was, and the step exits 1 at the end.
Private people are never written: a payee the source marks as an individual, or a sole proprietorship whose name does not read as a
business, is added into the "everything else" row of its program and counted (not named) in the meta file.
"""
import csv, datetime as dt, gzip, io, json, re, sys, time
from pathlib import Path
from identity import USER_AGENT

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://api.usaspending.gov"
CBP = "https://www.cbp.gov/"
ENC_PAGE = "https://www.cbp.gov/document/stats/nationwide-encounters"
CUSTODY_PAGE = "https://www.cbp.gov/newsroom/stats/custody-and-transfer-statistics"
NOTICE_PAGE = "https://www.cbp.gov/newsroom/accountability-and-transparency"
T39 = "https://ohss.dhs.gov/topics/immigration/yearbook/{year}/table39"
ORR_PAGES = {"ops": "https://acf.gov/orr/data/uac-operational", "rel": "https://acf.gov/orr/data/uac-monthly-release-sponsor"}
MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# ---- what each agency's money is, in the source's own terms -------------------------------------------------------------------------
CONTRACTS, GRANTS = ["A", "B", "C", "D"], ["02", "03", "04", "05"]
AG = {"CBP": ("U.S. Customs and Border Protection", "Department of Homeland Security"),
      "ACF": ("Administration for Children and Families", "Department of Health and Human Services"),
      "FEMA": ("Federal Emergency Management Agency", "Department of Homeland Security"),
      "USMS": ("U.S. Marshals Service", "Department of Justice")}
ICE_FUNDED_BY_DHS_HQ = [{"type": "funding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"},
                        {"type": "awarding", "tier": "subtier", "name": "Office of Procurement Operations", "toptier_name": "Department of Homeland Security"}]
# CBP product codes that are about holding people: tents and buildings and running them, medical care, guards, food, care, transport.
# Border wall, IT, aircraft and the like are left out on purpose.
CBP_HOLD = ["W054", "M1AZ", "M1JZ"]
CBP_MED = ["Q403", "Q999", "Q201", "Q301", "Q402", "Q501", "Q702"]
CBP_CARE = ["S206", "S203", "S201", "R401", "V111", "V211", "V221", "V222", "V231"]
PROGRAMS = [  # agency, program key, award types, agency key, extra filters
    ("CBP", "holding", CONTRACTS, "CBP", {"psc_codes": CBP_HOLD}),
    ("CBP", "medical", CONTRACTS, "CBP", {"psc_codes": CBP_MED}),
    ("CBP", "care", CONTRACTS, "CBP", {"psc_codes": CBP_CARE}),
    ("HHS", "children_grants", GRANTS, "ACF", {"program_numbers": ["93.676"]}),
    ("HHS", "children_contracts", CONTRACTS, "ACF", {"description": "unaccompanied"}),
    ("FEMA", "detention_grants", GRANTS, None, {"program_numbers": ["97.158"]}),
    ("FEMA", "shelter_grants", GRANTS, None, {"program_numbers": ["97.141", "97.149"]}),
    ("DHS", "state_border_fund", GRANTS, None, {"program_numbers": ["97.159"]}),             # State Border Security Reinforcement Fund (P.L. 119-21)
    ("ICE", "via_dhs_hq", CONTRACTS, None, {"agencies": ICE_FUNDED_BY_DHS_HQ}),              # ICE money in contracts DHS headquarters awarded
    ("DOJ", "marshals_detention", CONTRACTS, "USMS", {"description": "detention"}),         # the Marshals also pay detention companies
]
# Defense contracts for immigration detention, read one by one (a word search also finds flood-control "detention basins").
DOD_AWARDS = ["CONT_AWD_W9124J25FA075_9700_N0002325D0004_9700",      # Army task order: Camp East Montana, Fort Bliss (moved to ICE Oct 2025)
              "CONT_AWD_W9124J25CA014_9700_-NONE-_-NONE-"]           # Army: detention security officers and transport, El Paso
TOP = 15

ORG = re.compile(r"\b(LLC|L\.L\.C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PLLC|PC|PA|GROUP|SERVICES?|SOLUTIONS|ASSOCIATES|"
                 r"PARTNERS|HOLDINGS|ENTERPRISES?|INTERNATIONAL|SYSTEMS|TECHNOLOGIES|TECHNOLOGY|CONSULTING|CONSTRUCTION|MANAGEMENT|AGENCY|"
                 r"FOUNDATION|CENTER|CENTRE|INSTITUTE|UNIVERSITY|COLLEGE|SCHOOL|HOSPITAL|CLINIC|HEALTH|MINISTRIES|CHURCH|COUNTY|CITY|STATE|"
                 r"DEPARTMENT|DIVISION|AUTHORITY|DISTRICT|COUNCIL|ASSOCIATION|SOCIETY|TRUST|FUND|JOINT VENTURE|JV|PROGRAMS?|HOME|HOMES|"
                 r"SHELTER|CHARITIES|CATHOLIC|LUTHERAN|COMMITTEE|NETWORK|ALLIANCE|COALITION|PROJECT|INDUSTRIES|LOGISTICS|SUPPLY|"
                 r"STAFFING|MEDICAL|AVIATION|AIR|AIRLINES|TRANSPORT|TRANSPORTATION|SECURITY|DEFENSE|FEDERAL|GOVERNMENT|NATIONAL|AMERICA|"
                 r"AMERICAN|US|USA|OF)\b", re.I)


# A practice named after a person (Dr. ..., ... M.D.) is a business on paper but names a private person, so it is left out too.
PERSONAL = re.compile(r"^(DR|MR|MRS|MS|MISS)\.?\s|\b(M\.?D|D\.?D\.?S|PH\.?D|ESQ|R\.?N|LCSW|LPC)\.?(,|\s|$)", re.I)


def looks_like_business(name):
    return bool(ORG.search(name or ""))


def drop_people(recips, individuals, sole_props):
    """recips: [(name, dollars)]. Returns (kept, dropped_count, dropped_dollars). A payee is dropped when the source marks it as an
    individual, or as a sole proprietorship and its name does not read as a business. Names that only say MULTIPLE RECIPIENTS or
    REDACTED are dropped too: they are the source's own stand-ins for private people."""
    kept, n, amt = [], 0, 0.0
    for name, a in recips:
        up = (name or "").upper()
        if not name or "REDACTED" in up or "MULTIPLE RECIPIENTS" in up or name in individuals or PERSONAL.search(name) or (name in sole_props and not looks_like_business(name)):
            n += 1; amt += a or 0; continue
        kept.append((name, a))
    return kept, n, amt


def money_rows(agency, program, total, recips, complete, top=TOP):
    """Largest payees by size (a negative amount is money taken back), then one row for everything else, so the program adds up to
    the source's own total (in millions). complete: every payee was read, so their sum must match the total."""
    m = lambda x: round(x / 1e6, 1)
    if complete and abs(sum(a for _, a in recips) - total) > 0.01 * abs(total) + 5e5:
        raise ValueError(f"{agency}/{program}: payees add to {m(sum(a for _, a in recips))}M, not the total {m(total)}M")
    keep = sorted([(n, a) for n, a in recips if a and abs(a) >= 5e5], key=lambda x: -abs(x[1]))[:top]
    rows = [{"agency": agency, "program": program, "recipient": n.replace("|", "/"), "musd": m(a)} for n, a in keep]
    rows.append({"agency": agency, "program": program, "recipient": "", "musd": round(m(total) - sum(r["musd"] for r in rows), 1)})
    return rows


# ---- CBP encounters ------------------------------------------------------------------------------------------------------------------
def newest_encounter_csv(links):
    """The newest nationwide-encounters state file among page links, by its upload folder (YYYY-MM) then its last fiscal year."""
    best = None
    for u in links:
        m = re.search(r"/(\d{4})-(\d{2})/nationwide-encounters-fy(\d\d)-fy(\d\d)-?(\w*?)-?state(?:_\d)?\.csv$", u)
        if m:
            k = (int(m.group(1)), int(m.group(2)), int(m.group(4)))
            if best is None or k > best[0]: best = (k, u)
    return best[1] if best else None


def encounters_by_month(rows):
    """rows: CBP's own CSV rows. -> [{month: 'YYYY-MM', fy, total, southwest, northern, other, title42, uac}] oldest first."""
    agg = {}
    for r in rows:
        fy = int(re.match(r"\d{4}", r["Fiscal Year"]).group(0)); mo = MON[r["Month (abbv)"].strip().upper()[:3]]
        yr = fy - 1 if mo >= 10 else fy
        k = f"{yr}-{mo:02d}"; a = agg.setdefault(k, {"month": k, "fy": fy, "total": 0, "southwest": 0, "northern": 0, "other": 0, "title42": 0, "uac": 0})
        n = int(str(r["Encounter Count"]).replace(",", "") or 0)
        a["total"] += n
        reg = (r.get("Land Border Region") or "").lower()
        a["southwest" if "southwest" in reg else "northern" if "northern" in reg else "other"] += n
        if "42" in (r.get("Title of Authority") or ""): a["title42"] += n
        if (r.get("Demographic") or "").strip().upper() == "UAC": a["uac"] += n
    out = [agg[k] for k in sorted(agg)]
    if len(out) < 24: raise ValueError(f"only {len(out)} months in the encounters file")
    return out


# ---- CBP custody tables --------------------------------------------------------------------------------------------------------------
def _month(h):
    m = re.match(r"([A-Za-z]{3})-(\d\d)$", h.strip())
    return f"20{m.group(2)}-{MON[m.group(1).upper()]:02d}" if m else None


def _num(s):
    s = re.sub(r"\(.*?\)", "", s or "").replace(",", "").strip()
    return int(s) if re.fullmatch(r"\d+", s) else None


def custody_by_month(html):
    """CBP's custody and transfer page -> {month: {...}} for the months it has numbers for."""
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser"); out = {}
    want = {("sector", "total"): "usbp_in_custody", ("transfer destination", "federal (ero, orr, other)"): "usbp_to_federal",
            ("processing disposition", "total apprehensions"): "usbp_apprehended", ("detention capacity", "%"): "ofo_sw_in_custody"}
    for tb in s.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])] for r in tb.find_all("tr")]
        if not rows or len(rows[0]) < 2: continue
        head = rows[0][0].lower(); months = [_month(h) for h in rows[0][1:]]
        for r in rows[1:]:
            key = want.get((head, re.sub(r"\s*\d+$", "", r[0]).strip().lower()))
            if not key: continue
            for mo, v in zip(months, r[1:]):
                n = _num(v)
                if mo and n is not None: out.setdefault(mo, {})[key] = n
    return out


def merge_months(old_rows, new):
    """Keep earlier months from the old file; months the page now shows replace the old values."""
    cols = ["usbp_apprehended", "usbp_in_custody", "usbp_to_federal", "ofo_sw_in_custody"]
    have = {r["month"]: {c: r.get(c, "") for c in cols} for r in old_rows}
    for mo, v in new.items(): have[mo] = {c: v.get(c, have.get(mo, {}).get(c, "")) for c in cols}
    return [{"month": mo, **have[mo]} for mo in sorted(have)]


# ---- DHS repatriations (Yearbook table 39) -------------------------------------------------------------------------------------------
def table39(html, since=2010):
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser"); out = []
    for tb in s.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])] for r in tb.find_all("tr")]
        if not rows or not rows[0] or "Administrative Returns" not in " ".join(rows[0]): continue
        h = [x.split(" [")[0].strip().lower() for x in rows[0]]
        ix = {k: h.index(k) for k in ["year", "administrative returns", "enforcement returns", "removals", "expulsions", "total repatriations"]}
        for r in rows[1:]:
            if not re.fullmatch(r"\d{4}", r[ix["year"]]) or int(r[ix["year"]]) < since: continue
            v = lambda k: _num(r[ix[k]]) or 0
            row = {"fy": int(r[ix["year"]]), "removals": v("removals"), "enforcement_returns": v("enforcement returns"),
                   "administrative_returns": v("administrative returns"), "expulsions": v("expulsions"), "total": v("total repatriations")}
            parts = row["removals"] + row["enforcement_returns"] + row["administrative_returns"] + row["expulsions"]
            if abs(parts - row["total"]) > 60: raise ValueError(f"table 39, {row['fy']}: parts {parts} vs total {row['total']}")
            out.append(row)
    if len(out) < 10: raise ValueError("table 39 not found or too short")
    return out


# ---- HHS Office of Refugee Resettlement (children without a parent) ----------------------------------------------------------------
ORR_ROWS = {"average number of children in care": "in_care", "maximum number of operational beds": "beds",
            "average length of care (for those discharged)": "days_discharged", "average length of care (for those in care)": "days_in_care",
            "30-day average number of uac referrals": "referrals_per_day", "total": "released"}
ORR_COLS = ["in_care", "beds", "days_discharged", "days_in_care", "referrals_per_day", "released"]


def orr_sheet(rows):
    """rows: an ORR workbook sheet as lists. -> ({month: {col: value}}, {fy: days}). The months header names its fiscal year."""
    out, fy_days, fy, months = {}, {}, None, None
    for i, r in enumerate(rows):
        r = list(r) + [None] * 14
        lab = str(r[0] or "").replace("\xa0", " ").strip()
        m = re.search(r"FY ?(\d{4})", lab)
        if m and not lab.upper().startswith("FY"): fy = int(m.group(1))         # "... in FY2026" names the year of the months below
        if [str(c or "").strip().upper()[:3] for c in r[1:13]] == ["OCT", "NOV", "DEC", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP"]:
            months = [f"{fy - 1 if k < 3 else fy}-{(10 + k - 1) % 12 + 1:02d}" for k in range(12)] if fy else None
            continue
        if lab.upper().startswith("FY") and re.fullmatch(r"FY\d{4}", lab.upper()) and i + 1 < len(rows):
            nxt = list(rows[i + 1])
            for k, c in enumerate(r[:12]):
                if c and re.fullmatch(r"FY\d{4}", str(c).upper()) and k < len(nxt) and isinstance(nxt[k], (int, float)): fy_days[int(str(c)[2:])] = int(nxt[k])
            continue
        key = ORR_ROWS.get(re.sub(r"\*+$", "", lab).strip().lower())
        if key and months:
            for mo, v in zip(months, r[1:13]):
                if isinstance(v, (int, float)): out.setdefault(mo, {})[key] = v
    return out, fy_days


# ---- writing ---------------------------------------------------------------------------------------------------------------------------
def write(name, rows, cols):
    tmp = REF / (name + ".part")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    tmp.replace(REF / name)


def read(name):
    p = REF / name
    return list(csv.DictReader(open(p, encoding="utf-8"), delimiter="|")) if p.exists() else []


def main():
    import requests, icefetch
    from money_usaspending import window
    failed = []

    def part(name, fn):
        try: fn(); print(f"{name}: ok", flush=True)
        except Exception as e: failed.append(name); print(f"{name} FAILED: {str(e)[:300]}", flush=True)

    def page(url, origin=CBP):
        b = icefetch.fetch_bytes([url], origin=origin, pause=1.0).get(url)
        if not b: raise RuntimeError(f"could not read {url}")
        return b

    def encounters():
        html = page(ENC_PAGE).decode("utf-8", "replace")
        from urllib.parse import urljoin
        links = [urljoin(ENC_PAGE, h) for h in re.findall(r'href="([^"]+\.csv)"', html)]
        u = newest_encounter_csv(links)
        if not u: raise RuntimeError("no encounters file linked")
        rows = list(csv.DictReader(io.TextIOWrapper(io.BytesIO(page(u)), encoding="utf-8-sig")))
        out = encounters_by_month(rows)
        last = dt.date.fromisoformat(out[-1]["month"] + "-01")
        if (dt.date.today() - last).days > 160: raise RuntimeError(f"newest month {out[-1]['month']} is too old")
        write("cbp_encounters_by_month.csv", out, ["month", "fy", "total", "southwest", "northern", "other", "title42", "uac"])
        meta["encounters"] = {"file": u, "read": dt.date.today().isoformat(), "to": out[-1]["month"]}

    def custody():
        new = custody_by_month(page(CUSTODY_PAGE).decode("utf-8", "replace"))
        if not new or not any("usbp_in_custody" in v for v in new.values()): raise RuntimeError("custody tables not found")
        write("cbp_custody_by_month.csv", merge_months(read("cbp_custody_by_month.csv"), new), ["month", "usbp_apprehended", "usbp_in_custody", "usbp_to_federal", "ofo_sw_in_custody"])
        meta["custody"] = {"read": dt.date.today().isoformat(), "to": max(new)}

    def repatriations():
        year, got = dt.date.today().year, None
        for y in range(year, year - 5, -1):        # newest yearbook that has table 39
            try: got = (y, table39(page(T39.format(year=y), origin="https://ohss.dhs.gov/").decode("utf-8", "replace"))); break
            except Exception as e: print(f"  yearbook {y}: {str(e)[:100]}")
        if not got: raise RuntimeError("no yearbook table 39 could be read")
        write("ohss_repatriations.csv", got[1], ["fy", "removals", "enforcement_returns", "administrative_returns", "expulsions", "total"])
        meta["repatriations"] = {"yearbook": got[0], "url": T39.format(year=got[0]), "read": dt.date.today().isoformat(), "to": got[1][-1]["fy"]}

    def orr():
        import openpyxl
        from urllib.parse import urljoin
        got, fy_days = {}, {}
        for k, u in ORR_PAGES.items():
            html = page(u, origin="https://acf.gov/").decode("utf-8", "replace")
            link = next((urljoin(u, h) for h in re.findall(r'href="([^"]+\.xlsx)"', html)), None)
            if not link: raise RuntimeError(f"no workbook linked from {u}")
            wb = openpyxl.load_workbook(io.BytesIO(page(link, origin="https://acf.gov/")), data_only=True)
            for ws in wb.worksheets:
                m, d = orr_sheet(list(ws.iter_rows(values_only=True)))
                for mo, v in m.items(): got.setdefault(mo, {}).update(v)
                fy_days.update(d)
            meta.setdefault("orr", {})[k] = link
        if not any("in_care" in v for v in got.values()): raise RuntimeError("children-in-care row not found")
        have = {r["month"]: r for r in read("orr_by_month.csv")}
        for mo, v in got.items(): have[mo] = {"month": mo, **{c: v.get(c, have.get(mo, {}).get(c, "")) for c in ORR_COLS}}
        write("orr_by_month.csv", [have[k] for k in sorted(have)], ["month"] + ORR_COLS)
        old = {int(r["fy"]): int(r["days"]) for r in read("orr_days_by_fy.csv")}; old.update(fy_days)
        write("orr_days_by_fy.csv", [{"fy": k, "days": old[k]} for k in sorted(old)], ["fy", "days"])
        meta["orr"]["read"] = dt.date.today().isoformat(); meta["orr"]["to"] = max(got)

    def notices():
        html = page(NOTICE_PAGE).decode("utf-8", "replace")
        found = {}
        for href, title in re.findall(r'href="([^"]*summary-incident[^"]*)"[^>]*>([^<]+)<', html):
            found.setdefault(href if href.startswith("http") else "https://www.cbp.gov" + href, re.sub(r"\s+", " ", title).strip())
        old = {r["url"]: r for r in read("cbp_notices_seen.csv")}
        for u, t in found.items(): old.setdefault(u, {"url": u, "title": t.replace("|", "/"), "first_seen": dt.date.today().isoformat()})
        write("cbp_notices_seen.csv", sorted(old.values(), key=lambda r: r["first_seen"]), ["url", "title", "first_seen"])
        meta["notices"] = {"read": dt.date.today().isoformat(), "listed": len(found)}

    def money():
        s = requests.Session(); s.headers["User-Agent"] = USER_AGENT
        def call(path, body=None, tries=4):
            for i in range(tries):
                try:
                    r = s.post(API + path, json=body, timeout=90) if body is not None else s.get(API + path, timeout=90)
                    if r.status_code == 200: time.sleep(0.4); return r.json()
                    err = f"{r.status_code} {r.text[:150]}"
                except Exception as e: err = str(e)[:150]
                time.sleep(5 * (i + 1))
            raise RuntimeError(f"USAspending did not answer {path}: {err}")
        start, end, fys = window(dt.date.today())
        rows, progs, payees = [], {}, []
        for agency, prog, types, ag, extra in PROGRAMS:
            F = {"time_period": [{"start_date": start, "end_date": end}], "award_type_codes": types, **extra}
            if ag: F["agencies"] = [{"type": "awarding", "tier": "subtier", "name": AG[ag][0], "toptier_name": AG[ag][1]}]
            yearly = {int(x["time_period"]["fiscal_year"]): x["aggregated_amount"] or 0 for x in call("/api/v2/search/spending_over_time/", {"group": "fiscal_year", "filters": F})["results"]}
            total = sum(yearly.values())
            recips, pg, complete = [], 1, False
            while pg <= 8:
                j = call("/api/v2/search/spending_by_category/recipient/", {"filters": F, "limit": 100, "page": pg})
                recips += [(x.get("name"), x.get("amount") or 0) for x in j["results"]]
                if not j.get("page_metadata", {}).get("hasNext"): complete = True; break
                pg += 1
            names = lambda kind: {x.get("name") for x in call("/api/v2/search/spending_by_category/recipient/", {"filters": dict(F, recipient_type_names=[kind]), "limit": 100, "page": 1})["results"]}
            if complete and abs(sum(a for _, a in recips) - total) > 0.01 * abs(total) + 5e5:
                raise ValueError(f"{agency}/{prog}: payees add to {sum(a for _, a in recips) / 1e6:.1f}M, not the total {total / 1e6:.1f}M")
            kept, n_drop, a_drop = drop_people(recips, names("individuals"), names("sole_proprietorship"))
            rows += money_rows(agency, prog, total, kept, False)
            payees += [{"agency": agency, "program": prog, "recipient": n.replace("|", "/"), "musd": round(a / 1e6, 1)} for n, a in kept if abs(a) >= 1e6]
            progs[f"{agency}/{prog}"] = {"total_musd": round(total / 1e6, 1), "by_fy_musd": {str(k): round(v / 1e6, 1) for k, v in sorted(yearly.items())},
                                         "private_people_left_out": n_drop, "all_payees_read": complete,
                                         "taken_back_musd": round(-sum(a for _, a in recips if a < 0) / 1e6, 1), "filters": extra}
        # every ICE contract payee, only for matching companies across agencies (the ICE money itself is shown from money_usaspending.py)
        F = {"time_period": [{"start_date": start, "end_date": end}], "award_type_codes": CONTRACTS,
             "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}]}
        ice, pg = [], 1
        while pg <= 12:
            j = call("/api/v2/search/spending_by_category/recipient/", {"filters": F, "limit": 100, "page": pg})
            ice += [(x.get("name"), x.get("amount") or 0) for x in j["results"]]
            if not j.get("page_metadata", {}).get("hasNext"): break
            pg += 1
        names = lambda kind: {x.get("name") for x in call("/api/v2/search/spending_by_category/recipient/", {"filters": dict(F, recipient_type_names=[kind]), "limit": 100, "page": 1})["results"]}
        kept, _, _ = drop_people(ice, names("individuals"), names("sole_proprietorship"))
        write("ice_payees_all.csv", [{"recipient": n.replace("|", "/"), "musd": round(a / 1e6, 1)} for n, a in kept if abs(a) >= 1e6], ["recipient", "musd"])
        dod = []
        for aid in DOD_AWARDS:
            d = call(f"/api/v2/awards/{aid}/")
            dod.append({"award": d.get("piid"), "recipient": (d.get("recipient") or {}).get("recipient_name"), "awarding": ((d.get("awarding_agency") or {}).get("subtier_agency") or {}).get("name"),
                        "obligated_musd": round((d.get("total_obligation") or 0) / 1e6, 1), "ceiling_musd": round((d.get("base_and_all_options") or 0) / 1e6, 1),
                        "start": (d.get("period_of_performance") or {}).get("start_date"), "what": (d.get("description") or "")[:160],
                        "url": f"https://www.usaspending.gov/award/{aid}"})
        write("other_money.csv", rows, ["agency", "program", "recipient", "musd"])
        write("other_money_payees.csv", payees, ["agency", "program", "recipient", "musd"])     # every payee of $1M or more (either way), for matching across agencies
        json.dump({"from": start, "to": end, "fys": fys, "read": dt.date.today().isoformat(), "programs": progs, "dod_awards": dod},
                  open(REF / "other_money_meta.json", "w", encoding="utf-8"), indent=1)

    meta_p = REF / "other_sources_meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    for name, fn in [("encounters", encounters), ("custody", custody), ("repatriations", repatriations), ("orr", orr), ("notices", notices), ("money", money)]:
        part(name, fn)
    meta_p.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    if failed: print(f"failed parts: {', '.join(failed)} (their old files are unchanged)"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
