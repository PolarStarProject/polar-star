"""data/site_data.json + data/flights/legs_*.json -> site/index.html (facility pages and flights in one page)."""
import csv, glob, json, math, os, re, sys, time
import datetime as dt
import urllib.parse
os.environ["TZ"] = "UTC"
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"): _s.reconfigure(errors="replace")      # a Windows console cannot print every character in the build notes
if hasattr(time, "tzset"): time.tzset()   # one clock for every date on the page: GitHub Actions runs in UTC, so the build does too (Windows has no tzset; see utc_today)
from pathlib import Path
from flights import STAGING, km
from money_awards import award_competition
from firm_profiles import core, is_person, on_trail, trail_people, recipient, PERSONAL

ROOT = Path(__file__).parent.parent
NEAR_AIRPORT_KM = 5      # "next to" the airport
CLOSE_AIRPORT_KM = 45    # nearest staging airport worth naming, with its distance
US_TERRITORIES = {"PR", "VI", "GU", "MP", "AS"}
COUNTRY = {"US": "the United States", "MX": "Mexico", "GT": "Guatemala", "HN": "Honduras", "SV": "El Salvador", "CO": "Colombia", "EC": "Ecuador",
           "CU": "Cuba", "DO": "the Dominican Republic", "HT": "Haiti", "BR": "Brazil", "VE": "Venezuela", "NI": "Nicaragua", "PE": "Peru",
           "CR": "Costa Rica", "PA": "Panama", "JM": "Jamaica", "BS": "the Bahamas"}


def join(site, legs, airports):
    """Attach each staging airport to the facilities beside it, and summarise the flights that used it."""
    stage = {c: {"name": STAGING[c].split(",")[0], "place": STAGING[c], "lat": float(airports[c]["latitude_deg"]), "lon": float(airports[c]["longitude_deg"])} for c in STAGING}
    for f in site["facilities"].values():
        f.pop("near", None); f.pop("close", None)
        if "lat" in f:
            c, d = min(((c, km(f["lat"], f["lon"], s["lat"], s["lon"])) for c, s in stage.items()), key=lambda x: x[1])
            if d <= NEAR_AIRPORT_KM: f["near"] = c
            elif d <= CLOSE_AIRPORT_KM: f["close"] = [c, round(d)]
    for l in legs:
        l["via"] = l["basis"].split("day includes ")[1][:3] if "day includes " in l["basis"] else ""      # "" = found from the aircraft, not from a staging airport
    for c, s in stage.items():
        mine = [l for l in legs if (l["origin"] == c and l["origin_certain"]) or (l["dest"] == c and l["dest_certain"])]     # confirmed take-offs from or landings at this airport, the same rule as the flights tab; not every flight of an aircraft that called there that day
        abroad = {}
        for l in mine:                      # only confirmed landings name a country
            for cc, sure in ((l["origin_country"], l["origin_certain"]), (l["dest_country"], l["dest_certain"])):
                if cc != "US" and sure: abroad[cc] = abroad.get(cc, 0) + 1
        s["flights"], s["international"] = len(mine), sum(1 for l in mine if l["kind"] == "international")
        s["countries"] = [COUNTRY.get(k, k) for k, _ in sorted(abroad.items(), key=lambda kv: -kv[1])]
    return stage


STATE_NAMES = {"AL":"ALABAMA","AK":"ALASKA","AZ":"ARIZONA","AR":"ARKANSAS","CA":"CALIFORNIA","CO":"COLORADO","CT":"CONNECTICUT","DE":"DELAWARE","FL":"FLORIDA","GA":"GEORGIA","HI":"HAWAII","ID":"IDAHO","IL":"ILLINOIS","IN":"INDIANA","IA":"IOWA","KS":"KANSAS","KY":"KENTUCKY","LA":"LOUISIANA","ME":"MAINE","MD":"MARYLAND","MA":"MASSACHUSETTS","MI":"MICHIGAN","MN":"MINNESOTA","MS":"MISSISSIPPI","MO":"MISSOURI","MT":"MONTANA","NE":"NEBRASKA","NV":"NEVADA","NH":"NEW HAMPSHIRE","NJ":"NEW JERSEY","NM":"NEW MEXICO","NY":"NEW YORK","NC":"NORTH CAROLINA","ND":"NORTH DAKOTA","OH":"OHIO","OK":"OKLAHOMA","OR":"OREGON","PA":"PENNSYLVANIA","RI":"RHODE ISLAND","SC":"SOUTH CAROLINA","SD":"SOUTH DAKOTA","TN":"TENNESSEE","TX":"TEXAS","UT":"UTAH","VT":"VERMONT","VA":"VIRGINIA","WA":"WASHINGTON","WV":"WEST VIRGINIA","WI":"WISCONSIN","WY":"WYOMING","GU":"GUAM","PR":"PUERTO RICO","MP":"NORTHERN MARIANA ISLANDS"}


def county_key(state_name, county):
    import re
    c = re.sub(r"\b(county|couny|conty|couty|countey|parish|borough|municipality|city and)\b", "", str(county).lower())   # misspellings are ICE's
    c = re.sub(r"\bsaint\b", "st", c)
    return str(state_name).upper().strip(), re.sub(r"[^a-z]", "", c)


STATE_FIX = {"NEW HAMSPHIRE": "NEW HAMPSHIRE"}                     # misspelled in ICE's own sheet


def facility_kind(code, name):
    """A rough grouping from the facility's code and name. ICE's own facility-type field is not in this dataset, so this is
    a reading of the name, not ICE's classification. D dedicated immigration site, J local or state jail or prison,
    F federal prison, H hold room or field office, S staging site, O other (hospitals, hotels, juvenile, unknown)."""
    import re
    n = name.lower()
    if code.endswith("HOLD") or re.search(r"\bhold\b|hold room|field office|sub[- ]?office|\bfo\b", n): return "H"
    if "staging" in n: return "S"
    if code.startswith("BOP") or re.search(r"federal (detention|correctional|medical)|\bfdc\b|\bmdc\b|\bfci\b|penitentiary|marshal", n): return "F"
    if re.search(r"hospital|medical center|health|behavioral|hotel|inn\b|suites|juvenile|children|shelter", n): return "O"
    if re.search(r"\bice\b|processing|service processing|camp east montana|residential|transitional|contract detention", n): return "D"
    if re.search(r"county|parish|city|sheriff|jail|correction|prison|regional|police|dept|department|state", n): return "J"
    if re.search(r"detention (center|facility|complex)", n): return "D"
    return "O"


def tidy_addr(a):
    """The federal list is upper case; title-casing leaves '26Th'."""
    import re
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), a or "")


def _agency_key(s):
    import re
    return re.sub(r"[^a-z]", "", s.lower())


def _near(a, b):
    """True when two agency names differ by at most two letters added, dropped or changed (ICE's list has typos: "Counry", "Pymathuning")."""
    if abs(len(a) - len(b)) > 2: return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1): cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1] <= 2


def ended_agreements(gone, current, abbr):
    """Agreements that were on ICE's list and no longer are -> rows for the page, and how many were left out.
    Left out: one that is on the current list after all (same state, kind and signing date, same name give or take two letters:
    ICE re-listed it or fixed a typo), and a second copy of the same ended agreement under another spelling."""
    code = {"Task Force Model": "T", "Jail Enforcement Model": "J", "Warrant Service Officer": "W"}
    live = {}
    for r in current: live.setdefault((r["state"].upper(), code.get(r["model"], r["model"]), r["signed"]), []).append(_agency_key(r["agency"]))
    out, seen, dropped = [], {}, 0
    for r in gone:
        k = (r["state"].upper(), r["model"], r["signed"]); name = _agency_key(r["agency"])
        if any(_near(name, x) for x in live.get(k, [])) or any(_near(name, x) for x in seen.get(k, [])): dropped += 1; continue
        seen.setdefault(k, []).append(name)
        out.append([abbr.get(r["state"], r["state"]), r["agency"], r["model"], r["signed"], r["last_listed"]])
    return out, dropped


def agreements_index(rows, contacts, centroids, bans, pdfs=(), signers=()):
    """The nationwide list by state, one map point per county, and the states whose law bars these agreements.
    Agency row: [agency, county, kind, signed, phone, address, date the contact was last checked, signed agreement path,
    who]. who is [name, title, "s"] for the agency's signer read from the agreement (moa_signers.py checks), or
    [name, title, "c"] for the agency contact the agreement types out, or "" when neither reads cleanly."""
    pdf = {(p["state"].upper(), p["agency"], p["model"]): p["pdf"] for p in pdfs}
    sig = {}
    for g in signers:
        if g.get("status") == "named" and g.get("name"): sig[g["pdf"]] = [re.sub(r"^(Chief|Sheriff|Constable|Director|Colonel|Marshal|Mayor)\s+", "", g["name"]), g["title"], "s"]
        elif g.get("contact"): sig[g["pdf"]] = [g["contact"], g["contact_title"], "c"]
    code = {"Task Force Model": "T", "Jail Enforcement Model": "J", "Warrant Service Officer": "W"}
    abbr = {v: k for k, v in STATE_NAMES.items()}
    fix = lambda s: STATE_FIX.get(s.upper(), s.upper())
    con = {(fix(c["state"]), c["agency"]): c for c in contacts}
    cen = {}
    for c in sorted(centroids, key=lambda c: c["fips"]):             # same name twice in a state (St. Louis county and city): the county has the lower code
        cen.setdefault(county_key(c["state"], c["county"]), c)
    states, pts, off_map = {}, {}, 0
    for r in rows:
        st = fix(r["state"]); ab = abbr.get(st, st); c = con.get((st, r["agency"]), {})
        states.setdefault(ab, []).append([r["agency"], r["county"].replace(" County", ""), code.get(r["model"], "?"), r["signed"],
                                          c.get("phone", ""), tidy_addr(c.get("address", "")), c.get("checked", "")[:4], pdf.get((r["state"].upper(), r["agency"], r["model"]), ""),
                                          sig.get(pdf.get((r["state"].upper(), r["agency"], r["model"]), ""), "")])
        hit = cen.get(county_key(st, r["county"])) if r["county"] else None
        if hit: p = pts.setdefault(hit["fips"], [float(hit["lat"]), float(hit["lon"]), 0, f'{hit["county"]}, {ab}', ab]); p[2] += 1
        else: off_map += 1
    for v in states.values(): v.sort(key=lambda x: (x[1], x[0]))
    out = {"states": states, "total": len(rows), "sheet": rows[0]["source_sheet"].split("_")[1][:8] if rows else "",
           "points": sorted(pts.values(), key=lambda p: -p[2]), "off_map": off_map, "phones": sum(1 for v in states.values() for a in v if a[4]),
           "signers": sum(1 for v in states.values() for a in v if a[8] and a[8][2] == "s"), "contacts": sum(1 for v in states.values() for a in v if a[8] and a[8][2] == "c"),
           "bans": {b["state"]: b["source"] for b in bans}}
    mp = Path(__file__).resolve().parent.parent / "data" / "reference" / "287g_agreements_meta.json"
    if mp.exists(): out["moa"] = json.loads(mp.read_text(encoding="utf-8")).get("commit", "")
    return out, f'{len(pts)} counties on the agreements map, {off_map} agencies not placed; {out["phones"]} agencies with a phone number'


def attach_agency_phones(site, rows, contacts):
    con = {(STATE_FIX.get(c["state"].upper(), c["state"].upper()), c["agency"]): c.get("phone", "") for c in contacts}
    for f in site["facilities"].values():
        if f.get("agreements") and f.get("state") in STATE_NAMES:
            for a in f["agreements"]["list"]:
                del a[2:]; a.append(con.get((STATE_NAMES[f["state"]], a[0]), ""))


def attach_287g(site, rows):
    """Local agencies in the facility's county that have signed an agreement to do immigration enforcement for ICE."""
    by = {}
    for r in rows:
        if r["county"]: by.setdefault(county_key(r["state"], r["county"]), []).append(r)
    n = 0
    for f in site["facilities"].values():
        f.pop("agreements", None)
        if not f.get("county") or f.get("state") not in STATE_NAMES: continue
        hit = by.get(county_key(STATE_NAMES[f["state"]], f["county"]))
        if hit:
            hit = sorted(hit, key=lambda r: r["agency"])
            f["agreements"] = {"n": len(hit), "list": [[r["agency"], r["model"]] for r in hit[:6]]}; n += 1
    return n


def operator_on(site):
    """Returns at(code, date=None) -> the group a site's records belong to on that date: the company that ran it then, "PUB" for
    a government, "OTH" for a site not on ICE's list. facility_operator_history.csv (by hand) holds earlier operators with the
    last day each ran the site; a date after all of them, or no date, gives today's operator. A month ("YYYY-MM") is judged
    by its 15th day. ASSUMPTION: a site with no history row was run by today's operator on every date."""
    ops, hist = site.get("operators", {}), site.get("op_history", {})
    listed = {c[7] for c in site.get("contracts", []) if c[7]}
    def at(code, date=None):
        if code not in listed: return "OTH"
        if date:
            d = date[:10] if len(date) >= 10 else date[:7] + "-15"
            for p in hist.get(code, []):                              # oldest first
                if d <= p[2]: return p[0]
        return ops.get(code, ["PUB"])[0]
    return at


def load_operator_history(site, rows):
    """Earlier operators of a site -> site["op_history"] = {code: [[operator, from, to, url, sure], ...]} oldest first. Refuses bad rows."""
    import datetime as _dt
    out = {}
    for r in rows:
        c = r["facility_code"]
        if c not in site["facilities"]: raise ValueError(f"facility_operator_history.csv: unknown facility code {c}")
        _dt.date.fromisoformat(r["to"]); r["from"] and _dt.date.fromisoformat(r["from"])
        if r["from"] > r["to"] or not r["url"].startswith("http") or not r["operator"]: raise ValueError(f"facility_operator_history.csv: bad row for {c}")
        if r["operator"] == site.get("operators", {}).get(c, ["PUB"])[0]: raise ValueError(f"facility_operator_history.csv: {c} lists today's operator as an earlier one")
        out.setdefault(c, []).append([r["operator"], r["from"], r["to"], r["url"], r["sure"]])
    for c, ps in out.items():
        ps.sort(key=lambda p: p[2])
        for a, b in zip(ps, ps[1:]):
            if not b[1] or b[1] <= a[2]: raise ValueError(f"facility_operator_history.csv: periods overlap for {c}")
    site["op_history"] = out
    return len(out)


def bed_use(site, hist):
    """Guaranteed beds against people actually held. For every site where ICE's facility list gives a guaranteed minimum (beds
    ICE pays for whether or not they are filled), compares it with ICE's own average daily population for the newest fiscal
    year in the same file. Returns {"fy", "n", "beds", "below": [[code, guaranteed, average, empty]], "empty"} or None.
    No dollar figure: the daily price of a bed is not in any file here. The yearly average covers the whole fiscal year to
    date, so a site that opened, or whose guarantee began, part-way through looks emptier than it now is."""
    fys = sorted({fy for v in hist.values() for fy in v})
    if not fys: return None
    fy, rows = fys[-1], []
    for c in site.get("contracts", []):
        code, gm = c[7], c[4]
        if not code or not gm or fy not in hist.get(code, {}): continue
        rows.append([code, gm, round(hist[code][fy])])
    below = sorted(([c, gm, a, gm - a] for c, gm, a in rows if a < gm), key=lambda r: -r[3])
    return {"fy": fy, "n": len(rows), "beds": sum(r[1] for r in rows), "below": below, "empty": sum(r[3] for r in below), "counted": sorted(r[0] for r in rows)}


def bed_revenue(site, rows):
    """What a company has told investors it expects a site to bring in each year (facility_bed_revenue.csv, read by hand from
    the filing or announcement named in each row), and that figure spread evenly over the company's own bed count and 365 days.
    The result is this page's arithmetic, not a contract price: no contract's daily rate is public. Returns
    {code: [musd, at_least, beds, per_bed_day, payment, company, doc, doc_date, url, sold, sold_url, max_musd, max_per_bed_day]}. No total is ever made."""
    out = {}
    for r in rows:
        c = r["facility_code"]; musd, beds = float(r["annual_musd"]), int(r["beds"])
        if c not in site["facilities"]: raise ValueError(f"facility_bed_revenue.csv: unknown facility code {c}")
        if c in out: raise ValueError(f"facility_bed_revenue.csv: {c} listed twice")
        if not (0 < musd < 2000 and 50 <= beds <= 10000): raise ValueError(f"facility_bed_revenue.csv: {c} figures out of range (millions of dollars a year, beds)")
        if r["payment"] not in ("", "fixed", "mixed") or r["doc"] not in ("annual", "release") or r["at_least"] not in ("0", "1"): raise ValueError(f"facility_bed_revenue.csv: bad code in row for {c}")
        if not r["url"].startswith("https://") or (r["sold"] and not r["sold_url"].startswith("https://")): raise ValueError(f"facility_bed_revenue.csv: {c} needs a source link")
        mx = float(r["annual_max_musd"]) if r.get("annual_max_musd") else None          # a range the company gave ("$30 million to $35 million"): the top of it
        if mx is not None and (mx <= musd or r["at_least"] == "1"): raise ValueError(f"facility_bed_revenue.csv: {c} range must rise, and cannot also be 'at least'")
        out[c] = [musd, int(r["at_least"]), beds, round(musd * 1e6 / beds / 365), r["payment"], r["company"], r["doc"], r["doc_date"], r["url"], r["sold"], r["sold_url"], mx, round(mx * 1e6 / beds / 365) if mx else None]
    return out


def awards_by_recipient(rows, meta):
    """ICE contracts of $1 million or more, grouped under each recipient's name (ice_awards.csv from money_awards.py).
    Returns {"meta", "by": {NAME: [[award_id, musd, start, end, type, what, uid, window_musd, competed, offers, reason, extent]]}}; musd is MILLIONS to one decimal, converted
    here from the file's whole dollars. It is the amount over the award's whole life, not the page's three-year window, so the
    page never adds these to a company's window total. window_musd is the part committed inside the window (None when not read);
    competed is "C", "N" or ""; offers is the recorded number of offers (None = not recorded, which is not zero);
    reason and extent are the source's own words and code. Rejects a file that does not match its own meta."""
    by, n = {}, 0
    for r in rows:
        amt = int(r["amount_usd"])
        if amt < int(meta["floor_usd"]) or not r["uid"] or not r["recipient"]: raise ValueError(f"ice_awards.csv: bad row {r.get('award_id')}")
        win = r.get("window_usd") or ""                 # blank = that award's detail was not read; never shown as zero
        by.setdefault(r["recipient"].upper(), []).append([r["award_id"], round(amt / 1e6, 1), r["start"], r["end"], r["type"], r["what"], r["uid"], round(int(win) / 1e6, 1) if win != "" else None, award_competition(r.get("competed") or "", r.get("reason")), int(r["offers"]) if (r.get("offers") or "") != "" else None, r.get("reason") or "", r.get("extent") or ""]); n += 1
    if n != int(meta["awards"]): raise ValueError(f"ice_awards.csv has {n} rows, its meta says {meta['awards']}")
    for v in by.values(): v.sort(key=lambda a: -a[1])
    return {"meta": {k: meta[k] for k in ("from", "to", "read", "floor_usd", "awards", "recipients")}, "by": by}


def headline(site):
    """The page's headline counts as {key: number}, for the record of what changed between updates. A key is left out when its
    data is missing, so a missing file is never recorded as a fall to zero."""
    h = {}
    if site.get("custody"): h["held"] = site["custody"][-1][1]
    if site.get("deaths"): h["deaths"] = sum(n for _, n in site["deaths"]["years"])
    if site.get("a287"): h["agreements"] = site["a287"]["total"]
    if site.get("money", {}).get("total"): h["contract_musd"] = site["money"]["total"]
    if site.get("contracts"): h["facilities"] = len(site["contracts"])
    alleg = sum(a[1] or 0 for f in site.get("facilities", {}).values() for a in f.get("prea", [])) + sum(a[2] or 0 for a in site.get("prea_unplaced", []))
    if alleg: h["allegations"] = alleg
    if site.get("denied"): h["refusals"] = len(site["denied"])
    insp = sum(len(f.get("inspections", [])) for f in site.get("facilities", {}).values())
    if insp: h["inspections"] = insp
    return h


def record_changes(history, today, now):
    """Adds today's headline counts to the history ([{"date", "v"}], oldest first; one entry per day, a day with nothing changed
    adds nothing) and returns (history, changes). changes = {"date", "since", "rows": [[key, before, after]]} for the newest entry
    against the one before it, only keys present in both and different; None when there is no earlier entry."""
    history = [e for e in history if e["date"] != today]
    if not history or history[-1]["v"] != now: history.append({"date": today, "v": now})
    if len(history) < 2: return history, None
    a, b = history[-2], history[-1]
    return history, {"date": b["date"], "since": a["date"], "rows": [[k, a["v"][k], b["v"][k]] for k in b["v"] if k in a["v"] and a["v"][k] != b["v"][k]]}


def facility_awards(site, rows):
    """Guard-service contracts (product code S206, the code used for running detention sites) placed at a facility by where the
    work is performed. A contract is attached only when exactly ONE facility on ICE's own list is in that city and state; a
    city with two or more listed facilities gets none, because the award does not say which. This is a match by place, not a
    statement by the source that the contract is for that facility, and the page says so.
    Returns ({code: [[recipient, award_id, life_musd, window_musd, start, end, competed, uid]]}, {"guard", "placed", "shared", "nowhere"})."""
    listed = {c[7] for c in site.get("contracts", []) if c[7]}; at = {}
    for code in listed:
        f = site["facilities"][code]; at.setdefault(((f.get("city") or "").strip().upper(), (f.get("state") or "").strip().upper()), []).append(code)
    out, n = {}, {"guard": 0, "placed": 0, "shared": 0, "nowhere": 0}
    for r in rows:
        if (r.get("psc") or "") != "S206": continue
        n["guard"] += 1; codes = at.get(((r.get("pop_city") or "").strip().upper(), (r.get("pop_state") or "").strip().upper()))
        if not codes or not codes[0]: n["nowhere"] += 1; continue
        if len(codes) > 1: n["shared"] += 1; continue
        win = r.get("window_usd") or ""; n["placed"] += 1
        out.setdefault(codes[0], []).append([r["recipient"], r["award_id"], round(int(r["amount_usd"]) / 1e6, 1), round(int(win) / 1e6, 1) if win != "" else None, r["start"], r["end"], award_competition(r.get("competed") or "", r.get("reason")), r["uid"]])
    for v in out.values(): v.sort(key=lambda a: -(a[3] if a[3] is not None else a[2]))
    return out, n


