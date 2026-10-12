"""Collect members of Congress's own press statements about being refused entry to, or visiting, ICE detention sites.

Usage (on Windows):  python pipeline\\visit_statements.py            (weekly: newest 3 pages per member)
                     python pipeline\\visit_statements.py --pages 15 (first run: goes back about 150 releases per member, slow)
Reads  data/reference/legislators-current.csv (each member's official site and press feed) and data/site_data.json
Writes data/reference/oversight_statements.csv   (rows are only ever added, never removed)

What this is: the member, date and link of a press release on the member's official .gov site. The headline is read to decide
whether the release is about a visit or a refusal, and is NOT kept: headlines can name a detained person, and this project stores nothing about a private person.
What this is not: a checked record of a visit. A release that only comments on someone else's visit can match too,
so the page shows these as "statements", apart from the hand-checked visit log.

Only .house.gov and .senate.gov pages are read, so a row can only come from an official site.
House: the press-release listing at <site>/media/press-releases, which most House sites share (checked live 2026-10-04;
the site-wide /rss.xml there lists static pages, not releases, so it is not used). Senate: the member's press feed when
the legislators file has one. Members whose site has neither are skipped and counted.
"""
import csv, json, re, sys, urllib.error, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent
PLACE = re.compile(r"\bI\.?C\.?E\b\.?|(?i:\b(immigration|detention|detainees?|processing center|holding (?:facility|area|cells?))\b)")      # "ICE" in capitals only: "Miracle on Ice" is not the agency
NOT_A_SITE = re.compile(r"hockey|olympic|southern border|\bUSCIS\b|citizenship and immigration services", re.I)
NOT_YET = re.compile(r"\b(plans?|announces?|requests?|invites?)\b.{0,70}\b(visit|tour)|\brestrictions on\b.{0,30}\bvisits?\b", re.I)          # a visit planned, asked for or argued about is not a visit
DENIED = re.compile(r"\b(den(?:ied|ies|y|ial)|refus(?:ed|es|al)|block(?:ed|s)|barred|turned away|locked out|stonewall\w*)\b.{0,80}\b(entry|access|oversight|visit|tour|inspect\w*|enter\w*)\b|\b(entry|access|visit|tour|inspection)\b.{0,60}\b(denied|refused|blocked)\b", re.I | re.S)
VISIT = re.compile(r"\b(oversight (?:visit|inspection|tour)|unannounced (?:visit|inspection)|toured|inspect(?:s|ed)|visit(?:s|ed))\b", re.I)
GENERIC = re.compile(r"\b(ice|processing|center|centre|detention|facility|correctional|corrections|county|jail|staging|service|regional|federal|institution|complex|annex|hold|room|the|of|and|us|dept|department|sheriff|sheriffs|office|prison|adult|justice|public|safety|law|enforcement)\b", re.I)
FIELDS = ["date", "official", "party", "kind", "title", "link", "facility_code", "collected"]
COVER = ["member", "party", "type", "state", "status", "listing", "releases_read", "oldest", "why"]


def official_host(url):
    h = (urlparse(url).hostname or "").lower()
    return h.endswith(".house.gov") or h.endswith(".senate.gov")


def feeds_for(m):
    out = [m["rss_url"].replace("http://", "https://")] if m.get("rss_url") and m["type"] == "sen" else []
    return [u for u in out if official_host(u)]


LISTINGS = ["/media/press-releases", "/news/documentquery.aspx?DocumentTypeID=27", "/media-center/press-releases",
            "/newsroom/press-releases", "/news/press-releases", "/press-releases",
            "/public/index.cfm/press-releases", "/public/index.cfm/news-releases", "/press-office/press-releases", "/news/releases", "/newsroom/releases",
            "/media/news-releases", "/news/news-releases", "/newsroom/news-releases", "/newsroom", "/news"]
RELEASE = re.compile(r"/press-releases?/[^/?#]{8,}|documentsingle\.aspx\?DocumentID=\d+|/(?:news-)?releases?/[^/?#]{8,}|/(?:press-releases|news-releases)\?ID=[0-9A-F-]{8,}"
                     r"|/(?:newsroom|news|media-center|media)/(?:\d{4}/(?:\d{1,2}/)?)?[a-z0-9]+(?:-[a-z0-9]+){3,}/?$", re.I)
