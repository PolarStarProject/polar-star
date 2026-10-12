"""Phone, address and map position for each agency on ICE's 287(g) list.

Usage (on Windows):  python pipeline\\agency_contacts.py
Reads  data/reference/287g_agencies.csv
Writes data/reference/287g_agency_contacts.csv   and keeps the download in data/raw/hifld_law_enforcement.json

Source: the federal "Local Law Enforcement Locations" list (HIFLD, Department of Homeland Security, public domain).
The federal site that published it closed in August 2025; this reads a public copy. Its records were last checked
by the government around 2018-2021, so every number carries the date it was checked and the page says to confirm it.

A wrong number sends a family to the wrong office, so a row is matched only when:
  the agency name and state match exactly after normalising, exactly one open office has that name,
  the county agrees when both lists give one, and the phone's area code belongs to that state.
Anything else gets no contact row. State agencies (highway patrols, corrections departments) are not in the
federal local list and stay unmatched.
"""
import csv, json, re, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
URL = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Local_Law_Enforcement_Locations/FeatureServer/0/query"
MIN_ROWS = 20000                  # the full list is about 23,500; fewer means a cut-off download
FIELDS = "NAME,ADDRESS,CITY,STATE,ZIP,TELEPHONE,STATUS,COUNTY,LATITUDE,LONGITUDE,WEBSITE,VAL_DATE,SOURCEDATE"
DROP = {"OFFICE", "DEPARTMENT", "DEPT", "OF", "THE", "AND", "TOWN", "CITY", "HEADQUARTERS", "HQ"}
SWAP = {"SHERIFFS": "SHERIFF", "PD": "POLICE", "SO": "SHERIFF", "CO": "COUNTY", "SAINT": "ST", "MARSHALS": "MARSHAL", "CONSTABLES": "CONSTABLE"}
STATE_FIX = {"NEW HAMSPHIRE": "NEW HAMPSHIRE"}


def agency_key(name):
    x = re.sub(r"[^A-Z0-9 ]", " ", str(name).upper().replace("'", "").replace("’", "").replace("&", " AND "))
    return " ".join(SWAP.get(w, w) for w in x.split() if w not in DROP)


def office_keys(name):
    """Keys an office in the federal list can be found under: its full name, and the agency part of names such as
    'X COUNTY SHERIFFS OFFICE / X COUNTY JAIL', 'X SHERIFFS OFFICE AND X DETENTION CENTER' or 'X SHERIFFS OFFICE - TOWN'.
    The second kind is a weaker match and is used only when no office has the plain name."""
    n = str(name).upper()
    full = agency_key(n)
    head = re.split(r"\s+/\s+|\s+-\s+|\s+AND\s+(?=.*(?:JAIL|DETENTION|CORRECTION))", n)[0]
    return full, (agency_key(head) if agency_key(head) != full else None)


def county_key(c):
    c = re.sub(r"\b(COUNTY|PARISH|BOROUGH|MUNICIPALITY|CITY AND)\b", "", str(c).upper())
    return re.sub(r"[^A-Z]", "", c.replace("SAINT", "ST"))


def clean_phone(p):
    d = re.sub(r"\D", "", str(p or ""))
    if len(d) == 11 and d[0] == "1": d = d[1:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else ""


def fmt_date(ms):
    """ArcGIS dates are milliseconds since 1970 (UTC). Text dates pass through."""
    if isinstance(ms, (int, float)) and ms > 0:
        import datetime
        return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
    return str(ms or "")[:10]


def download():
    rows, off = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "1=1", "outFields": FIELDS, "returnGeometry": "false", "orderByFields": "OBJECTID",
                                    "resultOffset": off, "resultRecordCount": 2000, "f": "json"}).encode()
        with urllib.request.urlopen(urllib.request.Request(URL, data=q, headers={"User-Agent": "detention-map/1.0"}), timeout=120) as r:
            page = json.load(r)
        if "error" in page: raise RuntimeError(page["error"])
        got = [f["attributes"] for f in page.get("features", [])]
        rows += got; off += len(got)
        print(f"  {len(rows)} offices", flush=True)
        if not got or not page.get("exceededTransferLimit"): break
    return rows