def leg_kind(origin_country, dest_country):
    """"domestic" when both ends are in the US, "international" when exactly one is (the flight left or entered the US),
    "abroad" when neither is (for example a removal flight's next hop between two airports in Mexico). Territories are
    already "US" by this point. Only "international" may be counted or labelled as leaving or entering the country."""
    us = (origin_country == "US") + (dest_country == "US")
    return "domestic" if us == 2 else "international" if us == 1 else "abroad"


NAME_FIXES = [(r"\bBakerfield\b", "Bakersfield"), (r"\bSaipain\b", "Saipan"), (r"\bCorecivic\b", "CoreCivic"), (r"\bLA Palma\b", "La Palma"), (r"\bMcfarland\b", "McFarland"),
              (r"\(Nwipc\)", "(NWIPC)"), (r"\bMccook\b", "McCook"), (r"\bMcallen\b", "McAllen"), (r"\bMchenry\b", "McHenry"), (r"\bDekalb\b", "DeKalb"), (r"\(McF\)", "(MCF)")]


def fix_name(nm):
    """A facility name with known spelling slips from ICE's lists corrected (Bakerfield, Saipain, Corecivic...). Display only."""
    for a, b in NAME_FIXES: nm = re.sub(a, b, nm)
    m = re.match(r"^(.*\S)\s*\(([^()]*)\)$", nm); key = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    if m and key(m.group(2)) and key(m.group(2)) == key(m.group(1)): nm = m.group(1)            # "Federal Detention Center, Honolulu (Federal Detention Center Honolulu)"
    return re.sub(r",\s*[A-Z]{2}$", "", nm)                                                    # a trailing state code repeats the state shown beside the name


def conduct_rates(site, pdays, min_avg=50, history=None):
    """Sexual-abuse allegations and deaths set against days of detention served, grouped by who runs the site.
    pdays: {facility_code: {"YYYY-MM": person_days}} from pipeline/person_days.py. Counts only, never a person.

    An audit is used for a rate only if ICE's report states a total (not a floor) AND states the period that total
    covers (period_start, period_end in prea_audits.csv, read from each report), and that whole period is inside the
    day counts, and the site held an average of at least min_avg people over it. Periods run from one to three years,
    so nothing is assumed. Days in a part-month are taken in proportion. Deaths are counted from the first month in the day counts."""
    import calendar, datetime as _dt
    months = sorted({m for v in pdays.values() for m in v})
    if not months: return None
    first, last = months[0], months[-1]
    def older(code, ym):
        """Days for a month before the day counts begin, from ICE's yearly average for that facility. None if ICE lists no figure."""
        y, m = int(ym[:4]), int(ym[5:7]); v = (history or {}).get(code, {}).get(f"FY{(y + (m >= 10)) % 100:02d}")
        return None if v is None else v * calendar.monthrange(y, m)[1]
    def span(a, b):
        """[(month, share of that month inside a..b)], and the number of days from a to b inclusive."""
        a, b = _dt.date.fromisoformat(a), _dt.date.fromisoformat(b); out = []; y, m = a.year, a.month
        while (y, m) <= (b.year, b.month):
            n = calendar.monthrange(y, m)[1]; lo = a.day if (y, m) == (a.year, a.month) else 1; hi = b.day if (y, m) == (b.year, b.month) else n
            out.append((f"{y}-{m:02d}", (hi - lo + 1) / n)); y, m = (y, m + 1) if m < 12 else (y + 1, 1)
        return out, (b - a).days + 1
    listed = {c[7] for c in site.get("contracts", []) if c[7]}; at = operator_on(site)
    G, sites, flags, skipped = {}, [], {}, {"no_period": 0, "outside": 0, "small": 0, "changed": 0}
    tot_a = tot_d = 0
    grp = lambda k: G.setdefault(k, {"n": 0, "aud": 0, "alleg": 0, "adays": 0, "sub_aud": 0, "sub": 0, "dead": 0, "days": 0})
    for code in sorted(listed):
        f = site["facilities"][code]; days = pdays.get(code, {})
        grp(at(code))["n"] += 1                               # a site is counted under today's operator; its days and events go to whoever ran it then
        for m, v in days.items(): grp(at(code, m))["days"] += v
        dead = 0
        for d in f.get("death_reports", []):
            if first <= d[0][:7] <= last: dead += 1; grp(at(code, d[0]))["dead"] += 1
        best = None
        for a in f.get("prea", []):
            if a[2] != "S" or a[1] is None: continue
            if not a[5]: skipped["no_period"] += a[0][:7] >= span(first + "-01", first + "-01")[0][0][0] and a[0][:4] + a[0][4:7] >= f"{int(first[:4]) + 1}{first[4:]}"; continue
            if a[6][:7] > last: continue
            win, plen = span(a[5], a[6]); parts = [(days.get(m, 0) if m >= first else older(code, m), w) for m, w in win]
            if any(v is None for v, _ in parts): skipped["outside"] += a[6][:7] >= first; continue
            d = sum(v * w for v, w in parts)
            if d < min_avg * plen: skipped["small"] += 1; continue
            ka, kb = at(code, a[5]), at(code, a[6]); tot_a += a[1]; tot_d += d
            if ka == kb:
                g = grp(ka); g["aud"] += 1; g["alleg"] += a[1]; g["adays"] += d
                if a[3] is not None: g["sub_aud"] += 1; g["sub"] += a[3]
            else: skipped["changed"] += 1                     # the operator changed inside the audit's period: kept in the site list, left out of both operators' rates
            row = [code, a[0], a[1], round(d / plen), round(a[1] / d * 365000, 1), a[4], round(plen / 30.44), a[5][:7] < first, ka if ka == kb else "CHG"]; sites.append(row)
            if best is None: best = row                       # audits are newest first
        flags[code] = [best, dead, len(f.get("watchdog", [])), sum(1 for v in f.get("visits", []) if v[2] == "denied"), (f.get("contract") or [None] * 4)[3] == "Fail"]
    overall = tot_a / tot_d * 365000 if tot_d else 0
    over = []
    for code, (best, dead, wd, den, fail) in flags.items():
        high = bool(best and best[4] >= 2 * overall)
        if high + bool(dead) + bool(wd) + bool(den) + fail >= 3: over.append([code, best[4] if high else None, dead, wd, den, fail])
    over.sort(key=lambda r: -(bool(r[1]) + bool(r[2]) + bool(r[3]) + bool(r[4]) + r[5]))
    years = {}
    for f in site["facilities"].values():
        for a in f.get("prea", []):
            if a[2] == "S" and a[1] is not None: y = years.setdefault(a[0][:4], [0, 0]); y[0] += 1; y[1] += a[1]
    return {"first": first, "last": last, "overall": round(overall, 1), "ops": {k: [g[x] for x in ("n", "aud", "alleg", "adays", "sub_aud", "sub", "dead", "days")] for k, g in G.items()},
            "sites": sorted(sites, key=lambda r: -r[4])[:15], "audits_used": len(sites), "skipped": skipped, "audit_sites": len({r[0] for r in sites}), "overlap": over, "years": sorted([y, *v] for y, v in years.items())}


def attach_prea(site, rows):
    """Sexual-abuse allegations as counted in ICE's own PREA audit reports. Counts only, never a person.
    basis: S = the report states a total; F = only the files the auditor reviewed (a floor); N = not stated."""
    for f in site["facilities"].values(): f.pop("prea", None)
    n = 0
    words = {c: _name_words(f["name"]) for c, f in site["facilities"].items()}
    for r in sorted(rows, key=lambda r: r["audit_start"], reverse=True):
        if not r["facility_code"]:                                   # a row the collector added: place it only if exactly one facility fits the name
            a = _name_words(r["facility_as_reported"]); hits = [c for c, w in words.items() if a and w and len(a & w) / len(a | w) >= 0.8]
            if len(hits) == 1: r["facility_code"] = hits[0]
        f = site["facilities"].get(r["facility_code"])
        if not f: continue
        b = {"stated": "S", "files reviewed": "F", "not stated": "N", "unread": "U"}[r["basis"]]      # unread: found by pipeline/prea_audits.py, count not yet read by a person
        if (b in "NU") != (r["allegations"] == ""): raise ValueError(f"prea_audits.csv: count and basis disagree for {r['facility_code']}")
        f.setdefault("prea", []).append([r["audit_start"], int(r["allegations"]) if r["allegations"] != "" else None, b,
                                         int(r["substantiated"]) if r["substantiated"] != "" else None, r["report_url"],
                                         r.get("period_start") or None, r.get("period_end") or None]); n += 1
        if (r.get("period_start") or "") > (r.get("period_end") or "") or bool(r.get("period_start")) != bool(r.get("period_end")): raise ValueError(f"prea_audits.csv: bad review period for {r['facility_code']} {r['audit_start']}")
    return n


def _name_words(s):
    import re
    s = re.sub(r"\(.*?\)|[.,'/-]", " ", s.upper().replace("&", " AND "))
    for a, b in (("CTR", "CENTER"), ("CORR", "CORRECTIONAL"), ("DET", "DETENTION"), ("CO", "COUNTY"), ("FED", "FEDERAL"), ("INST", "INSTITUTION"),
                 ("STE", "SAINTE"), ("ST", "SAINT"), ("FT", "FORT"), ("DEPT", "DEPARTMENT")):
        s = re.sub(r"\b" + a + r"\b", b, s)
    return set(w for w in s.split() if w not in ("THE", "OF", "ICE"))


def name_matcher(site):
    """Returns match(name, city, state) -> facility code or "". Same rule as the contract list: same state, and either nearly
    all name words shared, or the same city and a third of them. Anything weaker is left unmatched rather than guessed."""
    by, memo, alias = {}, {}, site.get("_aliases", {})
    for c, f in site["facilities"].items(): by.setdefault(f.get("state"), []).append((c, f, _name_words(f["name"]), _name_words(f.get("city") or "")))
    def match(name, city, state):
        k = (name, city, state)
        if name in alias: return alias[name]
        if k not in memo:
            a, ac, best = _name_words(name), _name_words(city or ""), None
            for c, f, b, bc in by.get(state, []):
                if not a or not b: continue
                j = len(a & b) / len(a | b); same = bool(ac) and ac == bc
                if not best or (j + (0.3 if same else 0)) > best[0]: best = (j + (0.3 if same else 0), c, j, same)
            memo[k] = best[1] if best and (best[2] >= 0.8 or (best[3] and best[2] >= 0.34)) else ""
        return memo[k]
    return match


def population_history(site, rows):
    """ICE's yearly average population per facility -> {code: {"FY19": people held on an average day}}. Names ICE uses for one
    site in one year (for example a main building and an annex that share a code here) are added together."""
    match, out, missed = name_matcher(site), {}, 0
    for r in rows:
        c = match(r["name"], r["city"], r["state"])
        if not c: missed += float(r["adp"]); continue
        out.setdefault(c, {}); out[c][r["fy"]] = round(out[c].get(r["fy"], 0) + float(r["adp"]), 1)
    return out, round(missed)


def segregation_rates(site, rows, pdays, min_avg=50):
    """Placements into segregation (solitary confinement) as ICE reports them each month, against days of detention served.
    rows: month, name, placements. The sheet gives no city or state, so a name is matched only if exactly one facility in
    the whole country fits it; the rest are counted as unmatched, never guessed.
    ASSUMPTION: ICE lists a site in a month only when it had a placement, so a site missing from a month had none."""
    words = {c: _name_words(f["name"]) for c, f in site["facilities"].items()}
    memo = dict(site.get("_aliases", {}))
    def find(name):
        if name not in memo:
            a = _name_words(name); hits = [c for c, b in words.items() if a and b and len(a & b) / len(a | b) >= 0.8]
            memo[name] = hits[0] if len(hits) == 1 else ""
        return memo[name]
    at = operator_on(site)
    per, months, unmatched, total, G = {}, {}, 0, 0, {}
    for r in rows:
        n = int(r["placements"]); total += n; months[r["month"]] = months.get(r["month"], 0) + n
        c = find(r["name"]); d = pdays.get(c, {}).get(r["month"], 0) if c else 0
        if not c or not d: unmatched += n; continue
        per.setdefault(c, [0, 0, 0])[0] += n; G.setdefault(at(c, r["month"]), [0, 0, 0])[0] += n     # to whoever ran the site that month
    for c, x in per.items():                                     # a month a site is not listed is a month with no placements: its days still count
        mine = [m for m in months if pdays[c].get(m)]; x[1], x[2] = sum(pdays[c][m] for m in mine), len(mine)
        for m in mine: G.setdefault(at(c, m), [0, 0, 0])[1] += pdays[c][m]
        G.setdefault(at(c), [0, 0, 0])[2] += 1
    sites = sorted(([c, n, round(d / (30.44 * m)), round(n / d * 36500, 1), m] for c, (n, d, m) in per.items() if d / (30.44 * m) >= min_avg and m >= 6), key=lambda r: -r[3])
    ms = sorted(months)
    every = [str(p) for p in __import__("pandas").period_range(ms[0], ms[-1], freq="M")]
    return {"from": ms[0], "to": ms[-1], "missing": [m for m in every if m not in months], "months": [[m, months[m]] for m in ms], "ops": G, "sites": sites[:15], "total": total, "unmatched": unmatched,
            "overall": round(sum(g[0] for g in G.values()) / max(1, sum(g[1] for g in G.values())) * 36500, 1)}


def _insp_date(s):
    """ICE's inspection dates ("Dec. 10-12, 2024", "Sept. 30-Oct. 2, 2025") -> the first day as YYYY-MM-DD, or None if it cannot be read."""
    import re
    m = re.match(r"\s*([A-Za-z]{3})[a-z]*[.,]?\s+(\d{1,2})", s or ""); y = re.findall(r"\b(20\d\d)\b", s or "") or ["20" + x for x in re.findall(r",\s*(\d\d)\s*$", s or "")]
    mon = "jan feb mar apr may jun jul aug sep oct nov dec".split()
    if not m or not y or m.group(1).lower() not in mon: return None
    mi = mon.index(m.group(1).lower()) + 1; yr = int(y[-1])
    if len(y) == 1 and mi == 12 and re.search(r"Jan", s): yr -= 1          # "Dec. 30-Jan. 2, 2025" begins the year before
    return f"{yr}-{mi:02d}-{int(m.group(2)):02d}"


def inspection_findings(site, rows):
    """Deficiencies ICE's inspectors cited in each inspection report (pipeline/inspection_findings.py), put on each facility's
    inspection and added up by who runs the site. A report that could not be read is counted as unread, never as zero."""
    by = {r["url"]: r for r in rows}; at = operator_on(site)
    G, std, sites, unread, read = {}, {}, [], 0, 0
    for c, f in site["facilities"].items():
        for i in f.get("inspections", []):
            r = by.get(i[2]); del i[3:]; iso = _insp_date(i[1])    # i becomes [year, dates as ICE wrote them, url, deficiencies, first day]
            if not r: i += [None, iso]; continue
            if r["read"] == "unreadable": i += [None, iso]; unread += 1; continue
            n = int(r["deficiencies"]); stated = int(r["stated"]) if r["stated"] != "" else None
            n = stated if stated is not None else n; i += [n, iso]; read += 1     # the report's own total when it could be read, else the citations found
            k = at(c, iso); g = G.setdefault(k, [0, 0]); g[0] += 1; g[1] += n      # whoever ran the site when the inspection began
            for part in filter(None, r["standards"].split(";")):
                a, b = part.split(":"); std[a] = std.get(a, 0) + int(b)
            sites.append([c, i[1], n, i[2], k])
    return {"read": read, "unread": unread, "ops": G, "standards": sorted(std.items(), key=lambda kv: -kv[1])[:12], "sites": sorted(sites, key=lambda r: -r[2])[:15]}


def held_summary(site, prof):
    """Who is held now (pipeline/held_profile.py) put on each facility, plus long detention added up by who runs the site.
    Group figures are rebuilt from rounded percentages, so they are approximate; a suppressed share counts as zero."""
    for f in site["facilities"].values(): f.pop("held", None)
    at, G, sites = operator_on(site), {}, []
    for c, h in prof["facilities"].items():
        f = site["facilities"].get(c)
        if not f: continue
        f["held"] = [h["n"], h["women"], h["over180"], h["over365"], h["median_days"], h["countries"], h["ages"]]
        k = at(c, prof["as_of"]); g = G.setdefault(k, [0, 0, 0]); g[0] += h["n"]; g[1] += h["n"] * (h["over180"] or 0) / 100; g[2] += h["n"] * (h["over365"] or 0) / 100
        if h["n"] >= 100 and h["over365"] is not None: sites.append([c, h["n"], h["over180"], h["over365"]])
    nat = prof["national"]
    return {"as_of": prof["as_of"], "n": nat["n"], "women": nat["women"], "over180": nat["over180"], "over365": nat["over365"], "median_days": nat["median_days"], "countries": nat["countries"], "ages": nat["ages"],
            "min_site": prof["min_site"], "deaths": prof.get("deaths"), "ops": {k: [g[0], round(g[1]), round(g[2])] for k, g in G.items()}, "sites": sorted(sites, key=lambda r: (-r[3], -r[2]))[:15]}


def court_summary(site, rows, cross, meta, min_n=20):
    """Immigration court results by hearing location (pipeline/court_outcomes.py) put on facilities and added up by who runs the site.
    A hearing location is tied to a facility by court_location_facility.csv (by hand), else only if exactly one facility fits its name.
    Several dockets at one site are added together. Locations that serve many jails (for example "Chicago Detained") stay untied."""
    K = ["bond_n", "granted", "denied", "no_jurisdiction", "withdrawn", "cases_n", "removed", "voluntary", "relief", "ended_other", "represented"]
    words = {c: _name_words(f["name"]) for c, f in site["facilities"].items()}
    bad = sorted(set(cross.values()) - set(site["facilities"]))
    if bad: raise ValueError(f"court_location_facility.csv names facility codes that do not exist: {bad}")
    per, nat, tied = {}, [0] * len(K), 0
    for r in rows:
        v = [int(r[k]) for k in K]; nat = [a + b for a, b in zip(nat, v)]
        c = cross.get(r["code"])
        if not c:
            a = _name_words(r["name"]); hits = [x for x, w in words.items() if a and w and len(a & w) / len(a | w) >= 0.8]
            c = hits[0] if len(hits) == 1 else ""
        if not c: continue
        tied += v[0] + v[5]; per[c] = [a + b for a, b in zip(per.get(c, [0] * len(K)), v)]
    for f in site["facilities"].values(): f.pop("court", None)
    at, G, sites = operator_on(site), {}, []
    for c, v in per.items():
        if v[0] < min_n and v[5] < min_n: continue
        site["facilities"][c]["court"] = v
        k = at(c, meta["from"])                              # the court file gives one total per place for the whole period, so a site whose
        if k != at(c, meta["to"]): k = "CHG"                 # operator changed inside it is kept out of every operator's total
        G[k] = [a + b for a, b in zip(G.get(k, [0] * len(K)), v)]
        decided = v[1] + v[2]
        if decided >= 100: sites.append([c, v[0], round(100 * v[1] / decided), round(100 * v[3] / v[0]), round(100 * v[10] / v[5]) if v[5] else None])
    return {"from": meta["from"], "to": meta["to"], "nat": nat, "ops": G, "tied": tied, "all": nat[0] + nat[5],
            "low": sorted(sites, key=lambda r: r[2])[:12], "high": sorted(sites, key=lambda r: -r[2])[:6]}


def match_contracts(site, rows, officials=None):
    """ICE's own facility list (contract type, guaranteed minimum, last inspection rating) matched to facilities here.
    A row's facility_code, when filled in by hand, wins. Otherwise: same state, and either nearly all name words shared, or the
    same city and a third of them. Anything weaker is left unmatched rather than guessed. Returns rows for the page:
    [name, city, state, type, guaranteed minimum, last inspection, last rating, code]."""
    import re
    by = {}
    for c, f in site["facilities"].items(): by.setdefault(f.get("state"), []).append((c, f))
    out = []
    for r in rows:
        code = (r.get("facility_code") or "").strip()
        if code and code not in site["facilities"]: raise ValueError(f"ice_facility_contracts.csv: unknown facility_code {code}")
        if not code:
            a, best = _name_words(r["name"]), None
            for c, f in by.get(r["state"], []):
                b = _name_words(f["name"]); j = len(a & b) / len(a | b); city = _name_words(f.get("city") or "") == _name_words(r["city"])
                if not best or (j + (0.3 if city else 0)) > best[0]: best = (j + (0.3 if city else 0), c, j, city)
            if best and (best[2] >= 0.8 or (best[3] and best[2] >= 0.34)): code = best[1]
        gm = r["guaranteed_minimum"]
        nm = re.sub(r"\b(Ice|Ipc|Spc|Mdc|Fci|Fdc|Clipc|Cca|Ero|Ssm|Tgk|Us|Iah|Mt|In|Ny|Fl|Mo|Ne)\b", lambda m: m.group(1).upper(), r["name"].title()).replace("'S", "'s")
        out.append([nm, r["city"].title(), r["state"], r["type"], int(gm) if gm else None, r["last_inspection"], r["last_rating"], code])
        if code: site["facilities"][code]["contract"] = [r["type"], int(gm) if gm else None, r["last_inspection"], r["last_rating"]]
        o = (officials or {}).get((r["name"], r["state"]))
        if code and o: site["facilities"][code]["runby"] = o
    return out


def airports_used(legs, airports):
    """Every airport where a kept flight was seen taking off or landing, over all days. Only ends the positions confirm
    (close to the airport and low) are counted; an end where the signal was lost in the air names no airport.
    Returns ([code, town, country, state or '', take-offs, landings, lat, lon] busiest first, ends confirmed, ends lost)."""
    n, lost = {}, 0
    for l in legs:
        for i, k in enumerate(("origin", "dest")):
            if l[k + "_certain"]: n.setdefault(l[k], [0, 0])[i] += 1
            else: lost += 1
    rows = [[c, airports[c]["municipality"], airports[c]["iso_country"], airports[c]["iso_region"].split("-")[1] if airports[c]["iso_country"] == "US" else "", v[0], v[1], round(float(airports[c]["latitude_deg"]), 2), round(float(airports[c]["longitude_deg"]), 2)]
            for c, v in n.items()]
    return sorted(rows, key=lambda r: (-(r[4] + r[5]), r[0])), sum(r[4] + r[5] for r in rows), lost


