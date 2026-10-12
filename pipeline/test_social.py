"""Organizations to follow: an account is shown only while it passes every automatic check, with no hand approval."""
import csv, datetime as dt, json, re
from pathlib import Path
import social_check as sc
import build_site as bs

TODAY = dt.date(2026, 10, 10)
ROW = {"org": "Org A", "id_type": "EIN", "id": "12-3456789", "website": "orga.org", "platform": "instagram", "account_url": "https://www.instagram.com/orga/",
       "scope": "national", "state": "", "kind": "advocacy", "language": "en", "evidence_url": "https://orga.org/about"}
BSKY = dict(ROW, platform="bluesky", account_url="https://bsky.app/profile/orga.bsky.social")
IRS = {"organization": {"name": "ORG A"}}


def run(rows, pages, js, prev=None):
    return sc.check(rows, prev or {}, TODAY, lambda u: pages.get(u), lambda u: js(u))


def test_exact_handle_only():
    assert sc.links_account('<a href="https://instagram.com/orga">', ROW)
    assert sc.links_account('<a href="https://www.instagram.com/OrgA/?hl=en">', ROW)
    assert not sc.links_account('<a href="https://instagram.com/orga_fan">', ROW)        # a longer handle is someone else
    assert not sc.links_account('follow us @orga on Instagram', ROW)                       # a name in text is not a link
    assert sc.links_account('<a href="https://bsky.app/profile/orga.bsky.social">', BSKY)
    d = dict(BSKY, account_url="https://bsky.app/profile/did:plc:abc123")
    assert sc.links_account('href="https://bsky.app/profile/did:plc:abc123"', d)


def test_passes_and_fails_for_the_right_reasons():
    page = {"https://orga.org/about": '<a href="https://www.instagram.com/orga/">IG</a>'}
    out, err = run([ROW], page, lambda u: IRS)
    assert out[0]["ok"] == "1" and out[0]["last_ok"] == "2026-10-10" and err == 0
    out, _ = run([ROW], page, lambda u: None)                                                 # no IRS record
    assert out[0]["ok"] == "0" and "IRS" in out[0]["reason"]
    out, _ = run([ROW], {"https://orga.org/about": "<p>nothing</p>", "https://orga.org/": "<p>none</p>"}, lambda u: IRS)
    assert out[0]["ok"] == "0" and "no longer links" in out[0]["reason"]
    out, _ = run([ROW], {"https://orga.org/": '<a href="https://instagram.com/orga">'}, lambda u: IRS)   # found on the homepage instead
    assert out[0]["ok"] == "1"
    gov = dict(ROW, id_type="GOV", id="example.com", website="example.com")
    out, _ = run([gov], {"https://orga.org/about": '<a href="https://instagram.com/orga">'}, lambda u: IRS)
    assert out[0]["ok"] == "0" and ".gov" in out[0]["reason"]


def test_bluesky_needs_a_recent_post():
    page = {"https://orga.org/about": '<a href="https://bsky.app/profile/orga.bsky.social">'}
    feed = lambda day: (lambda u: IRS if "propublica" in u else {"feed": [{"post": {"record": {"createdAt": day + "T12:00:00Z"}}}]})
    assert run([BSKY], page, feed("2026-09-01"))[0][0]["ok"] == "1"
    o = run([BSKY], page, feed("2026-06-01"))[0][0]
    assert o["ok"] == "0" and "90 days" in o["reason"] and o["last_post"] == "2026-06-01"
    repost_only = lambda u: IRS if "propublica" in u else {"feed": [{"reason": {"$type": "repost"}, "post": {"record": {"createdAt": "2026-10-01T00:00:00Z"}}}]}
    assert run([BSKY], page, repost_only)[0][0]["ok"] == "0"                                   # reposts are not the account's own posts


def test_unreachable_site_keeps_a_recent_pass_only():
    k = (ROW["platform"], ROW["account_url"])
    out, err = run([ROW], {}, lambda u: IRS, {k: {"last_ok": "2026-10-01"}})
    assert out[0]["ok"] == "1" and err == 1 and "could not check" in out[0]["reason"]
    out, _ = run([ROW], {}, lambda u: IRS, {k: {"last_ok": "2026-09-01"}})
    assert out[0]["ok"] == "0"
    out, _ = run([ROW], {}, lambda u: IRS)
    assert out[0]["ok"] == "0"


def test_page_list_groups_by_organization(tmp):
    rows = [ROW, BSKY, dict(ROW, org="Org B", account_url="https://www.instagram.com/orgb/", scope="state", state="TX", website="orgb.org"),
            dict(ROW, org="Org C", account_url="https://www.instagram.com/orgc/")]
    with open(tmp / "social_orgs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ROW), delimiter="|"); w.writeheader(); w.writerows(rows)
    chk = [{"org": r["org"], "platform": r["platform"], "account_url": r["account_url"], "ok": "0" if r["org"] == "Org C" else "1", "reason": "", "last_post": "", "checked": "2026-10-10", "last_ok": ""} for r in rows]
    with open(tmp / "social_checked.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sc.FIELDS, delimiter="|"); w.writeheader(); w.writerows(chk)
    (tmp / "social_meta.json").write_text(json.dumps({"checked": "2026-10-10"}))
    S = bs.social_list(tmp)
    names = [o[0] for o in S["orgs"]]
    assert names == ["Org A", "Org B"] and S["checked"] == "2026-10-10"                     # Org C failed, so it is not shown; national first
    a = S["orgs"][0]
    assert [p for p, _ in a[5]] == ["bluesky", "instagram"] and a[2] == "" and a[4] == "https://orga.org"
    assert S["orgs"][1][2] == "TX"


def test_page_has_the_sections_in_both_languages():
    s = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text(encoding="utf-8")
    for i in ('id="v-orgs"', 'id="sv-orgs"', 'id="v-news"', "ground.news/interest/immigration-and-customs-enforcement"): assert i in s
    for k in ("so_h", "so_how", "so_warn", "nw_h", "nw_note", "so_kind"): assert len(re.findall(r"[\s,{]" + k + r":", s)) == 2, k
