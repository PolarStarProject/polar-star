"""Profiles of the lobbying firms that work for detention and ICE flight companies, from the Senate's Lobbying Disclosure
Act records (lda.gov API).

Usage:  python pipeline/firm_profiles.py        (needs internet; runs in GitHub Actions)

The firms are the ones in lobbying_firms.csv (hired by GEO, CoreCivic, MTC or CSI Aviation). For each firm, for the last
two calendar years, from its own filings:
  clients      every client on its quarterly reports (the latest version per client and quarter): what it reported
               being paid, how many reports, and whether a report listed ICE or the Department of Homeland Security among
               the agencies contacted or "Immigration" among the issues
  money        its semiannual LD-203 reports: political contributions reported by the firm and by its registered
               lobbyists, added up by the official or committee they went to, and by kind (to a campaign or committee,
               or paying for an event that honored an official). Contributors are never named: a lobbyist's personal
               gift is reported under the firm's name here.
  former       lobbyists on its reports who list a past government post ("covered position"), named only for that post,
               as they filed it (the same rule as lobbying_former_officials.csv)
A firm with very many filings is read up to PAGE_CAP pages a year, and the profile says so ("partial").
Writes data/reference/firm_clients.csv, firm_money.csv, firm_former.csv and firm_meta.json. Nothing is written unless
most requests succeed.
"""
import csv, datetime as dt, hashlib, json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from identity import USER_AGENT

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://lda.gov/api/v1/"
YEARS_BACK, PAGE_CAP = 1, 40           # this year and last year; at most 40 pages (1,000 reports) a firm a year
SUFFIX = {"INC", "INCORPORATED", "LLC", "L", "C", "LLP", "LP", "PLLC", "PC", "P", "CORP", "CORPORATION", "CO", "COMPANY", "THE", "LTD", "PLC", "DC", "D"}
QUARTER = {"first_quarter": "Q1", "second_quarter": "Q2", "third_quarter": "Q3", "fourth_quarter": "Q4", "mid_year": "H1", "year_end": "H2"}
EVENT = {"he": "honorary", "me": "meeting", "ple": "library", "pic": "inaugural"}


def core(name):
    """The words that name a firm, without legal suffixes or a "d/b/a" tail: "Capitol Counsel, LLC" -> "CAPITOL COUNSEL"."""
    n = re.split(r"\b(?:D/B/A|DBA|F/K/A|FKA|FORMERLY)\b", (name or "").upper())[0]
    return " ".join(w for w in re.sub(r"[^A-Z0-9 ]+", " ", re.sub(r"\(.*?\)", " ", n)).split() if w not in SUFFIX)


def qname(name):
    """The name to search lda.gov with: the firm's name without a legal suffix, keeping "&" ("Holland & Knight LLP" ->
    "Holland & Knight"). lda.gov matches part of a name, so the search is wide; core() then keeps only this firm's filings."""
    w = re.sub(r"\(.*?\)", " ", re.split(r"(?i)\b(?:d/b/a|dba)\b", name or "")[0]).replace(",", " ").replace(".", " ").split()
    while len(w) > 1 and w[-1].upper() in SUFFIX: w.pop()
    return " ".join(w)


TITLE = re.compile(r"^(?:the\s+)?(?:hon(?:orable)?\.?\s+|rep(?:resentative)?\.?\s+|congress(?:wo)?man\s+|sen(?:ator)?\.?\s+|mr\.?\s+|ms\.?\s+|mrs\.?\s+|dr\.?\s+|gov(?:ernor)?\.?\s+|leader\s+|speaker\s+|whip\s+)+", re.I)


def recipient(name):
    """One spelling per official: titles dropped ("Senator John Cornyn" -> "John Cornyn"), spaces and case tidied."""
    n = TITLE.sub("", re.sub(r"\s+", " ", (name or "")).strip().strip(",;. "))
    m = re.fullmatch(r"([^,;]+), ([^,;]+)", n)                        # "Cornyn, John" -> "John Cornyn"; "King Jr., Angus" -> "Angus King Jr."
    if m and len(m.group(2).split()) <= 3 and not ORGWORD.search(n):
        last, first = m.group(1).strip(), m.group(2).strip()
        sfx = re.search(r"\s+(Jr\.?|Sr\.?|II|III|IV)$", last, re.I)
        n = f"{first} {last[:sfx.start()]}{sfx.group(0)}" if sfx else f"{first} {last}"
    if not (n.isupper() or n.islower()): return n
    keep = lambda w: w.upper() in ("PAC", "PACS", "USA") or (len(w) <= 5 and not re.search(r"[AEIOUY]", w.upper()))      # NRSC, DSCC, PAC stay as written
    return " ".join(w.upper() if keep(w) else w.title() for w in n.split())


