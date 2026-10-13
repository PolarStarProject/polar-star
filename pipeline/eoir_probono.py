"""The Justice Department's List of Pro Bono Legal Service Providers (EOIR), read in full from its PDF.

Usage:  python pipeline/eoir_probono.py [path-to-pdf]
        With no path it downloads the current list from justice.gov (it is published each January, April, July and October).

The PDF is printed from a spreadsheet: one or more pages per immigration court, a court title at the top, and providers in
two columns of boxes. Each box starts with the provider's name in bold, marked * (non-profit), ** (referral service) or
*** (private attorney), then its address, phone, email, website and bullet notes. Text is read word by word with its
position, so the two columns never mix.

Writes data/reference/legal_aid_providers.csv (state|name|phone|city|kind|courts, one row per provider and state, courts
joined by "/") and legal_aid_meta.json. Nothing is written if the list looks broken: fewer than MIN_PROVIDERS providers,
a court with none, or a drop of more than a quarter from the list already on file.
"""
import csv, datetime as dt, io, json, re, sys, urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
URL = "https://www.justice.gov/eoir/file/probonofulllist/download"
MIN_PROVIDERS = 150
KIND = {1: "nonprofit", 2: "referral", 3: "attorney"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
STATES = {"ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
          "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA", "GUAM": "GU", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
          "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
          "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
          "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "NORTHERN MARIANA ISLANDS": "MP", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
          "PENNSYLVANIA": "PA", "PUERTO RICO": "PR", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX",
          "UTAH": "UT", "VERMONT": "VT", "VIRGIN ISLANDS": "VI", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY"}
PHONE = re.compile(r"(?:\+?1[\s.-]*)?\(?(\d{3})\)?[\s.-]*(\d{3})[\s.-]*(\d{4})")
CITY = re.compile(r"^(.+?),\s*([A-Z]{2})\s+\d{5}(?:-\d{4})?$")
SPLIT_X = 296          # the line between the two columns of boxes (points)
TOP_Y = 60             # the page header (key to the * marks, title, link, date) sits above this


def spans(page):
    """A page's text pieces: (x, y, size, bold, text), top to bottom."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = s["text"].replace("\xa0", " ").strip()
                if t: out.append((s["bbox"][0], s["bbox"][1], round(s["size"], 1), "Bold" in s["font"] or bool(s["flags"] & 16), t))
    return sorted(out, key=lambda r: (round(r[1]), r[0]))


def hlines(page):
    """The y of each horizontal box border on a page, per column: {0: [...], 1: [...]}. Boxes are split on these, so a bold
    word inside a box's notes is never taken for a new provider."""
    out = {0: set(), 1: set()}
    for d in page.get_drawings():
        r = d["rect"]
        if r.height <= 2 and r.width > 150:
            if r.x0 < SPLIT_X - 50: out[0].add(round(r.y0))
            if r.x1 > SPLIT_X + 50: out[1].add(round(r.y0))
    return {c: sorted(v) for c, v in out.items()}


def court_short(title):
    """'Eloy Immigration Court' -> 'Eloy'; 'Los Angeles Immigration Courts Juvenile Docket' -> 'Los Angeles juvenile docket'."""
    t = re.sub(r"\s+", " ", title).strip()
    juv = re.search(r"juvenile docket", t, re.I)
    t = re.sub(r"\s*Immigration Courts?\b", "", t, flags=re.I)
    t = re.sub(r"\s*Juvenile Docket\b", "", t, flags=re.I).strip()
    return t + (" juvenile docket" if juv else "")


def box_fields(lines):
    """One provider's box (its text lines, in order) -> dict or None. The name is the bold lines at the top."""
    name = []
    while lines and lines[0][1]: name.append(lines.pop(0)[0])
    if not name: return None
    if lines and (re.search(r"[,&/-]\s*$", name[-1]) or re.search(r"\*\s*$", lines[0][0])) and not re.search(r"\d|@|www\.|^tel", lines[0][0], re.I):
        name.append(lines.pop(0)[0])                                   # a name that runs onto a plain line ("..., College of Law," / "Law Clinic*")
    nm = re.sub(r"\s+", " ", " ".join(name)).strip()
    m = re.search(r"(\*{1,3})\s*(?:\(cont(?:inued|\.)?\))?\s*$", nm, re.I)
    kind = KIND.get(len(m.group(1)), "") if m else ""
    nm = re.sub(r"\s*\*+\s*$", "", re.sub(r"\s*\(cont(?:inued|\.)?\)\s*$", "", nm, flags=re.I).rstrip()).strip()
    text = [t for t, _ in lines]
    phone = ""
    for t in text:                                                     # the "Tel:" line first, then any number in the box
        if re.match(r"(?i)(tel|phone|telephone)\b", t):
            p = PHONE.search(t)
            if p: phone = f"({p.group(1)}) {p.group(2)}-{p.group(3)}"; break
    if not phone:
        for t in text:
            p = PHONE.search(t)
            if p: phone = f"({p.group(1)}) {p.group(2)}-{p.group(3)}"; break
    city = ""
    for t in text:
        c = CITY.match(t.strip())
        if c: city = f"{c.group(1).strip()}, {c.group(2)}"; break
    return {"name": nm, "kind": kind, "phone": phone, "city": city}


def parse_pages(pages):
    """Every page's (spans, box borders) -> ([(state, court, provider dict)], edition). A box cut by a page break carries
    on in the same column of the next page."""
    out, state, court, edition = [], "", "", ""
    open_box = {0: None, 1: None}
    for sp, hl in pages:
        title = [t for x, y, sz, bd, t in sp if sz >= 13.5 and bd and y > 45]
        hdr = " ".join(t for x, y, sz, bd, t in sp if y < TOP_Y)
        m = re.search(r"Updated\s+([A-Z][a-z]+) (\d{4})", hdr)
        if m and m.group(1) in MONTHS: edition = f"{m.group(2)}-{MONTHS.index(m.group(1)) + 1:02d}"      # "Updated October 2026" -> "2026-10"
        body = [r for r in sp if r[1] >= TOP_Y and not (r[2] >= 13.5 and r[4] in title)]
        if not title:                                                   # a state divider page or the contents
            for x, y, sz, bd, t in body:
                if bd and t.upper() in STATES and len(body) <= 3: state = STATES[t.upper()]
            continue
        new_court = court_short(" ".join(title))
        if new_court != court: open_box = {0: None, 1: None}
        court = new_court
        place = lambda t: re.match(r"^(.+?),\s*([A-Za-z .]+?)\s*(?:\(page \d+ o[fr] \d+\))?$", t)
        for x, y, sz, bd, t in body:                                     # "Eloy, Arizona" or "Adelanto, California (page 1 of 2)": the court's place and state
            m2 = place(t)
            if bd and y < 90 and m2 and m2.group(2).strip().upper() in STATES: state = STATES[m2.group(2).strip().upper()]
        cells = {0: {}, 1: {}}
        for x, y, sz, bd, t in body:
            m2 = place(t)
            if y < 90 and bd and m2 and m2.group(2).strip().upper() in STATES: continue      # the place line in the box header
            c = 0 if x < SPLIT_X else 1
            k = sum(1 for b in hl.get(c, []) if b <= y + 2)                # which box: how many borders lie above this line
            cells[c].setdefault(k, []).append((t, bd))
        for c in (0, 1):
            boxes = [cells[c][k] for k in sorted(cells[c])]
            for i, bx in enumerate(boxes):
                if i == 0 and not bx[0][1] and open_box[c] is not None:    # the rest of a box from the page before: fill what it lacked
                    more = box_fields([("x", True)] + list(bx))
                    for fld in ("phone", "city"):
                        if not open_box[c][fld]: open_box[c][fld] = more[fld]
                    continue
                f = box_fields(list(bx))
                if f: out.append((state, court, f)); open_box[c] = f
    return out, edition


def merge(rows):
    """One row per provider and state; the courts it is listed for joined by '/', in the order they appear."""
    by = {}
    for st, court, f in rows:
        k = (st, re.sub(r"[^a-z0-9]", "", f["name"].lower()))
        o = by.setdefault(k, {"state": st, "name": f["name"], "phone": f["phone"], "city": f["city"], "kind": f["kind"], "courts": []})
        for fld in ("phone", "city", "kind"):
            if not o[fld] and f[fld]: o[fld] = f[fld]
        if court not in o["courts"]: o["courts"].append(court)
    return [dict(o, courts="/".join(o["courts"])) for o in by.values()]


def main():
    import pymupdf
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src: doc = pymupdf.open(src)
    else:
        from identity import USER_AGENT
        with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": USER_AGENT}), timeout=120) as r: doc = pymupdf.open(stream=r.read(), filetype="pdf")
    rows, edition = parse_pages([(spans(p), hlines(p)) for p in doc])
    prov = merge(rows)
    courts = {c for _, c, _ in rows}
    old = list(csv.DictReader(open(REF / "legal_aid_providers.csv", encoding="utf-8"), delimiter="|")) if (REF / "legal_aid_providers.csv").exists() else []
    meta_p = REF / "legal_aid_meta.json"
    old_meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    if len(prov) < MIN_PROVIDERS: raise SystemExit(f"Only {len(prov)} providers read: the layout may have changed. Nothing written.")
    if old_meta.get("full") and len(prov) < 0.75 * len(old): raise SystemExit(f"{len(prov)} providers, down from {len(old)}. Nothing written.")
    if any(not st for st, _, _ in rows): raise SystemExit("A provider has no state: the layout may have changed. Nothing written.")
    with open(REF / "legal_aid_providers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["state", "name", "phone", "city", "kind", "courts"], delimiter="|", lineterminator="\n")
        w.writeheader(); w.writerows(sorted(prov, key=lambda r: (r["state"], r["kind"] != "referral", r["name"])))
    meta_p.write_text(json.dumps({"edition": edition, "read": str(dt.date.today()), "providers": len(prov), "courts": len(courts), "full": True, "source": URL}, indent=1), encoding="utf-8")
    print(f"{len(prov)} providers across {len(courts)} court lists, edition {edition or '?'}", file=sys.stderr)


if __name__ == "__main__": main()
