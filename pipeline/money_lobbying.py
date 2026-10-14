"""Federal lobbying by detention contractors, from the Senate's Lobbying Disclosure Act filings (lda.gov API).

Usage:  python pipeline/money_lobbying.py
For each company and each year from 2023: every quarterly report naming the company as the client (including a firm hired
"on behalf of" it), the latest version per registrant, client and quarter.
  own_usd      what the company's own lobbying report gives as its spending
  outside_usd  what outside firms report being paid by it. The two can overlap: never add them.
Writes data/reference/lobbying_by_year.csv, lobbying_firms.csv, lobbying_targets.csv, lobbying_former_officials.csv and
lobbying_meta.json.
A registrant that is a person, not a firm (a lobbyist registered under their own name), is named as filed: being paid by a
detention company puts them on the money trail, and the registration is a public federal filing. No addresses are kept.
Lobbyists are named only in lobbying_former_officials.csv, and only those who disclosed a past government post: they are
named for that public post, as they reported it.
Nothing is written unless every request succeeds.
"""
import csv, datetime as dt, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from identity import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://lda.gov/api/v1/filings/?"
COMPANIES = {"GEO": ("GEO Group", r"\bGEO GROUP\b"), "CC": ("CoreCivic", r"CORECIVIC"), "MTC": ("Management & Training", r"MANAGEMENT\s*(?:&|AND)\s*TRAINING\s+CORP"), "CSI": ("CSI Aviation", r"CSI AVIATION")}
FIRST_YEAR = 2023
ORG = re.compile(r"\b(LLC|LLP|L\.L\.C|INC|CORP|GROUP|STRATEG|PARTNERS|ASSOCIATES|CONSULTING|AFFAIRS|RELATIONS|ADVOCATES|COUNSEL|GLOBAL|FIRM|COMPANY|ADVISORS|SOLUTIONS|PLLC|P\.C|LTD|STRAUSS|GUMP|KNIGHT|BOGGS|TRAURIG|TOWER|CAPITOL|WASHINGTON)\b|&", re.I)
TARGETS = {"HOUSE OF REPRESENTATIVES": "House of Representatives", "SENATE": "Senate", "Homeland Security, Dept of (DHS)": "Department of Homeland Security", "U.S. Immigration & Customs Enforcement (ICE)": "ICE",
           "Office of Management & Budget (OMB)": "Office of Management and Budget", "Justice, Dept of (DOJ)": "Department of Justice", "Executive Office of the President (EOP)": "Executive Office of the President",
           "Bureau of Prisons (BOP)": "Bureau of Prisons", "Health & Human Services, Dept of (HHS)": "Department of Health and Human Services", "White House Office": "White House Office",
           "Labor, Dept of (DOL)": "Department of Labor", "Federal Aviation Administration (FAA)": "Federal Aviation Administration"}


def person_name(raw):
    """A lobbyist registered under their own name, as filed: 'SMITH, JOHN A.' -> 'John A. Smith'."""
    n = re.sub(r"\s*\(.*?\)", "", raw or "").strip()
    if "," in n: last, first = [x.strip() for x in n.split(",", 1)]; n = f"{first} {last}"
    return " ".join(w if w.isupper() and len(w) <= 3 and "." not in w and w not in ("JR", "SR") else w.title() for w in n.split()) or "A registrant filing under a personal name"


def norm(name): return re.sub(r"[^A-Z0-9]+", " ", re.sub(r"\(.*?\)", " ", name.upper())).strip()


