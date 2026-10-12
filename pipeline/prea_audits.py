"""Find newly published sexual-abuse (PREA) audit reports on ICE's site and add them to data/reference/prea_audits.csv.

Usage:  python pipeline/prea_audits.py
Reads ICE's FOIA library listing of PREA audit reports, and for each report not yet in the file adds a row with:
  the facility name and audit date from the listing, the report link,
  the review period, when the report states one ("... review period between July 18, 2023, and July 18, 2024"),
  and `evidence`: the sentences that mention a number of allegations, for a person to read.

It does NOT fill in the allegation count. Tested against 36 audits already read by hand, an automatic reading of the
count was wrong about 1 time in 15 even under a strict rule, and a wrong count here is worse than a missing one.
New rows get basis "unread": the page lists the audit and its link and says the count has not been read yet.
To finish a row by hand: set allegations and basis ("stated", "files reviewed" or "not stated"), and facility_code if blank.
"""
import csv, datetime as dt, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
LIST = "https://www.ice.gov/foia/library?field_foia_category_target_id=540&page={}"
FIELDS = ["facility_as_reported", "facility_code", "audit_start", "allegations", "basis", "substantiated", "note", "report_url", "period_start", "period_end", "period_basis", "evidence"]
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
D = r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s?\d{1,2}\s?,\s?\d{4})"


def parse_listing(html):
    """[(title, url)] for every PREA audit PDF linked on one listing page."""
    out = []
    for href, text in re.findall(r'<a[^>]+href="([^"]*prea_audit/[^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.I | re.S):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).replace("&amp;", "&").replace("&#039;", "'").replace("&nbsp;", " ").strip()
        out.append((t, href if href.startswith("http") else "https://www.ice.gov" + href))
    return out


def parse_title(title):
    """'Florence Service Processing Center — Aug. 12-14, 2025' -> ('Florence Service Processing Center', '2025-08-12'). Date is '' if unreadable."""
    parts = re.split(r"\s+[–—-]\s+", title, maxsplit=1)
    name, rest = parts[0].strip(), (parts[1] if len(parts) > 1 else "")
    m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})", rest); y = re.findall(r"(20\d\d)", rest)
    if not m or not y or m.group(1).lower() not in MON: return name, ""
    year = int(y[-1]); mon = MON[m.group(1).lower()]
    if len(y) == 1 and mon == 12 and re.search(r"Jan", rest): year -= 1          # "Dec. 30-Jan. 1, 2026" starts the year before
    return name, f"{year}-{mon:02d}-{int(m.group(2)):02d}"


def iso(s):
    m = re.match(r"([A-Za-z]+)\s?(\d{1,2})\s?,\s?(\d{4})", s); return f"{m.group(3)}-{MON[m.group(1)[:3].lower()]:02d}-{int(m.group(2)):02d}"


def parse_report(text, audit_start):
    """Report text -> (period_start, period_end, period_basis, evidence). The period is kept only if it ends near the audit and runs 6 months to 4 years."""
    x = re.sub(r"\s+", " ", text)
    ps = pe = ""; basis = "not stated"
    m = re.search(r"(?:period|audit period)[^.]{0,40}?(?:between|from|is|of)\s?" + D + r"[ ,]*(?:and|through|to|thru|-|–)[ ,]*" + D, x, re.I)
    if m:
        a, b = iso(m.group(1)), iso(m.group(2))
        try:
            da, db = dt.date.fromisoformat(a), dt.date.fromisoformat(b); au = dt.date.fromisoformat(audit_start) if audit_start else db
            if db > au + dt.timedelta(days=10): db, basis2 = au + dt.timedelta(days=2), "stated start; the stated end is after the audit, so the audit date is used"
            else: basis2 = "stated"
            if 180 <= (db - da).days <= 1500 and abs((au - db).days) <= 120: ps, pe, basis = da.isoformat(), db.isoformat(), basis2
        except ValueError: pass
    ev = [s.strip()[:240] for s in re.findall(r"[^.]{0,120}\b(?:\d{1,3}|no|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:\(\d+\)\s+)?(?:PREA\s+|sexual abuse\s+)?allegations?[^.]{0,110}\.?", x, re.I)]
    seen, keep = set(), []
    for s in ev:
        if s not in seen: seen.add(s); keep.append(s)
    return ps, pe, basis, " // ".join(keep[:4]).replace("|", "/")


def main():
    sys.path.insert(0, str(Path(__file__).parent)); from icefetch import fetch_bytes
    rows = list(csv.DictReader(open(REF / "prea_audits.csv", encoding="utf-8", newline="")))
    key = lambda u: u.rsplit("/", 1)[1].lower().replace("%20", "").replace(" ", "")
    have = {key(r["report_url"]) for r in rows}
    same = {(r["audit_start"], r["facility_as_reported"].split()[0].lower()) for r in rows}      # ICE lists some audits twice under different file names
    listed = []
    for page in range(0, 40):
        u = LIST.format(page); html = fetch_bytes([u]).get(u, b"").decode("utf-8", "replace"); got = parse_listing(html)
        if not got: break
        listed += got
    if len(listed) < 100: raise SystemExit(f"Only {len(listed)} audits listed; ICE's page may have changed. Nothing written.")
    new = [(t, u) for t, u in dict.fromkeys(listed) if key(u) not in have and (parse_title(t)[1], (parse_title(t)[0].split() or [""])[0].lower()) not in same]
    print(f"{len(listed)} audits listed by ICE; {len(new)} not in the file yet", flush=True)
    if not new: return
    import pymupdf
    got = fetch_bytes([u.replace(" ", "%20") for _, u in new], pause=0.5); added = 0
    for title, u in new:
        data = got.get(u.replace(" ", "%20")); name, start = parse_title(title)
        if not data or data[:4] != b"%PDF": print(f"  not downloaded: {u}"); continue
        try: text = "\n".join(p.get_text() for p in pymupdf.open(stream=data, filetype="pdf"))
        except Exception as e: print(f"  could not read {u}: {str(e)[:100]}"); continue
        ps, pe, pb, ev = parse_report(text, start)
        if not start: print(f"  no audit date in the title, skipped: {title}"); continue
        rows.append({"facility_as_reported": name, "facility_code": "", "audit_start": start, "allegations": "", "basis": "unread", "substantiated": "", "note": "", "report_url": u,
                     "period_start": ps, "period_end": pe, "period_basis": pb, "evidence": ev}); added += 1
        print(f"  added: {name}, {start}, period {ps or '-'} to {pe or '-'}")
    with open(REF / "prea_audits.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)
    print(f"{added} audits added, marked unread; {sum(r['basis'] == 'unread' for r in rows)} in the file still need their count read by a person")


if __name__ == "__main__": main()
