"""Re-read ICE's public facility pages and field office list, and update the phone files.

Usage (on Windows, not inside a sandbox):  python pipeline\\refresh_contacts.py
Needs:  pip install requests beautifulsoup4      (optional fallback: pip install playwright; playwright install chromium)

Safety rules:
  * a number is never removed because a page failed to load; the old row is kept
  * if far fewer pages parse than last time, nothing is written (the site changed or blocked us)
  * every change is appended to data/reference/contacts_changes.log
"""
import csv, re, sys, time
from datetime import date
from pathlib import Path

BASE = "https://www.ice.gov"
REF = Path(__file__).parent.parent / "data" / "reference"
PHONE = re.compile(r"\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"}
OFFICE_KEY = {"Miramar Sub Office": "Miami"}   # ICE lists no "Miami Field Office"; this office covers Florida


def squash(text): return re.sub(r"\s+", " ", text).strip()


def parse_facility_links(html):
    return sorted(set(re.findall(r'href="(/detain/detention-facilities/[a-z0-9-]+)"', html)))


def parse_facility(main_text, title):
    """Return (name, phone). The phone is the one ICE gives for asking about a detainee, else ''."""
    t = squash(main_text)
    i = t.find("information about a detainee")
    if i < 0:                                   # some pages word it differently; use the section under its heading
        i = t.rfind("Contacting a Detainee")
    m = PHONE.search(t[i:i + 400]) if i >= 0 else None
    return squash(title), (m.group(0) if m else "")


def parse_field_offices(li_texts):
    """From the list items on the field offices page, keep ERO offices that publish a phone number."""
    out = {}
    for raw in li_texts:
        t = squash(raw)
        m = re.match(r"^(.{2,40}?) - ERO\s*(.*?(?:Field Office|Sub Office))", t)
        ph = re.search(r"\(\d{3}\) \d{3}-\d{4}", t)
        if not m or not ph or len(t) > 700: continue
        label = m.group(2).strip()
        key = OFFICE_KEY.get(label) or (label[:-len(" Field Office")] if label.endswith(" Field Office") else None)
        if key: out[key] = (label, ph.group(0))
    return out


def parse_inspection(title, href):
    """'2026 Adelanto ICE Processing Center, Adelanto, CA - Jul. 14-16, 2026' -> a row, or None if the title has another shape."""
    m = re.match(r"^(\d{4}) (.+), ([^,]+), ([A-Z]{2}) ?[-\u2013\u2014] ?(.+)$", squash(title))
    if not m: return None
    return {"fiscal_year": m.group(1), "facility": m.group(2).strip(), "city": m.group(3).strip(), "state": m.group(4), "dates": m.group(5).strip(),
            "url": BASE + href if href.startswith("/") else href}


def parse_death_counts(headings, table_row_counts):
    """ICE lists deaths in one table per fiscal year. Returns {year: deaths}, or {} if headings and tables do not line up."""
    years = [h.split()[1] for h in headings if re.match(r"^FY \d{4}$", h.strip())]
    if not years or len(years) != len(table_row_counts): return {}
    return {y: n - 1 for y, n in zip(years, table_row_counts)}          # minus the header row


def merge(old_rows, new_rows, key, today, log):
    """Update old rows from new ones by key. Returns merged rows; appends human-readable changes to log."""
    old = {r[key]: r for r in old_rows}
    for k, r in new_rows.items():
        if k not in old: log.append(f"{today} NEW {k}: {r['phone']}")
        elif old[k]["phone"] != r["phone"]:
            if not r["phone"]:                       # page loaded but no number found: keep the old one, flag it
                log.append(f"{today} MISSING-ON-PAGE {k}: kept {old[k]['phone']}"); continue
            log.append(f"{today} CHANGED {k}: {old[k]['phone']} -> {r['phone']}")
        old[k] = {**old.get(k, {}), **r, "retrieved": today}
    return [old[k] for k in sorted(old)]


def get(url, session):
    r = session.get(url, headers=UA, timeout=30)
    if r.status_code == 200: return r.text
    raise RuntimeError(f"{url} returned {r.status_code}")


def get_with_browser(urls):
    """Fallback when plain requests are refused: load the pages in a real browser."""
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False); page = b.new_page()
        for u in urls:
            page.goto(u, wait_until="domcontentloaded"); out[u] = page.content(); time.sleep(0.3)
        b.close()
    return out