FIND_LISTING = re.compile(r"press releases?|news releases?|newsroom", re.I)


def discover(html, base):
    """The site's own link to its press releases, from its home page, as a path. '' if none is found."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urlparse
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        if FIND_LISTING.search(a.get_text(" ", strip=True)):
            u = urlparse(urljoin(base, a["href"]))
            if official_host(u.geturl()) and u.path not in ("", "/"): return u.path + (("?" + u.query) if u.query else "")
    return ""
DATE = re.compile(r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, \d{4})\b|\b(\d{1,2}/\d{1,2}/\d{2,4})\b|\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b")


def page_url(base, listing, page):
    """Listing pages: Drupal sites count from ?page=0, documentquery sites from &Page=1."""
    u = base.rstrip("/") + listing
    if not page: return u
    return u + (f"&Page={page + 1}" if "documentquery" in listing else f"?page={page}")


def to_day(text):
    m = DATE.search(text or "")
    if not m: return ""
    raw = m.group(0).replace("Sept ", "Sep ").replace(".", "/") if m.group(3) else m.group(0).replace("Sept", "Sep").replace(".", "")
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try: return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError: continue
    return ""


def parse_listing(html, base):
    """[(title, link, date, summary)] from a press-release listing page, whatever the site layout: every link that
    points at a single release, with the date and text found in the block around it."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    out, seen = [], set()
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=RELEASE):
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        link = urljoin(base, a["href"])
        if len(title) < 15 or link in seen or not official_host(link): continue
        seen.add(link)
        box, day = a, ""
        for _ in range(4):                                           # climb to the row that holds the date
            if box.parent is None: break
            box = box.parent
            day = to_day(box.get_text(" ", strip=True).replace(title, " "))
            if day: break
        body = re.sub(r"\s+", " ", box.get_text(" ", strip=True).replace(title, " "))[:600] if day else ""
        out.append((title, link, day, body))
    return out


def parse_feed(xml_text):
    """[(title, link, date YYYY-MM-DD or '', summary)] from RSS 2.0 or Atom."""
    root = ET.fromstring(xml_text)
    strip = lambda t: t.split("}")[-1]
    out = []
    for it in (e for e in root.iter() if strip(e.tag) in ("item", "entry")):
        d = {}
        for c in it:
            k = strip(c.tag)
            if k == "link": d["link"] = (c.text or "").strip() or c.get("href", "")
            elif k in ("title", "description", "summary", "content", "pubDate", "published", "updated", "date"): d.setdefault(k, (c.text or "").strip())
        raw = d.get("pubDate") or d.get("published") or d.get("date") or d.get("updated") or ""
        day = ""
        try: day = parsedate_to_datetime(raw).date().isoformat()
        except Exception:
            m = re.match(r"\d{4}-\d{2}-\d{2}", raw); day = m.group(0) if m else ""
        text = re.sub(r"<[^>]+>", " ", d.get("description") or d.get("summary") or d.get("content") or "")
        out.append((re.sub(r"\s+", " ", d.get("title", "")), d.get("link", ""), day, re.sub(r"\s+", " ", text)))
    return out


def classify(title, summary):
    """'denied', 'visit' or None, from the title alone. Body text is too loose: a release about detainees being
    'denied access to clergy' is not a member being refused entry."""
    if not PLACE.search(title) or NOT_A_SITE.search(title) or NOT_YET.search(title): return None
    if DENIED.search(title): return "denied"
    if VISIT.search(title): return "visit"
    return None


def facility_index(facilities):
    """Distinctive part of each facility name -> code, only where that part belongs to one facility."""
    seen = {}
    for code, f in facilities.items():
        short = re.sub(r"\s+", " ", GENERIC.sub(" ", re.sub(r"[^A-Za-z ]", " ", f["name"]))).strip().lower()
        if len(short) >= 6: seen.setdefault(short, []).append(code)
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


