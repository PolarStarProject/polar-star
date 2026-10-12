"""Help lines and help links on For families, each confirmed every week on the official page that publishes it.

Usage:  python pipeline/hotlines_check.py        (needs internet; runs in GitHub Actions)

data/reference/hotlines.csv lists each phone number (or link) with one or more official pages that should publish it.
A number is shown only while one of those pages has its digits; a link is shown only while its page loads and has the
expected word. A page that cannot be reached keeps a row that passed within the last 21 days. Nothing is approved by
hand. Writes data/reference/hotlines_checked.csv: key | ok | source | checked | last_ok | reason.
"""
import csv, datetime as dt, html, json, re, sys
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
GRACE_DAYS = 21
FIELDS = ["key", "ok", "source", "checked", "last_ok", "reason"]


def page_text(page):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page or ""))).lower()


def has_number(page, digits):
    """True when the page shows these digits as one phone number (any spacing, dots, dashes, brackets or a leading 1)."""
    if not page: return False
    raw = html.unescape(page)
    if len(digits) < 7: return re.search(r"(?<!\d)" + re.escape(digits) + r"(?!\d)", raw) is not None    # a speed dial such as 9233
    for m in re.finditer(r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-‑–]?\d{3}[\s.\-‑–]?\d{4}(?!\d)", raw):
        d = re.sub(r"\D", "", m.group(0))
        if d[-10:] == digits[-10:]: return True
    return any(re.sub(r"\D", "", t)[-10:] == digits[-10:] for t in re.findall(r"tel:([+\d\-().\s]+)", raw))


def check(rows, prev, today, get_text):
    out, unreachable = [], 0
    for r in rows:
        p = prev.get(r["key"], {})
        res = {"key": r["key"], "ok": "0", "source": "", "checked": str(today), "last_ok": p.get("last_ok", ""), "reason": ""}
        reached = False
        for u in r["sources"].split():
            page = get_text(u)
            if page is None: print(f"  {r['key']}: could not load {u}", file=sys.stderr); continue
            reached = True
            if r["number"] and not has_number(page, r["match"]): print(f"  {r['key']}: loaded {u} ({len(page):,} characters), number not on it", file=sys.stderr)
            hit = has_number(page, r["match"]) if r["number"] else r["match"].lower() in page_text(page)
            if hit: res.update(ok="1", source=u, last_ok=str(today)); break
        if res["ok"] == "0":
            if not reached:
                unreachable += 1; res["reason"] = "no source page could be reached"
                if p.get("last_ok") and (today - dt.date.fromisoformat(p["last_ok"])).days <= GRACE_DAYS: res.update(ok="1", source=p.get("source", ""))
            else: res["reason"] = "not found on any source page"
        out.append(res)
    return out, unreachable


def main():
    from social_check import fetcher
    rows = list(csv.DictReader(open(REF / "hotlines.csv", encoding="utf-8"), delimiter="|"))
    pp = REF / "hotlines_checked.csv"
    prev = {r["key"]: r for r in csv.DictReader(open(pp, encoding="utf-8"), delimiter="|")} if pp.exists() else {}
    out, bad = check(rows, prev, dt.date.today(), fetcher()[0])
    if bad > len(rows) / 2: raise SystemExit(f"{bad} of {len(rows)} help lines could not be checked: left the list as it was.")
    with open(pp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(out)
    for r in out: print(f"{r['key']}: {'shown' if r['ok'] == '1' else 'hidden'} {r['source'] or r['reason']}", file=sys.stderr)


if __name__ == "__main__": main()