def money_extras(site, rd):
    """Year-by-year spending, how contracts were awarded, lobbying by quarter and by issue, and when political money was given.
    Each part is optional: a missing or inconsistent file leaves that part off the page, never a wrong figure on it."""
    M = site["money"]; total = M["total"]
    yr = rd("ice_spending_by_year.csv")
    if yr:
        fys = [int(k[2:]) for k in yr[0] if k.startswith("fy")]; val = lambda r: [int(r[f"fy{fy}"]) for fy in fys]
        groups = [[r["name"], *val(r)] for r in yr if r["kind"] == "group"]
        if abs(sum(sum(g[1:]) for g in groups) - total) <= len(fys):  # the same total as everything else in the section (each year is rounded to a million), or it is from another run
            recips = [[r["name"], *val(r)] for r in yr if r["kind"] == "recipient" and r["checked"] == "yes"]
            new = [[r[0], sum(r[1:])] for r in recips if r[1] == 0 and sum(r[1:]) >= 5]       # nothing in the first year, at least $5 million since
            M["byyear"] = {"fys": fys, "groups": groups, "recips": recips, "unchecked": sum(1 for r in yr if r["kind"] == "recipient" and r["checked"] != "yes"), "new": sorted(new, key=lambda r: -r[1])}
    cp = rd("ice_competition.csv")
    if cp:
        fys = [int(k[2:]) for k in cp[0] if k.startswith("fy")]; rows = {r["how"]: [int(r[f"fy{fy}"]) for fy in fys] for r in cp}
        if abs(sum(sum(v) for v in rows.values()) - total) <= len(fys) and all(k in rows for k in ("competed", "not_competed", "not_recorded")):
            M["comp"] = {"fys": fys, "rows": rows, "top": [[r["recipient"], int(r["musd"])] for r in rd("ice_not_competed_top.csv")]}
    lq, li = rd("lobbying_by_quarter.csv"), rd("lobbying_issues.csv")
    for r in lq: M.setdefault("lobby_q", {}).setdefault(r["company"], []).append([r["quarter"], int(r["own_usd"]), int(r["outside_usd"])])
    for r in li: M.setdefault("lobby_issues", {}).setdefault(r["company"], []).append([r["issue"], int(r["filings"])])
    fq = rd("fec_by_quarter.csv")
    if fq:
        qs = sorted({r["quarter"] for r in fq}); by = {(r["quarter"], r["pac"]): int(r["usd"]) for r in fq}
        M["pac_quarters"] = [[q, by.get((q, "G"), 0), by.get((q, "C"), 0), by.get((q, "M"), 0)] for q in qs]
        cyc_of = lambda q: int(q[:4]) + int(q[:4]) % 2          # 2025 Q3 belongs to the 2026 election cycle
        qsum, csum = {}, {}
        for r in fq: qsum[(r["pac"], cyc_of(r["quarter"]))] = qsum.get((r["pac"], cyc_of(r["quarter"])), 0) + int(r["usd"])
        for r in rd("fec_pac_recipients.csv"):
            for c in (2024, 2026): csum[(r["pac"], c)] = csum.get((r["pac"], c), 0) + int(r.get(f"cycle_{c}") or 0)
        M["pac_q_gap"] = [[k[0], k[1], v, csum.get(k, 0)] for k, v in sorted(qsum.items()) if abs(v - csum.get(k, 0)) >= 1000]   # where the two FEC counts disagree, the page says by how much


def pac_money(rows, total, cycles=(2024, 2026), read="2026-10-04"):
    """Contributions by contractor committees to other committees, as FEC records them.
    Rows are recipient COMMITTEES, never people. Raises if the rows stop adding to the total read from FEC."""
    out, per = [], {}
    for r in rows:
        a, b = int(r[f"cycle_{cycles[0]}"]), int(r[f"cycle_{cycles[1]}"])
        if r["pac"] not in "GCM" or r["type"] not in "HSPQ": raise ValueError(f"bad pac/type in {r}")
        party = r["party"] if r["party"] in ("REP", "DEM") else ""
        per.setdefault(r["pac"], [0, 0]); per[r["pac"]][0] += a; per[r["pac"]][1] += b
        out.append([r["pac"], a, b, r["recipient"], r["type"], party, int(r.get("gifts") or 0)])
    got = sum(r[1] + r[2] for r in out)
    if got != total: raise ValueError(f"PAC rows add to {got}, expected {total}")
    return {"total": total, "per": per, "rows": sorted(out, key=lambda r: -(r[1] + r[2])), "read": read, "cycles": list(cycles)}


def lobby_money(years, firms, targets):
    """Lobbying as filed under the Lobbying Disclosure Act. Raises if a company's firm rows stop adding to its outside total."""
    out = {}
    for r in years:
        out.setdefault(r["company"], {"y": [], "firms": [], "targets": []})["y"].append([r["year"], int(r["own_usd"]), int(r["outside_usd"])])
    for r in firms: out[r["company"]]["firms"].append([r["firm"], int(r["usd"])])
    for r in targets: out[r["company"]]["targets"].append([r["target"], int(r["filings"])])
    for k, o in out.items():
        a, b = sum(f[1] for f in o["firms"]), sum(y[2] for y in o["y"])
        if a != b: raise ValueError(f"lobbying firms for {k} add to {a}, outside total is {b}")
        o["firms"].sort(key=lambda f: -f[1])
    return out


def month_end(ym):
    """'2026-08' -> '2026-08-31'"""
    y, m = map(int, ym.split("-")); return (dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()


def source_rows(rows, dyn, today):
    """Footer list of sources. A row with a key takes its date from the data itself (dyn); the others carry the date they were
    last read by hand. stale = older than the row's max_age_days (0 = never goes stale). Returns rows and the stale names."""
    out, stale = [], []
    for r in rows:
        d = dyn.get(r["key"]) or r["read"]; age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(d)).days
        old = int(r["max_age_days"]) > 0 and age > int(r["max_age_days"])
        if old: stale.append(f'{r["what_en"]} ({d}, {age} days)')
        out.append([r["what_en"], r["what_es"], r["publisher"], d, r["url"], int(bool(r["key"])), int(old)])
    return out, stale


def write_layers(site, flights, folder):
    """GeoJSON copies of the map data, for loading into a globe (God's Eye View or any GIS tool). Organisations and places only."""
    folder.mkdir(parents=True, exist_ok=True)
    pt = lambda lon, lat, props: {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}
    fc = lambda feats: {"type": "FeatureCollection", "features": feats}
    out = {"facilities": fc([pt(f["lon"], f["lat"], {"code": c, "name": f["name"], "city": f.get("city", ""), "state": f.get("state", ""), "kind": f.get("kind", "")})
                             for c, f in site["facilities"].items() if f.get("lat") is not None and f.get("lon") is not None])}
    if site.get("a287"):
        out["agreements_287g"] = fc([pt(p[1], p[0], {"agencies": p[2], "county": p[3], "state": p[4]}) for p in site["a287"]["points"]])
    if flights:
        C = flights["coords"]
        out["airports"] = fc([pt(r[7], r[6], {"code": r[0], "town": r[1], "country": r[2], "state": r[3], "departures": r[4], "arrivals": r[5]}) for r in flights["used"]["rows"]])
        pairs = {}
        for l in flights["all"]:
            if l[3] == l[5] or l[3] not in C or l[5] not in C: continue
            k = tuple(sorted([l[3], l[5]])); p = pairs.setdefault(k, [0, 0, l[0], l[0]]); p[0] += 1; p[1] += l[7]; p[2] = min(p[2], l[0]); p[3] = max(p[3], l[0])
        out["flight_routes"] = fc([{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[C[a][1], C[a][0]], [C[b][1], C[b][0]]]},
                                    "properties": {"from": a, "to": b, "flights": v[0], "international": v[1], "first": v[2], "last": v[3]}} for (a, b), v in sorted(pairs.items(), key=lambda kv: -kv[1][0])])
        out["flight_tracks_recent"] = fc([{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in l["track"]]},
                                           "properties": {"date": l["date"], "departed_utc": l["departed_utc"], "arrived_utc": l["arrived_utc"], "from": l["origin"], "to": l["dest"], "kind": l["kind"], "registration": l["registration"]}} for l in flights["legs"] if len(l["track"]) > 1])
    for name, g in out.items(): (folder / f"{name}.geojson").write_text(json.dumps(g, separators=(",", ":")), encoding="utf-8")
    return {k: len(v["features"]) for k, v in out.items()}


def money_flow(rows, total):
    """ICE contract obligations grouped by what was bought (federal product/service codes), with the largest recipients
    in each group. Millions of dollars. The group totals must not exceed the overall total."""
    groups = {}
    for r in rows:
        g = groups.setdefault(r["group"], [r["group"], int(r["group_total_musd"]), []])
        if r["recipient"]: g[2].append([r["recipient"], int(r["musd"])])
    out = sorted(groups.values(), key=lambda g: (g[0] == "OTHER", -g[1]))
    if sum(g[1] for g in out) != total: raise ValueError(f"ice_money_flow.csv: groups add to {sum(g[1] for g in out)}, not the total {total}")
    for g in out:
        if sum(v for _, v in g[2]) > g[1] * 1.03 + 1: raise ValueError(f"ice_money_flow.csv: recipients in {g[0]} exceed the group total")   # a little over is real: cancelled awards count as negatives in the group total
    return {"total": total, "groups": out}


def attach_inspections(site, rows):
    """ICE's own inspection reports, matched first by a hand-kept other name (facility_name_aliases.csv), then on state + city and a
    similar name. Unsure matches are left out."""
    import difflib, re
    ap = ROOT / "data" / "reference" / "facility_name_aliases.csv"
    alias = {r["name"].strip().upper(): r["facility_code"] for r in csv.DictReader(open(ap, encoding="utf-8"), delimiter="|")} if ap.exists() else {}
    norm = lambda x: re.sub(r"[^a-z0-9 ]", " ", str(x).lower().replace("saint", "st")).split()
    def similar(a, b):
        drop = {"the", "ice", "county", "co", "center", "cntr", "facility", "detention", "jail", "correctional", "processing"}
        a, b = [w for w in norm(a) if w not in drop], [w for w in norm(b) if w not in drop]
        return difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio() if a and b else 0
    by_city = {}
    for c, f in site["facilities"].items():
        f.pop("inspections", None)
        if f.get("city") and f.get("state"): by_city.setdefault((f["state"], " ".join(norm(f["city"]))), []).append(c)
    n = 0
    for r in rows:
        a = alias.get(r["facility"].strip().upper())
        if a in site["facilities"]: site["facilities"][a].setdefault("inspections", []).append([r["fiscal_year"], r["dates"], r["url"]]); n += 1; continue
        cands = by_city.get((r["state"], " ".join(norm(r["city"]))), [])
        scored = sorted(((similar(site["facilities"][c]["name"], r["facility"]), c) for c in cands), reverse=True)
        if not scored or scored[0][0] < 0.6 or (len(scored) > 1 and scored[0][0] - scored[1][0] < 0.15): continue
        site["facilities"][scored[0][1]].setdefault("inspections", []).append([r["fiscal_year"], r["dates"], r["url"]]); n += 1
    for f in site["facilities"].values():
        if "inspections" in f: f["inspections"] = sorted(f["inspections"], reverse=True)[:3]
    return n


def when(l, key):
    import datetime as dt
    t = dt.datetime.strptime(l["date"] + " " + l[key], "%Y-%m-%d %H:%M")
    if key == "arrived_utc" and l["arrived_utc"] < l["departed_utc"]: t += dt.timedelta(days=1)
    return t


RECENT_DAYS = 14                                   # days whose individual flights and tracks go on the page


def trends(legs):
    """What the positions show across all days on record. Counts are flights, never people."""
    import statistics
    by = {}
    out = [l for l in legs if l["origin_country"] == "US" and l["dest_country"] != "US"]
    back = [l for l in legs if l["origin_country"] != "US" and l["dest_country"] == "US"]
    # a country only counts as a destination when the aircraft was seen low and close to an airport there;
    # otherwise the signal was lost over that country and the flight may have gone on
    for l in legs:
        if l["dest_country"] == "US": continue
        if l["dest_certain"]: by.setdefault(l["dest_country"], [0, 0, 0])[0] += 1          # landed, wherever the leg was first seen
        elif l["origin_country"] == "US": by.setdefault(l["dest_country"], [0, 0, 0])[1] += 1
    for l in back: by.setdefault(l["origin_country"], [0, 0, 0])[2] += 1
    gaps = []
    for l in out:                                   # the same aircraft's next flight: did it come back, and how soon?
        later = sorted((x for x in legs if x["hex"] == l["hex"] and when(x, "departed_utc") >= when(l, "arrived_utc")), key=lambda x: when(x, "departed_utc"))
        nxt = next((x for x in later if x["dest_country"] == "US"), None)
        if nxt is not None and (when(nxt, "departed_utc") - when(l, "arrived_utc")).total_seconds() < 12 * 3600:
            gaps.append((when(nxt, "departed_utc") - when(l, "arrived_utc")).total_seconds() / 3600)
    routes, dom, sure = {}, 0, 0
    for l in legs:
        if l["kind"] != "domestic": continue
        dom += 1
        if not (l["origin_certain"] and l["dest_certain"]): continue    # signal lost in the air at one end: the nearest airport is a guess (a flight "to Houma" may have gone on over the Gulf), so it is not a route
        sure += 1; k = " – ".join(sorted([l["origin"], l["dest"]])); routes[k] = routes.get(k, 0) + 1
    return {"countries": [{"country": COUNTRY.get(k, k), "landed": v[0], "lost": v[1], "back": v[2]} for k, v in sorted(by.items(), key=lambda kv: -sum(kv[1]))],
            "dom": dom, "dom_sure": sure, "left": len(out), "returned_within_12h": len(gaps), "median_hours_before_return": round(statistics.median(gaps), 1) if gaps else None,
            "routes": [{"route": k, "n": v} for k, v in sorted(routes.items(), key=lambda kv: -kv[1])[:8] if v >= 2]}


GOV_KINDS = {"official", "partisan", "news", "research"}
GOV_SECTIONS = {"cbp", "hhs", "doj", "dod", "fema", "states", "countries", "data", "dhs"}


def gov_section(site, ref):
    """Agencies, states and countries beyond ICE -> site["gov"]. Refuses rows with an unknown kind of source, a facility code the page
    does not have, a link that is not https, or English text with no Spanish (every line here is shown in both languages)."""
    rd = lambda n: list(csv.DictReader(open(ref / n, encoding="utf-8"), delimiter="|")) if (ref / n).exists() else []
    es, missing = site.get("es", {}), []
    def say(*texts):
        for t in texts:
            if t and t not in es: missing.append(t)
    def src(r, need=("url",)):
        if r.get("kind") and r["kind"] not in GOV_KINDS: raise ValueError(f"unknown kind of source {r['kind']!r} in {r}")
        for k in need:
            if not (r.get(k) or "").startswith("https://"): raise ValueError(f"link must be https: {r.get(k)!r}")
    g = {}
    enc = rd("cbp_encounters_by_month.csv")
    if enc: g["enc"] = [[r["month"], int(r["total"]), int(r["southwest"]), int(r["northern"]), int(r["other"]), int(r["title42"]), int(r["uac"])] for r in enc]
    cus = rd("cbp_custody_by_month.csv")
    if cus: g["cust"] = [[r["month"]] + [int(r[c]) if r[c] != "" else None for c in ("usbp_apprehended", "usbp_in_custody", "usbp_to_federal", "ofo_sw_in_custody")] for r in cus]
    rep = rd("ohss_repatriations.csv")
    if rep: g["repat"] = [[int(r["fy"]), int(r["removals"]), int(r["enforcement_returns"]), int(r["administrative_returns"]), int(r["expulsions"]), int(r["total"])] for r in rep]
    orr = rd("orr_by_month.csv")
    if orr: g["orr"] = [[r["month"]] + [float(r[c]) if r[c] != "" else None for c in ("in_care", "beds", "days_discharged", "days_in_care", "referrals_per_day", "released")] for r in orr]
    od = rd("orr_days_by_fy.csv")
    if od: g["orr_fy"] = [[int(r["fy"]), int(r["days"])] for r in od]
    m = ref / "other_sources_meta.json"
    if m.exists(): g["meta"] = json.loads(m.read_text(encoding="utf-8"))
    cy = rd("cbp_deaths_by_year.csv")
    for r in cy: src(r)
    if cy: g["cdy"] = [[int(r["fy"]), int(r["in_custody"]), int(r["all_reviewed"]) if r["all_reviewed"] else None, r["source"], r["url"]] for r in cy]
    cn = rd("cbp_death_notices.csv")
    for r in cn:
        src(r); say(r["what"])
        if r["custody"] not in ("arrested", "not_stated", "port", "force", "pursuit", "released"): raise ValueError(f"cbp_death_notices.csv: custody {r['custody']!r}")
    if cn: g["cdn"] = [[r["died"], r["component"], r["unit"], r["state"], r["what"], r["custody"], r["posted"], r["url"]] for r in sorted(cn, key=lambda r: r["died"], reverse=True)]
    facts = {}
    for r in rd("gov_facts.csv"):
        src(r); say(r["text"])
        if r["section"] not in GOV_SECTIONS: raise ValueError(f"gov_facts.csv: unknown section {r['section']!r}")
        facts.setdefault(r["section"], []).append([r["text"], r["source"], r["url"], r["kind"], r["as_of"]])
    if facts: g["facts"] = facts
    st = rd("state_sites.csv")
    for r in st:
        src(r); say(r["run_by"], r["status"])
        if r["facility_code"] and r["facility_code"] not in site["facilities"]: raise ValueError(f"state_sites.csv: unknown facility code {r['facility_code']}")
    if st: g["states"] = [[r["name"], r["place"], r["state"], r["run_by"], r["facility_code"], r["status"], r["source"], r["url"], r["kind"]] for r in st]
    pay = rd("third_country_payments.csv")
    for r in pay: src(r); say(r["note"])
    if pay: g["pay"] = [[r["country"], float(r["paid_musd"]), int(r["people"]) if r["people"] else None, r["note"], r["source"], r["url"], r["kind"], r["as_of"]] for r in pay]
    sh = rd("data_sharing.csv")
    for r in sh: src(r); say(r["agency"], r["what"], r["since"], r["status"])
    if sh: g["share"] = [[r["agency"], r["what"], r["since"], r["status"], r["source"], r["url"], r["kind"]] for r in sh]
    dk = rd("went_dark.csv")
    for r in dk:
        src(r); say(r["publisher"], r["what"], r["cadence"], r["last"], r["status"])
        if r.get("tab") not in ("over", "trends"): raise ValueError(f"went_dark.csv: tab must be over or trends, not {r.get('tab')!r}")
    if dk: g["dark"] = [[r["publisher"], r["what"], r["cadence"], r["last"], r["status"], r["source"], r["url"], r["kind"], r["tab"]] for r in dk]
    om, mm = rd("other_money.csv"), ref / "other_money_meta.json"
    if om and mm.exists():
        meta = json.loads(mm.read_text(encoding="utf-8")); progs = {}
        for r in om: progs.setdefault(f'{r["agency"]}/{r["program"]}', []).append([r["recipient"], float(r["musd"])])
        for k, rows in progs.items():
            tot = meta["programs"][k]["total_musd"]
            if abs(sum(x[1] for x in rows) - tot) > 0.15: raise ValueError(f"other_money.csv: {k} adds to {sum(x[1] for x in rows):.1f}M, not {tot}M")
        g["money"] = {"from": meta["from"], "to": meta["to"], "read": meta["read"], "fys": meta["fys"], "dod": meta.get("dod_awards", []),
                      "progs": {k: {"rows": rows, **{x: meta["programs"][k][x] for x in ("total_musd", "by_fy_musd", "private_people_left_out", "taken_back_musd") if x in meta["programs"][k]}} for k, rows in progs.items()}}
    g["bop"] = sorted(c for c in site["facilities"] if c.startswith("BOP"))
    if missing: raise ValueError(f"{len(missing)} lines in the other-agencies files have no Spanish in es_text.csv, e.g. {missing[:3]}")
    return g


