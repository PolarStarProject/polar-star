"""Checks every candidate organization account in data/reference/social_orgs.csv against the publishing rules, so that
nobody approves entries by hand. An account is shown on the page only while all the checks below pass.

Usage:  python pipeline/social_check.py        (needs internet; runs in GitHub Actions)

The checks, for each account:
  identity   EIN: the IRS record exists (ProPublica Nonprofit Explorer, which republishes IRS filings).
             GOV: the website is a .gov domain. NEWS: a news outlet's own website is listed.
  two-way    the organization's own page (evidence_url, or its homepage) links this exact account.
  active     Bluesky: the newest post is no more than 90 days old (Bluesky's public API).
             Instagram: Instagram does not let a script read a profile without signing in, so activity is not
             machine-checked; the page says so.
The other rules (no paid services, no fundraising for single cases, no personal details of officers or detained
people, immigration as a core focus) are applied when a candidate is added to social_orgs.csv.

A site that cannot be reached is not the same as a link that is gone: an account that passed within the last 21 days
keeps its place through a fetch error, so one bad night does not empty the list. If most fetches fail, nothing is
written.

Writes data/reference/social_checked.csv and social_meta.json.
"""
import csv, datetime as dt, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
ACTIVE_DAYS, GRACE_DAYS = 90, 21
FIELDS = ["org", "platform", "account_url", "ok", "reason", "last_post", "checked", "last_ok"]


def handle(row):
    """The account's handle or Bluesky DID, lower case, from its profile URL."""
    u = row["account_url"].rstrip("/")
    return u.split("/profile/")[1].lower() if row["platform"] == "bluesky" else u.rsplit("/", 1)[1].lower()


def links_account(html, row):
    """True when the page links this exact account (not a longer handle that starts the same way)."""
    h, s = re.escape(handle(row)), html.lower()
    pat = (r"bsky\.app/profile/" + h if row["platform"] == "bluesky" else r"instagram\.com/" + h) + r"(?![a-z0-9_.\-])"
    return re.search(pat, s) is not None


def identity_ok(row, get_json):
    if row["id_type"] == "EIN":
        j = get_json(f"https://projects.propublica.org/nonprofits/api/v2/organizations/{row['id'].replace('-', '')}.json")
        return bool((j or {}).get("organization")), "no IRS record for that EIN"
    if row["id_type"] == "GOV": return row["website"].lower().endswith(".gov"), "not a .gov site"
    if row["id_type"] in ("NEWS", "UNIV", "FAITH"): return bool(row["website"]), "no website"
    return False, "unknown identity type"


def last_post(row, get_json):
    j = get_json("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?" + urllib.parse.urlencode({"actor": handle(row), "limit": 5, "filter": "posts_no_replies"}))
    days = [f["post"]["record"]["createdAt"][:10] for f in (j or {}).get("feed", []) if not f.get("reason")]   # own posts, not reposts
    return max(days) if days else ""


def check(rows, prev, today, get_text, get_json):
    out, errors = [], 0
    for r in rows:
        p = prev.get((r["platform"], r["account_url"]), {})
        res = {"org": r["org"], "platform": r["platform"], "account_url": r["account_url"], "ok": "0", "reason": "", "last_post": "", "checked": str(today), "last_ok": p.get("last_ok", "")}
        try:
            ok, why = identity_ok(r, get_json)
            if not ok: res["reason"] = why; out.append(res); continue
            pages = [r["evidence_url"]] + ([f"https://{r['website']}/"] if r["website"] else [])
            seen = fetched = False
            for u in pages:
                html = get_text(u)
                if html is None: continue
                fetched = True
                if links_account(html, r): seen = True; break
            if not fetched: raise IOError("site unreachable")
            if not seen: res["reason"] = "the organization's site no longer links this account"; out.append(res); continue
            if r["platform"] == "bluesky":
                lp = last_post(r, get_json); res["last_post"] = lp
                if not lp or (today - dt.date.fromisoformat(lp)).days > ACTIVE_DAYS: res["reason"] = f"no post in {ACTIVE_DAYS} days"; out.append(res); continue
            res["ok"], res["last_ok"] = "1", str(today)
        except Exception as e:
            errors += 1
            res["reason"] = f"could not check: {str(e)[:80]}"
            if p.get("last_ok") and (today - dt.date.fromisoformat(p["last_ok"])).days <= GRACE_DAYS: res["ok"] = "1"   # reached recently: keep it through one failure
        out.append(res)
    return out, errors