ORGWORD = re.compile(r"\b(?:INC|INCORPORATED|LLC|LLP|LP|PLLC|PC|PBC|CORP|CORPORATION|CO|COMPANY|COMPANIES|GROUP|LTD|LIMITED|PLC|SA|S\.A|AG|NV|GMBH|SPA|AB|"
                     r"ASSOCIATION|ASSN|ASSOCIATES|COUNCIL|FOUNDATION|UNIVERSITY|COLLEGE|SCHOOL|CITY|COUNTY|STATE|TOWN|VILLAGE|BOROUGH|PORT|TRIBE|NATION|BAND|INSTITUTE|SOCIETY|"
                     r"COALITION|ALLIANCE|PARTNERS|PARTNERSHIP|HOLDINGS|TECHNOLOGIES|TECHNOLOGY|SYSTEMS|SERVICES|HEALTH|HEALTHCARE|HOSPITAL|MEDICAL|BANK|FUND|FUNDS|TRUST|AUTHORITY|"
                     r"DISTRICT|DEPARTMENT|AGENCY|BUREAU|CENTER|CENTRE|NETWORK|INDUSTRIES|ENERGY|POWER|WATER|GAS|OIL|AIR|AIRLINES|AVIATION|USA|US|AMERICA|AMERICAN|NATIONAL|INTERNATIONAL|"
                     r"GLOBAL|WORLD|PROJECT|CAMPAIGN|FORUM|LEAGUE|UNION|FEDERATION|CONFERENCE|COMMITTEE|COMMISSION|BOARD|CLUB|CHURCH|MINISTRIES|ACTION|FRONT|PARTY|CAPITAL|VENTURES|"
                     r"MANAGEMENT|RESEARCH|LABS|LABORATORIES|SOLUTIONS|PRODUCTS|BRANDS|FOODS|FARMS|MOTORS|STEEL|GOLD|MINING|RESOURCES|SPACE|SECURITY|DEFENSE|MEDIA|NEWS|SOCIAL|"
                     r"CLOUD|TOUR|CASINOS|RACING|CONSULTING|CONSULTANTS|ADVISORS|SYSTEM|MARITIME|SHIPPING|HOUSING|DEVELOPMENT|ENTERPRISES|CONNECTIVITY|READER|COMMUNITY|HOME|HOMES|CHILDREN|CHILDREN'S|INDIAN|PUEBLO|OUR|OF|THE|AND|FOR)\b", re.I)
PERSON_DESC = re.compile(r"\b(?:individual|private citizen|private person|philanthropist|entrepreneur|businessman|businesswoman|investor|self\b|personal capacity|on (?:his|her) own behalf)", re.I)
PERSONAL = "A client filing under a personal name"
NAMED_FOR_PEOPLE = {"MORGAN STANLEY", "WOOD MACKENZIE", "THOMSON REUTERS", "HUI HULIAU", "RELATED ROSS", "LIBERTY MARITIME", "JUST RIGHT READER", "SAVE OUR SIMULATION"}      # companies whose names read like a person's
PEOPLE = {'6a49206e1f24', '93da670413ec'}      # people found by review whose first name the name list does not know; kept as short hashes so no name is stored here
_given = None


def is_person(name, desc=""):
    """Is this lobbying client a person rather than an organization? Private people are never named on the page (the same
    rule as lobbying_firms.csv). A person: a short name with no organization word, and either a first name that is a known
    given name ("SMITH, JOHN" or "JOHN SMITH") with a last name that is not one, or a description such as "Individual"."""
    global _given
    n = re.sub(r"\s+", " ", (name or "")).strip()
    if not n or re.search(r"[\d&/]", n) or ORGWORD.search(n): return False
    if "," in n: last, first = [x.strip() for x in n.split(",", 1)]; w = first.split() + last.split()
    else: w = n.split()
    w = [x.strip(".") for x in w if x.strip(".").upper() not in ("JR", "SR", "II", "III", "IV", "MR", "MS", "MRS", "DR") and len(x.strip(".")) > 1]
    if not 2 <= len(w) <= 4 or len(w[0]) < 3 or not all(re.fullmatch(r"[A-Za-z'\-]+", x) for x in w): return False
    if PERSON_DESC.search(desc or ""): return True
    if _given is None:
        try:
            import gender_guesser.detector as gg; _given = gg.Detector(case_sensitive=False).get_gender
        except ImportError: _given = False
    if not _given: return False
    known = lambda x: _given(x.capitalize()) != "unknown"
    if hashlib.sha1(" ".join(w).upper().encode()).hexdigest()[:12] in PEOPLE: return True
    return known(w[0]) and " ".join(w).upper() not in NAMED_FOR_PEOPLE