NEAR = r"(?:\w+ ){0,3}(?:ice|detention|processing|facility|center|jail|field office|holding)"


def match_facility(text, index, official="", state="", fstate=None):
    """Code of the one facility named in the text, else ''. A one-word name counts only when it is not a word of the
    official's own name (Randall, Wilson) and a detention word follows within a few words."""
    t = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", text.lower())) + " "
    own = set(re.sub(r"[^a-z ]", " ", official.lower()).split())
    hits = set()
    for short, code in index.items():
        if f" {short} " not in t: continue
        if fstate is not None:                                       # same place name in two states (Bowling Green KY / VA): the facility's
            fs = fstate.get(code, "")                                # state must be the member's own, or be named in the text
            from build_site import STATE_NAMES
            if fs != state and f" {STATE_NAMES.get(fs, '~').lower()} " not in t: continue
        if " " not in short and (short in own or not re.search(rf" {re.escape(short)} {NEAR}\b", t)): continue
        hits.add(code)
    return hits.pop() if len(hits) == 1 else ""          # two different facilities named: leave it unassigned


def read_member(m, fetch, pages, since):
    """(items, status, listing used). House: the first listing address that yields releases, paged back until `pages`
    pages or a release older than `since`. Senate: the same addresses, plus the press feed if the file has one."""
    items, used, why = [], "", ""
    if m.get("url") and official_host(m["url"]):
        def order():                                                 # the six usual addresses, then the site's own press link, then rarer addresses
            yield from LISTINGS[:6]
            nonlocal why
            try:
                x = discover(fetch(m["url"]), m["url"])
                if x and x not in LISTINGS: yield x
            except Exception as e: why = why or str(e)[:60]
            yield from LISTINGS[6:]
        for listing in order():
            try: got = parse_listing(fetch(page_url(m["url"], listing, 0)), m["url"])
            except Exception as e: why = why or str(e)[:60]; continue
            if not got: why = why or "no release links found"; continue
            used, items = listing, got
            for p in range(1, pages):
                dated = [d for _, _, d, _ in items if d]
                if since and dated and min(dated) < since: break
                try: more = parse_listing(fetch(page_url(m["url"], listing, p)), m["url"])
                except Exception: break
                fresh = [r for r in more if r[1] not in {i[1] for i in items}]
                if not fresh: break                                  # past the last page (or the site ignores the page number)
                items += fresh
            break
    for u in feeds_for(m):
        try: items += [r for r in parse_feed(fetch(u)) if r[1] not in {i[1] for i in items}]; used = used or "feed"
        except Exception: continue
    WHY[m.get("full_name", "")] = "" if items else (why or "no listing page answered")
    if items: return items, "read", used
    return [], ("no_site" if not m.get("url") else "unreadable"), ""


WHY = {}      # member -> why the last read failed, for oversight_coverage.csv


def collect(members, fetch, index, have, today, pages=3, progress=None, since="", fstate=None):
    rows, cover = [], []
    stats = {"members": 0, "feeds_read": 0, "no_feed": 0, "feed_failed": 0}
    for m in members:
        stats["members"] += 1
        if progress and stats["members"] % 25 == 0: progress(stats["members"], len(members), rows, cover)
        items, status, used = read_member(m, fetch, pages, since)
        dated = [d for _, _, d, _ in items if d]
        cover.append({"member": m["full_name"], "party": m.get("party", ""), "type": m["type"], "state": m["state"], "status": status,
                      "listing": used, "releases_read": len(items), "oldest": min(dated) if dated else "", "why": WHY.get(m["full_name"], "")})
        stats["feeds_read" if status == "read" else "no_feed" if status == "no_site" else "feed_failed"] += 1
        title_of = "Senator" if m["type"] == "sen" else "Representative"
        official = f'U.S. {title_of} {m["full_name"]} ({m["state"]})'
        for title, link, day, summary in items:
            if not link or link in have or not official_host(link): continue
            if since and day and day < since: continue
            kind = classify(title, summary)
            if not kind: continue
            have.add(link)
            rows.append({"date": day, "official": official, "party": m.get("party", ""), "kind": kind, "title": "",      # the headline decides the kind and is then thrown away: headlines can name a detained person

                         "link": link, "facility_code": match_facility(f"{title} {summary}", index, m["full_name"], m["state"], fstate), "collected": today})
    return rows, stats, cover


