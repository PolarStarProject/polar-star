"""Governors, local jail heads, signed 287(g) agreements and former officials lobbying: each shown only after its own check."""
import datetime as dt, re
from pathlib import Path
import officials_check as oc, moa_links as ml, money_lobbying as lob

TODAY = dt.date(2026, 10, 10)


def test_name_on_page():
    page = "<h1>Meet Sheriff Kevin&nbsp;J. Rambosk</h1>"
    assert oc.page_names(page, "Kevin Rambosk") and oc.page_names(page, "Kevin J. Rambosk")
    assert not oc.page_names(page, "Kevin Smith")
    assert not oc.page_names("<p>Ramboskian</p><p>Kevin</p>", "Kevin Rambosk")              # whole words only
    assert oc.page_names("Joseph D. McDonald Jr., Sheriff", "Joseph D. McDonald Jr.")
    assert not oc.page_names(None, "Kevin Rambosk")


def test_local_rows_need_a_page_that_names_them():
    rows = [{"facility_name": "A JAIL", "state": "FL", "official": "Ann Lee", "source_url": "u1"},
            {"facility_name": "B JAIL", "state": "FL", "official": "Bo Day", "source_url": ""},
            {"facility_name": "C JAIL", "state": "FL", "official": "Cy Ray", "source_url": "u3"},
            {"facility_name": "D JAIL", "state": "FL", "official": "Di Fox", "source_url": "u4"}]
    pages = {"u1": "Sheriff Ann Lee", "u3": "Sheriff Someone Else"}
    prev = {("D JAIL", "FL"): {"last_ok": "2026-10-01"}}
    out, err = oc.check_rows(rows, prev, TODAY, pages.get, lambda r: (r["facility_name"], r["state"]), lambda r: r["official"], lambda r: r["source_url"])
    assert [r["ok"] for r in out] == ["1", "0", "0", "1"] and err == 1                        # D: unreachable, but passed 9 days ago
    assert "no official page" in out[1]["reason"] and "does not name" in out[2]["reason"]


def test_governors_one_per_state():
    b = lambda iso, p, name, party=None, site="https://gov.example": {k: {"value": v} for k, v in {"iso": iso, "person": p, "personLabel": name, "start": "2023-01-02T00:00:00Z", "partyLabel": party, "site": site}.items() if v}
    j = {"results": {"bindings": [b("US-AA", "q1", "Pat One", "Republican Party"), b("US-AA", "q1", "Pat One", "Republican Party"),
                                  b("US-BB", "q2", "Sam Two", "Democratic Party"), b("US-BB", "q3", "Lee Three", "Democratic Party"),
                                  dict(b("US-DD", "q5", "Old Five"), start={"value": "2015-01-01T00:00:00Z"}), dict(b("US-DD", "q6", "New Six"), start={"value": "2023-01-09T00:00:00Z"}),
                                  b("US-CC", "q4", "Kim Four")]}}
    g = oc.governors(lambda q: j)
    assert [(r["state"], r["name"], r["party"], r["start"]) for r in g] == [("AA", "Pat One", "R", "2023-01-02"), ("CC", "Kim Four", "", "2023-01-02"), ("DD", "New Six", "", "2023-01-09")]   # BB: two holders with the same start, skipped; DD: the later start


def test_agreement_links_match_agency_and_model():
    ag = [{"state": "TEXAS", "agency": "Goliad County Sheriff’s Office", "model": "Jail Enforcement Model"},
          {"state": "TEXAS", "agency": "Goliad County Sheriff's Office", "model": "Task Force Model"},
          {"state": "TEXAS", "agency": "Goliad County Sheriff's Office", "model": "Warrant Service Officer"},
          {"state": "MONTANA", "agency": "Flathead County Sheriff's Office", "model": "Warrant Service Officer"}]
    paths = ["agreements/agreements_20250519_024922/TEXAS/Goliad_County_Sheriff's_Office/GoliadCo_TFM_MOA_02.18.25.pdf",
             "agreements/agreements_20260101_000000/TEXAS/Goliad_County_Sheriff's_Office/GoliadCo_TFM_MOA_2026.pdf",
             "agreements/agreements_20250519_024922/TEXAS/Goliad_County_Sheriff’s_Office/287gJEM_GoliadCoTX_06-09-2020.pdf",
             "agreements/agreements_20250519_024922/MONTANA/Flathead_County_Sheriff's_Department/287gWSO_FlatheadCoMt2020-02-12.pdf"]
    got = ml.newest(paths, ag)
    assert got[("TEXAS", "Goliad County Sheriff's Office", "Task Force Model")].endswith("2026.pdf")       # the newest download
    assert ("TEXAS", "Goliad County Sheriff’s Office", "Jail Enforcement Model") in got
    assert ("TEXAS", "Goliad County Sheriff's Office", "Warrant Service Officer") not in got              # no WSO file: nothing linked in its place
    assert ("MONTANA", "Flathead County Sheriff's Office", "Warrant Service Officer") in got             # "Department" and "Office" are the same agency