def clients_of(filings, key):
    """A firm's filings -> {client: {usd, filings, ice, dhs, imm, first, last}}. Only filings the firm itself filed (its
    name, without suffixes, is the firm's), the latest version per client and quarter, registrations left out."""
    keep = {}
    for f in filings:
        if core((f.get("registrant") or {}).get("name")) != key or re.fullmatch(r"R[RA]", f.get("filing_type") or ""): continue
        c = f.get("client") or {}
        k = (c.get("id"), f.get("filing_year"), f.get("filing_period"))
        if k not in keep or (f.get("dt_posted") or "") > (keep[k].get("dt_posted") or ""): keep[k] = f
    out = {}
    for f in keep.values():
        c = f.get("client") or {}
        name = re.sub(r"\s+", " ", (c.get("name") or "")).strip()
        if not name: continue
        acts = f.get("lobbying_activities") or []
        ents = {g.get("name") or "" for a in acts for g in a.get("government_entities") or []}
        q = f"{f.get('filing_year')} {QUARTER.get(f.get('filing_period'), '')}".strip()
        o = out.setdefault(name, {"usd": 0, "filings": 0, "ice": 0, "dhs": 0, "imm": 0, "first": q, "last": q, "person": False})
        o["person"] = o["person"] or is_person(name, c.get("general_description") or "")
        o["usd"] += int(float(f.get("income") or 0)); o["filings"] += 1
        o["ice"] += any("Immigration & Customs Enforcement" in e for e in ents)
        o["dhs"] += any(e.startswith("Homeland Security") for e in ents)
        o["imm"] += any((a.get("general_issue_code") or "") == "IMM" for a in acts)
        o["first"], o["last"] = min(o["first"], q), max(o["last"], q)
    return out


def person_key(name):
    """'SMITH, JOHN A.' / 'John A. Smith Jr.' -> ('JOHN', 'SMITH'): first and last name, to match one record against another."""
    n = re.sub(r"\s+", " ", (name or "")).strip().upper()
    if "," in n: last, first = n.split(",", 1); n = f"{first} {last}"
    w = [x for x in re.sub(r"[^A-Z' -]", " ", n).split() if x not in ("JR", "SR", "II", "III", "IV", "MR", "MS", "MRS", "DR") and len(x) > 1]
    return (w[0], w[-1]) if len(w) >= 2 else None


def trail_people(ref):
    """People already on the detention money trail in other records: named donors to the detention companies' committees
    (fec_donors.csv). A lobbying client who is one of them is named."""
    p = Path(ref) / "fec_donors.csv"
    if not p.exists(): return frozenset()
    return frozenset(k for k in (person_key(r["name"]) for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="|")) if k)


def on_trail(name, v, donors=frozenset()):
    """A private person is named only when their own records tie them to the detention money trail: a lobbying report of
    theirs lists ICE or Homeland Security among the agencies lobbied or immigration among the issues, or they are a named
    donor to a detention company's committee. Checked again on every refresh, so a person who becomes tied is named then."""
    return bool(int(v.get("ice") or 0) or int(v.get("dhs") or 0) or int(v.get("imm") or 0) or person_key(name) in donors)


def mask_people(clients, donors=frozenset()):
    """{client: fields} -> the same, with each private person not on the trail replaced by an unnamed row (one per person)."""
    out = {}
    for name, v in clients.items():
        if v.get("person") and not on_trail(name, v, donors): name = PERSONAL + "#" + hashlib.sha1(name.upper().encode()).hexdigest()[:8]
        out[name] = {k: x for k, x in v.items() if k != "person"}
    return out


def money_of(reports, key):
    """LD-203 reports by a firm and its lobbyists -> {(recipient, kind): [usd, gifts]}. The recipient is the honoree when
    one is named (the official), else the payee (the committee). kind is "campaign" for a contribution to a candidate or
    committee, or the kind of event paid for. No contributor is kept."""
    out, seen = {}, set()
    for r in reports:
        if core((r.get("registrant") or {}).get("name")) != key: continue
        rid = r.get("filing_uuid") or r.get("url") or id(r)
        if rid in seen: continue
        seen.add(rid)
        for it in r.get("contribution_items") or []:
            kind = "campaign" if (it.get("contribution_type") or "").lower() == "feca" else EVENT.get((it.get("contribution_type") or "").lower(), "other")
            to = recipient(it.get("honoree_name") or it.get("payee_name"))
            try: usd = float(it.get("amount") or 0)
            except (TypeError, ValueError): usd = 0
            if not to or usd <= 0: continue
            o = out.setdefault((to, kind), [0.0, 0]); o[0] += usd; o[1] += 1
    return out