def read_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8"))) if path.exists() else []


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def main():
    import requests
    from bs4 import BeautifulSoup
    today, log, s = str(date.today()), [], requests.Session()

    def fetch_all(urls):
        try:
            out = {}
            for u in urls: out[u] = get(u, s); time.sleep(0.3)
            return out
        except Exception as e:
            print(f"plain download refused ({e}); retrying in a browser"); return get_with_browser(urls)

    def text_of(html):
        soup = BeautifulSoup(html, "html.parser"); main = soup.find("main") or soup
        return main, (soup.find("h1").get_text() if soup.find("h1") else "")

    # facility pages
    links, n = set(), 0
    while n < 40:
        page = fetch_all([f"{BASE}/detention-facilities?page={n}"]).popitem()[1]
        found = set(parse_facility_links(page))
        if not found - links: break
        links |= found; n += 1
    pages = fetch_all([BASE + l for l in sorted(links)])
    new = {}
    for url, html in pages.items():
        main, h1 = text_of(html); name, phone = parse_facility(main.get_text(" "), h1)
        slug = url.rsplit("/", 1)[1]
        new[slug] = {"slug": slug, "name": name, "phone": phone, "source": url}
    old = read_csv(REF / "ice_facility_contacts.csv")
    if len([r for r in new.values() if r["phone"]]) < 0.8 * max(1, len([r for r in old if r["phone"]])):
        sys.exit(f"Only {len(new)} facility pages parsed against {len(old)} on file. Nothing written. Check the site by hand.")
    write_csv(REF / "ice_facility_contacts.csv", merge(old, new, "slug", today, log), ["slug", "name", "phone", "retrieved", "source"])

    # field offices
    lis, n = [], 0
    while n < 30:
        main, _ = text_of(fetch_all([f"{BASE}/contact/field-offices?page={n}"]).popitem()[1])
        got = [li.get_text(" ") for li in main.find_all("li") if re.search(r" - (ERO|HSI|OPLA|OPE)\b", squash(li.get_text(" ")))]
        if not got: break
        lis += got; n += 1
    offices = {k: {"field_office": k, "office_label": lab, "phone": ph, "source": f"{BASE}/contact/field-offices"}
               for k, (lab, ph) in parse_field_offices(lis).items()}
    old_o = read_csv(REF / "ice_field_offices.csv")
    if len(offices) < 0.8 * max(1, len(old_o)):
        sys.exit(f"Only {len(offices)} field offices parsed against {len(old_o)} on file. Field office file not written.")
    write_csv(REF / "ice_field_offices.csv", merge(old_o, offices, "field_office", today, log), ["field_office", "office_label", "phone", "retrieved", "source"])

    # inspection reports: this fiscal year and the two before it
    insp, fy = {}, date.today().year + (1 if date.today().month >= 10 else 0)
    for yr in (fy, fy - 1, fy - 2):
        n = 0
        while n < 60:
            soup = BeautifulSoup(fetch_all([f"{BASE}/foia/library?field_foia_category_target_id=275&created={yr}&page={n}"]).popitem()[1], "html.parser")
            links = [a for a in (soup.find("main") or soup).find_all("a", href=True) if "odo-compliance-inspections" in a["href"]]
            before = len(insp)
            for a in links:
                row = parse_inspection(a.get_text(" "), a["href"])
                if row: insp[row["url"]] = row
            if not links or len(insp) == before: break
            n += 1
    old_i = read_csv(REF / "ice_inspections.csv")
    if len(insp) >= 0.8 * len(old_i) and insp:
        keep = {r["url"]: r for r in old_i}; keep.update(insp)           # reports stay listed even after ICE moves them off these pages
        write_csv(REF / "ice_inspections.csv", [keep[k] for k in sorted(keep)], ["fiscal_year", "facility", "city", "state", "dates", "url"])
        if len(keep) != len(old_i): log.append(f"{today} INSPECTIONS {len(old_i)} -> {len(keep)} reports listed")
    else:
        print(f"Only {len(insp)} inspection reports parsed against {len(old_i)} on file. Inspection file not written.")

    # deaths in custody, counted per fiscal year from ICE's own tables (no names are stored)
    soup = BeautifulSoup(fetch_all([f"{BASE}/detain/detainee-death-reporting"]).popitem()[1], "html.parser"); main_el = soup.find("main") or soup
    heads = [h.get_text(" ").strip() for h in main_el.find_all(["h2", "h3", "h4", "button", "summary"])]
    counts = parse_death_counts(heads, [len(t.find_all("tr")) for t in main_el.find_all("table")])
    if counts:
        old_d = {r["fiscal_year"]: r["deaths_listed"] for r in read_csv(REF / "ice_deaths_by_year.csv")}
        for y, n in counts.items():
            if old_d.get(y) != str(n): log.append(f"{today} DEATHS FY{y}: {old_d.get(y, 'none')} -> {n}")
        write_csv(REF / "ice_deaths_by_year.csv", [{"fiscal_year": y, "deaths_listed": n, "retrieved": today, "source": f"{BASE}/detain/detainee-death-reporting"}
                                                  for y, n in sorted(counts.items(), reverse=True)], ["fiscal_year", "deaths_listed", "retrieved", "source"])
    else:
        print("Death tables did not line up with their fiscal-year headings. Death counts not written.")

    with open(REF / "contacts_changes.log", "a", encoding="utf-8") as f:
        f.write("".join(l + "\n" for l in log) or f"{today} no changes\n")
    print(f"{len(new)} facility pages, {len(offices)} field offices, {len(insp)} inspection reports, {len(counts)} years of death counts, {len(log)} changes")


if __name__ == "__main__":
    main()