def match(agencies, offices, abbr, area_state=None):
    """(contact rows, counts of why rows were left out)"""
    by, branch = {}, {}
    for o in offices:
        if str(o.get("STATUS", "")).upper() not in ("OPEN", ""): continue
        full, head = office_keys(o.get("NAME"))
        by.setdefault((o.get("STATE"), full), []).append(o)
        if head: branch.setdefault((o.get("STATE"), head), []).append(o)
    out, why = [], {"matched": 0, "no_office_with_that_name": 0, "several_offices_with_that_name": 0, "county_disagrees": 0,
                    "phone_area_code_in_another_state": 0, "position_outside_state_box": 0}
    for a in agencies:
        state = STATE_FIX.get(a["state"].upper(), a["state"].upper()); st = abbr.get(state)
        k = (st, agency_key(a["agency"]))
        hits = by.get(k) or branch.get(k, [])
        if a.get("county") and len(hits) > 1:
            hits = [h for h in hits if county_key(h.get("COUNTY")) == county_key(a["county"])]
        if not hits: why["no_office_with_that_name"] += 1; continue
        if len(hits) > 1: why["several_offices_with_that_name"] += 1; continue
        h = hits[0]
        if a.get("county") and h.get("COUNTY") and county_key(h["COUNTY"]) != county_key(a["county"]):
            why["county_disagrees"] += 1; continue
        phone = clean_phone(h.get("TELEPHONE"))
        if phone and area_state:
            s = area_state(phone)
            if s and s != st: phone = ""; why["phone_area_code_in_another_state"] += 1
        lat, lon = h.get("LATITUDE"), h.get("LONGITUDE")
        try:
            lat, lon = float(lat), float(lon)
            if not (-180 <= lon <= -60 or 130 <= lon <= 180) or not (13 <= lat <= 72): raise ValueError   # west longitudes are negative; Guam and the Marianas are east
        except (TypeError, ValueError):
            lat = lon = ""; why["position_outside_state_box"] += 1
        web = str(h.get("WEBSITE") or ""); web = web if web.lower().startswith("http") else ""
        addr = ", ".join(x for x in [str(h.get("ADDRESS") or "").title(), str(h.get("CITY") or "").title(), f'{st} {h.get("ZIP") or ""}'.strip()] if x and x.upper() not in ("NOT AVAILABLE", "<NULL>", "NULL", "NONE"))      # the federal list writes a missing part as "<Null>"
        out.append({"state": state, "agency": a["agency"], "county": a.get("county", ""), "phone": phone, "address": addr,
                    "lat": lat, "lon": lon, "website": web, "checked": fmt_date(h.get("VAL_DATE") or h.get("SOURCEDATE")), "matched_name": h.get("NAME")})
        why["matched"] += 1
    return out, why


def main():
    sys.path.insert(0, str(Path(__file__).parent))
    from build_site import STATE_NAMES
    from build_transfers import area_state
    abbr = {v: k for k, v in STATE_NAMES.items()}
    ref = ROOT / "data" / "reference"; raw = ROOT / "data" / "raw" / "hifld_law_enforcement.json"
    agencies = list(csv.DictReader(open(ref / "287g_agencies.csv", encoding="utf-8")))
    try:
        offices = download()
        if len(offices) < MIN_ROWS: raise RuntimeError(f"only {len(offices)} offices came back; expected over {MIN_ROWS}")
        raw.parent.mkdir(parents=True, exist_ok=True); raw.write_text(json.dumps(offices), encoding="utf-8")
    except Exception as e:
        if not raw.exists(): sys.exit(f"download failed and there is no earlier copy: {e}")
        print(f"download failed ({e}); using the earlier copy"); offices = json.loads(raw.read_text(encoding="utf-8"))
    rows, why = match(agencies, offices, abbr, area_state)
    out = ref / "287g_agency_contacts.csv"
    if out.exists():
        old = sum(1 for _ in open(out, encoding="utf-8")) - 1
        if len(rows) < 0.8 * old: sys.exit(f"only {len(rows)} matches against {old} last time; file left as it was")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} of {len(agencies)} agencies matched; {sum(1 for r in rows if r['phone'])} with a phone number")
    for k, v in why.items(): print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