def former_of(filings, key):
    """Lobbyists on the firm's reports who list a past government post, with that post as they filed it."""
    out = {}
    for f in filings:
        if core((f.get("registrant") or {}).get("name")) != key: continue
        for a in f.get("lobbying_activities") or []:
            for l in a.get("lobbyists") or []:
                cp = re.sub(r"\s+", " ", (l.get("covered_position") or "")).strip()
                if not cp or cp.upper().strip(". ") in ("N/A", "NA", "NONE", "N A", "NOT APPLICABLE"): continue
                p = l.get("lobbyist") or {}
                name = " ".join(x for x in [p.get("first_name"), p.get("middle_name"), p.get("last_name"), p.get("suffix")] if x).strip().title()
                if name and len(cp) > len(out.get(name, "")): out[name] = cp
    return out


def main():
    asked = failed = 0
    key = os.environ.get("LDA_API_KEY", "").strip()                   # optional, free from lda.gov: 120 requests a minute instead of 15
    head = {"Accept": "application/json", "User-Agent": USER_AGENT, **({"Authorization": f"Token {key}"} if key else {})}
    pause = 0.6 if key else 4.2
    def fetch(url):
        nonlocal asked, failed
        asked += 1
        for i in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=90) as r:
                    time.sleep(pause); return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                err = str(e); time.sleep(30 if "429" in err else 8)
        failed += 1; return None
    def pages(endpoint, q):
        url, out, n, full = API + endpoint + "/?" + urllib.parse.urlencode(dict(q, page_size=25)), [], 0, True
        while url:
            if n >= PAGE_CAP: full = False; break
            j = fetch(url); n += 1
            if j is None: break
            out += j.get("results") or []; url = j.get("next")
        return out, full
    firms = sorted({r["firm"] for r in csv.DictReader(open(REF / "lobbying_firms.csv", encoding="utf-8"), delimiter="|") if "personal name" not in r["firm"]})
    this = dt.date.today().year
    donors = trail_people(REF)
    rows_c, rows_m, rows_f, meta = [], [], [], {"read": str(dt.date.today()), "years": [this - YEARS_BACK, this], "firms": {}}
    for firm in firms:
        key = core(firm); cl, mo, fo, partial = {}, {}, {}, False
        for y in range(this - YEARS_BACK, this + 1):
            fl, full = pages("filings", {"registrant_name": qname(firm), "filing_year": y}); partial |= not full
            for k, v in clients_of(fl, key).items():
                o = cl.setdefault(k, {"usd": 0, "filings": 0, "ice": 0, "dhs": 0, "imm": 0, "first": v["first"], "last": v["last"], "person": False})
                o["person"] = o["person"] or v["person"]
                for f in ("usd", "filings", "ice", "dhs", "imm"): o[f] += v[f]
                o["first"], o["last"] = min(o["first"], v["first"]), max(o["last"], v["last"])
            for k, v in former_of(fl, key).items():
                if len(v) > len(fo.get(k, "")): fo[k] = v
            rp, full = pages("contributions", {"registrant_name": qname(firm), "filing_year": y}); partial |= not full
            for k, (usd, n) in money_of(rp, key).items():
                o = mo.setdefault(k, [0.0, 0]); o[0] += usd; o[1] += n
        cl = mask_people(cl, donors)                                       # private people off the trail: counted, not named
        rows_c += [{"firm": firm, "client": k.split("#")[0] if k.startswith(PERSONAL) else k, **v} for k, v in sorted(cl.items(), key=lambda kv: -kv[1]["usd"])]
        rows_m += [{"firm": firm, "recipient": k[0], "kind": k[1], "usd": round(v[0]), "gifts": v[1]} for k, v in sorted(mo.items(), key=lambda kv: -kv[1][0])]
        rows_f += [{"firm": firm, "lobbyist": k, "covered_position": v} for k, v in sorted(fo.items())]
        meta["firms"][firm] = {"clients": len(cl), "partial": partial}
        print(f"  {firm}: {len(cl)} clients, {len(mo)} recipients, {len(fo)} former officials{' (partial)' if partial else ''}", file=sys.stderr)
    if not asked or failed > asked / 4: raise SystemExit(f"{failed} of {asked} lda.gov requests failed: left the profiles as they were.")
    def write(n, rows, fields):
        with open(REF / n, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n", extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    write("firm_clients.csv", rows_c, ["firm", "client", "usd", "filings", "ice", "dhs", "imm", "first", "last"])
    write("firm_money.csv", rows_m, ["firm", "recipient", "kind", "usd", "gifts"])
    write("firm_former.csv", rows_f, ["firm", "lobbyist", "covered_position"])
    (REF / "firm_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{len(firms)} firms profiled", file=sys.stderr)


if __name__ == "__main__": main()
