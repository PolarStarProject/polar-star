"""Checks every organization in data/reference/family_orgs.csv each week, so the Organizations tab never sends a family to
a dead or taken-over website or an old phone number. An organization is shown only while all of these pass:

  identity  EIN or PROJECT: the IRS record exists (ProPublica Nonprofit Explorer, which republishes IRS filings).
            GOV: the website is a .gov or .mil site. UNIV, FAITH: the website loads (checked below).
            Blank: never shown until someone adds the record.
  website   the homepage loads, ends up on the same site (not a different domain), and does not look parked or for sale.
  phone     when a phone is listed, its digits are still on the page named in phone_source.

A site that cannot be reached is not the same as one that is gone: an organization that passed within the last 21 days
keeps its place through a fetch error. If most fetches fail, nothing is written.

Usage:  python pipeline/family_orgs_check.py     (needs internet; runs in GitHub Actions)
Writes data/reference/family_orgs_checked.csv.
"""
import csv, datetime as dt, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from social_check import fetcher

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
GRACE_DAYS = 21
FIELDS = ["org", "ok", "reason", "checked", "last_ok"]
PARKED = re.compile(r"domain (is|may be) for sale|buy this domain|this domain has expired|parked (free|domain)|casino|slot gacor|\bbetting\b", re.I)


def host(u):
    return urllib.parse.urlparse(u).netloc.lower().removeprefix("www.")


def digits(s):
    return re.sub(r"\D", "", s or "")


PHONE = re.compile(r"\(?\d{3}\)?[\s.\-]*\d{3}[\s.\-]*\d{4}")


def numbers(phone):
    """Every ten-digit number in the phone field ("Tucson (520) 777-5600; Phoenix (602) 307-1008"), or a short code
    such as the free 9233# line from detention phones."""
    n = [digits(m) for m in PHONE.findall(phone or "")]
    return n or ([digits(phone)] if len(digits(phone)) >= 4 else [])


def phone_on(page, phone):
    """True when every number in the phone field is on the page, whatever the punctuation."""
    p, n = digits(page), numbers(phone)
    return bool(n) and all(x in p for x in n)


def check_one(r, get_page, get_json):
    """-> (ok, reason). Raises IOError when the site could not be reached at all."""
    t = r["id_type"]
    if not t: return False, "no IRS record or other identity on file"
    if t in ("EIN", "PROJECT"):
        j = get_json(f"https://projects.propublica.org/nonprofits/api/v2/organizations/{r['ein'].replace('-', '')}.json")
        if not (j or {}).get("organization"): return False, "no IRS record for that EIN"
    if t == "GOV" and not re.search(r"\.(gov|mil)$", host(r["website"])): return False, "not a .gov site"
    page = get_page(r["website"])
    if page is None: raise IOError("website unreachable")
    html, final = page
    if host(final) != host(r["website"]) and not host(final).endswith("." + host(r["website"])): return False, f"website now goes to {host(final)}"
    if PARKED.search(html[:20000]) and len(html) < 60000: return False, "website looks parked or for sale"
    if r["phone"]:
        src = html if r["phone_source"].rstrip("/") == r["website"].rstrip("/") else (get_page(r["phone_source"]) or (None,))[0]
        if src is None: raise IOError("phone page unreachable")
        if not phone_on(src, r["phone"]): return False, "the phone is no longer on the page named"
    return True, ""


def check(rows, prev, today, get_page, get_json):
    out, errors = [], 0
    for r in rows:
        p = prev.get(r["org"], {})
        res = {"org": r["org"], "ok": "0", "reason": "", "checked": str(today), "last_ok": p.get("last_ok", "")}
        try:
            ok, why = check_one(r, get_page, get_json)
            res["reason"] = why
            if ok: res["ok"], res["last_ok"] = "1", str(today)
        except Exception as e:
            errors += 1
            res["reason"] = f"fetch failed: {str(e)[:80]}"
            if p.get("last_ok") and (today - dt.date.fromisoformat(p["last_ok"])).days <= GRACE_DAYS: res["ok"] = "1"
        out.append(res)
    return out, errors


def page_fetcher():
    UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    def get_page(url):
        for i in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.8"})
                with urllib.request.urlopen(req, timeout=40) as resp: time.sleep(0.5); return resp.read().decode("utf-8", "replace"), resp.geturl()
            except urllib.error.HTTPError as e:
                if e.code in (404, 410) or i == 2: return None
            except Exception:
                if i == 2: return None
            time.sleep(3)
    return get_page


def main():
    rows = list(csv.DictReader(open(REF / "family_orgs.csv", encoding="utf-8"), delimiter="|"))
    pp = REF / "family_orgs_checked.csv"
    prev = {r["org"]: r for r in csv.DictReader(open(pp, encoding="utf-8"), delimiter="|")} if pp.exists() else {}
    out, errors = check(rows, prev, dt.date.today(), page_fetcher(), fetcher()[1])
    if errors > len(rows) / 2: raise SystemExit(f"{errors} of {len(rows)} organizations could not be checked: left the list as it was.")
    with open(pp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(out)
    for r in out:
        if r["ok"] != "1": print(f"hidden: {r['org']}: {r['reason']}", file=sys.stderr)
    print(f"{sum(r['ok'] == '1' for r in out)} of {len(rows)} organizations pass", file=sys.stderr)


if __name__ == "__main__":
    main()
