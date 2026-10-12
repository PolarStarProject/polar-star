"""ICE's detention statistics workbooks -> population, solitary confinement and the contract list, per facility.

Usage:  python pipeline/detention_stats.py        (reads https://www.ice.gov/detain/detention-management)
Writes, in data/reference/ (all "|" separated):
  facility_adp_by_year.csv    fy|name|city|state|type|adp        average number of people held a day, each fiscal year since 2019
  facility_segregation.csv    month|name|placements              placements into segregation (solitary confinement) each month
  ice_facility_contracts.csv  the newest year's facility list: contract type, guaranteed beds, last inspection and rating
  detention_stats_files.csv   fy|url|read                        which workbook each year came from, and the day it was last checked
  ice_semiannual.csv          group|country|measure|fy|value     arrests, book-ins and removals by fiscal year: military members and veterans,
                                                                 US citizens, parents of US-citizen children, people from TPS countries
  ice_segregation_reasons.csv fy|quarter|reason|placements|...   segregation placements each quarter by the reason ICE records, average days held
  ice_bond_monthly.csv        month|book_outs|bond_posted|avg_bond|alos   releases from ICE custody, how many after bond, average bond, average stay
  ice_length_of_stay.csv      day|population|alos|d0_180|...     average days in custody and how long people had been held, twice a month
  These four keep a src column (the workbook each row came from). ICE's later files show earlier years as 0; a zero never replaces a
  count an older file gave, and such rows are marked zeroed_in=<the later file>.

A workbook is read again only when its link changes (ICE reposts the current year every few weeks). Counts only, never a person.
A fiscal year runs October to September: FY26 is October 2025 to September 2026.
"""
import calendar, csv, datetime as dt, io, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
PAGE = "https://www.ice.gov/detain/detention-management"
MONTHS = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}


def find_workbooks(html):
    """{'FY26': url, ...} from the links on ICE's page."""
    out = {}
    for href in re.findall(r'href="([^"]+\.xlsx)"', html, re.I):
        m = re.search(r"/(FY(\d\d))[-_]?detention[-_ ]?stats[^/]*\.xlsx$", href, re.I)
        if m: out["FY" + m.group(2)] = href if href.startswith("http") else "https://www.ice.gov" + href
    return out


def cell(v): return "" if v is None else str(v).strip()


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0


def parse_facilities(rows):
    """rows of a 'Facilities' sheet -> [{name, city, state, type, adp, gm, insp, rating}]. adp is the four classification levels added up."""
    hi = next((i for i, r in enumerate(rows) if r and cell(r[0]) == "Name"), None)
    if hi is None: raise ValueError("no header row starting with 'Name'")
    H = [cell(c) for c in rows[hi]]
    def col(*names):
        for n in names:
            for i, h in enumerate(H):
                if h.lower() == n.lower(): return i
        return None
    c_city, c_state, c_type = col("City"), col("State"), col("Type Detailed")
    lv = [col(f"Level {x}") for x in "ABCD"]
    if None in (c_city, c_state, c_type) or None in lv: raise ValueError(f"expected columns missing; found {H[:14]}")
    c_gm, c_insp, c_rate = col("Guaranteed Minimum"), col("Last Inspection End Date"), col("Last Final Rating")
    out = []
    for r in rows[hi + 1:]:
        r = list(r) + [None] * (len(H) - len(r))
        name, state = re.sub(r"\s+", " ", cell(r[0])), cell(r[c_state])
        if not name or not re.fullmatch(r"[A-Z]{2}", state): continue
        insp = r[c_insp] if c_insp is not None else None
        insp = insp.date().isoformat() if isinstance(insp, dt.datetime) else (insp.isoformat() if isinstance(insp, dt.date) else cell(insp)[:10])
        gm = r[c_gm] if c_gm is not None else None
        out.append({"name": name, "city": cell(r[c_city]), "state": state, "type": cell(r[c_type]), "adp": round(sum(num(r[i]) for i in lv), 1),
                    "gm": str(int(num(gm))) if num(gm) > 0 else "", "insp": cell(r[c_insp]) if c_insp is not None and not isinstance(r[c_insp], (dt.datetime, dt.date)) else insp, "rating": cell(r[c_rate]) if c_rate is not None else ""})
    return out


