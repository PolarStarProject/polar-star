"""family_orgs.csv: rows that break the rules stop the build; the weekly check decides what is shown."""
import datetime as dt
from build_site import family_orgs, ORG_COLS
from family_orgs_check import check, phone_on

GOOD = {"org": "Helpers", "types": "legal;kids", "scope": "state", "states": "TX", "website": "https://helpers.org/", "phone": "(512) 555-0100",
        "phone_source": "https://helpers.org/contact", "languages": "en;es", "id_type": "EIN", "ein": "12-3456789",
        "ein_source": "https://projects.propublica.org/nonprofits/organizations/123456789", "desc_en": "Free lawyers.", "desc_es": "Abogados gratuitos.", "notes": ""}

def write(tmp, rows, checked=None):
    (tmp / "family_orgs.csv").write_text("|".join(ORG_COLS) + "\n" + "".join("|".join(r[c] for c in ORG_COLS) + "\n" for r in rows), encoding="utf-8")
    if checked is not None:
        (tmp / "family_orgs_checked.csv").write_text("org|ok|reason|checked|last_ok\n" + "".join("|".join(c) + "\n" for c in checked), encoding="utf-8")

def rejects(tmp, **change):
    write(tmp, [{**GOOD, **change}], [])
    try: family_orgs(tmp, {}, "2026-10-28")
    except ValueError: return True
    return False

def test_rules(tmp):
    assert not rejects(tmp)
    for ch in ({"types": "legal;lawyers"}, {"types": ""}, {"scope": "state", "states": ""}, {"states": "TX;ZZ"}, {"website": "http://helpers.org/"},
               {"phone_source": ""}, {"id_type": "EIN", "ein": "123"}, {"id_type": "NGO"}, {"desc_es": ""}):
        assert rejects(tmp, **ch), ch

def test_only_checked_organizations_show(tmp):
    write(tmp, [GOOD, {**GOOD, "org": "Unchecked"}, {**GOOD, "org": "No id", "id_type": "", "ein": "", "ein_source": ""}],
          [["Helpers", "1", "", "2026-10-28", "2026-10-28"], ["No id", "1", "", "2026-10-28", "2026-10-28"]])
    o = family_orgs(tmp, {"orgs": [["X", "advocacy", "", "en", "https://www.helpers.org", [["bluesky", "https://bsky.app/profile/helpers.org"]]]]}, "2026-10-28")
    assert [x[0] for x in o["orgs"]] == ["Helpers"] and o["hidden"] == ["Unchecked", "No id"]
    assert o["orgs"][0][1] == ["legal", "kids"] and o["orgs"][0][3] == ["TX"] and o["orgs"][0][9] == [["bluesky", "https://bsky.app/profile/helpers.org"]]

def test_fetch_failure_keeps_a_recent_pass_only(tmp):
    write(tmp, [GOOD], [["Helpers", "0", "fetch failed: timeout", "2026-10-28", "2026-10-20"]])
    assert len(family_orgs(tmp, {}, "2026-10-28")["orgs"]) == 1
    assert len(family_orgs(tmp, {}, "2026-11-20")["orgs"]) == 0
    write(tmp, [GOOD], [["Helpers", "0", "website now goes to casino.example", "2026-10-28", "2026-10-20"]])
    assert len(family_orgs(tmp, {}, "2026-10-28")["orgs"]) == 0

def test_phone_digits_match_any_punctuation():
    assert phone_on("Call us: 512.555.0100 today", "(512) 555-0100") and phone_on("+1 512 555 0100", "512-555-0100") and not phone_on("512 555 0199", "512-555-0100")
    assert phone_on("Tucson 520-777-5600, Phoenix 602.307.1008", "Tucson (520) 777-5600; Phoenix (602) 307-1008") and not phone_on("Tucson 520-777-5600", "Tucson (520) 777-5600; Phoenix (602) 307-1008")
    assert phone_on("Dial 9233# free", "9233# (free from a detention facility phone)")

def test_weekly_check():
    today = dt.date(2026, 10, 28)
    ok_json = lambda u: {"organization": {"ein": 1}}
    pages = {"https://helpers.org/": ("<html>Helpers home</html>", "https://www.helpers.org/"), "https://helpers.org/contact": ("Phone (512) 555-0100", "https://helpers.org/contact")}
    out, err = check([GOOD], {}, today, pages.get, ok_json)
    assert out[0]["ok"] == "1" and err == 0
    moved = {**pages, "https://helpers.org/": ("<html>Best casino slots</html>", "https://casino.example/")}
    assert check([GOOD], {}, today, moved.get, ok_json)[0][0]["reason"].startswith("website now goes to")
    old_phone = {**pages, "https://helpers.org/contact": ("Phone (512) 555-0199", "https://helpers.org/contact")}
    assert check([GOOD], {}, today, old_phone.get, ok_json)[0][0]["reason"] == "the phone is no longer on the page named"
    assert check([GOOD], {}, today, pages.get, lambda u: None)[0][0]["reason"] == "no IRS record for that EIN"
    out, err = check([GOOD], {"Helpers": {"last_ok": "2026-10-20"}}, today, lambda u: None, ok_json)
    assert err == 1 and out[0]["ok"] == "1" and out[0]["reason"].startswith("fetch failed")
    gov = {**GOOD, "id_type": "GOV", "ein": "", "ein_source": ""}
    assert check([gov], {}, today, pages.get, ok_json)[0][0]["reason"] == "not a .gov site"