def fetcher():
    def get(url, accept):
        for i in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.8"})
                with urllib.request.urlopen(req, timeout=40) as resp: time.sleep(0.5); return resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code in (404, 410): return None
                if i == 2: return None
            except Exception:
                if i == 2: return None
            time.sleep(3)
    get_text = lambda u: get(u, "text/html,*/*")
    def get_json(u):
        t = get(u, "application/json")
        try: return json.loads(t) if t else None
        except ValueError: return None
    return get_text, get_json


def main():
    rows = list(csv.DictReader(open(REF / "social_orgs.csv", encoding="utf-8"), delimiter="|"))
    pp = REF / "social_checked.csv"
    prev = {(r["platform"], r["account_url"]): r for r in csv.DictReader(open(pp, encoding="utf-8"), delimiter="|")} if pp.exists() else {}
    today = dt.date.today()
    out, errors = check(rows, prev, today, *fetcher())
    if errors > len(rows) / 2: raise SystemExit(f"{errors} of {len(rows)} accounts could not be checked: left the list as it was.")
    with open(pp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(out)
    n = sum(r["ok"] == "1" for r in out)
    (REF / "social_meta.json").write_text(json.dumps({"checked": str(today), "candidates": len(rows), "shown": n}, indent=1), encoding="utf-8")
    for r in out:
        if r["ok"] != "1": print(f"hidden: {r['org']} ({r['platform']}): {r['reason']}", file=sys.stderr)
    print(f"{n} of {len(rows)} accounts pass", file=sys.stderr)
    write_profiles(rows, today, *fetcher())


PROFILE_FIELDS = ["org", "city", "state", "desc", "desc_url", "checked"]


def site_description(html):
    """The organization's own one-line description of itself: its page's meta description (or og:description), first
    sentence, at most about 220 characters. Nothing is written by this page."""
    if not html: return ""
    for pat in (r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*name=["\']description',
                r'<meta[^>]+property=["\']og:description["\'][^>]*content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:description'):
        m = re.search(pat, html, re.I)
        if m:
            import html as H
            t = re.sub(r"\s+", " ", H.unescape(m.group(1))).strip()
            if len(t) > 220:
                cut = re.search(r"^(.{40,220}?[.!?])\s", t)
                t = cut.group(1) if cut else t[:217].rsplit(" ", 1)[0] + "…"
            return t
    return ""


def write_profiles(rows, today, get_text, get_json):
    """Where each organization is based (from its IRS record; .gov sites are federal agencies in Washington, DC) and how
    it describes itself (its own website). A failed fetch keeps last week's values. Writes social_profiles.csv."""
    pp = REF / "social_profiles.csv"
    prev = {r["org"]: r for r in csv.DictReader(open(pp, encoding="utf-8"), delimiter="|")} if pp.exists() else {}
    out, seen = [], set()
    for r in rows:
        if r["org"] in seen: continue
        seen.add(r["org"]); p = prev.get(r["org"], {})
        city, state = p.get("city", ""), p.get("state", "")
        if r["id_type"] == "EIN":
            o = ((get_json(f"https://projects.propublica.org/nonprofits/api/v2/organizations/{r['id'].replace('-', '')}.json") or {}).get("organization")) or {}
            if o.get("city"): city, state = o["city"].title(), o.get("state", "")
        elif r["id_type"] == "GOV": city, state = "Washington", "DC"
        url = f"https://{r['website']}/" if r["website"] else ""
        d = site_description(get_text(url)) if url else ""
        out.append({"org": r["org"], "city": city, "state": state, "desc": (d or p.get("desc", "")).replace("|", "/"), "desc_url": url if d else p.get("desc_url", ""), "checked": str(today)})
    with open(pp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PROFILE_FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(out)
    print(f"profiles: {sum(1 for x in out if x['desc'])} with a description, {sum(1 for x in out if x['state'])} with a location", file=sys.stderr)


if __name__ == "__main__": main()
