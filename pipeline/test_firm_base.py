"""Checks for the all-firms comparison and for matching the firms' political money to members of Congress."""
import datetime as dt
from firm_base import settled_quarter, tally
from build_site import firm_members, _first_last


def test_settled_quarter_waits_35_days():
    assert settled_quarter(dt.date(2026, 8, 3)) == (2026, "first_quarter")
    assert settled_quarter(dt.date(2026, 8, 4)) == (2026, "second_quarter")
    assert settled_quarter(dt.date(2026, 2, 4)) == (2025, "fourth_quarter")
    assert settled_quarter(dt.date(2026, 1, 15)) == (2025, "third_quarter")


def test_tally_latest_version_income_only():
    f = lambda rid, rn, cid, inc, posted, ft="Q2": {"registrant": {"id": rid, "name": rn}, "client": {"id": cid}, "income": inc, "dt_posted": posted, "filing_type": ft}
    t = tally([f(1, "Big Firm LLC", 10, "50000", "2026-07-01"), f(1, "Big Firm LLC", 10, "70000", "2026-07-15", "Q2A"),     # amendment replaces
               f(1, "Big Firm LLC", 11, "20000", "2026-07-01"), f(2, "In House Co", 12, None, "2026-07-01"),               # self-filer: expenses only
               f(3, "New Firm", 13, None, "2026-07-01", "RR")])
    assert t == {"BIG FIRM": ["Big Firm LLC", 90000, 2]}


def test_members_matched_by_first_and_last_name_only_when_unique():
    assert _first_last("Adam B. Schiff") == ("ADAM", "SCHIFF") == _first_last("ADAM SCHIFF JR.")
    M = [["A1", "Adam B. Schiff", "S", "D", "", "", "", ["Judiciary"], "", 0, 0, 1], ["B1", "Aaron Bean", "H", "R", "", "", "", [], "", 0, 0, 1],
         ["C1", "John Smith", "H", "R", "", "", "", [], "", 0, 0, 1], ["C2", "John Smith", "H", "D", "", "", "", [], "", 0, 0, 1]]
    pat = {"_money": [["F1", "Adam Schiff", "campaign", 1000], ["F2", "Adam Schiff", "campaign", 500], ["F1", "John Smith", "campaign", 300], ["F1", "Some PAC", "campaign", 50]]}
    firm_members(pat, M)
    m = pat["members"]
    assert m["on"] == [1, 1, 1500] and m["off"] == [3, 0, 0]
    assert m["top"] == [["A1", 1500, ["F1", "F2"]]] and m["un_n"] == 2 and m["un_usd"] == 350