def parse_segregation(rows):
    """rows of a 'Monthly Segregation' sheet -> [(YYYY-MM, facility, placements)]. Each month is a block headed by its name."""
    out, month = [], None
    for r in rows:
        a, b = (cell(r[0]) if r else ""), (cell(r[1]) if r and len(r) > 1 else "")
        m = re.match(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\b", a, re.I)
        if m and not b: month = f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"; continue
        if not a or not month or re.match(r"facilit|grand total", a, re.I): continue
        try: n = int(float(b))
        except ValueError: continue
        out.append((month, re.sub(r"\s+", " ", a), n))
    return out


def read_workbook(data):
    """bytes -> (facility rows, segregation rows)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    fac = seg = None
    for name in wb.sheetnames:
        if re.match(r"\s*Facilities", name, re.I) and fac is None: fac = parse_facilities(list(wb[name].iter_rows(values_only=True)))
        elif re.search(r"Segregation", name, re.I) and seg is None: seg = parse_segregation(list(wb[name].iter_rows(values_only=True, max_col=3)))
    if not fac: raise ValueError("no Facilities sheet")
    return fac, seg or []


MON3 = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]


def parse_atd(rows):
    """An 'ATD' sheet -> {as_of, total, cost, tech: {name: count}}: people on alternatives to detention and the daily technology cost."""
    out, tech, start = {}, {}, None
    for i, r in enumerate(rows):
        c = [cell(v) for v in r]
        if start is None and len(c) > 2 and c[0] == "Technology" and c[1] == "Count": start = i; continue
        if start is not None and "total" not in out and c and c[0]:
            if c[0] == "Total": out["total"], out["cost"] = int(num(r[1])), round(num(r[2]), 2)
            else: tech[c[0]] = int(num(r[1]))
        m = re.search(r"Participants Report,\s*(\d{1,2})[./](\d{1,2})[./](\d{4})", " ".join(c))
        if m and "as_of" not in out: out["as_of"] = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    if "total" not in out or "as_of" not in out or sum(tech.values()) != out["total"]: return None
    out["tech"] = tech
    return out


def parse_detention(rows, fy):
    """A 'Detention' sheet -> {detained: [total, by ICE arrest, by CBP arrest], bookins: {month: {agency: n}}, removals}."""
    out = {}
    for i, r in enumerate(rows):
        c = [cell(v) for v in r]
        if "detained" not in out and c and c[0] == "Criminality" and i + 1 < len(rows) and cell(rows[i + 1][0]) == "Total":
            t = rows[i + 1]; out["detained"] = [int(num(t[5])), int(num(t[1])), int(num(t[3]))]
        if "Agency" in c and "Oct" in c and "bookins" not in out:
            a, o = c.index("Agency"), c.index("Oct"); got = {}
            for r2 in rows[i + 1:i + 4]:
                lab = cell(r2[a]).upper()
                if lab in ("ICE", "CBP"):
                    for k, mname in enumerate(MON3):
                        v = num(r2[o + k]) if o + k < len(r2) else 0
                        y = int("20" + fy[2:]) - (1 if k < 3 else 0)
                        if v: got.setdefault(f"{y}-{['10', '11', '12', '01', '02', '03', '04', '05', '06', '07', '08', '09'][k]}", {})[lab] = int(v)
            out["bookins"] = got
        if "removals" not in out and "Removals" in c:
            k = c.index("Removals"); j = next((x for x in range(k + 1, len(c)) if c[x] == "Total"), None)     # the value sits under the "Total" heading
            for r2 in rows[i + 1:i + 3]:
                if j is not None and len(r2) > j and cell(r2[k]) == "Total" and num(r2[j]): out["removals"] = int(num(r2[j])); break
    return out


def read_summary(data, fy):
    """The ATD and detention summary tables of one workbook (the facility list is read by read_workbook)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    atd, det = [], {}
    for name in wb.sheetnames:
        if re.match(r"\s*ATD", name, re.I):
            a = parse_atd(list(wb[name].iter_rows(values_only=True, max_row=40)))
            if a: atd.append(a)
        elif re.match(r"\s*Detention", name, re.I) and not det: det = parse_detention(list(wb[name].iter_rows(values_only=True, max_row=60)), fy)
    return atd, det


SEMI_GROUPS = [("armed_forces", r"armed forces"), ("parents_usc", r"parents of us"), ("us_citizens", r"united states citizen"), ("tps", r"temporary protected status")]


def parse_semiannual(rows):
    """The 'Semiannual' sheet -> [{group, country, measure, fy, value}]: arrests, book-ins and removals by fiscal year of military
    members and veterans, US citizens, parents of US-citizen children, and people from countries with temporary protected status.
    A blank cell (a country not yet designated that year) is left out, not counted as zero."""
    out, cur = [], None
    for r in rows:
        c = [cell(v) for v in r]
        if not c or not c[0]: continue
        m = re.match(r"(.+?)\s+(arrests|bookins|book-ins|removals)\s+FY\s?\d{4}", c[0], re.I)
        if m and not any(c[1:]):
            g = next((k for k, pat in SEMI_GROUPS if re.search(pat, m.group(1), re.I)), None)
            cur = {"group": g, "measure": {"bookins": "book_ins", "book-ins": "book_ins"}.get(m.group(2).lower(), m.group(2).lower()), "fys": None} if g else None; continue
        if not cur: continue
        if c[0].lower() in ("fiscal year", "citizenship country"):
            cur["fys"] = [re.sub(r"\D", "", x) for x in c[1:]] if c[0].lower() == "citizenship country" else None; continue
        fy = re.fullmatch(r"FY\s?(\d{4})", c[0])
        if fy and cur["group"] != "tps" and len(c) > 1 and c[1] != "":
            out.append({"group": cur["group"], "country": "", "measure": cur["measure"], "fy": int(fy.group(1)), "value": int(num(r[1]))})
        elif cur["group"] == "tps" and cur["fys"] and not fy:
            for y, v in zip(cur["fys"], r[1:]):
                if y and v is not None and cell(v) != "": out.append({"group": "tps", "country": c[0], "measure": cur["measure"], "fy": int(y), "value": int(num(v))})
    return out


def parse_vulnerable(rows):
    """The 'Vulnerable & Special Population' sheet -> [{fy, quarter, reason, placements, avg_consecutive, avg_cumulative, people}]:
    segregation placements by stated reason each quarter. people (unique detainees) is on the Total row only."""
    out, q, tot = [], None, None
    for r in rows:
        c = [cell(v) for v in r]
        if not c or not c[0]: continue
        m = re.match(r"Fiscal Year \(FY\)\s*(\d{4})\s*Quarter\s*(\d)", c[0], re.I)
        if m: q = (int(m.group(1)), int(m.group(2))); tot = None; continue
        if not q or c[0].lower().startswith("placement reason"): continue
        u = re.search(r"represents\s+([\d,]+)\s+unique", c[0], re.I)
        if u and tot is not None: tot["people"] = int(u.group(1).replace(",", "")); q = None; continue
        if len(r) > 3 and isinstance(r[1], (int, float)):
            reason = "Total" if c[0].lower() == "grand total" else re.sub(r"^Medical Mental$", "Medical/Mental Health", re.sub(r"\s+", " ", c[0]))
            row = {"fy": q[0], "quarter": q[1], "reason": reason, "placements": int(r[1]), "avg_consecutive": round(num(r[2]), 1), "avg_cumulative": round(num(r[3]), 1), "people": ""}
            out.append(row)
            if reason == "Total": tot = row
    return out


def parse_bond(rows):
    """'Monthly Bond Statistics' -> [{month, book_outs, bond_posted, avg_bond, alos}]. Months shown as all zeros are left out:
    ICE blanks earlier months to zero in later files, so a zero here means 'not given', not 'none'."""
    months, out = None, {}
    for r in rows:
        if months is None and sum(isinstance(v, (dt.datetime, dt.date)) for v in r) >= 6:
            months = [(v.strftime("%Y-%m") if isinstance(v, (dt.datetime, dt.date)) else None) for v in r]; continue
        if months is None or not r or not cell(r[0]): continue
        lab = cell(r[0]).lower()
        k = "bond_posted" if "bond posted" in lab and "%" not in lab else "book_outs" if lab.startswith("total ice final") else "avg_bond" if "average bond" in lab else "alos" if lab.startswith("alos") else None
        if not k: continue
        for mth, v in zip(months, r):
            if mth: out.setdefault(mth, {"month": mth})[k] = v
    return [{"month": m, "book_outs": int(num(d.get("book_outs"))), "bond_posted": int(num(d.get("bond_posted"))), "avg_bond": round(num(d.get("avg_bond"))), "alos": round(num(d.get("alos")), 1)}
            for m, d in sorted(out.items()) if num(d.get("book_outs")) > 0]


LOS_POP = {"adult facility": "adult", "single adults with a positive fear": "fear_single", "total": "total"}


def parse_length_of_stay(rows):
    """' ICLOS and Detainees' -> [{day, population, alos, d0_180, d181_365, d366_730, d730p}]: average days in custody, and how many
    people had been held each length of time, twice a month (mid and end). Populations always zero (family units) are left out."""
    head = next((i for i, r in enumerate(rows) if r and cell(r[0]).lower().startswith("population") and any(isinstance(v, int) and 2000 < v < 2100 for v in r[1:])), None)
    if head is None: return []
    y0 = next(v for v in rows[head][1:] if isinstance(v, int)); mrow, hrow = rows[head + 1], rows[head + 2]
    cols, y, last = {}, y0, None
    for j in range(1, len(mrow)):
        mn = cell(mrow[j]).lower() or (cols[j - 1][1] if j - 1 in cols else "")
        if mn not in MONTHS: continue
        if last and MONTHS[mn] < MONTHS[last] and cell(mrow[j]): y += 1
        if cell(mrow[j]): last = mn
        half = "mid" if cell(hrow[j] if j < len(hrow) else "").lower().startswith("mid") else "end"
        cols[j] = (f"{y}-{MONTHS[mn]:02d}-" + ("15" if half == "mid" else str(calendar.monthrange(y, MONTHS[mn])[1])), mn)
    data, section, pop = {}, "alos", None
    for r in rows[head + 3:]:
        a = cell(r[0]) if r else ""
        if a.lower() == "detainees": section = "count"; continue
        if not a or a.lower().startswith(("population", "january")) or a.lower() in ("mid", "end"): continue
        key = next((v for k, v in LOS_POP.items() if a.lower().startswith(k)), None)
        if section == "alos" and key:
            for j, (per, _) in cols.items():
                if j < len(r) and isinstance(r[j], (int, float)): data.setdefault((per, key), {})["alos"] = round(r[j], 1)
        elif section == "count":
            if not any(isinstance(v, (int, float)) for v in r[1:]): pop = key; continue          # a population heading; an unknown one (family units, FSC) is skipped
            b = {"0-180 days": "d0_180", "181-365 days": "d181_365", "366-730 days": "d366_730", "more than 730 days": "d730p"}.get(a.lower())
            if b and pop:
                for j, (per, _) in cols.items():
                    if j < len(r) and isinstance(r[j], (int, float)): data.setdefault((per, pop), {})[b] = int(r[j])
    out = []
    for (per, pop), d in sorted(data.items()):
        if not d.get("alos") and not any(d.get(k) for k in ("d0_180", "d181_365", "d366_730", "d730p")): continue
        out.append({"day": per, "population": pop, "alos": d.get("alos", ""), **{k: d.get(k, "") for k in ("d0_180", "d181_365", "d366_730", "d730p")}})
    return out


def merge_newest(old, new, key, fy):
    """Fold one workbook's rows into what is on file. The newer workbook wins, except that a zero in it never replaces a count an
    older workbook gave (ICE's later files show earlier years as 0). Rows kept that way are marked zeroed_in=<the newer file>."""
    have = {tuple(str(r[k]) for k in key): r for r in old}
    for r in new:
        k = tuple(str(r[x]) for x in key); o = have.get(k); r = {**r, "src": fy, "zeroed_in": ""}
        if o is None or o.get("src", "") <= fy and not (num(r.get("value", 1)) == 0 and num(o.get("value", 0)) != 0 and o.get("src", "") < fy): have[k] = r
        elif num(r.get("value", 1)) == 0 and num(o.get("value", 0)) != 0: o["zeroed_in"] = fy
    return list(have.values())


EXTRA = {   # file: (sheet name pattern, parser, key fields, fields)
    "ice_semiannual.csv": (r"semiannual", parse_semiannual, ["group", "country", "measure", "fy"], ["group", "country", "measure", "fy", "value", "src", "zeroed_in"]),
    "ice_segregation_reasons.csv": (r"vulnerable", parse_vulnerable, ["fy", "quarter", "reason"], ["fy", "quarter", "reason", "placements", "avg_consecutive", "avg_cumulative", "people", "src", "zeroed_in"]),
    "ice_bond_monthly.csv": (r"bond", parse_bond, ["month"], ["month", "book_outs", "bond_posted", "avg_bond", "alos", "src", "zeroed_in"]),
    "ice_length_of_stay.csv": (r"iclos", parse_length_of_stay, ["day", "population"], ["day", "population", "alos", "d0_180", "d181_365", "d366_730", "d730p", "src", "zeroed_in"]),
}


def read_extra(data):
    """{file: rows} for the four tables in EXTRA, from one workbook. A sheet that is missing or unreadable gives no rows."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True); out = {}
    for f, (pat, fn, _, _) in EXTRA.items():
        name = next((n for n in wb.sheetnames if re.search(pat, n, re.I)), None)
        if name:
            try: out[f] = fn(list(wb[name].iter_rows(values_only=True)))
            except Exception as e: print(f"    {name}: not read ({e})", flush=True)
    return out


def read_csv(path): return list(csv.DictReader(open(path, encoding="utf-8", newline=""), delimiter="|")) if path.exists() else []


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)


def main():
    sys.path.insert(0, str(Path(__file__).parent)); from icefetch import fetch_bytes
    html = fetch_bytes([PAGE]).get(PAGE, b"").decode("utf-8", "replace")
    books = find_workbooks(html)
    if len(books) < 3: raise SystemExit(f"Found only {len(books)} workbooks on {PAGE}; the page may have changed. Nothing written.")
    seen = {r["fy"]: r for r in read_csv(REF / "detention_stats_files.csv")}
    adp, seg = read_csv(REF / "facility_adp_by_year.csv"), read_csv(REF / "facility_segregation.csv")
    snaps, bk = read_csv(REF / "ice_stats_snapshots.csv"), read_csv(REF / "ice_bookins_by_agency.csv")
    extra = {f: read_csv(REF / f) for f in EXTRA}
    todo = {fy: u for fy, u in books.items() if seen.get(fy, {}).get("url") != u or not any(r["fy"] == fy for r in adp) or not any(r["fy"] == fy for r in snaps)
            or fy >= "FY24" and not any(r.get("src") == fy for r in extra["ice_semiannual.csv"])}      # older workbooks give nothing newer files lack
    print(f"{len(books)} workbooks listed; {len(todo)} new or changed: {', '.join(sorted(todo)) or 'none'}", flush=True)
    got = fetch_bytes(todo.values()); today = str(dt.date.today()); newest = max(books); newest_fac = None
    seg_fy = {}                                                    # month -> (fy it was read from, rows); a later year's workbook wins
    for r in seg: seg_fy.setdefault(r["month"], (r.get("fy", ""), []))[1].append(r)
    for fy in sorted(todo):
        data = got.get(todo[fy])
        if not data: print(f"  {fy}: could not download; kept what was there"); continue
        try: fac, sg = read_workbook(data)
        except Exception as e: print(f"  {fy}: could not read ({e}); kept what was there"); continue
        if len(fac) < 60: print(f"  {fy}: only {len(fac)} facilities, implausible; kept what was there"); continue
        adp = [r for r in adp if r["fy"] != fy] + [{"fy": fy, "name": f["name"], "city": f["city"], "state": f["state"], "type": f["type"], "adp": f["adp"]} for f in fac]
        months = {}
        for m, n, c in sg: months.setdefault(m, []).append({"month": m, "name": n, "placements": c, "fy": fy})
        for m, rows in months.items():
            if m not in seg_fy or seg_fy[m][0] <= fy: seg_fy[m] = (fy, rows)
        seen[fy] = {"fy": fy, "url": todo[fy], "read": today}
        try:
            atd, det = read_summary(data, fy)
            m8 = re.search(r"(\d{2})(\d{2})(\d{4})\.xlsx$", todo[fy]); day = atd[0]["as_of"] if atd else (f"{m8.group(3)}-{m8.group(1)}-{m8.group(2)}" if m8 else today)     # the tables share the ATD report's date; the file name is the posting date
            new = []
            for a in atd:
                new += [{"as_of": a["as_of"], "fy": fy, "measure": "atd_total", "value": a["total"]}, {"as_of": a["as_of"], "fy": fy, "measure": "atd_daily_tech_cost", "value": a["cost"]}]
                new += [{"as_of": a["as_of"], "fy": fy, "measure": "atd_" + re.sub(r"\W+", "_", k.lower()).strip("_"), "value": v} for k, v in a["tech"].items()]
            if det.get("detained"):
                for k, v in zip(("detained_total", "detained_ice_arrest", "detained_cbp_arrest"), det["detained"]): new.append({"as_of": day, "fy": fy, "measure": k, "value": v})
            if det.get("removals"): new.append({"as_of": day, "fy": fy, "measure": "removals_fytd", "value": det["removals"]})
            keys = {(r["as_of"], r["measure"]) for r in new}
            snaps = [r for r in snaps if (r["as_of"], r["measure"]) not in keys] + new
            if det.get("bookins"):
                bk = [r for r in bk if r["fy"] != fy] + [{"month": m, "agency": ag, "book_ins": n, "fy": fy} for m, d in det["bookins"].items() for ag, n in d.items()]
            print(f"  {fy}: {len(atd)} ATD tables, detained {det.get('detained')}, {len(det.get('bookins', {}))} months of book-ins", flush=True)
        except Exception as e: print(f"  {fy}: summary tables not read ({e})", flush=True)
        try:
            for f, rows in read_extra(data).items():
                if rows: extra[f] = merge_newest(extra[f], rows, EXTRA[f][2], fy)
                print(f"    {f}: {len(rows)} rows from {fy}", flush=True)
        except Exception as e: print(f"  {fy}: extra tables not read ({e})", flush=True)
        if fy == newest: newest_fac = fac
        print(f"  {fy}: {len(fac)} facilities, {len(months)} months of segregation counts", flush=True)
    for fy in books:                                               # "read" is the day the link was last checked, changed or not
        if fy in seen and fy not in todo: seen[fy]["read"] = today
    write_csv(REF / "facility_adp_by_year.csv", sorted(adp, key=lambda r: (r["fy"], r["name"], r["state"])), ["fy", "name", "city", "state", "type", "adp"])
    write_csv(REF / "facility_segregation.csv", [r for m in sorted(seg_fy) for r in sorted(seg_fy[m][1], key=lambda r: r["name"])], ["month", "name", "placements", "fy"])
    write_csv(REF / "detention_stats_files.csv", [seen[k] for k in sorted(seen)], ["fy", "url", "read"])
    write_csv(REF / "ice_stats_snapshots.csv", sorted(snaps, key=lambda r: (r["as_of"], r["measure"])), ["as_of", "fy", "measure", "value"])
    for f, (_, _, key, fields) in EXTRA.items():
        if extra[f]: write_csv(REF / f, sorted(extra[f], key=lambda r: tuple(str(r[k]).zfill(6) if str(r[k]).isdigit() else str(r[k]) for k in key)), fields)
    write_csv(REF / "ice_bookins_by_agency.csv", sorted(bk, key=lambda r: (r["month"], r["agency"])), ["month", "agency", "book_ins", "fy"])
    if newest_fac and len(newest_fac) >= 150:
        old = {(r["name"], r["state"]): r.get("facility_code", "").strip() for r in read_csv(REF / "ice_facility_contracts.csv")}
        write_csv(REF / "ice_facility_contracts.csv", [{"name": f["name"], "city": f["city"], "state": f["state"], "type": f["type"], "guaranteed_minimum": f["gm"], "last_inspection": f["insp"],
                                                        "last_rating": f["rating"], "facility_code": old.get((f["name"], f["state"]), "")} for f in newest_fac],
                  ["name", "city", "state", "type", "guaranteed_minimum", "last_inspection", "last_rating", "facility_code"])
        print(f"  contract list rewritten from {newest}: {len(newest_fac)} facilities")
    print(f"{len(adp)} facility-years, {sum(len(v[1]) for v in seg_fy.values())} facility-months of segregation counts ({min(seg_fy, default='-')} to {max(seg_fy, default='-')})")


if __name__ == "__main__": main()