def summarise(filings, pattern, old_names=None):
    """Filings for one company and year -> (own, outside, {firm: usd}, {target: filings}, latest quarter seen)."""
    rx, keep = re.compile(pattern, re.I), {}
    for f in filings:
        if not rx.search(f["client"]["name"]) or re.fullmatch(r"R[RA]", f["filing_type"]): continue      # registrations carry no amounts
        k = (f["registrant"]["id"], f["client"]["id"], f["filing_period"])
        if k not in keep or f["dt_posted"] > keep[k]["dt_posted"]: keep[k] = f
    own = out = 0; firms, targets, last = {}, {}, ""
    for f in keep.values():
        last = max(last, {"first_quarter": "Q1", "second_quarter": "Q2", "third_quarter": "Q3", "fourth_quarter": "Q4", "mid_year": "Q2", "year_end": "Q4"}.get(f["filing_period"], ""))
        if rx.search(f["registrant"]["name"]): own += int(float(f["expenses"] or 0) + float(f["income"] or 0))
        else:
            v = int(float(f["income"] or 0)); out += v; raw = f["registrant"]["name"]
            name = (old_names or {}).get(norm(raw)) or (re.sub(r"\s*\(.*?\)", "", raw).title().replace(" Llc", " LLC").replace(" Llp", " LLP").replace(" Dc", " DC") if ORG.search(raw) else person_name(raw))
            firms[name] = firms.get(name, 0) + v
        seen = {g["name"] for a in f.get("lobbying_activities") or [] for g in a.get("government_entities") or []}
        for n in seen: t = TARGETS.get(n, n); targets[t] = targets.get(t, 0) + 1
    return own, out, firms, targets, last


QUARTER = {"first_quarter": "Q1", "second_quarter": "Q2", "third_quarter": "Q3", "fourth_quarter": "Q4", "mid_year": "Q2", "year_end": "Q4"}


def by_quarter(filings, pattern):
    """Filings for one company and year -> ({quarter: [own, outside]}, {issue area: filings}). Same rule as summarise(): the
    latest version per registrant, client and quarter. Issue areas are the form's own fixed list (for example "Immigration",
    "Budget/Appropriations"); the free-text description on each filing is never stored."""
    rx, keep = re.compile(pattern, re.I), {}
    for f in filings:
        if not rx.search(f["client"]["name"]) or re.fullmatch(r"R[RA]", f["filing_type"]): continue
        k = (f["registrant"]["id"], f["client"]["id"], f["filing_period"])
        if k not in keep or f["dt_posted"] > keep[k]["dt_posted"]: keep[k] = f
    q, issues = {}, {}
    for f in keep.values():
        name = QUARTER.get(f["filing_period"])
        if name:
            v = q.setdefault(name, [0, 0])
            if rx.search(f["registrant"]["name"]): v[0] += int(float(f["expenses"] or 0) + float(f["income"] or 0))
            else: v[1] += int(float(f["income"] or 0))
        for i in {(a.get("general_issue_code_display") or "").strip() for a in f.get("lobbying_activities") or []} - {""}: issues[i] = issues.get(i, 0) + 1
    return q, issues



def former_officials(filings, pattern):
    """Lobbyists on the company's reports who list a past government post ("covered position" on the LDA form), with
    the firm that filed and the years they appear. These are the lobbyists' own disclosures, as filed."""
    out = {}
    for f in filings:
        if not re.search(pattern, ((f.get("client") or {}).get("name") or "").upper()): continue
        firm, y = (f.get("registrant") or {}).get("name") or "", f.get("filing_year")
        if not ORG.search(firm): firm = person_name(firm)
        for a in f.get("lobbying_activities") or []:
            for l in a.get("lobbyists") or []:
                cp = re.sub(r"\s+", " ", (l.get("covered_position") or "")).strip()
                if not cp or cp.upper().strip(". ") in ("N/A", "NA", "NONE", "N A", "NOT APPLICABLE"): continue
                p = l.get("lobbyist") or {}
                name = " ".join(x for x in [p.get("first_name"), p.get("middle_name"), p.get("last_name"), p.get("suffix")] if x).strip()
                if not name: continue
                k = (name.title(), cp, firm)
                o = out.setdefault(k, [y, y]); o[0], o[1] = min(o[0], y), max(o[1], y)
    return out