def norm_payee(n):
    """A company name reduced for matching across agencies: case, punctuation and legal-form words removed."""
    n = re.sub(r"[^A-Z0-9 ]", " ", (n or "").upper().replace("&", " AND "))
    n = re.sub(r"\b(THE|LLC|L L C|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PLLC|PC)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def shared_payees(lists, parents=None, min_musd=1.0):
    """lists: {payer: [(name, musd)]}. Returns [[name, parent, [[payer, musd]...], total]] for every company paid by two or more payers,
    largest first. A company's parent (when known) joins its units, so one owner paid through two companies counts once per payer."""
    parents = {norm_payee(k): v for k, v in (parents or {}).items() if v}
    by = {}
    for payer, rows in lists.items():
        for name, m in rows:
            k = norm_payee(parents.get(norm_payee(name)) or name)
            if not k: continue
            e = by.setdefault(k, {"name": parents.get(norm_payee(name)) or name, "pay": {}})
            e["pay"][payer] = round(e["pay"].get(payer, 0) + m, 1)
    out = []
    for e in by.values():
        pay = {p: v for p, v in e["pay"].items() if abs(v) >= min_musd}
        if len(pay) >= 2: out.append([e["name"], "", sorted(pay.items(), key=lambda x: -abs(x[1])), round(sum(pay.values()), 1)])
    return sorted(out, key=lambda r: -abs(r[3]))



def page_identity(html):
    """Fill the publisher details from pipeline/identity.py. With no repository set yet, the raw-data line is left out
    rather than pointing at an old or personal account."""
    import identity
    for k, v in (("{{PUBLISHER}}", identity.PUBLISHER), ("{{CONTACT}}", identity.CONTACT)):
        if not re.fullmatch(r"[\w .@+-]*", v): raise ValueError(f"identity: {k} has characters the page cannot carry safely")
        html = html.replace(k, v)
    site_url = getattr(identity, "SITE_URL", "")
    if site_url and not re.fullmatch(r"https://[\w.-]+(/[\w./-]*)?", site_url): raise ValueError("identity.SITE_URL must be a plain https address")
    html = html.replace("{{SITE_URL}}", site_url.rstrip("/"))
    if identity.REPO_URL:
        if not identity.REPO_URL.startswith("https://"): raise ValueError("identity.REPO_URL must be an https address")
        return html.replace("{{REPO_DATA}}", identity.REPO_URL.rstrip("/") + "/tree/main/data/reference")
    html, n = re.subn(r'\n\s*<p id="raw-line">.*?</p>', "", html, flags=re.S)
    if n != 1: raise ValueError("template: the raw-data line (id raw-line) was not found")
    return html


def people_section(ref):
    """Arrests, alternatives to detention, book-ins by arresting agency, removals, staff and spending by kind -> site["people"]. Counts only."""
    rd = lambda n: list(csv.DictReader(open(ref / n, encoding="utf-8"), delimiter="|")) if (ref / n).exists() else []
    jm = lambda n: json.loads((ref / n).read_text(encoding="utf-8")) if (ref / n).exists() else {}
    P = {}
    am = rd("arrests_by_month.csv")
    if am:
        P["arr"] = [[r["month"], int(r["arrests"]), int(r["no_conviction_pct"]) if r["no_conviction_pct"] != "" else None] for r in am]
        meth = {}
        for r in rd("arrests_by_method.csv"): meth.setdefault(r["method"], {})[r["month"]] = int(r["arrests"])
        P["arr_m"] = {k: [v.get(m[0], 0) for m in P["arr"]] for k, v in meth.items()}
        for i, m in enumerate(P["arr"]):                      # the methods must add up to the month's total
            if sum(v[i] for v in P["arr_m"].values()) != m[1]: raise ValueError(f"arrests_by_method.csv: {m[0]} does not add up to {m[1]}")
        st = {}
        for r in rd("arrests_by_state_fy.csv"): st.setdefault(r["fy"], {})[r["state"]] = int(r["arrests"])
        P["arr_st"] = st; P["arr_meta"] = jm("arrests_meta.json")
    dm = rd("detainers_by_month.csv")                         # requests to jails and prisons to hold people for ICE
    if dm:
        num = lambda v: int(v) if v not in ("", None) else None
        P["det"] = [[r["month"], int(r["detainers"]), num(r["hold_requests"]), num(r["notice_requests"]), num(r["no_conviction_pct"]), num(r["violent_pct"])] for r in dm]
        st = {}
        for r in rd("detainers_by_state_fy.csv"): st.setdefault(r["fy"], {})[r["state"]] = int(r["detainers"])
        lf = {}
        for r in rd("detainers_by_lift.csv"): lf.setdefault(r["fy"], {})[r["reason"]] = int(r["detainers"])
        P["det_st"], P["det_lift"], P["det_meta"] = st, lf, jm("detainers_meta.json")
    hb = rd("habeas_trac.csv")                                # habeas petitions challenging immigration detention (TRAC, from federal court records)
    if hb: P["hab"] = {"m": [[r["month"], int(r["habeas"])] for r in hb], "d": [[r["district"], int(r["filings"])] for r in rd("habeas_districts.csv")]}
    rc = rd("removals_by_country.csv")                        # removals from detention, by destination country and month
    if rc:
        ms = sorted({r["month"] for r in rc}); g = {}
        for r in rc: g.setdefault(r["country"], [0] * len(ms))[ms.index(r["month"])] = int(r["removals"])
        P["rmc"] = {"months": ms, "by": g, "meta": jm("removals_by_country_meta.json")}
    sn = rd("ice_stats_snapshots.csv")
    if sn:
        by = {}
        for r in sn: by.setdefault(r["measure"], []).append([r["as_of"], float(r["value"]) if "." in r["value"] else int(r["value"])])
        P["ice"] = {k: sorted(v) for k, v in by.items()}
    bk = rd("ice_bookins_by_agency.csv")
    if bk:
        ms = sorted({r["month"] for r in bk}); g = {(r["month"], r["agency"]): int(r["book_ins"]) for r in bk}
        P["bk"] = [[m, g.get((m, "ICE"), 0), g.get((m, "CBP"), 0)] for m in ms]
    sm = rd("staff_by_month.csv")
    if sm:
        P["staff"] = {}
        for r in sm: P["staff"].setdefault(r["agency"], []).append([r["month"], int(r["employees"])])
        fl = rd("staff_flows.csv")
        P["flows"] = {}
        for r in fl: P["flows"].setdefault(r["agency"], []).append([r["month"], int(r["hires"]) if r["hires"] else None, int(r["separations"]) if r["separations"] else None])
        se = rd("staff_by_series.csv"); last = max(r["month"] for r in se) if se else ""
        P["series"], P["officers"] = {}, {}
        for r in se:
            if r["month"] == last: P["series"].setdefault(r["agency"], []).append([r["series"], int(r["employees"])])
            if r["agency"] == "ICE" and r["series"] in ("1801", "1811"): P["officers"][r["month"]] = P["officers"].get(r["month"], 0) + int(r["employees"])     # officers and agents: 1801 enforcement, 1811 investigators
        P["officers"] = sorted(P["officers"].items())
        P["staff_meta"] = {"read": jm("staff_meta.json").get("read", ""), "series_month": last}
    oc = rd("agency_object_class.csv")
    if oc:
        P["oc"] = {}
        for r in oc:
            d = P["oc"].setdefault(r["agency"], {}).setdefault(r["fy"], {}); d[r["object_class"]] = round(d.get(r["object_class"], 0) + float(r["musd"]), 1)
        P["oc_meta"] = jm("agency_object_class_meta.json")
        P["oc_minor"] = {}
        for r in rd("agency_object_class_minor.csv"): P["oc_minor"].setdefault(r["agency"], {}).setdefault(r["fy"], []).append([r["code"], r["name"], float(r["musd"])])
        P["linked"] = {}
        for r in rd("agency_award_linked.csv"): P["linked"].setdefault(r["agency"], {}).setdefault(r["fy"], {})[r["object_class"]] = [float(r["linked_musd"]), float(r["total_musd"])]
        P["by_state"] = {r["state"]: float(r["musd"]) for r in rd("ice_spending_by_state.csv")}
    se = rd("ice_semiannual.csv")                              # military members, US citizens, parents of US citizens, TPS countries, by fiscal year
    if se:
        sa = {}
        for r in se: sa.setdefault(r["group"], {}).setdefault(r["country"] or "_", {}).setdefault(r["measure"], []).append([int(r["fy"]), int(r["value"]), 1 if r["zeroed_in"] else 0])
        for g in sa.values():
            for c in g.values():
                for k in c: c[k].sort()
        P["semi"] = sa; P["semi_src"] = max(r["src"] for r in se)
    sr = rd("ice_segregation_reasons.csv")
    if sr:
        q = {}
        for r in sr: q.setdefault(f'{r["fy"]} Q{r["quarter"]}', {})[r["reason"]] = [int(r["placements"]), float(r["avg_consecutive"]), float(r["avg_cumulative"]), int(r["people"]) if r["people"] else None]
        for k, v in q.items():                                 # the reasons must add up to ICE's total
            if "Total" in v and sum(x[0] for n, x in v.items() if n != "Total") != v["Total"][0]: raise ValueError(f"ice_segregation_reasons.csv: {k} reasons do not add up to {v['Total'][0]}")
        P["segr"] = fill_quarters(sorted(q.items(), key=lambda kv: (int(kv[0][:4]), kv[0][-1])))
    bo = rd("ice_bond_monthly.csv")
    if bo: P["bond"] = [[r["month"], int(r["book_outs"]), int(r["bond_posted"]), int(r["avg_bond"]), float(r["alos"])] for r in bo]
    lo = rd("ice_length_of_stay.csv")
    if lo: P["los"] = fill_halfmonths([[r["day"], float(r["alos"]) if r["alos"] else None, *[int(r[k]) if r[k] else None for k in ("d0_180", "d181_365", "d366_730", "d730p")]] for r in lo if r["population"] == "total"])
    return P


def _member_in(text, first, last, state=""):
    """Does a free-text list of officials ("U.S. Representatives Ilhan Omar, Kelly Morrison and Angie Craig") name this member?
    Needs a federal title in the text, the member's first and last name as whole words, and the state when the text gives one."""
    import re
    if not re.search(r"U\.S\.|Congress|Senator|Representative", text) or re.search(r"\bState (Senator|Representative)s?\b", text) and "U.S." not in text: return False
    w = lambda x: re.search(r"(?<![\w])" + re.escape(x) + r"(?![\w])", text) is not None
    if not (w(last) and w(first)): return False
    m = re.search(r"\(([A-Z]{2})\)", text)
    return not m or not state or m.group(1) == state


def official_flags(P, cards, rules):
    """Watch list › Officials and money. One rule for every current member: (com) on a committee that oversees ICE and at least
    officials_min_usd from contractor committees or named staff; (local) a privately run facility in the district (state for a
    senator) is run by a company whose committee or staff gave them at least that much. Facts only; no judgment is made."""
    PAC2CO, mn = {"G": "GEO", "C": "CC", "M": "MTC"}, rules.get("officials_min_usd", 0)
    out = []
    for m in P["m"]:
        if not m[11]: continue
        c = cards.get(m[0], {}); pac = sum(x[2] for x in c.get("pac", [])); don = sum(d[2] for d in c.get("don", [])); gifts = sum(d[3] for d in c.get("don", [])) + sum(x[4] for x in c.get("pac", []) if len(x) > 4)
        by, src = {}, {}
        for x in c.get("pac", []):
            k = PAC2CO.get(x[0], x[0]); by[k] = by.get(k, 0) + x[2]; src.setdefault(k, set()).add("pac")
        for d in c.get("don", []): by[d[1]] = by.get(d[1], 0) + d[2]; src.setdefault(d[1], set()).add("staff")
        cos = {k for k, v in by.items() if v > 0 and v >= mn}
        why = []
        if m[7] and pac + don > 0 and pac + don >= mn: why.append("com")
        local = [[f[0], f[1], f[2]] for f in c.get("fac", []) if f[2] and f[2] in cos]
        if local: why.append("local")
        cl = sorted({f[2] for f in local})
        if why: out.append({"bg": m[0], "why": why, "pac": pac, "don": round(don), "gifts": gifts, "people": len(c.get("don", [])), "local": local, "cos": cl,
                            "pgifts": sum(x[4] for x in c.get("pac", []) if len(x) > 4), "dgifts": sum(d[3] for d in c.get("don", [])),
                            "src": {k: ("both" if len(src.get(k, ())) == 2 else next(iter(src.get(k, {"both"})))) for k in cl}})
    return out


def pol_cards(site, ref):
    """One scorecard per member of Congress, from records already on the page: contractor committee money by committee,
    joint fundraisers they share in that took that money, named staff donors, facilities in their district (House) or state
    (Senate), and oversight visits, refusals and statements that name them. Officials acting in office only.
    Returns ({bioguide: card}, notes)."""
    import re
    P = site.get("pol")
    if not P: return {}, []
    rd = lambda n: list(csv.DictReader(open(ref / n, encoding="utf-8"), delimiter="|")) if (ref / n).exists() else []
    norm = lambda x: re.sub(r"[^A-Z0-9]+", " ", (x or "").upper()).strip()
    mc = rd("member_committees.csv"); own, jfc_names, own_id = {}, set(), {}
    for r in mc:
        if r["designation"] == "J": jfc_names.add(norm(r["name"])); continue          # a joint fundraiser is listed with the funds, not as the member's own money
        own.setdefault(norm(r["name"]), set()).add(r["bioguide"]); own_id.setdefault(r["committee_id"], set()).add(r["bioguide"])
    names = {m[0]: m[1] for m in P["m"]}
    cards = {m[0]: {} for m in P["m"]}; notes = []
    # contractor committee money, by the committee that received it (exact FEC committee names on both sides)
    link = {r["recipient"]: r["link"] for r in rd("fec_committee_candidates.csv")}
    detail = {r["recipient"]: r for r in rd("fec_committee_detail.csv")}
    cyc = [k for k in (rd("fec_pac_recipients.csv")[:1] or [{}])[0] if k.startswith("cycle_")]
    pac_to = {}
    for r in rd("fec_pac_recipients.csv"):
        usd = sum(int(r[k]) for k in cyc); pac_to.setdefault(r["recipient"], []).append([r["pac"], usd, int(r.get("gifts") or 0)])
        who = own_id.get(r.get("recipient_id") or "", set()) or own.get(norm(r["recipient"]), set())
        if len(who) == 1 and r["type"] != "P":
            (bg,) = who
            if bg in cards: cards[bg].setdefault("pac", []).append([r["pac"], r["recipient"], usd, "L" if (detail.get(r["recipient"], {}).get("kind") == "D" or link.get(r["recipient"]) == "L") else "C", int(r.get("gifts") or 0)])
    # joint fundraisers that took contractor money and share it with a member's own committee
    for jn, r in detail.items():
        if r["kind"] != "J" or jn not in pac_to: continue
        parts = [x.strip() for x in r["shares_with"].split(";") if x.strip()]
        members = sorted({bg for x in parts for bg in own.get(norm(x), set()) if bg in cards})
        got = sum(u for _, u, _n in pac_to[jn])
        for bg in members:
            cards[bg].setdefault("jfc", []).append([jn, got, len(parts), [names[o] for o in members if o != bg], sorted({p for p, _, _n in pac_to[jn]}), sum(n for _, _, n in pac_to[jn])])
    # named staff donors: one person filed with and without a middle initial, or with a title, at the same company is one donor
    def parts(r):
        last, _, rest = r["name"].upper().partition(","); w = [x for x in re.sub(r"[^A-Z ]+", " ", rest).split() if x not in ("MR", "MRS", "MS", "DR", "COL", "HON", "JR", "SR", "II", "III", "IV", "MD", "PHD", "ESQ")]
        return (r["co"], re.sub(r"[^A-Z ]+", " ", last).strip(), w[0] if w else ""), (w[1][:1] if len(w) > 1 else "")
    mi_seen = {}
    for r in rd("fec_donors.csv"):
        b, m = parts(r); mi_seen.setdefault(b, set())
        if m: mi_seen[b].add(m)
    def donor_key(r, seen):
        b, m = parts(r); return b + ((m,) if len(seen[b]) > 1 else ())
    for r in rd("fec_donors.csv"):
        if r["bioguide"] in cards:
            d = cards[r["bioguide"]].setdefault("don", {}); k = donor_key(r, mi_seen)
            g = d.setdefault(k, [r["name"], r["co"], 0.0, 0]); g[2] += float(r["usd"]); g[3] += 1
    for c in cards.values():
        if "don" in c: c["don"] = sorted(([n, co, round(u), k] for n, co, u, k in c["don"].values()), key=lambda x: -x[2])
    # facilities in the member's district or state
    watch = {a.get("code") for a in (site.get("watch") or {}).get("alerts", []) if a.get("code")}
    ops = site.get("operators") or {}
    by_dist, by_state = {}, {}
    for code, f in site["facilities"].items():
        held = (f.get("held") or [None])[0]
        row = [code, f.get("name", ""), (ops.get(code) or [""])[0], held, len(f.get("death_reports") or []), 1 if code in watch else 0]
        by_state.setdefault(f.get("state"), []).append(row)
        if f.get("rep"): by_dist.setdefault(f["rep"][3], []).append(row)
    for m in P["m"]:
        L = by_dist.get(f"{m[4]}-{m[5]}", []) if m[2] == "H" else by_state.get(m[4], []) if m[2] == "S" else []
        if L: cards[m[0]]["fac"] = sorted(L, key=lambda x: -(x[3] or 0))
    # oversight visits, refusals and statements naming the member
    ev = []
    for code, f in site["facilities"].items():
        for v in f.get("visits") or []: ev.append([v[0], v[1], v[2], f.get("name", ""), v[4] if len(v) > 4 else "", code])
    for v in site.get("denied") or []: ev.append([v[0], v[2], "denied", v[1], v[4], v[6] if len(v) > 6 else ""])
    for v in (site.get("statements") or []) + (site.get("statements_visits") or []): ev.append([v[0], v[1], v[2], "", v[4], ""])
    seen = set()
    for m in P["m"]:
        parts = m[1].replace(",", " ").split(); parts = [x for x in parts if x not in ("Jr.", "Sr.", "II", "III", "IV")]
        if len(parts) < 2: continue
        for e in ev:
            if _member_in(e[1], parts[0], parts[-1], m[4]):
                k = (m[0], e[0], e[4] or e[3])
                if k in seen: continue
                seen.add(k); cards[m[0]].setdefault("ov", []).append([e[0], e[2], e[3], e[4], e[5]])
    for c in cards.values():
        if "ov" in c: c["ov"].sort(reverse=True)
    for r in rd("member_top_donors.csv"):                       # every member's largest committee donors and outside spending, any cause
        if r["bioguide"] not in cards: continue
        if r["kind"].startswith("T"): cards[r["bioguide"]].setdefault("top", {}).setdefault("tie", {})[r["kind"][1:]] = [int(r["usd"]), int(r["count"])]
        else: cards[r["bioguide"]].setdefault("top", {}).setdefault(r["kind"], []).append([r["name"], int(r["usd"]), int(r["count"]), r["committee_id"]])
    pm = {r["bioguide"]: int(r["campaign_usd"]) + int(r["leadership_usd"]) for r in rd("pac_members_votes.csv")}
    for r in rd("pac_members_votes.csv"):                      # money the member totals count but no committee name matched (renamed committees): one row saying so
        bg = r["bioguide"]
        if bg not in cards: continue
        for kind, col in (("C", "campaign_usd"), ("L", "leadership_usd")):
            gap = int(r[col]) - sum(x[2] for x in cards[bg].get("pac", []) if x[3] == kind)
            if gap > 0: cards[bg].setdefault("pac", []).append(["", "", gap, kind, 0])
    off = [bg for bg, usd in pm.items() if bg in cards and abs(sum(x[2] for x in cards[bg].get("pac", [])) - usd) > 0]
    if off: notes.append(f"scorecards: committee money for {len(off)} members is more than the member totals: {off}")
    return {bg: c for bg, c in cards.items() if c}, notes


def donor_people(rows):
    """Distinct donors, merging one person filed with and without a middle initial or a title at the same company (the page's rule)."""
    import re
    skip = {"MR", "MRS", "MS", "DR", "COL", "HON", "JR", "SR", "II", "III", "IV", "MD", "PHD", "ESQ"}
    def parts(r):
        last, _, rest = r[2].upper().partition(","); w = [x for x in re.sub(r"[^A-Z ]+", " ", rest).split() if x not in skip]
        return (r[0], re.sub(r"[^A-Z ]+", " ", last).strip(), w[0] if w else ""), (w[1][:1] if len(w) > 1 else "")
    mi = {}
    for r in rows:
        b, m = parts(r); mi.setdefault(b, set())
        if m: mi[b].add(m)
    return len({b + ((m,) if len(mi[b]) > 1 else ()) for b, m in map(parts, rows)})


def donors_section(ref):
    """Named individual contributions from staff of detention and removal contractors (FEC Schedule A, itemized, public record).
    Name, employer and occupation as the donor reported them; state only, never an address. None until money_donors.py has run.
    Raises if the rows stop adding to the total the collector wrote, or a row has a non-FEC link or an unknown company."""
    if not (ref / "fec_donors.csv").exists() or not (ref / "fec_donors_meta.json").exists(): return None
    meta = json.loads((ref / "fec_donors_meta.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(ref / "fec_donors.csv", encoding="utf-8"), delimiter="|"))
    out = []
    for r in rows:
        if r["co"] not in ("GEO", "CC", "MTC", "LAS", "ICA", "CSI"): raise ValueError(f"fec_donors.csv: unknown company {r['co']!r}")
        if not (r["url"].startswith("https://docquery.fec.gov/") or r["url"].startswith("https://www.fec.gov/")): raise ValueError(f"fec_donors.csv: link {r['url']}")
        if not r["url"].startswith("https://www.fec.gov/data/receipts/"):        # older rows link the scanned filing, which prints a street address
            r["url"] = "https://www.fec.gov/data/receipts/?" + urllib.parse.urlencode({"committee_id": r["committee_id"], "contributor_name": r["name"], "two_year_transaction_period": r["cycle"]})
        own = r["committee_id"] in ("C00382150", "C00366468", "C00208322")      # a company's own committee (GEO, CoreCivic, MTC): its gifts on are counted as PAC money
        out.append([r["co"], r["date"], r["name"], r["employer"], r["occupation"], r["state"], float(r["usd"]), r["committee"], "O" if own else r["ctype"], r["party"], r["bioguide"], r["url"], int(r["cycle"])])
    got = round(sum(r[6] for r in out), 2)
    if abs(got - meta["total"]) > 0.01: raise ValueError(f"donor rows add to {got}, expected {meta['total']}")
    return {"read": meta["read"], "cycles": meta["cycles"], "total": meta["total"], "rows": out}


def politicians_section(ref):
    """Members of Congress: votes on the enforcement laws (official roll calls), oversight committees, and money from detention
    and ICE contractor committees (FEC). None until pipeline/politicians.py has run. Officials acting in office only."""
    rd = lambda n: list(csv.DictReader(open(ref / n, encoding="utf-8"), delimiter="|")) if (ref / n).exists() else []
    calls, mv, mem = rd("roll_calls.csv"), rd("member_votes.csv"), rd("members.csv")
    if not calls or not mem: return None
    ids = [c["vote_id"] for c in calls]; vote = {}
    pday = {}
    for r in mv: vote.setdefault(r["bioguide"], {})[r["vote_id"]] = r["vote"]; pday.setdefault(r["bioguide"], {})[r["vote_id"]] = (r.get("party") or "-")[:1]
    money = {r["bioguide"]: (int(r["campaign_usd"]), int(r["leadership_usd"])) for r in rd("pac_members_votes.csv")}
    staff = {}
    for r in rd("fec_donors.csv"):
        if r["bioguide"]: g = staff.setdefault(r["bioguide"], [0.0, set()]); g[0] += float(r["usd"]); g[1].add(r["name"].upper())
    # money to a former member who cast none of these votes (one who left before 2025) stays on Follow the money only
    m = [[r["bioguide"], r["name"], r["chamber"], r["party"], r["state"], r["district"], r["url"], [x for x in r["committees"].split(";") if x],
          "".join(vote.get(r["bioguide"], {}).get(i, "-") for i in ids), *money.get(r["bioguide"], (0, 0)), 1 if r["current"] else 0,
          "".join(pday.get(r["bioguide"], {}).get(i, "-") for i in ids),                      # party as each roll call records it on the day
          round(staff[r["bioguide"]][0]) if r["bioguide"] in staff else 0, len(staff[r["bioguide"]][1]) if r["bioguide"] in staff else 0] for r in mem]   # gifts from contractor staff (FEC, named on Follow the money)
    return {"votes": [[c["vote_id"], c["chamber"], c["date"], c["bill"], c["law"], c["question"], int(c["yeas"]), int(c["nays"]), c["url"]] for c in calls],
            "m": m, "fec": json.loads((ref / "fec_meta.json").read_text(encoding="utf-8")) if (ref / "fec_meta.json").exists() else {}}


def fill_quarters(rows):
    """[("2025 Q3", {...}), ("2026 Q1", {...})] -> the missing quarter added as ("2025 Q4", {}) so a chart shows the gap instead of joining across it."""
    if not rows: return rows
    have = dict(rows); y, q = int(rows[0][0][:4]), int(rows[0][0][-1]); ly, lq = int(rows[-1][0][:4]), int(rows[-1][0][-1]); out = []
    while (y, q) <= (ly, lq):
        k = f"{y} Q{q}"; out.append((k, have.get(k, {}))); q += 1
        if q > 4: y, q = y + 1, 1
    return out


def fill_halfmonths(rows):
    """Rows dated the 15th and the last day of each month -> any missing date added with empty values and a 1 in position 6 (a gap)."""
    import calendar
    if not rows: return rows
    have = {r[0]: r for r in rows}; y, m = int(rows[0][0][:4]), int(rows[0][0][5:7]); last = rows[-1][0]; out = []
    while f"{y}-{m:02d}-01" <= last:
        for d in (15, calendar.monthrange(y, m)[1]):
            k = f"{y}-{m:02d}-{d:02d}"
            if k < rows[0][0] or k > last: continue
            out.append(have.get(k) or [k, None, None, None, None, None, 1])
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out

def money_wide(site, ref):
    """Money across every payer -> site["mw"]: the budget laws, what each agency committed, companies paid by more than one agency,
    and what the federal spending data leaves out. Refuses unknown kinds of source and English with no Spanish."""
    rd = lambda n: list(csv.DictReader(open(ref / n, encoding="utf-8"), delimiter="|")) if (ref / n).exists() else []
    es, missing, w = site.get("es", {}), [], {}
    laws = rd("budget_laws.csv")
    for r in laws:
        if not r["url"].startswith("https://"): raise ValueError(f"budget_laws.csv: link must be https: {r['url']}")
        if r["kind"] not in ("detention", "enforcement", "border", "states", "courts"): raise ValueError(f"budget_laws.csv: kind {r['kind']!r}")
        for x in (r["what"], r["to"]):
            if x not in es and x not in ("ICE", "DHS", "CBP"): missing.append(x)
    if laws: w["laws"] = [[r["law"], r["signed"], r["section"], r["to"], int(r["musd"]), r["what"], r["until"], r["kind"], r["url"]] for r in laws]
    g, M = site.get("gov", {}), site.get("money", {})
    ag = []
    if M.get("total"): ag.append(["ICE", M["total"], {str(y): m for y, m in (site.get("vendors_meta") or {}).get("by_fy", [])}])
    for k, P in (g.get("money") or {}).get("progs", {}).items(): ag.append([k, P["total_musd"], P.get("by_fy_musd", {})])
    dod = (g.get("money") or {}).get("dod", [])
    if dod: ag.append(["ARMY", round(sum(a["obligated_musd"] for a in dod), 1), {}])
    if g.get("pay"): ag.append(["STATE", round(sum(r[1] for r in g["pay"]), 2), {}])
    w["agencies"] = ag
    lists = {}
    ice = rd("ice_payees_all.csv")
    if ice: lists["ICE"] = [(r["recipient"], float(r["musd"])) for r in ice]
    for r in rd("other_money_payees.csv"):
        lists.setdefault(r["agency"], []).append((r["recipient"], float(r["musd"])))
    for a in dod: lists.setdefault("ARMY", []).append((a["recipient"], a["obligated_musd"]))
    par = {r["recipient"]: r["parent"] for r in rd("ice_recipient_parents.csv") if r.get("parent")}
    if len(lists) >= 2: w["shared"] = shared_payees(lists, par)
    costs = rd("detention_costs.csv")              # bed rates and purchases from GAO, by hand
    for r in costs:
        if r["kind"] not in GOV_KINDS or not r["url"].startswith("https://"): raise ValueError(f"detention_costs.csv: {r['key']}: bad kind or link")
        if r["text"] not in es: missing.append(r["text"])
    if costs: w["costs"] = [[r["key"], float(r["value"]), r["text"], r["source"], r["url"], r["kind"]] for r in costs]
    subs = (M.get("subs") or []); awards = rd("ice_awards.csv")
    fill = {"{subs_musd}": f"${round(sum(x[2] for x in subs)):,} million", "{contract_musd}": f"${M.get('total', 0) / 1000:.1f} billion",
            "{offers_missing}": f"{sum(1 for r in awards if not r['offers']):,}", "{awards_n}": f"{len(awards):,}"}
    gaps = []
    for r in rd("money_gaps.csv"):
        if r["kind"] not in GOV_KINDS or not r["url"].startswith("https://"): raise ValueError(f"money_gaps.csv: bad source in {r}")
        if r["text"] not in es: missing.append(r["text"])
        gaps.append([r["text"], r["source"], r["url"], r["kind"]])
    if gaps: w["gaps"], w["fill"] = gaps, fill
    if missing: raise ValueError(f"{len(missing)} money lines have no Spanish in es_text.csv, e.g. {missing[:3]}")
    return w




def prefill_text(html, hot=None):
    """Writes the English wording into the page's empty labelled elements, so a slow phone shows the menu, the family steps
    and their phone numbers while the data is still arriving. The script fills the same elements again (in Spanish, if
    chosen) once it runs. Only plain text strings are written; anything computed is left to the script."""
    import subprocess
    a = html.find("const T = {")
    if a < 0: return html
    b = html.find("\n};", a) + 3
    js = "const T=(" + html[a + 10:b - 1] + ");const o={};for(const[k,v]of Object.entries(T.en))if(typeof v==='string')o[k]=v;process.stdout.write(JSON.stringify(o));"
    try: en = json.loads(subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", timeout=60, check=True).stdout)
    except Exception as e:
        print(f"prefill skipped: {e}"); return html
    import html as H
    head, cut = html[:html.find("<script")], html.find("<script")
    head = re.sub(r'(<[a-z0-9]+\b[^<>]*\sdata-t="([a-zA-Z0-9_]+)"[^<>]*>)(</)', lambda m: m.group(1) + (H.escape(en[m.group(2)], quote=False) if m.group(2) in en else "") + m.group(3), head)
    hot = hot or {}      # confirmed help lines: the number written in, and an unconfirmed line's paragraph hidden, as the script would
    head = re.sub(r'(<span\b[^<>]*\sdata-hl="([a-z_]+)"[^<>]*>)(</span>)', lambda m: m.group(1) + (H.escape(hot[m.group(2)][0]) if hot.get(m.group(2)) and hot[m.group(2)][0] else "") + m.group(3), head)
    head = re.sub(r'<([a-z0-9]+)\b([^<>]*\sdata-hlp="([a-z_]+)")', lambda m: m.group(0) if hot.get(m.group(3)) else f"<{m.group(1)} hidden{m.group(2)}", head)
    return head + html[cut:]


def rd_pipe(path):
    return list(csv.DictReader(open(path, encoding="utf-8"), delimiter="|")) if Path(path).exists() else []


PAC_LIMIT_CYCLE = 10_000     # a multicandidate PAC may give a candidate $5,000 per election: primary and general in one two-year cycle


def state_officials(site, ref):
    """Governors, the heads of local jails that hold people for ICE, and former officials lobbying for detention
    companies, for the Politicians tab. Each list carries only rows that passed their own checks."""
    out = {}
    gov = rd_pipe(ref / "governors.csv")       # every state is listed; a governor whose official site failed the check is marked, not dropped
    if gov:
        a287 = list(csv.DictReader(open(ref / "287g_agencies.csv", encoding="utf-8"))) if (ref / "287g_agencies.csv").exists() else []
        abbr = {v: k for k, v in STATE_NAMES.items()}
        n, stat = {}, {}
        for r in a287:
            st = abbr.get(STATE_FIX.get(r["state"].upper(), r["state"].upper()), "")
            n[st] = n.get(st, 0) + 1
            nm, sn = r["agency"], STATE_NAMES.get(st, "").title()
            if sn and nm.startswith(sn + " ") and not re.search(r"\b(County|City|Town|Village|Parish|Beach|College|University)\b", nm) and (not nm.endswith("Police Department") or "State Police" in nm):
                stat.setdefault(st, []).append(nm)                                    # an agency named for the state: a state agency
        bans = {b["state"] for b in (csv.DictReader(open(ref / "state_287g_bans.csv", encoding="utf-8")) if (ref / "state_287g_bans.csv").exists() else [])}
        held, fac = {}, {}
        for f in site["facilities"].values():
            st = f.get("state"); fac[st] = fac.get(st, 0) + 1
        sites = {}
        for r in rd_pipe(ref / "state_sites.csv"): sites.setdefault(r["state"], []).append(r["name"])
        out["gov"] = [[r["state"], r["name"], r["party"], r["start"], r["site"], n.get(r["state"], 0), sorted(set(stat.get(r["state"], []))), r["state"] in bans, sites.get(r["state"], []), fac.get(r["state"], 0), "" if r["ok"] == "1" else r["checked"]] for r in gov]
        out["gov_checked"] = max(r["checked"] for r in gov)
    code_of = {}
    for c in site.get("contracts", []):
        if c[7]: code_of[c[7]] = c[0]
    loc = [[c, site["facilities"][c]["name"], site["facilities"][c].get("state", "")] + site["facilities"][c]["runby"] for c in site["facilities"] if site["facilities"][c].get("runby")]
    if loc:
        out["local"] = sorted(loc, key=lambda r: (r[2], r[1]))
        om = json.loads((ref / "officials_meta.json").read_text(encoding="utf-8")) if (ref / "officials_meta.json").exists() else {}
        out["local_cov"] = [om.get("local_shown", len(loc)), om.get("local_candidates", len(loc))]     # how many of the jails on file have a confirmed official
    cp, cm = rd_pipe(ref / "country_pacs.csv"), rd_pipe(ref / "country_pacs_money.csv")
    if cp and cm:
        money = {}
        cp = [r for r in cp if not r["basis"].startswith("affiliate") or r["source"].startswith("https://www.fec.gov/")]   # an affiliate counts only on the FEC's own record
        keep = {r["committee_id"] for r in cp}; held = []
        for r in cm:
            if r["committee_id"] not in keep: continue
            if r["kind"] == "G" and int(r["usd"]) > PAC_LIMIT_CYCLE: held.append(f'{r["committee_id"]} to {r["bioguide"]} ${int(r["usd"]):,}'); continue   # over what a PAC may give from its own funds: held back for review
            money.setdefault(r["bioguide"], []).append([r["committee_id"], r["kind"], int(r["usd"]), int(r["count"])])
        if held: print("COUNTRY PAC AMOUNTS HELD FOR REVIEW (own funds above the legal limit per cycle): " + "; ".join(held), file=sys.stderr)
        meta = json.loads((ref / "country_pacs_meta.json").read_text(encoding="utf-8")) if (ref / "country_pacs_meta.json").exists() else {}
        out["cpac"] = {"pacs": [[r["committee_id"], r["name"], r["country"], r["basis"], r["source"]] for r in cp], "money": money, "read": meta.get("read", ""), "cycle": meta.get("cycle", 0), "held": len(held)}
    fa = rd_pipe(ref / "fara_principals.csv")
    if fa:
        firms = {core(r["firm"]): r["firm"] for r in rd_pipe(ref / "lobbying_firms.csv") if "personal name" not in r["firm"]}
        fmap = {r["registrant"]: firms[core(r["registrant"])] for r in fa if core(r["registrant"]) in firms}     # registered foreign agent -> the same firm's name in the lobbying records
        meta = json.loads((ref / "fara_meta.json").read_text(encoding="utf-8")) if (ref / "fara_meta.json").exists() else {}
        out["fara"] = {"rows": [[r["country"], r["principal"].strip("'\" "), r["registrant"], int(r["reg_number"]), r["since"], r["exhibit_url"]] for r in fa], "both": sorted(fmap), "fmap": fmap, "read": meta.get("read", "")}
    rev = rd_pipe(ref / "lobbying_former_officials.csv")
    if rev:                                # one entry per person and company: the newest wording of the post they filed, every firm, the full span
        g = {}
        for r in rev:
            k = (r["company"], r["lobbyist"]); o = g.setdefault(k, {"cp": "", "cpy": 0, "firms": [], "y1": 9999, "y2": 0})
            y1, y2 = int(r["first_year"]), int(r["last_year"])
            if (y2, len(r["covered_position"])) > (o["cpy"], len(o["cp"])): o["cp"], o["cpy"] = r["covered_position"], y2
            if r["firm"] not in o["firms"]: o["firms"].append(r["firm"])
            o["y1"], o["y2"] = min(o["y1"], y1), max(o["y2"], y2)
        order = ["GEO", "CC", "MTC", "CSI"]
        out["rev"] = [[c, n, o["cp"], " and ".join(o["firms"]), o["y1"], o["y2"]] for (c, n), o in sorted(g.items(), key=lambda kv: (order.index(kv[0][0]) if kv[0][0] in order else 9, -kv[1]["y2"], kv[0][1]))]
    return out

def firm_cards(ref):
    """One card per lobbying firm hired by a detention or ICE flight company: who paid it for that work, its foreign clients
    (FARA), the countries among them that ICE pays to take deportees, its other clients and political money (lda.gov,
    when firm_profiles.py has run), and its lobbyists who list a past government post. Built from public filings only;
    private contributors are never named (firm_profiles.py does not keep them)."""
    lf = [r for r in rd_pipe(ref / "lobbying_firms.csv") if "personal name" not in r["firm"]]
    if not lf: return {}
    CO = {"GEO": "GEO Group", "CC": "CoreCivic", "MTC": "Management & Training Corp", "CSI": "CSI Aviation"}
    names = {}
    for r in lf: names.setdefault(core(r["firm"]), r["firm"])
    out = {n: {"det": [], "fara": [], "via": [], "reg": "", "pay": [], "former": [], "clients": [], "n_clients": 0, "money": [], "m_kind": {}, "partial": False} for n in names.values()}
    for r in lf: out[names[core(r["firm"])]]["det"].append([CO.get(r["company"], r["company"]), int(r["usd"])])
    pay = {r["country"]: float(r["paid_musd"] or 0) for r in rd_pipe(ref / "third_country_payments.csv")}
    for r in rd_pipe(ref / "fara_principals.csv"):
        pc = f' {core(r["principal"])} '
        for k, m in names.items():                # another registered agent hired through this firm ("X on behalf of ...", "... via X")
            if f" {k} " in pc and core(r["registrant"]) != k: out[m]["via"].append([r["registrant"], r["country"], r["principal"].strip("'\" "), r["since"], r["exhibit_url"]])
        n = names.get(core(r["registrant"]))
        if not n: continue
        o = out[n]; o["reg"] = o["reg"] or f'{r["registrant"]} (No. {r["reg_number"]})'
        o["fara"].append([r["country"], r["principal"].strip("'\" "), r["since"], r["exhibit_url"]])
        if r["country"] in pay and r["country"] not in o["pay"]: o["pay"].append(r["country"])
    seen = {}
    for r in rd_pipe(ref / "lobbying_former_officials.csv") + [dict(x, company="") for x in rd_pipe(ref / "firm_former.csv")]:
        n = names.get(core(r["firm"]))
        if not n: continue
        k = (n, r["lobbyist"]); o = seen.setdefault(k, [r["covered_position"], set()])
        if len(r["covered_position"]) > len(o[0]): o[0] = r["covered_position"]
        if r.get("company"): o[1].add(CO.get(r["company"], r["company"]))
    for (n, who), (cp, cos) in sorted(seen.items()): out[n]["former"].append([who, cp, sorted(cos)])
    awards = {}
    for r in rd_pipe(ref / "ice_awards.csv"):
        k = core(r["recipient"]); awards[k] = awards.get(k, 0) + int(float(r.get("window_usd") or r["amount_usd"] or 0))      # what ICE committed to it in the contract window (ice_awards_meta.json)
    pc, donors = {}, trail_people(ref)
    for r in rd_pipe(ref / "firm_clients.csv"):
        n = names.get(core(r["firm"]))
        if not n: continue
        o = out[n]
        if r["client"] == PERSONAL or (is_person(r["client"]) and not on_trail(r["client"], r, donors)):     # private people off the trail are counted, not named
            k = pc.setdefault(n, [PERSONAL, 0, 0, 0, 0, 0, r["first"], r["last"], 0, 0]); k[1] += int(r["usd"]); k[2] += int(r["filings"]); k[9] += 1
            k[6], k[7] = min(k[6], r["first"]), max(k[7], r["last"]); continue
        o["n_clients"] += 1
        o["clients"].append([r["client"], int(r["usd"]), int(r["filings"]), int(r["ice"]), int(r["dhs"]), int(r["imm"]), r["first"], r["last"], awards.get(core(r["client"]), 0)])
    for n, k in pc.items(): out[n]["n_clients"] += k[9]; out[n]["clients"].append(k[:9] + [k[9]])
    mm = {}
    for r in rd_pipe(ref / "firm_money.csv"):
        n = names.get(core(r["firm"]))
        if not n: continue
        k = mm.setdefault((n, recipient(r["recipient"]), r["kind"]), [0, 0]); k[0] += int(r["usd"]); k[1] += int(r["gifts"])      # one spelling per official
        out[n]["m_kind"][r["kind"]] = out[n]["m_kind"].get(r["kind"], 0) + int(r["usd"])
    for (n, to, kind), (u, g) in mm.items(): out[n]["money"].append([to, kind, u, g])
    meta = json.loads((ref / "firm_meta.json").read_text(encoding="utf-8")) if (ref / "firm_meta.json").exists() else {}
    for n, o in out.items():
        o["partial"] = bool((meta.get("firms") or {}).get(n, {}).get("partial"))
        o["clients"].sort(key=lambda c: (-(c[3] + c[4] + c[5] > 0 or c[8] > 0), -c[1]))       # clients that lobbied ICE/DHS or on immigration, or hold ICE contracts, first
        o["n_ice"] = sum(1 for c in o["clients"] if c[3] or c[4] or c[5]); o["n_con"] = sum(1 for c in o["clients"] if c[8])
        o["c_usd"] = sum(c[1] for c in o["clients"]); o["m_usd"] = sum(m[2] for m in o["money"]); o["n_rec"] = len(o["money"])
        o["clients"] = o["clients"][:60]; o["money"].sort(key=lambda m: -m[2]); o["money"] = o["money"][:40]
        o["fara"].sort(key=lambda f: (f[0], f[1]))
    am = json.loads((ref / "ice_awards_meta.json").read_text(encoding="utf-8")) if (ref / "ice_awards_meta.json").exists() else {}
    return {"cards": out, "read": meta.get("read", ""), "years": meta.get("years", []), "cw": [am.get("from", "")[:7], am.get("to", "")[:7]], "pat": firm_patterns(ref, lf, out, names, awards)}


def _first_last(n):
    """'Adam B. Schiff' / 'John Cornyn Jr.' -> ('ADAM', 'SCHIFF'): first and last name, without middle names, initials or suffixes."""
    w = [x for x in re.sub(r"[^A-Za-z' -]", " ", re.sub(r"\(.*?\)", " ", n or "")).upper().split() if x not in ("JR", "SR", "II", "III", "IV")]
    return (w[0], w[-1]) if len(w) >= 2 else None


def firm_patterns(ref, lf, cards, names, awards):
    """Patterns across the firms, each set beside a comparison where the records allow one. Counts only; no judgment.
      fara      the share of the detention companies' outside lobbying fees paid to firms that are also registered foreign
                agents, by company, and (base) the same share of every firm's fees in one quarter, from firm_base.py
      former    lobbyists listing a past government post on detention-company accounts: how many work at those firms
      pay       each country the U.S. paid to take deported people: its registered foreign agents, and which of them also
                lobby for a detention company
      members   (after firm_profiles.py) the firms' reported political money matched to members of Congress, members on the
                committees that oversee ICE set beside the other members
      shared    (after firm_profiles.py) ICE contractors that hire one of the firms the detention companies hire"""
    fa = rd_pipe(ref / "fara_principals.csv"); regs = {core(r["registrant"]) for r in fa}
    CO = {"GEO": "GEO Group", "CC": "CoreCivic", "MTC": "Management & Training Corp", "CSI": "CSI Aviation"}
    out = {}
    by, allf = {}, rd_pipe(ref / "lobbying_firms.csv")                 # the personal-name registrants count in the totals, never as a foreign agent
    isf = lambda r: "personal name" not in r["firm"] and core(r["firm"]) in regs
    for r in allf: o = by.setdefault(CO.get(r["company"], r["company"]), [0, 0]); o[0] += int(r["usd"]); o[1] += int(r["usd"]) if isf(r) else 0
    tot = sum(int(r["usd"]) for r in allf); fara = sum(int(r["usd"]) for r in allf if "personal name" not in r["firm"] and core(r["firm"]) in regs)
    out["fara"] = {"tot": tot, "fara": fara, "firms": sorted(n for n in cards if core(n) in regs), "by": [[k, v[0], v[1]] for k, v in sorted(by.items(), key=lambda kv: -kv[1][0])]}
    bm = json.loads((ref / "firm_base.json").read_text(encoding="utf-8")) if (ref / "firm_base.json").exists() else {}
    base = rd_pipe(ref / "firm_income_all.csv")
    if bm and base:
        bt = sum(int(r["usd"]) for r in base); bf = sum(int(r["usd"]) for r in base if core(r["firm"]) in regs)
        out["fara"]["base"] = {"tot": bt, "fara": bf, "firms": len(base), "fara_firms": sum(1 for r in base if core(r["firm"]) in regs), "q": f'{bm["year"]} Q{["first_quarter", "second_quarter", "third_quarter", "fourth_quarter"].index(bm["period"]) + 1}'}
    rev = rd_pipe(ref / "lobbying_former_officials.csv")
    ppl = {}
    for r in rev: ppl.setdefault(r["lobbyist"], set()).add(core(r["firm"]))
    out["former"] = {"all": len(ppl), "fara": sum(1 for v in ppl.values() if v & regs)}
    pay = rd_pipe(ref / "third_country_payments.csv")
    if pay:
        rows = []
        for p in pay:
            ag = sorted({r["registrant"] for r in fa if r["country"] == p["country"]})
            rows.append([p["country"], len(ag), [names[core(a)] for a in ag if core(a) in names]])
        out["pay"] = rows
    fm = rd_pipe(ref / "firm_money.csv")
    out["_money"] = [[r["firm"], recipient(r["recipient"]), r["kind"], int(r["usd"])] for r in fm if r["kind"] == "campaign"]        # matched to members after the member list is built (firm_members)
    fc = rd_pipe(ref / "firm_clients.csv")
    if fc:
        sh = {}
        for r in fc:
            n = names.get(core(r["firm"])); a = awards.get(core(r["client"]), 0)
            if n and a and core(r["client"]) not in ("GEO GROUP", "CORECIVIC", "MANAGEMENT TRAINING", "CSI AVIATION"):
                o = sh.setdefault(core(r["client"]), [r["client"], a, set()]); o[2].add(n)          # one row per company, however each firm spelled it
        out["shared"] = [[c, a, sorted(f)] for c, a, f in sorted(sh.values(), key=lambda v: -v[1])]
    return out


def firm_members(pat, members):
    """Match the firms' campaign money to members of Congress by first and last name; a name that fits more than one member,
    or none, is left unmatched and counted. members: the Politicians list (bioguide, name, chamber, party, ..., [oversight
    committees] at 7, serving at 11). Returns per-member totals and the committee/other comparison."""
    money = pat.pop("_money", [])
    if not money: return
    idx = {}
    for m in members:
        k = _first_last(m[1])
        if k: idx.setdefault(k, []).append(m)
    got, un, un_usd = {}, set(), 0
    for firm, rec, kind, usd in money:
        k = _first_last(rec); hit = idx.get(k, []) if k else []
        if len(hit) != 1: un.add(rec); un_usd += usd; continue
        o = got.setdefault(hit[0][0], [0, set()]); o[0] += usd; o[1].add(firm)
    serving = [m for m in members if m[11]]
    grp = lambda f: [m for m in serving if f(m)]
    on, off = grp(lambda m: bool(m[7])), grp(lambda m: not m[7])
    stat = lambda L: [len(L), sum(1 for m in L if m[0] in got), sum(got[m[0]][0] for m in L if m[0] in got)]
    pat["members"] = {"on": stat(on), "off": stat(off), "top": [[b, v[0], sorted(v[1])] for b, v in sorted(got.items(), key=lambda kv: -kv[1][0])[:15]],
                      "matched_usd": sum(v[0] for v in got.values()), "un_n": len(un), "un_usd": un_usd}


VENDOR_CATS = [("tech", ("D", "7")), ("gear", ("10", "12", "13", "58", "63", "66", "84")), ("move", ("V", "23")), ("med", ("Q", "65")),
               ("prof", ("R", "B", "U")), ("guard", ("S",)), ("build", ("Y", "Z", "X"))]


def vendor_cat(psc):
    """What an award pays for, from its federal product/service code: tech, gear, move, med, prof, guard, build or other."""
    for k, pre in VENDOR_CATS:
        if any(psc.startswith(x) for x in pre): return k
    return "other"


def vl_core(name):
    from vendor_lobbying import core
    return core(name)


PARTY_CTYPE, CAND_CTYPE = {"X", "Y", "Z"}, {"H", "S", "P"}


def jfc_kind(name, ctype, desig):
    """party (a party committee), cand (a candidate's own campaign), lead (a leadership PAC) or pac (any other committee).
    The FEC's committee type decides; the name is used only when the FEC gave none."""
    if ctype in PARTY_CTYPE: return "party"
    if ctype in CAND_CTYPE or desig in ("P", "A"): return "cand"      # a principal or authorized campaign committee
    if re.search(r"\bFOR PRESIDENT\b", name.upper()): return "cand"   # a campaign the FEC has since re-filed as a PAC (Trump 2024 became a leadership PAC after the election)
    if desig == "D": return "lead"
    if ctype: return "pac"
    n = name.upper()
    if re.search(r"\b(REPUBLICAN|DEMOCRATIC|NRCC|NRSC|DCCC|DSCC|NATIONAL COMMITTEE)\b", n): return "party"
    if re.search(r"\bFOR (CONGRESS|SENATE|SENATOR|PRESIDENT|US SENATE|U\.S\. SENATE)\b|\bFRIENDS OF\b|\bFOR [A-Z]+$", n): return "cand"
    return "pac"


def jfc_party(name, party):
    p = (party or "").upper()[:3]
    if p in ("REP", "DEM", "IND"): return p[0]
    n = name.upper()
    if re.search(r"\b(REPUBLICAN|NRCC|NRSC)\b", n): return "R"
    if re.search(r"\b(DEMOCRATIC|DEMOCRAT|DCCC|DSCC)\b", n): return "D"
    return ""


def jfc_flows(totals, flows, pacs, meta):
    """Where the joint fundraisers that took detention-contractor money sent what they raised (jfc_flows.py).
    Per fundraiser and cycle the contractor share is contractor / receipts; a recipient's estimated contractor dollars are
    that share times what it was sent. Money is pooled, so this is an estimate, and the page says so."""
    share, funds = {}, {}
    gave = {}
    for r in pacs:
        if r.get("recipient_id"): gave.setdefault(r["recipient_id"], set()).add(r["pac"])
    for t in totals:
        k = (t["jfc_id"], int(t["cycle"])); rc, co = int(t["receipts"] or 0), int(t["contractor"] or 0)
        share[k] = co / rc if rc >= co > 0 else None
        f = funds.setdefault(t["jfc_id"], {"name": t["jfc"], "co": 0, "rc": 0, "sent": 0, "known": True, "to": {}})
        f["co"] += co; f["rc"] += rc; f["known"] &= share[k] is not None
    rec = {}
    for r in flows:
        k = (r["jfc_id"], int(r["cycle"])); usd = int(r["usd"]); f = funds.get(r["jfc_id"])
        if not f: continue
        f["sent"] += usd; f["to"][r["recipient"]] = f["to"].get(r["recipient"], 0) + usd
        o = rec.setdefault(r["recipient_id"], {"name": r["recipient"], "usd": 0, "est": 0.0, "jfcs": set(), "kind": jfc_kind(r["recipient"], r.get("ctype", ""), r.get("designation", "")),
                                               "party": jfc_party(r["recipient"], r.get("party", ""))})
        o["usd"] += usd; o["jfcs"].add(r["jfc_id"])
        if share.get(k): o["est"] += usd * share[k]
    by = {}
    for o in rec.values():
        g = by.setdefault(o["kind"] + o["party"], [0, 0.0, 0]); g[0] += o["usd"]; g[1] += o["est"]; g[2] += 1
    top = sorted(rec.values(), key=lambda o: -o["usd"])
    return {"n": len(funds), "co": sum(f["co"] for f in funds.values()), "rc": sum(f["rc"] for f in funds.values()), "sent": sum(f["sent"] for f in funds.values()),
            "est": round(sum(o["est"] for o in rec.values())), "recips": len(rec),
            "by": sorted([[k, v[0], round(v[1]), v[2]] for k, v in by.items()], key=lambda x: -x[1]),
            "top": [[o["name"], o["usd"], round(o["est"]), len(o["jfcs"]), o["kind"], o["party"]] for o in top[:40]],
            "shared": sorted([[o["name"], len(o["jfcs"]), o["usd"], round(o["est"]), o["kind"], o["party"]] for o in rec.values() if len(o["jfcs"]) > 1], key=lambda x: (-x[1], -x[2]))[:25],
            "funds": sorted([[f["name"], f["co"], f["rc"], f["sent"], sorted(gave.get(cid, [])), [[n, u] for n, u in sorted(f["to"].items(), key=lambda kv: -kv[1])[:5]], f["known"]]
                             for cid, f in funds.items()], key=lambda x: -x[1]),
            "read": meta.get("read", ""), "cycles": meta.get("cycles", [])}


def vendors(ref):
    """ICE contractors other than detention-site operators, grouped by what they are paid for. From ice_awards.csv (ICE contracts
    of $1 million or more, dollars committed inside the window). A company whose money is mostly for running detention sites (code
    S206) is on the Companies tab instead and is left out here. Lobbying on ICE comes from vendor_lobbying.csv when present."""
    rd = lambda n: list(csv.DictReader(open(Path(ref) / n, encoding="utf-8"), delimiter="|")) if (Path(ref) / n).exists() else []
    A = rd("ice_awards.csv")
    if not A: return {}
    parent = {r["recipient"]: r["parent"] for r in rd("ice_recipient_parents.csv")}
    lob = {r["recipient"]: r for r in rd("vendor_lobbying.csv")}
    co = {}
    for a in A:
        try: w = float(a["window_usd"] or 0)
        except ValueError: w = 0
        c = co.setdefault(a["recipient"], {"tot": 0.0, "det": 0.0, "cat": {}, "aw": []})
        c["tot"] += w; c["det"] += w if a["psc"] == "S206" else 0
        k = vendor_cat(a["psc"]); c["cat"][k] = c["cat"].get(k, 0) + w
        c["aw"].append([a["award_id"], (a["what"] or "").strip().capitalize()[:160], round(w), a["uid"], a["pop_city"].title(), a["pop_state"]])
    out = []
    for name, c in co.items():
        if c["tot"] < 1_000_000 or c["det"] > c["tot"] / 2: continue          # small in this window, or a detention operator (Companies tab)
        cat = max(c["cat"], key=c["cat"].get)
        aw = sorted(c["aw"], key=lambda x: -x[2])[:6]
        L = lob.get(name, {})
        out.append([name, parent.get(name, ""), cat, round(c["tot"]), len(c["aw"]), aw,
                    [int(L.get("usd") or 0), int(L.get("filings") or 0), int(L.get("ice_filings") or 0), int(L.get("imm_filings") or 0), L.get("example", ""), L.get("matched", "") if L.get("matched", "") != vl_core(name) else ""] if L else None])
    out.sort(key=lambda r: -r[3])
    meta = json.loads((Path(ref) / "ice_awards_meta.json").read_text(encoding="utf-8")) if (Path(ref) / "ice_awards_meta.json").exists() else {}
    lm = json.loads((Path(ref) / "vendor_lobbying_meta.json").read_text(encoding="utf-8")) if (Path(ref) / "vendor_lobbying_meta.json").exists() else {}
    return {"rows": out, "from": meta.get("from", ""), "to": meta.get("to", ""), "read": meta.get("read", ""), "lob_read": lm.get("read", ""), "lob_from": lm.get("from", "")}


HAND_DAYS = 30                       # a line checked by hand is shown for this long, then hidden until checked again
PRIORITY_LINES = ("dril", "ciam", "consular", "orr", "eoir")

def hotlines(ref, today=None):
    """Help lines and links that passed this week's check on their official page: {key: [number or "", source page, checked]}.
    When the weekly check cannot confirm a line (the official site blocks GitHub's servers), a check by hand in
    hotlines_manual.csv (key | checked | source | note) shows it for HAND_DAYS days, marked [.., "hand"] so the page says so."""
    rd = lambda n: list(csv.DictReader(open(Path(ref) / n, encoding="utf-8"), delimiter="|")) if (Path(ref) / n).exists() else []
    today = dt.date.fromisoformat(today) if today else dt.date.today()
    want = {r["key"]: r for r in rd("hotlines.csv")}
    out = {r["key"]: [want[r["key"]]["number"], r["source"], r["checked"]] for r in rd("hotlines_checked.csv") if r["ok"] == "1" and r["key"] in want}
    for r in rd("hotlines_manual.csv"):
        k = r["key"]
        if k not in want: raise ValueError(f"hotlines_manual.csv: {k!r} is not in hotlines.csv")
        if not r["source"].startswith("https://"): raise ValueError(f"hotlines_manual.csv: {k} needs the official page it was checked on")
        age = (today - dt.date.fromisoformat(r["checked"])).days
        if age < 0: raise ValueError(f"hotlines_manual.csv: {k} checked in the future")
        if k in out: continue                                       # the automatic check passed: that wins
        if age <= HAND_DAYS:
            out[k] = [want[k]["number"], r["source"], r["checked"], "hand"]
            if age > HAND_DAYS - 7: print(f"HAND-CHECKED LINE {k} is hidden after {r['checked']} + {HAND_DAYS} days: check it again on {r['source']}")
        else: print(f"HAND-CHECKED LINE {k} EXPIRED (checked {r['checked']}); hidden until it is checked again")
    hidden = [k for k in PRIORITY_LINES if k in want and k not in out]
    if hidden: print("FAMILY HELP LINES HIDDEN (not confirmed this week): " + ", ".join(hidden))
    return out


def social_list(ref):
    """Organizations' Bluesky and Instagram accounts that passed social_check.py, grouped one entry per organization:
    [name, kind, state ("" = national), language, website, [[platform, url], ...]]. Only accounts marked ok are shown."""
    src, chk = ref / "social_orgs.csv", ref / "social_checked.csv"
    if not (src.exists() and chk.exists()): return {}
    ok = {(r["platform"], r["account_url"]) for r in csv.DictReader(open(chk, encoding="utf-8"), delimiter="|") if r["ok"] == "1"}
    orgs = {}
    for r in csv.DictReader(open(src, encoding="utf-8"), delimiter="|"):
        if (r["platform"], r["account_url"]) not in ok: continue
        o = orgs.setdefault(r["org"], [r["org"], r["kind"], r["state"] if r["scope"] == "state" else "", r["language"], "https://" + r["website"], []])
        o[5].append([r["platform"], r["account_url"]])
    prof = {r["org"]: r for r in csv.DictReader(open(ref / "social_profiles.csv", encoding="utf-8"), delimiter="|")} if (ref / "social_profiles.csv").exists() else {}
    desc = {r["org"]: r for r in csv.DictReader(open(ref / "social_orgs_desc.csv", encoding="utf-8"), delimiter="|")} if (ref / "social_orgs_desc.csv").exists() else {}
    missing = sorted(set(orgs) - set(desc))
    if missing: print("ORGANIZATIONS WITHOUT A DESCRIPTION in social_orgs_desc.csv: " + "; ".join(missing), file=sys.stderr)
    for o in orgs.values():
        o[5].sort(key=lambda x: x[0] != "bluesky")         # Bluesky first
        p, d = prof.get(o[0], {}), desc.get(o[0], {}); o += [p.get("city", ""), p.get("state", ""), d.get("desc_en", ""), d.get("desc_es", "")]   # where it is based (IRS record) and what it does
    meta = json.loads((ref / "social_meta.json").read_text(encoding="utf-8")) if (ref / "social_meta.json").exists() else {}
    return {"checked": meta.get("checked", ""), "orgs": sorted(orgs.values(), key=lambda o: (o[2], o[0].lower()))}

DISPUTE_KINDS = {"lawsuit", "law", "order", "charge", "investigation"}
DISPUTE_COLS = ["id", "date", "state", "place", "kind", "started_by", "federal_party", "local_party", "officials", "what_en", "what_es", "status_en", "status_es", "status_date", "facility_codes", "source_url", "status_url", "final"]
LAWCOM = re.compile(r"^(House|Senate) Committee on (the Judiciary|Homeland Security)(?!.*Appropriations)")   # the committees that write immigration law
US_STATE_CODES = set("US AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR GU VI AS MP".split())

OFFICIAL_HOSTS = re.compile(r"(\.gov|\.gov\.[a-z]{2}|\.us|uscourts\.gov|courtlistener\.com|hennepinattorney\.org|cookcountystatesattorney\.org|chicityclerk\.s3\.[a-z0-9-]+\.amazonaws\.com)$")
COPY_HOSTS = {"clearinghouse.net", "store.ilrc.org", "www.ilrc.org", "ilrc.org"}

def source_kind(url):
    """official: the court, the government body or the legislature itself. copy: a court record or law hosted by someone
    else (a docket archive, a news site's copy of a filing). news: a news report. The page labels the last two."""
    from urllib.parse import urlparse
    u = urlparse(url or ""); h = (u.hostname or "").lower()
    if not h: return ""
    if OFFICIAL_HOSTS.search(h): return "official"
    if h in COPY_HOSTS or u.path.lower().endswith(".pdf"): return "copy"
    return "news"

def disputes_list(ref, facilities, today=None):
    """Formal disputes on public record between ICE/DHS/DOJ and state or local governments, researched by hand
    (data/reference/ice_local_disputes.csv; rules in the project spec). Rows are rejected loudly rather than shown wrong:
    [date, state, place, kind, started_by, federal_party, local_party, what_en, what_es, status_en, status_es, status_date, [facility codes], source_url, status_url]"""
    f = Path(ref) / "ice_local_disputes.csv"
    if not f.exists(): return []
    rows = list(csv.DictReader(open(f, encoding="utf-8"), delimiter="|"))
    if rows and list(rows[0].keys()) != DISPUTE_COLS: raise ValueError(f"ice_local_disputes.csv: columns must be {DISPUTE_COLS}")
    today = today or dt.date.today().isoformat(); seen = set(); out = []
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for r in rows:
        r = {k: (v or "").strip() for k, v in r.items()}; i = r["id"]
        def bad(why): raise ValueError(f"ice_local_disputes.csv row {i or '?'}: {why}")
        if not i or i in seen: bad("missing or repeated id")
        seen.add(i)
        for k in ("date", "state", "place", "kind", "started_by", "federal_party", "local_party", "what_en", "what_es", "source_url"):
            if not r[k]: bad(f"{k} is empty")
        if not iso.match(r["date"]) or r["date"] > today: bad(f"bad or future date {r['date']!r}")
        if r["state"] not in US_STATE_CODES: bad(f"unknown state {r['state']!r}")
        if r["kind"] not in DISPUTE_KINDS: bad(f"kind must be one of {sorted(DISPUTE_KINDS)}")
        if r["started_by"] not in ("federal", "state_local"): bad("started_by must be federal or state_local")
        for k in ("source_url", "status_url"):
            if r[k] and not r[k].startswith("https://"): bad(f"{k} must be an https link")
        if bool(r["status_en"]) != bool(r["status_es"]): bad("status needs both English and Spanish")
        if r["status_en"] and not (iso.match(r["status_date"]) and r["status_url"]): bad("a status needs its date and its own source")
        if r["status_date"] and (r["status_date"] < r["date"] or r["status_date"] > today): bad("status date before the dispute or in the future")
        offs = [o.strip() for o in r["officials"].split(";") if o.strip()]       # "Name (role in English / in Spanish)": elected officials and political appointees only
        if any(not re.fullmatch(r"[^()]+ \([^()/]+ / [^()/]+\)", o) for o in offs): bad("officials must be written Name (role / rol), separated by ;")
        if r["final"] not in ("", "Y") or (r["final"] and not r["status_en"]): bad("final is Y (the case or charge is over) or empty, and Y needs a status")
        codes = [c for c in r["facility_codes"].split(";") if c.strip()]
        unk = [c for c in codes if c not in facilities]
        if unk: bad(f"unknown facility codes {unk}")
        out.append([r["date"], r["state"], r["place"], r["kind"], r["started_by"], r["federal_party"], r["local_party"], r["what_en"], r["what_es"], r["status_en"], r["status_es"], r["status_date"], codes, r["source_url"], r["status_url"]])
    ck = Path(ref) / "disputes_checked.csv"                       # made by pipeline/disputes_check.py; a failed link is flagged, not hidden
    fail = {r["url"]: r["checked"] for r in csv.DictReader(open(ck, encoding="utf-8"), delimiter="|") if r["ok"] == "0"} if ck.exists() else {}
    laws = {}
    lf = Path(ref) / "disputed_laws.csv"                            # the state or local law at the center of each dispute, and who wrote it; by hand
    if lf.exists():
        for r in csv.DictReader(open(lf, encoding="utf-8"), delimiter="|"):
            r = {k: (v or "").strip() for k, v in r.items()}
            if r["dispute_id"] not in seen: raise ValueError(f"disputed_laws.csv: unknown dispute {r['dispute_id']!r}")
            if not (r["law_en"] and r["law_es"] and r["law_url"].startswith("https://")): raise ValueError(f"disputed_laws.csv: {r['dispute_id']} needs a name in both languages and an https source")
            au = [x.strip() for x in r["authors"].split(";") if x.strip()]
            if any(not re.fullmatch(r"[^()]+ \([^()/]+ / [^()/]+\)", x) for x in au): raise ValueError(f"disputed_laws.csv: {r['dispute_id']}: authors must be written Name (role / rol)")
            laws.setdefault(r["dispute_id"], []).append([r["law_en"], r["law_es"], r["law_url"], [[x.rsplit(" (", 1)[0], *x.rsplit(" (", 1)[1][:-1].split(" / ")] for x in au]])
    dk = {}
    for f2 in (Path(ref) / "dispute_dockets.csv", Path(ref) / "dispute_dockets_checked.csv"):   # hand list, then what dockets.py found
        for r in (csv.DictReader(open(f2, encoding="utf-8"), delimiter="|") if f2.exists() else []):
            if r["id"] not in seen: raise ValueError(f"{f2.name}: unknown dispute {r['id']!r}")
            dk[r["id"]] = {**dk.get(r["id"], {}), **r}
    for o, r in zip(out, rows):
        o.append(fail.get(o[13], "")); o.append([[x.rsplit(" (", 1)[0], *x.rsplit(" (", 1)[1][:-1].split(" / ")] for x in (y.strip() for y in r["officials"].split(";")) if x]); o.append(laws.get(r["id"], [])); o.append(r["final"] == "Y"); o.append([source_kind(r["source_url"]), source_kind(r["status_url"])])
        k = dk.get(r["id"], {}); lf = k.get("last_filing", "")                      # 20: [docket url, its newest filing, newer than the step on file]
        o.append([k.get("cl_url", ""), lf, bool(lf and lf > (r["status_date"] or r["date"]))] if k.get("cl_url") else [])
    return sorted(out, key=lambda x: x[0], reverse=True)

def _pnorm(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c)).lower()

def person_key(s):
    """First and last name only, lower case, no accents: filings drop middle names, initials and nicknames ("Chuy")."""
    w = re.sub(r"\([^)]*\)|\"[^\"]*\"", " ", _pnorm(s))
    w = re.sub(r",?\s+(jr|sr|ii|iii|iv)\.?\s*$", "", w.strip())
    w = [x for x in re.sub(r"[^a-z\s'-]", " ", w).split() if len(x) > 1]
    return f"{w[0]} {w[-1]}" if len(w) > 1 else ""

def staff_hit(posts, first, last):
    """A lobbyist's reported past post names this official by first and last name ("Chief of Staff, Rep. Vince Fong").
    Surname-only mentions ("Rep Gallego") are not enough: two members can share a surname. Interns are not counted."""
    pat = re.compile(rf"\b(rep|sen|senator|representative|congressman|congresswoman|gov|governor|mayor)\.?\s+{re.escape(first)}\s+([a-z]\.?\s+)?{re.escape(last)}\b")
    return any(pat.search(_pnorm(seg)) and "intern" not in seg.lower() for seg in (posts or "").split(";"))

def vote_summary(code):
    c = re.sub(r"[-PX]", "", code or ""); y, n = c.count("Y"), c.count("N")
    return None if not c else ["for" if not n else "ag" if not y else "mix", y, n]

def dispute_people(site):
    """Everyone the disputes tab names, checked against the rest of the page's records. Worked out here, not in the
    browser, so it is tested and can be read in the page data (DATA.dispute_people): {name as shown: {bg, v:[for|ag|mix, yes, no], t:[[code, detail]]}}.
    dm detention-company committee or staff money; jf joint fundraiser that received it; lf political money from a lobbying
    firm hired by a detention or ICE flight company; fs former staff now lobby at such a firm; ov the overlap rule on
    Politicians; re refused entry to an ICE facility; vi published oversight visits."""
    D, P = site.get("disputes") or [], site.get("pol") or {}
    if not D: return {}
    M, C = P.get("m") or [], P.get("c") or {}
    flagged = {f["bg"] for f in ((P.get("flags") or {}).get("list") or [])}
    names = set()
    for d in D:
        names.update(o[0] for o in d[16]); names.update(a[0] for l in d[17] for a in l[3])
        names.update(g[1] for g in (P.get("gov") or []) if g[0] == d[1])
        names.update(t[0] for t in (site.get("gov_terms") or {}).get(d[1], []))
        names.update(m[1] for m in M if m[4] == d[1] and m[11] and any(LAWCOM.match(c) for c in (m[7] or [])))
    names.update(s[2] for s in site.get("law_sponsors") or [])
    firm_money, staff = {}, []
    for fn, c in ((site.get("firms") or {}).get("cards") or {}).items():
        for n, k, u, g in c.get("money") or []:
            key = person_key(re.sub(r"\s*\([A-Z]{2}(-\d+)?\)\s*$", "", n))
            if key: firm_money.setdefault(key, []).append([fn, u])
        staff += [[fn, posts, cos] for lob, posts, cos in c.get("former") or []]
    visits = (site.get("statements_visits") or []) + [r for r in site.get("statements") or [] if r[2] == "visit"]
    def has(s, key): return f" {key} " in " " + re.sub(r"\s+", " ", re.sub(r"[^a-z\s'-]", " ", _pnorm(s))) + " "
    out = {}
    for nm in sorted(names):
        key = person_key(nm)
        if not key: continue
        first, last = key.split()
        m = next((m for m in M if _pnorm(m[1]) == _pnorm(nm) or _pnorm(re.sub(r'\s*"[^"]*"', "", m[1])) == _pnorm(nm)), None)
        bg = m[0] if m else ""; t = []
        if m and ((m[9] or 0) + (m[10] or 0) > 0 or (m[13] or 0) > 0): t.append(["dm", [(m[9] or 0) + (m[10] or 0), m[13] or 0]])
        if bg and (C.get(bg) or {}).get("jfc"): t.append(["jf", [j[0] for j in C[bg]["jfc"]]])
        if key in firm_money: t.append(["lf", firm_money[key]])
        fs = []
        for fn, posts, cos in staff:
            if staff_hit(posts, first, last) and [fn, cos] not in fs: fs.append([fn, cos])
        if fs: t.append(["fs", fs])
        if bg in flagged: t.append(["ov", 1])
        dn = [[r[1], r[0]] for r in site.get("denied") or [] if has(r[2], key)]
        if dn: t.append(["re", dn])
        vs = sum(1 for r in visits if has(r[1], key))
        if vs: t.append(["vi", vs])
        out[nm] = {"bg": bg, "v": vote_summary(m[8]) if m else None, "t": t}
    return out

def governor_changes(ref, current, terms):
    """The weekly check found a different governor in a state: the outgoing one must be in governor_terms.csv, or every
    older dispute in that state would silently lose its "Governor at the time". Raises until the line is added; once it
    is, governors_known.csv is brought up to date so the next build is clean."""
    f = Path(ref) / "governors_known.csv"
    if not f.exists() or not current: return []
    known = {r["state"]: r["name"] for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="|")}
    changed = [(st, known[st], nm) for st, nm in sorted(current.items()) if st in known and known[st] != nm]
    missing = [f"{st}: {old} -> {new}" for st, old, new in changed if not any(t[0] == old for t in terms.get(st, []))]
    if missing: raise ValueError("A governor changed and governor_terms.csv has no line for the one who left (name|party|start|end|source): " + "; ".join(missing))
    if changed or set(current) - set(known):
        f.write_text("state|name\n" + "".join(f"{st}|{nm}\n" for st, nm in sorted({**known, **current}.items())), encoding="utf-8")
    return changed

def governor_terms(ref):
    """Governors who left office since January 2025, kept by hand with a source each (data/reference/governor_terms.csv),
    so an entry can name the governor at the time when it differs from the governor now: {state: [[name, party, start, end]]}."""
    f = Path(ref) / "governor_terms.csv"
    if not f.exists(): return {}
    out = {}
    for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="|"):
        if r["state"] not in US_STATE_CODES or not (r["start"] < r["end"]) or not r["source"].startswith("https://"): raise ValueError(f"governor_terms.csv: bad row {r}")
        out.setdefault(r["state"], []).append([r["name"], r["party"], r["start"], r["end"]])
    return out

def future_dates(ref, today):
    """Every "read"/"checked"/"as_of" date in the reference metadata that is later than the build date (a clock mix-up)."""
    bad = []
    for f in sorted(Path(ref).glob("*meta*.json")):
        try: j = json.loads(f.read_text(encoding="utf-8"))
        except ValueError: continue
        for k, v in (j.items() if isinstance(j, dict) else []):
            if k in ("read", "checked", "as_of", "built") and isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v[:10]) and v[:10] > today: bad.append(f"{f.name} {k}={v[:10]}")
    return bad