def recheck(old, index, party_of, fstate=None):
    """Apply the current rules to rows collected under older rules; rows that no longer qualify are dropped."""
    out = []
    for r in old:
        if not r.get("title"):                                    # already judged and its headline discarded: kept as it is
            out.append({**{k: r.get(k, "") for k in FIELDS}, "party": r.get("party") or party_of.get(r["official"], "")}); continue
        kind = classify(r["title"], "")
        if not kind: continue
        name = re.sub(r"^U\.S\. (Senator|Representative) | \([A-Z]{2}\)$", "", r["official"])
        out.append({**{k: r.get(k, "") for k in FIELDS}, "kind": kind, "party": r.get("party") or party_of.get(r["official"], ""),
                    "facility_code": match_facility(r["title"], index, name, r["official"][-3:-1], fstate), "title": ""})
    return out


def main():
    ref = ROOT / "data" / "reference"; out = ref / "oversight_statements.csv"
    members = list(csv.DictReader(open(ref / "legislators-current.csv", encoding="utf-8")))
    sys.path.insert(0, str(Path(__file__).parent))
    facs = json.loads((ROOT / "data" / "site_data.json").read_text(encoding="utf-8"))["facilities"]
    index = facility_index(facs); fstate = {c: f.get("state", "") for c, f in facs.items()}
    party_of = {f'U.S. {"Senator" if m["type"] == "sen" else "Representative"} {m["full_name"]} ({m["state"]})': m.get("party", "") for m in members}
    old = recheck(list(csv.DictReader(open(out, encoding="utf-8"))) if out.exists() else [], index, party_of, fstate)
    arg = lambda name, default: sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    since = arg("--since", "")
    pages = int(arg("--pages", "400" if since else "3"))
    if "--recheck" in sys.argv: members = []
    import time
    browser = {}
    def by_browser(u):
        """A real browser, for sites that refuse a plain request. Started only when first needed; closed at the end of the run."""
        if "page" not in browser:
            from playwright.sync_api import sync_playwright
            browser["pw"] = sync_playwright().start(); browser["b"] = browser["pw"].chromium.launch(headless=False); browser["page"] = browser["b"].new_page()
        browser["page"].goto(u, wait_until="domcontentloaded", timeout=30000); time.sleep(1.0)
        return browser["page"].content()
    refused = set()
    def fetch(u):
        time.sleep(0.3)
        host = u.split("/")[2]
        if host not in refused:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
                with urllib.request.urlopen(req, timeout=20) as r: return r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code == 404: raise
                refused.add(host)                                     # 403, 429 and the like: this site wants a browser
            except Exception: refused.add(host)
        return by_browser(u)
    def save(rows, cover):
        allrows = sorted(old + rows, key=lambda r: r["date"], reverse=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(allrows)
        if cover:
            with open(ref / "oversight_coverage.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=COVER); w.writeheader(); w.writerows(cover)
        return allrows
    def progress(done, total, rows, cover):                          # so a long run shows it is alive and keeps what it has found
        print(f"  {done} of {total} members, {len(rows)} new statements so far", flush=True); save(rows, cover)
    rows, stats, cover = collect(members, fetch, index, {r["link"] for r in old}, datetime.now().date().isoformat(), pages, progress, since, fstate)
    allrows = save(rows, cover)
    print(f'{len(rows)} new statements, {len(allrows)} in the file; {stats["feeds_read"]} of {stats["members"]} member press pages read, '
          f'{stats["no_feed"]} with no site, {stats["feed_failed"]} unreadable')
    for party in sorted({c["party"] for c in cover}):
        got = [c for c in cover if c["party"] == party]
        print(f'  {party}: {sum(1 for c in got if c["status"] == "read")} of {len(got)} members read')
    if members and stats["feeds_read"] < 0.8 * stats["members"]: print("WARNING: under 80% of members were readable; see data/reference/oversight_coverage.csv")


if __name__ == "__main__":
    main()