def main():
    def fetch(url, tries=6):
        for i in range(tries):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}), timeout=90) as r:
                    time.sleep(4.5); return json.loads(r.read().decode("utf-8"))           # the API allows 15 requests a minute without a key
            except Exception as e:
                err = str(e)[:120]; time.sleep(30 if "429" in err else 8)
        raise SystemExit(f"lda.gov did not answer: {err}. Nothing written.")
    rd = lambda n: list(csv.DictReader(open(REF / n, encoding="utf-8"), delimiter="|")) if (REF / n).exists() else []
    old_names = {norm(r["firm"]): r["firm"] for r in rd("lobbying_firms.csv") if "personal name" not in r["firm"]}
    years, firms, targets, latest, quarters, issues, formers = [], {}, {}, "", [], {}, {}
    for co, (query, pattern) in COMPANIES.items():
        for y in range(FIRST_YEAR, dt.date.today().year + 1):
            url, fl = API + urllib.parse.urlencode({"client_name": query, "filing_year": y, "page_size": 25}), []
            while url:
                j = fetch(url); fl += j.get("results", []); url = j.get("next")
            own, out, fm, tg, last = summarise(fl, pattern, old_names)
            if own or out: years.append({"company": co, "year": y, "own_usd": own, "outside_usd": out}); latest = max(latest, f"{y} {last}")
            for k, v in fm.items(): firms[(co, k)] = firms.get((co, k), 0) + v
            for k, v in tg.items(): targets[(co, k)] = targets.get((co, k), 0) + v
            qs, iss = by_quarter(fl, pattern)
            for qn in sorted(qs): quarters.append({"company": co, "quarter": f"{y} {qn}", "own_usd": qs[qn][0], "outside_usd": qs[qn][1]})
            for k, v in iss.items(): issues[(co, k)] = issues.get((co, k), 0) + v
            for k, (a, b) in former_officials(fl, pattern).items():
                o = formers.setdefault((co,) + k, [a, b]); o[0], o[1] = min(o[0], a), max(o[1], b)
            print(f"  {co} {y}: own {own:,}, outside {out:,}", flush=True)
    if len(years) < 8: raise SystemExit(f"Only {len(years)} company-years found. Nothing written.")
    def write(name, rows, fields):
        with open(REF / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    order = list(COMPANIES)
    write("lobbying_by_year.csv", years, ["company", "year", "own_usd", "outside_usd"])
    write("lobbying_firms.csv", [{"company": c, "firm": k, "usd": v} for (c, k), v in sorted(firms.items(), key=lambda kv: (order.index(kv[0][0]), -kv[1])) if v], ["company", "firm", "usd"])
    top = {}
    for (c, k), v in sorted(targets.items(), key=lambda kv: -kv[1]): top.setdefault(c, []).append({"company": c, "target": k, "filings": v})
    write("lobbying_targets.csv", [r for c in order for i, r in enumerate(top.get(c, [])[:10]) if i < 3 or r["filings"] >= 2], ["company", "target", "filings"])      # one-off mentions past the top three are dropped
    for r in years:                                                   # the quarters must add up to the year, or the quarterly file is not written
        qsum = [sum(q[k] for q in quarters if q["company"] == r["company"] and q["quarter"].startswith(str(r["year"]))) for k in ("own_usd", "outside_usd")]
        if qsum != [r["own_usd"], r["outside_usd"]]: raise SystemExit(f"Quarters for {r['company']} {r['year']} add to {qsum}, not {r['own_usd']}, {r['outside_usd']}. Nothing more written.")
    write("lobbying_by_quarter.csv", quarters, ["company", "quarter", "own_usd", "outside_usd"])
    itop = {}
    for (c, k), v in sorted(issues.items(), key=lambda kv: -kv[1]): itop.setdefault(c, []).append({"company": c, "issue": k, "filings": v})
    write("lobbying_issues.csv", [r for c in order for r in itop.get(c, [])[:8]], ["company", "issue", "filings"])
    write("lobbying_former_officials.csv", [{"company": c, "lobbyist": n, "covered_position": cp, "firm": fm, "first_year": a, "last_year": b} for (c, n, cp, fm), (a, b) in sorted(formers.items(), key=lambda kv: (order.index(kv[0][0]), -kv[1][1], kv[0][1]))],
          ["company", "lobbyist", "covered_position", "firm", "first_year", "last_year"])
    (REF / "lobbying_meta.json").write_text(json.dumps({"read": str(dt.date.today()), "from": FIRST_YEAR, "latest": latest}, indent=1), encoding="utf-8")
    print(f"{len(years)} company-years written; newest quarter on file: {latest}")


if __name__ == "__main__": main()
