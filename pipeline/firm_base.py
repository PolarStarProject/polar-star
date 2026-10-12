"""What every lobbying firm reported being paid in one quarter, from the Senate's Lobbying Disclosure Act records (lda.gov
API). It is the comparison for the firm patterns: what share of all outside lobbying fees goes to firms that are also
registered foreign agents, set beside the same share for the detention companies' fees.

Usage:  python pipeline/firm_base.py [--force]      (needs internet; runs in GitHub Actions)

Reads the latest quarter whose reports are due and settled (35 days after the quarter ends), the latest version of each
firm-and-client report, registrations left out. Only "income" is added: what an outside firm reports being paid. Groups
lobbying for themselves report "expenses" instead and are not counted.
Skips the read when firm_base.json already holds that quarter (unless --force).
An optional LDA_API_KEY (from lda.gov, free) raises the request limit; without one a quarter takes about 40 minutes.
Writes data/reference/firm_income_all.csv (firm|usd|clients) and firm_base.json. Nothing is written unless every page is read.
"""
import csv, datetime as dt, json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path
from identity import USER_AGENT
from firm_profiles import core

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://lda.gov/api/v1/filings/?"
PERIODS = ["first_quarter", "second_quarter", "third_quarter", "fourth_quarter"]


def settled_quarter(today):
    """The newest quarter that ended at least 35 days before today (reports are due 20 days after it ends) -> (year, period)."""
    y, q = today.year, (today.month - 1) // 3          # q = index of the quarter before the current one
    while True:
        if q == 0: y, q = y - 1, 4
        end = dt.date(y + (q == 4), 1 if q == 4 else 3 * q + 1, 1) - dt.timedelta(days=1)
        if (today - end).days >= 35: return y, PERIODS[q - 1]
        q -= 1


def tally(filings):
    """One quarter's filings -> {firm core name: [display name, usd, clients]}. The latest version per firm and client."""
    keep = {}
    for f in filings:
        if (f.get("filing_type") or "").startswith("R"): continue
        k = ((f.get("registrant") or {}).get("id"), (f.get("client") or {}).get("id"))
        if k not in keep or (f.get("dt_posted") or "") > (keep[k].get("dt_posted") or ""): keep[k] = f
    out = {}
    for f in keep.values():
        try: usd = int(float(f.get("income") or 0))
        except (TypeError, ValueError): usd = 0
        if usd <= 0: continue
        name = (f.get("registrant") or {}).get("name") or ""
        o = out.setdefault(core(name), [name, 0, 0]); o[1] += usd; o[2] += 1
    return out


def main():
    y, period = settled_quarter(dt.date.today())
    meta_p = REF / "firm_base.json"
    old = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    if "--force" not in sys.argv and old.get("year") == y and old.get("period") == period and (REF / "firm_income_all.csv").exists():
        print(f"firm_base: {y} {period} already read", file=sys.stderr); return
    key = os.environ.get("LDA_API_KEY", "").strip()
    head = {"Accept": "application/json", "User-Agent": USER_AGENT, **({"Authorization": f"Token {key}"} if key else {})}
    pause = 0.6 if key else 4.2
    url, filings, pages = API + urllib.parse.urlencode({"filing_year": y, "filing_period": period, "page_size": 25}), [], 0
    while url:
        for i in range(6):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=90) as r:
                    j = json.loads(r.read().decode("utf-8")); break
            except Exception as e:
                err = str(e)[:120]; time.sleep(30 if "429" in err else 8)
        else: raise SystemExit(f"lda.gov did not answer page {pages + 1}: {err}. Nothing written.")
        filings += j.get("results") or []; url = j.get("next"); pages += 1; time.sleep(pause)
        if pages % 100 == 0: print(f"  {pages} pages, {len(filings)} filings", file=sys.stderr)
    t = tally(filings)
    if len(t) < 300: raise SystemExit(f"Only {len(t)} firms reported income for {y} {period}. Nothing written.")
    with open(REF / "firm_income_all.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|", lineterminator="\n"); w.writerow(["firm", "usd", "clients"])
        for k, (name, usd, n) in sorted(t.items(), key=lambda kv: -kv[1][1]): w.writerow([name, usd, n])
    meta_p.write_text(json.dumps({"year": y, "period": period, "filings": len(filings), "firms": len(t), "read": str(dt.date.today())}, indent=1), encoding="utf-8")
    print(f"{len(t)} firms, {len(filings)} filings, {y} {period}", file=sys.stderr)


if __name__ == "__main__": main()
