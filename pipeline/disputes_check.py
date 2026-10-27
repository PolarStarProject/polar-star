"""Every source link on ICE and state and local governments, checked each week.

Usage:  python pipeline/disputes_check.py        (needs internet; runs in GitHub Actions)

Reads data/reference/ice_local_disputes.csv and writes data/reference/disputes_checked.csv: url | ok | checked | last_ok.
A link that fails is flagged on the page, never hidden: the entry stays and says the link did not load on that date.
If more than half the links fail at once, the file is left as it was (the runner's network, not the sources).
"""
import csv, datetime as dt, sys
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
FIELDS = ["url", "ok", "checked", "last_ok"]


def check(urls, prev, today, get_text):
    out = []
    for u in urls:
        ok = get_text(u) is not None
        out.append({"url": u, "ok": "1" if ok else "0", "checked": str(today), "last_ok": str(today) if ok else prev.get(u, {}).get("last_ok", "")})
    return out


def links(rows):
    return sorted({u for r in rows for u in (r["source_url"].strip(), r["status_url"].strip()) if u})


def main():
    from social_check import fetcher
    src = REF / "ice_local_disputes.csv"
    if not src.exists(): return
    urls = links(list(csv.DictReader(open(src, encoding="utf-8"), delimiter="|")))
    pp = REF / "disputes_checked.csv"
    prev = {r["url"]: r for r in csv.DictReader(open(pp, encoding="utf-8"), delimiter="|")} if pp.exists() else {}
    out = check(urls, prev, dt.date.today(), fetcher()[0])
    bad = sum(r["ok"] == "0" for r in out)
    if bad > len(out) / 2: raise SystemExit(f"{bad} of {len(out)} dispute links failed: left the check file as it was.")
    with open(pp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(out)
    for r in out:
        if r["ok"] == "0": print(f"  link did not load: {r['url']}", file=sys.stderr)


if __name__ == "__main__": main()
