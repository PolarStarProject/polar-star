"""Federal lobbying by ICE's other contractors (not the detention operators, which money_lobbying.py covers), from the Senate's
Lobbying Disclosure Act filings (lda.gov API).

Usage:  python pipeline/vendor_lobbying.py        (needs internet; runs in GitHub Actions)

For each ICE contractor with at least $10 million in ICE contracts in the window (ice_awards.csv), and for its parent company
when one is recorded: every quarterly report since 2023 naming it as the client, the latest version per registrant, client
and quarter. A filing counts for a company only when the client name on the filing starts with the company's own name.
  usd          what the reports give as spending (the company's own reports) plus what outside firms report being paid. Own
               and outside reports can overlap, so this is an upper figure, labelled as such on the page.
  filings      reports counted
  ice_filings  reports that list ICE among the agencies contacted
  imm_filings  reports that list "Immigration" among the issue areas
  example      the newest report that lists ICE, or else the newest that lists Immigration (a link to the filing itself)
Writes data/reference/vendor_lobbying.csv and vendor_lobbying_meta.json. Nothing is written unless most requests succeed.
"""
import csv, datetime as dt, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from identity import USER_AGENT

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://lda.gov/api/v1/filings/?"
FIRST_YEAR, MIN_USD = 2023, 10_000_000
SUFFIX = {"INC", "INCORPORATED", "LLC", "L", "C", "LLP", "LP", "CORP", "CORPORATION", "CO", "COMPANY", "THE", "FEDERAL", "USA", "US", "LTD", "PLC", "GROUP"}


def core(name):
    """The words that name the company, without legal suffixes: "CACI, INC. - FEDERAL" -> "CACI"."""
    w = [x for x in re.sub(r"[^A-Z0-9 ]+", " ", re.sub(r"\(.*?\)", " ", name.upper())).split() if x not in SUFFIX]
    return " ".join(w[:4])


def same_client(client, key):
    """The report's client is this company: its name, legal suffixes and "formerly ..." left aside, is the same name.
    "ITC" is not "ITC Holdings", and "Acuity" is not "Acuity Brands"."""
    c = core(re.split(r"\b(?:FORMERLY|FKA|F/K/A|DBA|D/B/A)\b", client.upper())[0])
    return bool(key) and c == key


def tally(filings, key):
    keep = {}
    for f in filings:
        if not same_client(f["client"]["name"], key) or re.fullmatch(r"R[RA]", f.get("filing_type") or ""): continue
        k = (f["registrant"]["id"], f["client"]["id"], f["filing_year"], f["filing_period"])
        if k not in keep or f["dt_posted"] > keep[k]["dt_posted"]: keep[k] = f
    usd = n = ice = imm = 0; ex_ice = ex_imm = None
    for f in keep.values():
        n += 1; usd += int(float(f.get("income") or 0) + float(f.get("expenses") or 0))
        acts = f.get("lobbying_activities") or []
        a_ice = any("Immigration & Customs Enforcement" in (g.get("name") or "") for a in acts for g in a.get("government_entities") or [])
        a_imm = any((a.get("general_issue_code") or "") == "IMM" for a in acts)
        ice += a_ice; imm += a_imm
        if a_ice and (not ex_ice or f["dt_posted"] > ex_ice["dt_posted"]): ex_ice = f
        if a_imm and (not ex_imm or f["dt_posted"] > ex_imm["dt_posted"]): ex_imm = f
    ex = ex_ice or ex_imm
    return {"usd": usd, "filings": n, "ice_filings": ice, "imm_filings": imm, "example": (ex or {}).get("filing_document_url", "")}


def main():
    def fetch(url):
        for i in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}), timeout=90) as r:
                    time.sleep(4.2); return json.loads(r.read().decode("utf-8"))      # about 15 requests a minute without a key
            except Exception as e:
                err = str(e); time.sleep(30 if "429" in err else 8)
        return None
    rd = lambda n: list(csv.DictReader(open(REF / n, encoding="utf-8"), delimiter="|")) if (REF / n).exists() else []
    tot = {}
    for a in rd("ice_awards.csv"):
        try: tot[a["recipient"]] = tot.get(a["recipient"], 0) + float(a["window_usd"] or 0)
        except ValueError: pass
    parent = {r["recipient"]: r["parent"] for r in rd("ice_recipient_parents.csv")}
    skip = {r["recipient"] for r in rd("ice_contract_recipients.csv") if float(r.get("detention_guard_musd") or 0) * 1e6 > tot.get(r["recipient"], 0) / 2}
    todo = [r for r, v in sorted(tot.items(), key=lambda kv: -kv[1]) if v >= MIN_USD and r not in skip]
    rows, failed, asked = [], 0, 0
    for rec in todo:
        par = parent.get(rec, "").split(";")[0].strip()
        keys = [k for k in dict.fromkeys([core(rec), "" if par in skip else core(par)]) if k]      # a detention operator's own lobbying is on the Companies tab
        best = None
        for key in keys:
            fl = []
            for y in range(FIRST_YEAR, dt.date.today().year + 1):
                url = API + urllib.parse.urlencode({"client_name": key, "filing_year": y, "page_size": 25})
                while url:
                    asked += 1; j = fetch(url)
                    if j is None: failed += 1; break
                    fl += j.get("results") or []; url = j.get("next")
            t = tally(fl, key)
            if t["filings"] and (not best or t["usd"] > best["usd"]): best = dict(t, matched=key)
        if best: rows.append(dict(best, recipient=rec)); print(f"  {rec}: {best['filings']} reports, ICE {best['ice_filings']}, IMM {best['imm_filings']}", file=sys.stderr)
    if asked and failed > asked / 4: raise SystemExit(f"{failed} of {asked} lda.gov requests failed: left the list as it was.")
    with open(REF / "vendor_lobbying.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recipient", "matched", "usd", "filings", "ice_filings", "imm_filings", "example"], delimiter="|", lineterminator="\n", extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    (REF / "vendor_lobbying_meta.json").write_text(json.dumps({"read": str(dt.date.today()), "from": FIRST_YEAR, "companies_checked": len(todo), "with_lobbying": len(rows)}, indent=1), encoding="utf-8")
    print(f"{len(rows)} of {len(todo)} contractors lobbied", file=sys.stderr)


if __name__ == "__main__": main()