def test_former_officials_from_filings():
    f = lambda y, cp, client="THE GEO GROUP, INC.", firm="Acme Strategies LLC": {"client": {"name": client}, "registrant": {"name": firm}, "filing_year": y,
        "lobbying_activities": [{"lobbyists": [{"lobbyist": {"first_name": "JANE", "last_name": "ROE"}, "covered_position": cp}, {"lobbyist": {"first_name": "JOHN", "last_name": "DOE"}, "covered_position": "N/A"}]}]}
    out = lob.former_officials([f(2024, "Chief of Staff, ICE"), f(2025, "Chief of Staff, ICE"), f(2025, "x", client="OTHER CO")], r"\bGEO GROUP\b")
    assert out == {("Jane Roe", "Chief of Staff, ICE", "Acme Strategies LLC"): [2024, 2025]}             # no "N/A" rows; other clients ignored
    out = lob.former_officials([f(2025, "Staff, House", firm="Jane Roe")], r"\bGEO GROUP\b")
    assert list(out)[0][2] == "Jane Roe"                                                                 # a lobbyist registered under their own name, as filed


def test_page_has_the_new_sections():
    s = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text(encoding="utf-8")
    for k in ("go_h", "lo_h", "rv_h", "ag_moa", "rb_line", "go_note", "rv_note"): assert len(re.findall(r"[\s,{]" + k + r":", s)) == 2, k
    assert "polExtra(box);" in s


def test_country_pac_rule_is_the_same_for_every_country():
    import country_pacs as cp
    W = cp.COUNTRIES
    assert cp.matches("AMERICAN ISRAEL PUBLIC AFFAIRS COMMITTEE PAC", W["Israel"]) == ["ISRAEL"]
    assert cp.matches("ARMENIAN NATIONAL COMMITTEE OF AMERICA PAC", W["Armenia"]) == ["ARMENIAN"]
    assert cp.matches("US-CUBA DEMOCRACY PAC", W["Cuba"]) == ["CUBA"]
    assert cp.matches("INDIAN AMERICAN IMPACT FUND", W["India"]) == []          # a US community, not a country's policy
    assert cp.matches("KOREAN AMERICANS FOR PROGRESS", W["Korea"]) == []
    assert cp.matches("INDIANA BANKERS PAC", W["India"]) == []                   # whole words only
    assert cp.matches("UA VOTE PAC (UNITED ASSOCIATION OF JOURNEYMEN OF THE UNITED STATES AND CANADA)", W["Canada"]) == []   # a binational union
    assert cp.matches("UNITED ASSOCIATION OF JOURNEYMEN & APPRENTICES OF THE U.S. & CANADA LOCAL 447", W["Canada"]) == []
    assert cp.matches("UNITED STATES-INDIA RELATIONSHIP COUNCIL", W["India"]) == ["INDIA"]
    for words in W.values():                                                     # no US state or common name is a search term
        assert not {"GEORGIA", "JORDAN", "CHAD", "NIGER", "TURKEY", "MEXICO"} & set(words)


def test_fara_rows_unwrap_both_shapes():
    import fara
    assert fara.rows({"REGISTRANTS_ACTIVE": {"ROW": [{"a": 1}, {"a": 2}]}}) == [{"a": 1}, {"a": 2}]
    assert fara.rows({"ROWSET": {"ROW": {"a": 1}}}) == [{"a": 1}]
    assert fara.rows({}) == [] and fara.rows(None) == []


def test_page_has_the_pac_and_fara_sections():
    s = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text(encoding="utf-8")
    for k in ("cy_h", "cy_note", "cy_pc_h", "fg_h", "fg_note", "fg_both"): assert len(re.findall(r"[\s,{]" + k + r":", s)) == 2, k


def test_earmarked_payments_are_told_apart():
    import country_pacs as cp
    assert cp.earmarked({"disbursement_description": "EARMARK OF A DONOR", "memo_text": "TRANSMITTED BY CHECK/EFT"})
    assert cp.earmarked({"disbursement_type": "24T"})
    assert not cp.earmarked({"disbursement_description": "CONTRIBUTION TO COMMITTEE", "disbursement_type": "24K"})


def test_an_affiliate_needs_the_fecs_own_record():
    import country_pacs as cp
    assert cp.fec_affiliated({"affiliated_committee_name": "AMERICAN ISRAEL PUBLIC AFFAIRS COMMITTEE POLITICAL ACTION COMMITTEE"}, "American Israel Public Affairs Committee")
    assert not cp.fec_affiliated({"affiliated_committee_name": None}, "American Israel Public Affairs Committee")
    assert not cp.fec_affiliated({}, "Armenian National Committee of America")