def display_names(site, ref):
    """The name families know a site by, shown as its title, with ICE's own name kept beside it (facility_display_names.csv,
    kept by hand, each with the public page that uses the name). Done last, after every match on ICE's names."""
    for r in rd_pipe(ref / "facility_display_names.csv"):
        f = site.get("facilities", {}).get(r["facility_code"])
        if not f: raise ValueError(f"facility_display_names.csv: unknown facility code {r['facility_code']}")
        if not r["name"].strip() or not r["source"].startswith("https://"): raise ValueError(f"facility_display_names.csv: {r['facility_code']} needs a name and an https source")
        if f.get("ice_name"): continue
        f["ice_name"], f["name"], f["name_src"] = f["name"], r["name"].strip(), r["source"]


def main():
    site = json.loads((ROOT / "data" / "site_data.json").read_text(encoding="utf-8"))
    legs = [l for f in sorted(glob.glob(str(ROOT / "data" / "flights" / "legs_*.json"))) for l in json.load(open(f, encoding="utf-8"))]
    import gzip
    from flights import fleet_extra
    every = [l for f in sorted(glob.glob(str(ROOT / "data" / "flights" / "all_*.json.gz"))) for l in json.load(gzip.open(f, "rt", encoding="utf-8"))]
    have = {(l["hex"], l["date"], l["departed_utc"]) for l in legs}
    extra_legs = [l for l in fleet_extra(every) if (l["hex"], l["date"], l["departed_utc"]) not in have]
    legs += extra_legs
    for l in legs:                                                    # Puerto Rico and the other territories are the United States, not another country
        for k in ("origin_country", "dest_country"):
            if l[k] in US_TERRITORIES: l[k] = "US"
        l["kind"] = leg_kind(l["origin_country"], l["dest_country"])
    codes = {c for l in legs for c in (l["origin"], l["dest"])} | set(STAGING)
    airports = {r["iata_code"]: r for r in csv.DictReader(open(ROOT / "data" / "reference" / "airports.csv", encoding="utf-8")) if r["iata_code"] in codes}
    stage = join(site, legs, airports)
    extra = []
    a287 = ROOT / "data" / "reference" / "287g_agencies.csv"
    if a287.exists():
        rows = list(csv.DictReader(open(a287, encoding="utf-8")))
        extra.append(f"{attach_287g(site, rows)} facilities in a county with a 287(g) agreement")
    ref = ROOT / "data" / "reference"
    if (ref / "ice_inspections.csv").exists():
        rows = list(csv.DictReader(open(ref / "ice_inspections.csv", encoding="utf-8")))
        extra.append(f"{attach_inspections(site, rows)} of {len(rows)} inspection reports matched to a facility")
    if (ref / "legal_aid_sections.csv").exists():
        site["legal_aid"] = {r["state"]: r["courts"] for r in csv.DictReader(open(ref / "legal_aid_sections.csv", encoding="utf-8"))}
    if (ref / "legal_aid_providers.csv").exists():
        prov = {}
        for r in csv.DictReader(open(ref / "legal_aid_providers.csv", encoding="utf-8"), delimiter="|"):
            prov.setdefault(r["state"], []).append([r["name"], r["phone"], r["city"], r["kind"], r["courts"]])
        site["legal_providers"] = prov
        lm = ref / "legal_aid_meta.json"                                  # which edition of the Justice Department list, and whether it was read in full
        if lm.exists(): site["legal_meta"] = {k: v for k, v in json.loads(lm.read_text(encoding="utf-8")).items() if k in ("edition", "read", "providers", "full")}
        if site.get("legal_meta", {}).get("full"):                       # the courts each state's section lists, from the list itself, so it never falls behind
            secs = {}
            for st, L in prov.items():
                for c in (x for p in L for x in p[4].split("/")):
                    if c and "juvenile" not in c and c not in secs.setdefault(st, []): secs[st].append(c)
            site["legal_aid"] = {st: "; ".join(v) for st, v in secs.items()}
    if (ref / "oversight_visits.csv").exists():
        n = 0
        for f in site["facilities"].values(): f.pop("visits", None)
        for r in csv.DictReader(open(ref / "oversight_visits.csv", encoding="utf-8")):
            if r["facility_code"] in site["facilities"]:
                site["facilities"][r["facility_code"]].setdefault("visits", []).append([r["date"], r["officials"], r["outcome"], r["reason_given"], r["source"]]); n += 1
        extra.append(f"{n} oversight visits attached")
    if (ref / "legislators-current.csv").exists():
        leg = list(csv.DictReader(open(ref / "legislators-current.csv", encoding="utf-8")))
        site["senators"] = {}
        for r in leg:
            if r["type"] == "sen": site["senators"].setdefault(r["state"], []).append([r["full_name"], r["phone"], r["url"]])
        reps = {(r["state"], str(int(r["district"] or 0))): [r["full_name"], r["phone"], r["url"]] for r in leg if r["type"] == "rep"}
        n = 0
        if (ref / "facility_districts.csv").exists():
            from districts import CONGRESS
            for r in csv.DictReader(open(ref / "facility_districts.csv", encoding="utf-8")):
                f = site["facilities"].get(r["code"])
                if f is None or str(r["congress"]) != str(CONGRESS): continue      # never name a member from another Congress's map
                member = reps.get((r["state"], r["district"]))
                if member: f["rep"] = member + [f'{r["state"]}-{r["district"]}' if r["district"] != "0" else f'{r["state"]} at large']; n += 1
        extra.append(f"{n} facilities matched to a House member")
    if a287.exists():
        rows = list(csv.DictReader(open(a287, encoding="utf-8")))
        rd = lambda name: list(csv.DictReader(open(ref / name, encoding="utf-8"))) if (ref / name).exists() else []
        hand = [{"state": STATE_NAMES.get(r["state"], r["state"]), "agency": r["agency"], "phone": r["phone"], "address": "", "checked": "2026-10-05"}       # looked up by hand on official sites;
                for r in csv.DictReader(open(ref / "287g_agency_contacts_manual.csv", encoding="utf-8"), delimiter="|")] if (ref / "287g_agency_contacts_manual.csv").exists() else []   # these win over the automatic match
        site["a287"], note = agreements_index(rows, rd("287g_agency_contacts.csv") + hand, rd("county_centroids.csv"), rd("state_287g_bans.csv"), rd_pipe(ROOT / "data" / "reference" / "287g_agreements.csv"), rd_pipe(ROOT / "data" / "reference" / "287g_signers.csv"))
        ab = {v: k for k, v in STATE_NAMES.items()}                  # agreements once on ICE's list and no longer there (pipeline/agreements_history.py)
        site["a287"]["gone"], dropped = ended_agreements(rd("287g_no_longer_listed.csv"), rows, ab)
        site["a287"]["n_agencies"] = len({(r["state"].upper(), _agency_key(r["agency"])) for r in rows})      # one agency can hold up to three agreements
        if dropped: extra.append(f"{dropped} 'no longer listed' agreements left out: still on the current list, or the same agreement under another spelling")
        attach_agency_phones(site, rows, rd("287g_agency_contacts.csv"))
        extra.append(note)
        log = rd("oversight_visits.csv")
        site["denied"] = sorted(([r["date"], r["facility_as_reported"], r["officials"], r["reason_given"], r["source"], r.get("who") or "congress", r["facility_code"]] for r in log if r["outcome"] == "denied"), reverse=True)
    for code, f in site["facilities"].items(): f["kind"] = facility_kind(code, f["name"])
    for f in site["facilities"].values(): f.pop("statements", None)
    if (ref / "oversight_statements.csv").exists():
        st = sorted(csv.DictReader(open(ref / "oversight_statements.csv", encoding="utf-8")), key=lambda r: r["date"], reverse=True)
        st = [r for r in st if r["link"].split("/")[2].endswith((".house.gov", ".senate.gov"))]        # official sites only, whatever is in the file
        # A member's headline can name a detained person (one named a five-year-old), so headlines are never put on the page: only who, when, and the link.
        site["statements"] = [[r["date"], r["official"], r["kind"], "", r["link"]] for r in st if r["kind"] == "denied"][:60]
        site["statements_visits"] = [[r["date"], r["official"], r["kind"], "", r["link"]] for r in sorted(st, key=lambda r: r["date"], reverse=True) if r["kind"] == "visit"][:120]
        for r in st:
            if r["facility_code"] in site["facilities"]:
                site["facilities"][r["facility_code"]].setdefault("statements", []).append([r["date"], r["official"], r["kind"], "", r["link"]])
        import collections
        den = [r for r in st if r["kind"] == "denied"]
        meta = {"party": dict(collections.Counter(r.get("party") or "Unknown" for r in den)), "oldest": min((r["date"] for r in st if r["date"]), default="")}
        if (ref / "oversight_coverage.csv").exists():
            cov = list(csv.DictReader(open(ref / "oversight_coverage.csv", encoding="utf-8")))
            meta["read"] = {p: [sum(1 for c in cov if c["party"] == p and c["status"] == "read"), sum(1 for c in cov if c["party"] == p)] for p in sorted({c["party"] for c in cov})}
            meta["cov"] = {c["member"]: [1 if c["status"] == "read" else 0, c.get("oldest", ""), int(c.get("releases_read") or 0)] for c in cov}   # per member: read or not, oldest release read, how many
        qs = collections.OrderedDict()
        for r in sorted(st, key=lambda r: r["date"]):
            if not r["date"]: continue
            q = f'{r["date"][:4]} Q{(int(r["date"][5:7]) - 1) // 3 + 1}'
            qs.setdefault(q, [0, 0])[0 if r["kind"] == "visit" else 1] += 1
        site["statement_quarters"] = [[q, v, d] for q, (v, d) in qs.items()]
        site["statements_meta"] = meta
        extra.append(f"{len(st)} press statements from members' own sites")
    if (ref / "pregnancy_reports.csv").exists():
        site["preg"] = [[r["measure_en"], r["measure_es"], r["value"], r["period"], r["source_name"], r["source_url"]] for r in csv.DictReader(open(ref / "pregnancy_reports.csv", encoding="utf-8"))]
    for f in site["facilities"].values(): f.pop("contract", None)
    if (ref / "ice_facility_contracts.csv").exists():
        cr = list(csv.DictReader(open(ref / "ice_facility_contracts.csv", encoding="utf-8"), delimiter="|"))
        lo = {(r["facility_name"], r["state"]): [r["official"], r["title"], r["office"], r["source_url"], r["checked"]] for r in rd_pipe(ref / "local_officials_checked.csv") if r["ok"] == "1"}
        site["contracts"] = match_contracts(site, cr, lo)
        site["contracts_meta"] = {"file": "FY26_detentionStats07202026.xlsx", "as_of": "2026-07-20"}
        if (ref / "detention_stats_files.csv").exists():             # written by pipeline/detention_stats.py
            fl = sorted(csv.DictReader(open(ref / "detention_stats_files.csv", encoding="utf-8"), delimiter="|"), key=lambda r: r["fy"])
            if fl:
                nm = fl[-1]["url"].rsplit("/", 1)[1]; m8 = re.search(r"(\d\d)(\d\d)(\d{4})\.xlsx$", nm)
                site["contracts_meta"] = {"file": nm, "as_of": f"{m8.group(3)}-{m8.group(1)}-{m8.group(2)}" if m8 else fl[-1]["read"]}
                if m8: site["contracts_meta"]["checked"] = max(r["read"] for r in fl)      # the day this page last looked at ICE's list of files
        extra.append(f'{sum(1 for c in site["contracts"] if c[7])} of {len(cr)} facilities on the ICE contract list matched')
    if (ref / "ice_contract_recipients.csv").exists():
        site["vendors"] = [[r["recipient"], int(r["obligated_musd"]), int(r["detention_guard_musd"]) if r["detention_guard_musd"] else None]
                           for r in csv.DictReader(open(ref / "ice_contract_recipients.csv", encoding="utf-8"), delimiter="|")]
        MM = json.loads((ref / "money_meta.json").read_text(encoding="utf-8")) if (ref / "money_meta.json").exists() else {"from": "2024-10-01", "to": "2026-09-30", "read": "2026-10-04", "total_musd": 12922, "subs_total_musd": 400.825}   # written by pipeline/money_usaspending.py
        site["vendors_meta"] = {"from": MM["from"], "to": MM["to"], "read": MM["read"], "by_fy": MM.get("by_fy_musd", [])}
    if (ref / "ice_money_flow.csv").exists():
        site["money"] = money_flow(list(csv.DictReader(open(ref / "ice_money_flow.csv", encoding="utf-8"), delimiter="|")), MM["total_musd"])
        if (ref / "ice_money_other.csv").exists():                  # what "everything else" is made of; written by the same collector run
            oc = [[r["code"], r["name"], int(r["musd"]), int(r["n_codes"])] for r in csv.DictReader(open(ref / "ice_money_other.csv", encoding="utf-8"), delimiter="|")]
            og = next((g for g in site["money"]["groups"] if g[0] == "OTHER"), None)
            if og and sum(r[2] for r in oc) == og[1]: site["money"]["other"] = oc     # a file from a different run would not add up: then it is left off, never shown wrong
            else: extra.append("ice_money_other.csv does not add up to the 'everything else' group and is not shown")
        rd = lambda name: list(csv.DictReader(open(ref / name, encoding="utf-8"), delimiter="|")) if (ref / name).exists() else []
        site["money"]["years"] = [[r["fiscal_year"], int(r["obligated_musd"]), int(r["paid_out_musd"]), int(r["available_musd"])] for r in rd("ice_budget_totals.csv")]
        site["money"]["accounts"] = [[r["fiscal_year"], r["account"], int(r["obligated_musd"]), int(r["available_musd"])] for r in rd("ice_budget_accounts.csv")]
        site["money"]["parents"] = {r["recipient"]: [r["parent"], r["kind"]] for r in rd("ice_recipient_parents.csv") if r["parent"] or r["kind"]}
        site["money"]["subs"] = [[r["prime"], r["sub"], float(r["musd"]), r["for"]] for r in rd("ice_subawards.csv")]
        if site["money"]["subs"] and abs(sum(x[2] for x in site["money"]["subs"]) - MM["subs_total_musd"]) > 0.01:      # every reported subcontract; the total is the source's own
            raise ValueError(f'subcontracts add to {sum(x[2] for x in site["money"]["subs"]):.3f}M, expected {MM["subs_total_musd"]}M')
        site["money"]["chain"] = [[r["recipient"], r["type"], r["top"], r["chain"], r["ticker"], r["note"], r["url"], r["sure"]] for r in rd("ice_ownership.csv")]   # researched 4 Oct 2026; organisations only
        fam = {}                                                     # one owner's companies added together, from the federal parent record
        for r in csv.DictReader(open(ref / "ice_contract_recipients.csv", encoding="utf-8"), delimiter="|"):
            par = site["money"]["parents"].get(r["recipient"], ["", ""])[0].split(";")[0].strip() or r["recipient"]
            fam.setdefault(par, [0, []]); fam[par][0] += int(r["obligated_musd"]); fam[par][1].append(r["recipient"])
        site["money"]["owners"] = sorted([[k, v[0], v[1]] for k, v in fam.items() if len(v[1]) > 1], key=lambda x: -x[1])
    if (ref / "fec_pac_recipients.csv").exists() and "money" in site:
        FM = json.loads((ref / "fec_meta.json").read_text(encoding="utf-8")) if (ref / "fec_meta.json").exists() else {"total": 1539950, "cycles": [2024, 2026], "read": "2026-10-04"}      # written by pipeline/money_fec.py
        site["money"]["pacs"] = pac_money(list(csv.DictReader(open(ref / "fec_pac_recipients.csv", encoding="utf-8"), delimiter="|")), FM["total"], FM["cycles"], FM["read"])
        if (ref / "fec_committee_detail.csv").exists():             # written by pipeline/money_fec.py; absent until that collector has run with a key
            site["money"]["pacs"]["detail"] = {r["recipient"]: [r["kind"], r["sponsors"], r["shares_with"]] for r in csv.DictReader(open(ref / "fec_committee_detail.csv", encoding="utf-8"), delimiter="|")}
        if (ref / "pac_members_votes.csv").exists():                 # made by pipeline/pac_votes.py; committee money joined to members and their H.R. 1 vote
            site["money"]["pacs"]["members"] = [[r["name"], r["chamber"], r["party"], r["state"], r["vote"], int(r["campaign_usd"]), int(r["leadership_usd"])] for r in rd("pac_members_votes.csv")]
        if (ref / "jfc_totals.csv").exists() and (ref / "jfc_flows.csv").exists():   # made by pipeline/jfc_flows.py
            site["money"]["pacs"]["jfc"] = jfc_flows(rd("jfc_totals.csv"), rd("jfc_flows.csv"), rd("fec_pac_recipients.csv"), json.loads((ref / "jfc_meta.json").read_text(encoding="utf-8")) if (ref / "jfc_meta.json").exists() else {})
    if "money" in site: money_extras(site, rd)
    if "money" in site and (ref / "ice_awards.csv").exists() and (ref / "ice_awards_meta.json").exists():      # made by pipeline/money_awards.py
        site["money"]["awards"] = awards_by_recipient(rd("ice_awards.csv"), json.loads((ref / "ice_awards_meta.json").read_text(encoding="utf-8")))
        fa, fan = facility_awards(site, rd("ice_awards.csv")); site["money"]["awards"]["meta"]["placed"] = fan
        for code, v in fa.items(): site["facilities"][code]["awards"] = v
        if fan["guard"]: extra.append(f'{fan["placed"]} of {fan["guard"]} guard-service contracts placed at a facility by city ({fan["shared"]} in a city with several facilities, {fan["nowhere"]} in a city with none)')
    if (ref / "lobbying_by_year.csv").exists() and "money" in site:
        site["money"]["lobby"] = lobby_money(rd("lobbying_by_year.csv"), rd("lobbying_firms.csv"), rd("lobbying_targets.csv"))
    if (ref / "sec_company_facts.csv").exists() and "money" in site:
        site["money"]["sec"] = {"facts": [[r["company"], r["fy"], float(r["revenue_musd"]), float(r["ice_pct"]), r["url"]] for r in rd("sec_company_facts.csv")],
                                "holders": [[r["company"], r["holder"], float(r["pct"]), r["kind"], r["url"]] for r in rd("sec_shareholders.csv")]}
    for f in site["facilities"].values(): f.pop("watchdog", None)
    if (ref / "watchdog_reports.csv").exists():                      # reports by inspectors other than ICE's own; researched by hand
        wd = list(csv.DictReader(open(ref / "watchdog_reports.csv", encoding="utf-8"), delimiter="|"))
        bad = [r["facility_code"] for r in wd if r["facility_code"] and r["facility_code"] not in site["facilities"]]
        if bad: raise ValueError(f"watchdog_reports.csv names facility codes that do not exist: {bad}")
        if (ref / "crcl_memos.csv").exists():                         # POGO's mirror, read by pipeline/crcl_memos.py; added to the hand-kept rows
            cand = [(_name_words(f["name"]), c, 0) for c, f in site["facilities"].items()]
            if (ref / "facility_name_aliases.csv").exists():                                   # a hand-kept other name outranks a plain name match
                cand += [(_name_words(r["name"]), r["facility_code"], 1) for r in csv.DictReader(open(ref / "facility_name_aliases.csv", encoding="utf-8"), delimiter="|") if r["facility_code"] in site["facilities"]]
            have = {(r["published"], r["facility_code"]) for r in wd if r["body"] == "CRCL"} | {r["url"] for r in wd}
            for m in csv.DictReader(open(ref / "crcl_memos.csv", encoding="utf-8"), delimiter="|"):
                tw = _name_words(m["title"] + " " + m["slug"].replace("-", " "))
                hits = sorted(((al, len(k), c) for k, c, al in cand if k and k <= tw), reverse=True)      # every word of a facility's name (or of a known other name) appears
                best = {c for al, n, c in hits if (al, n) == hits[0][:2]} if hits else set()
                code = best.pop() if len(best) == 1 else ""                                      # the longest name wins; two different facilities tied means none
                if not code and not re.search(r"\bICE\b|detention|segregation", m["title"]): continue      # the mirror also holds memos about other agencies
                if m["url"] in have or (code and (m["published"], code) in have): continue
                wd.append({"published": m["published"], "body": "CRCL", "facility_code": code, "facility": site["facilities"][code]["name"] if code else "", "number": "", "title": m["title"], "finding": "", "url": m["url"], "sure": "auto"})
        site["watchdog"] = sorted([[r["published"], r["body"], r["facility_code"], r["facility"], r["number"], r["title"].strip(), r["finding"], r["url"]] for r in wd], reverse=True)
        for r in wd:
            if r["facility_code"]: site["facilities"][r["facility_code"]].setdefault("watchdog", []).append([r["published"], r["body"], r["title"].strip(), r["url"]])
    if (ref / "access_court_events.csv").exists():
        site["access_case"] = [[r["date"], r["what_en"], r["what_es"], r["url"]] for r in csv.DictReader(open(ref / "access_court_events.csv", encoding="utf-8"), delimiter="|")]
    if (ref / "facility_operators.csv").exists():                    # which company runs each privately run site; researched by hand
        ops = list(csv.DictReader(open(ref / "facility_operators.csv", encoding="utf-8"), delimiter="|"))
        bad = [r["facility_code"] for r in ops if r["facility_code"] not in site["facilities"]]
        if bad or len({r["facility_code"] for r in ops}) != len(ops): raise ValueError(f"facility_operators.csv: unknown or repeated facility codes {bad}")
        site["operators"] = {r["facility_code"]: [r["operator"], r["role"], r["url"], r["sure"]] for r in ops}
        if (ref / "facility_operator_history.csv").exists():        # earlier operators, each with a source; by hand
            nh = load_operator_history(site, list(csv.DictReader(open(ref / "facility_operator_history.csv", encoding="utf-8"), delimiter="|")))
            extra.append(f"{nh} sites with a recorded change of operator")
    if (ref / "custody_by_month.csv").exists():                      # made by pipeline/custody_trend.py
        site["custody"] = [[r["month"], int(r["held"]), int(r["pct_no_crim"]), int(r["book_ins"]), int(r["deported"]), int(r["released"])] for r in csv.DictReader(open(ref / "custody_by_month.csv", encoding="utf-8"))]
    if (ref / "sources.csv").exists():
        SRC_ROWS = list(csv.DictReader(open(ref / "sources.csv", encoding="utf-8"), delimiter="|"))
    if (ref / "prea_audits.csv").exists():
        pr = list(csv.DictReader(open(ref / "prea_audits.csv", encoding="utf-8")))
        site["prea_meta"] = {"audits": len(pr), "placed": attach_prea(site, pr), "from": min(r["audit_start"] for r in pr)[:4]}
        site["prea_meta"]["unread"] = sum(r["basis"] == "unread" for r in pr)
        if site["prea_meta"]["unread"]: extra.append(f'{site["prea_meta"]["unread"]} sexual-abuse audits found but not yet read for their count')
        bm = {"stated": "S", "files reviewed": "F", "not stated": "N", "unread": "U"}
        site["prea_unplaced"] = [[r["facility_as_reported"], r["audit_start"], int(r["allegations"]) if r["allegations"] != "" else None, bm[r["basis"]],
                                  int(r["substantiated"]) if r["substantiated"] != "" else None, r["report_url"]]
                                 for r in sorted(pr, key=lambda r: r["audit_start"], reverse=True) if r["facility_code"] not in site["facilities"]]
        extra.append(f"{len(pr)} sexual-abuse audit reports")
    for f in site["facilities"].values(): f.pop("death_reports", None)
    if (ref / "ice_death_reports.csv").exists():
        dr = list(csv.DictReader(open(ref / "ice_death_reports.csv", encoding="utf-8")))
        # shown on a facility page only when ICE's detention record agrees, or the report itself says where the person was held
        shown = lambda r: r["facility_code"] and (r["evidence"] in ("report and record", "record") or (r["evidence"] == "report" and r["how_named"] == "stated"))
        n = 0
        for r in sorted(dr, key=lambda r: r["date_of_death"], reverse=True):
            if shown(r) and r["facility_code"] in site["facilities"]:
                site["facilities"][r["facility_code"]].setdefault("death_reports", []).append([r["date_of_death"], {"report and record": "B", "record": "R", "report": "P"}[r["evidence"]], r["report_url"]]); n += 1
        site["death_match"] = {"total": len(dr), "placed": n, "both": sum(1 for r in dr if r["evidence"] == "report and record"),
                               "outside": sum(1 for r in dr if r["evidence"] == "not in a facility"), "checking": len(dr) - n - sum(1 for r in dr if r["evidence"] == "not in a facility"),
                               "from": min(r["date_of_death"] for r in dr)[:7]}
        evc = {"report and record": "B", "record": "R", "report": "P", "not in a facility": "O", "unresolved": "U"}
        years = {}
        for r in sorted(dr, key=lambda r: r["date_of_death"], reverse=True):
            code = r["facility_code"] if shown(r) and r["facility_code"] in site["facilities"] else ""
            label = site["facilities"][code]["name"] if code else (r["facility_as_reported"] if r["evidence"] in ("not in a facility", "unresolved") else r["facility_as_reported"])
            years.setdefault(r["fiscal_year"], []).append([r["date_of_death"], code, label, evc[r["evidence"]], r["report_url"], site["facilities"][code].get("state", "") if code else ""])
        site["death_years"] = years
        extra.append(f"{n} of {len(dr)} ICE death reports placed at a facility")
    if (ref / "ice_deaths_by_year.csv").exists():
        rows = list(csv.DictReader(open(ref / "ice_deaths_by_year.csv", encoding="utf-8")))
        site["deaths"] = {"years": [[r["fiscal_year"], int(r["deaths_listed"])] for r in rows[:4]], "retrieved": rows[0]["retrieved"],
                          "earlier": [[r["fiscal_year"], int(r["deaths_listed"])] for r in rows[4:]]}     # years before the detention records begin: counted, not placed
    all_days = sorted({l["date"] for l in legs}); recent = set(all_days[-RECENT_DAYS:])
    months = {}
    for l in legs:
        m = months.setdefault(l["date"][:7], [0, 0, set()]); m[0] += 1; m[1] += l["kind"] == "international"; m[2].add(l["date"])
    monthly = [[k, v[0], v[1], len(v[2])] for k, v in sorted(months.items())]
    all_legs, legs = legs, [l for l in legs if l["date"] in recent]     # tracks are drawn only for recent days; older days are counted
    flights = {"fleet": len(extra_legs), "days": sorted(recent), "all_days": len(all_days), "first_day": all_days[0] if all_days else "", "monthly": monthly, "staging": stage,
               "airports": {c: a["municipality"] for c, a in airports.items()}, "trends": trends(all_legs), "used": dict(zip(("rows", "seen", "lost"), airports_used(all_legs, airports))),
               "coords": {c: [round(float(a["latitude_deg"]), 2), round(float(a["longitude_deg"]), 2)] for c, a in airports.items()},
               "all": [[l["date"], l["departed_utc"], l["arrived_utc"], l["origin"], int(bool(l["origin_certain"])), l["dest"], int(bool(l["dest_certain"])), {"domestic": 0, "international": 1, "abroad": 2}[l["kind"]], l["registration"]]
                       for l in sorted(all_legs, key=lambda l: (l["date"], l["departed_utc"]), reverse=True)],     # every flight on record, newest first, no tracks
               "legs": [{k: l[k] for k in ("date", "registration", "aircraft_type", "callsign", "departed_utc", "arrived_utc", "origin", "origin_certain",
                                           "dest", "dest_certain", "kind", "via", "track")} for l in legs]} if legs else None
    today = str(dt.datetime.now(dt.timezone.utc).date()); site["built"] = today; stale = []      # the UTC date on every machine, Windows included
    future = future_dates(ref, today)
    if future: raise SystemExit("Dates later than the build date: " + ", ".join(future))
    rd0 = lambda name: list(csv.DictReader(open(ref / name, encoding="utf-8"))) if (ref / name).exists() else []
    if (ref / "sources.csv").exists():
        dyn = {"stints": site["window"][1], "flights": all_days[-1] if all_days else "", "ice_site": max((r["retrieved"] for r in rd0("ice_facility_contacts.csv") if r.get("retrieved")), default=""),
               "statements": max((r["collected"] for r in rd0("oversight_statements.csv") if r.get("collected")), default="")}
        sh = (site.get("a287") or {}).get("sheet", "")
        if len(sh) == 8: dyn["a287"] = f"{sh[:4]}-{sh[4:6]}-{sh[6:]}"
        rdx = lambda name: list(csv.DictReader(open(ref / name, encoding="utf-8"), delimiter="|")) if (ref / name).exists() else []
        dyn["spending"] = json.loads((ref / "money_meta.json").read_text(encoding="utf-8"))["read"] if (ref / "money_meta.json").exists() else ""
        dyn["court"] = json.loads((ref / "court_meta.json").read_text(encoding="utf-8")).get("checked", "") if (ref / "court_meta.json").exists() else ""
        jm = lambda n: json.loads((ref / n).read_text(encoding="utf-8")) if (ref / n).exists() else {}
        dyn["legalaid"] = jm("legal_aid_meta.json").get("read", "")
        dyn["lobby"] = jm("lobbying_meta.json").get("read", ""); dyn["fec"] = jm("fec_meta.json").get("read", "")
        dyn["fec_donors"] = jm("fec_donors_meta.json").get("read", ""); dyn["fec_top"] = jm("member_top_donors_meta.json").get("read", ""); dyn["social"] = jm("social_meta.json").get("checked", "")
        dyn["sec"] = "" if jm("sec_meta.json").get("newer") else jm("sec_meta.json").get("checked", "")      # a newer filing exists: fall back to the day the files were last read by hand
        dyn["stats"] = (site.get("contracts_meta") or {}).get("as_of") or max((r["as_of"] for r in rdx("ice_stats_snapshots.csv") if r.get("as_of")), default="") or max((r["read"] for r in rdx("detention_stats_files.csv")), default="")   # the date in the newest file's own name comes first: ice_stats_snapshots' as_of is the day the file was read   # the date the figures in ICE's newest file are as of (not the day it was posted, nor the day it was read)
        dyn["findings"] = max((r["checked"] for r in rdx("ice_inspection_findings.csv")), default="")
        om = jm("other_sources_meta.json"); dyn["other_money"] = jm("other_money_meta.json").get("read", "")
        for k in ("encounters", "custody", "orr"):         # monthly series are dated by the last month they cover, so a source that stops publishing goes stale
            if (om.get(k) or {}).get("to"): dyn[k] = month_end(om[k]["to"])
        if (om.get("repatriations") or {}).get("to"): dyn["repatriations"] = f'{om["repatriations"]["to"]}-09-30'
        dyn["notices"] = (om.get("notices") or {}).get("read", "")
        dyn["arrests"] = jm("arrests_meta.json").get("last", "")
        dyn["detainers"] = jm("detainers_meta.json").get("last", ""); rcm = jm("removals_by_country_meta.json"); dyn["removed_to"] = month_end(rcm["last"]) if rcm.get("last") else ""
        sm = rdx("staff_by_month.csv"); dyn["staff"] = month_end(max(r["month"] for r in sm)) if sm else ""
        dyn["accounts"] = jm("agency_object_class_meta.json").get("read", "")
        dyn["cpac"] = jm("country_pacs_meta.json").get("read", ""); dyn["fara"] = jm("fara_meta.json").get("read", ""); dyn["officials"] = jm("officials_meta.json").get("checked", "")
        dyn["moa"] = jm("287g_agreements_meta.json").get("read", ""); dyn["hotlines"] = max((r["checked"] for r in rdx("hotlines_checked.csv")), default="")
        site["sources"], stale = source_rows(SRC_ROWS, dyn, today)
    layers = write_layers(site, flights, ROOT / "site" / "layers")
    pdm = {}
    if (ref / "facility_person_days.csv").exists():                 # made by pipeline/person_days.py; must come after operators, contracts, deaths, watchdog and visits are attached
        for r in csv.DictReader(open(ref / "facility_person_days.csv", encoding="utf-8")): pdm.setdefault(r["facility_code"], {})[r["month"]] = int(r["person_days"])
        rdp = lambda name: list(csv.DictReader(open(ref / name, encoding="utf-8"), delimiter="|")) if (ref / name).exists() else []
        site["_aliases"] = {r["name"]: r["facility_code"] for r in rdp("facility_name_aliases.csv")}   # ICE's other names for a site; by hand
        bad = sorted(set(site["_aliases"].values()) - set(site["facilities"]))
        if bad: raise ValueError(f"facility_name_aliases.csv names facility codes that do not exist: {bad}")
        hist, missed = population_history(site, rdp("facility_adp_by_year.csv"))
        site["conduct"] = conduct_rates(site, pdm, history=hist)
        site["beds"] = bed_use(site, hist)
        if site["beds"] and (ref / "facility_bed_revenue.csv").exists(): site["beds"]["rev"] = bed_revenue(site, rdp("facility_bed_revenue.csv"))   # by hand
        if hist: extra.append(f"yearly population for {len(hist)} facilities since 2019 ({missed:,} people a day at names not matched)")
        sg = rdp("facility_segregation.csv")
        if sg:
            site["segregation"] = segregation_rates(site, sg, pdm)
            extra.append(f'{site["segregation"]["total"] - site["segregation"]["unmatched"]:,} of {site["segregation"]["total"]:,} segregation placements matched to a facility')
        fi = rdp("ice_inspection_findings.csv")
        site.pop("_aliases", None)
        if fi:
            site["findings"] = inspection_findings(site, fi)
            extra.append(f'{site["findings"]["read"]} inspection reports read for deficiencies, {site["findings"]["unread"]} unreadable')
    if (ref / "court_by_location.csv").exists() and (ref / "court_meta.json").exists():      # made by pipeline/court_outcomes.py
        rdc = lambda name: list(csv.DictReader(open(ref / name, encoding="utf-8"), delimiter="|")) if (ref / name).exists() else []
        site["court"] = court_summary(site, rdc("court_by_location.csv"), {r["code"]: r["facility_code"] for r in rdc("court_location_facility.csv")}, json.loads((ref / "court_meta.json").read_text(encoding="utf-8")))
        extra.append(f'{site["court"]["tied"]:,} of {site["court"]["all"]:,} court decisions tied to a facility')
    if (ref / "held_profile.json").exists():                        # made by pipeline/held_profile.py
        site["held"] = held_summary(site, json.loads((ref / "held_profile.json").read_text(encoding="utf-8")))
    (ROOT / "data" / "health.json").write_text(json.dumps({"built": today, "stale": stale, "layers": layers}, indent=1), encoding="utf-8")
    html = page_identity((ROOT / "site" / "template.html").read_text(encoding="utf-8"))
    if (ref / "es_text.csv").exists():      # Spanish for text the site shows from its own data files (reasons, findings, notes, labels); by hand
        site["es"] = {r["en"]: r["es"] for r in csv.DictReader(open(ref / "es_text.csv", encoding="utf-8"), delimiter="|") if r["en"] and r["es"]}
    site["gov"] = gov_section(site, ref)
    site["people"] = people_section(ref)
    site["pol"] = politicians_section(ref)
    dn = donors_section(ref)
    if dn and site.get("money") is not None: site["money"]["donors"] = dn; site["money"]["donors_n"] = [len(dn["rows"]), dn["total"], donor_people(dn["rows"])]
    site["mw"] = money_wide(site, ref)
    for f in site["facilities"].values():                         # spelling slips in ICE's own facility names, corrected for display only (codes and matching are unchanged)
        if f.get("name"): f["name"] = fix_name(f["name"])
    for c in site.get("contracts", []): c[0] = fix_name(c[0])
    import watch, identity
    site["watch"] = watch.build(site, pdm, today, ref, ROOT, identity.PUBLISHER)       # the watch list: overdue required reports, long detention, facility alerts (after names are tidied)
    if site.get("pol"):
        site["pol"]["c"], pc_notes = pol_cards(site, ref)
        if (ref / "member_top_donors_meta.json").exists(): site["pol"]["topmeta"] = json.loads((ref / "member_top_donors_meta.json").read_text(encoding="utf-8"))
        for n in pc_notes: print(n)
        rules = json.loads((ref / "watch_rules.json").read_text(encoding="utf-8")) if (ref / "watch_rules.json").exists() else {}
        fl = official_flags(site["pol"], site["pol"]["c"], rules); (ROOT / "data" / "watch").mkdir(parents=True, exist_ok=True)
        (ROOT / "data" / "watch" / "officials_candidates.json").write_text(json.dumps(fl, indent=1), encoding="utf-8")
        site["pol"]["flags"] = {"min": rules.get("officials_min_usd", 0), **({"list": fl} if rules.get("officials_published") else {"pending": len(fl)})}
    site["social"] = social_list(ref)
    site["disputes"] = disputes_list(ref, site["facilities"]); site["gov_terms"] = governor_terms(ref)
    for st, old, new in governor_changes(ref, {r["state"]: r["name"] for r in rd_pipe(ref / "governors.csv")} if (ref / "governors.csv").exists() else {}, site["gov_terms"]): print(f"GOVERNOR CHANGE recorded: {st} {old} -> {new}")
    if (ref / "federal_law_sponsors.csv").exists():                  # who sponsored the enforcement laws on Politicians; by hand, from congress.gov
        fs = list(csv.DictReader(open(ref / "federal_law_sponsors.csv", encoding="utf-8"), delimiter="|"))
        laws = {v[4] for v in (site.get("pol") or {}).get("votes", [])}
        if laws and any(r["law"] not in laws for r in fs): raise ValueError("federal_law_sponsors.csv: a law that is not among the votes on Politicians")
        site["law_sponsors"] = [[r["law"], r["bill"], r["sponsor"], r["chamber"], r["state"], r["url"]] for r in fs]
    site["hotlines"] = hotlines(ref, today)
    site["contractors"] = vendors(ref)
    if site.get("pol"): site["pol"].update(state_officials(site, ref))
    fc = firm_cards(ref)
    if fc:
        firm_members(fc["pat"], (site.get("pol") or {}).get("m") or []); fc["pat"].pop("_money", None)
        site["firms"] = fc
    site["dispute_people"] = dispute_people(site)
    watch.add_disputes(ROOT, site.get("disputes"))                  # new disputes and new steps reach the same feed as the alerts
    hp = ROOT / "data" / "headline_history.json"                   # what the headline counts were at each update, so the page can say what changed
    hist, site["changes"] = record_changes(json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else [], today, headline(site))
    hp.write_text(json.dumps(hist, indent=1), encoding="utf-8")
    if site.get("a287"):     # the long agreement lists and the contract records go in a third file, fetched when a tab that needs them opens
        import hashlib
        more = json.dumps({"states": site["a287"]["states"], "gone": site["a287"].get("gone", []), "awards": site.get("money", {}).pop("awards", None), "donors": site.get("money", {}).pop("donors", None)}, separators=(",", ":"))
        site["a287"]["states"], site["a287"]["gone"], site["lazy"] = {}, [], hashlib.sha1(more.encode()).hexdigest()[:12]
        (ROOT / "site" / "more-data.js").write_text(f'window.DATA_MORE={{"v":"{site["lazy"]}","d":{more}}};', encoding="utf-8")
    if flights:      # the long lists and the world map go in a second file the page fetches when the flights tab opens; both carry one stamp
        import hashlib
        flights["n_all"] = len(flights["all"])
        heavy = json.dumps({"all": flights.pop("all"), "legs": flights.pop("legs"), "world": json.loads((ROOT / "site" / "vendor" / "countries-110m.json").read_text(encoding="utf-8"))}, separators=(",", ":"))
        flights["more"] = hashlib.sha1(heavy.encode()).hexdigest()[:12]
        (ROOT / "site" / "flights-data.js").write_text(f'window.FLIGHTS_MORE={{"v":"{flights["more"]}","d":{heavy}}};', encoding="utf-8")
    display_names(site, ref)
    html = prefill_text(html, site.get("hotlines") or {})
    html = (html.replace("/*__DATA__*/null", json.dumps(site, separators=(",", ":")))
                .replace("/*__FLIGHTS__*/null", json.dumps(flights, separators=(",", ":")))
                .replace("/*__US__*/null", (ROOT / "site" / "vendor" / "us-states-10m.json").read_text(encoding="utf-8")))
    (ROOT / "site" / "index.html").write_text(html, encoding="utf-8")
    print("; ".join(extra))
    print("STALE SOURCES: " + "; ".join(stale) if stale else "all sources within their expected age")
    near = sorted((f["name"], f["near"]) for f in site["facilities"].values() if f.get("near"))
    print(len(legs), "flights on", len(flights["days"]) if flights else 0, "day(s);", len(near), "facilities beside a staging airport:", near)


if __name__ == "__main__":
    main()
