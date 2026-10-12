"""Watch the SEC for new annual reports and proxy statements from GEO Group and CoreCivic.

Usage:  python pipeline/sec_watch.py
The figures the page uses (share of revenue from ICE, largest shareholders) are sentences and tables inside those filings,
which are read by a person. This script only checks the SEC's filing index and writes data/reference/sec_meta.json:
  checked   the day the index was read
  newer     filings posted after the ones data/reference/sec_company_facts.csv and sec_shareholders.csv were read from
When `newer` is not empty the page marks the SEC source as out of date until the files are re-read.
"""
import csv, datetime as dt, json, sys, time, urllib.request
from pathlib import Path
from identity import sec_user_agent

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
CIK = {"The GEO Group": "0000923796", "CoreCivic": "0001070985"}
FORMS = {"10-K": "sec_company_facts.csv", "DEF 14A": "sec_shareholders.csv"}


def newer(recent, have):
    """recent: the SEC's parallel lists (form, filingDate, accessionNumber, primaryDocument); have: {form: newest filed date on file}."""
    out = []
    for form, day, acc, doc in zip(recent["form"], recent["filingDate"], recent["accessionNumber"], recent["primaryDocument"]):
        if form in have and day > have[form]: out.append({"form": form, "filed": day, "accession": acc, "document": doc})
    return out


def main():
    rd = lambda n: list(csv.DictReader(open(REF / n, encoding="utf-8"), delimiter="|"))
    found, ua = [], sec_user_agent()
    if not ua: print("No contact address in pipeline/identity.py (CONTACT); the SEC refuses requests without one. Skipped; the page keeps the filings already read."); return
    for company, cik in CIK.items():
        have = {form: max((r["filed"] for r in rd(f) if r["company"] == company and r["filing"] == form), default="") for form, f in FORMS.items()}
        req = urllib.request.Request(f"https://data.sec.gov/submissions/CIK{cik}.json", headers={"User-Agent": ua, "Accept-Encoding": "identity"})      # the SEC refuses requests without a contact address
        try:
            with urllib.request.urlopen(req, timeout=60) as r: j = json.loads(r.read().decode("utf-8"))
        except Exception as e:                                       # the SEC often refuses data-centre addresses: try once in a real browser
            print(f"plain request refused ({str(e)[:60]}); retrying in a browser", flush=True)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch(headless=False); page = b.new_page(); page.goto(req.full_url, wait_until="domcontentloaded", timeout=45000)
                text = page.inner_text("body"); b.close()
            j = json.loads(text)
        for x in newer(j["filings"]["recent"], have):
            x["company"] = company; x["url"] = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{x['accession'].replace('-', '')}/{x['document']}"; found.append(x)
        time.sleep(1)
    (REF / "sec_meta.json").write_text(json.dumps({"checked": str(dt.date.today()), "newer": found}, indent=1), encoding="utf-8")
    print(f"{len(found)} filings newer than the ones on file" + "".join(f"\n  {x['company']} {x['form']} {x['filed']} {x['url']}" for x in found))


if __name__ == "__main__": main()
