"""The four extra tables in ICE's detention statistics workbooks: twice-yearly groups, segregation reasons, bond, length of stay."""
import datetime as dt
import detention_stats as d


def test_semiannual_reads_each_group_and_leaves_blank_tps_years_out():
    rows = [("The data contained within this Semiannual page has been refreshed",), (None,),
            ("United States Citizen Arrests FY2018 - FY2026 YTD", None), ("Fiscal Year", "Arrests"), ("FY2018", 30), ("FY2022 ", 1), (None,),
            ("Parents of USC Removals FY2018 - FY2026 YTD", None), ("Fiscal Year", "Removals"), ("FY2025", 0), ("FY2026", 10885), (None,),
            ("Temporary Protected Status Countries Bookins FY2018 - FY2026 YTD", None, None, None),
            ("Citizenship Country", "FY2024", "FY2025", "FY2026"), ("Lebanon", None, 0, 37), ("Haiti", 2239, 0, 1406)]
    out = d.parse_semiannual(rows)
    got = {(r["group"], r["country"], r["measure"], r["fy"]): r["value"] for r in out}
    assert got[("us_citizens", "", "arrests", 2022)] == 1 and got[("parents_usc", "", "removals", 2026)] == 10885
    assert got[("tps", "Haiti", "book_ins", 2024)] == 2239 and got[("tps", "Lebanon", "book_ins", 2026)] == 37
    assert ("tps", "Lebanon", "book_ins", 2024) not in got, "a blank cell (not yet designated) must not become 0"
    assert got[("parents_usc", "", "removals", 2025)] == 0


def test_vulnerable_takes_reasons_totals_and_unique_people():
    rows = [("Fiscal Year (FY) 2026 Quarter 3 Data",), ("Placement Reason", "Number of Placements", "Avg consecutive", "Avg cumulative"),
            ("Disciplinary", 151, 27.5, 34.6), ("Medical Mental", 65, 9.2, 12.5), ("Grand Total", 216, 23.0, 28.0), (None,),
            ("*Data represents 186 unique detainees. Some detainees have multiple placements within FY26 Q3 (216 total placements).",)]
    out = d.parse_vulnerable(rows)
    assert [r["reason"] for r in out] == ["Disciplinary", "Medical/Mental Health", "Total"]
    assert out[-1]["people"] == 186 and out[0]["people"] == "" and out[0]["fy"] == 2026 and out[0]["quarter"] == 3


def test_bond_drops_months_shown_as_zero():
    m = [dt.datetime(2025, k, 1) for k in (8, 9, 10, 11, 12, 1)]; m[-1] = dt.datetime(2026, 1, 1)
    rows = [("FY2026 Bonded Out",), (None, *m), ("Total ICE Final Book Outs", 0, 0, 37533, 36440, 38728, 37400), ("ICE Final Book Outs with Bond Posted", 0, 0, 1106, 1295, 2130, 2326),
            ("Bond Posted Book Outs/Releases (%)", 0, 0, .029, .036, .055, .062), ("Average Bond Amount ($)", 0, 0, 7352.0, 7548.7, 7005.6, 7773.7), ("ALOS (Days)", 0, 0, 51.29, 52.87, 58.23, 67.3)]
    out = d.parse_bond(rows)
    assert [r["month"] for r in out] == ["2025-10", "2025-11", "2025-12", "2026-01"]
    assert out[0] == {"month": "2025-10", "book_outs": 37533, "bond_posted": 1106, "avg_bond": 7352, "alos": 51.3}


def test_length_of_stay_dates_roll_over_the_year_and_skip_unknown_populations():
    months = ["November", None, "December", None, "January", None]
    rows = [("Average In Custody Length of Stay (ICLOS)",), (None,), (None,), ("Population ", 2023, None, None, None, 2024, None), (None, *months), (None, "mid ", "end", "mid ", "end", "mid ", "end"),
            ("Adult Facility Aliens", 40, 41, 42, 43, 44, 45), ("Family Units with a Positive Fear Determination Still in Custody", 0, 0, 0, 0, 0, 0), ("Total", 50, 51, 52, 53, 54, 55),
            (None,), ("Detainees",), (None,), (None,), ("Population ", 2023, None, None, None, 2024, None), (None, *months), (None, "mid ", "end", "mid ", "end", "mid ", "end"),
            ("Adult Facility Aliens",), ("0-180 Days", 1, 2, 3, 4, 5, 6), ("Total", 1, 2, 3, 4, 5, 6),
            ("FSC Facility Individuals",), ("0-180 Days", 0, 0, 0, 0, 0, 0),
            ("Total",), ("0-180 Days", 10, 20, 30, 40, 50, 60), ("181-365 Days", 1, 1, 1, 1, 1, 9)]
    out = {(r["day"], r["population"]): r for r in d.parse_length_of_stay(rows)}
    assert out[("2023-11-15", "total")]["alos"] == 50 and out[("2024-01-31", "total")]["alos"] == 55
    assert out[("2023-12-31", "adult")]["d0_180"] == 4, "the FSC zeros must not overwrite the adult counts"
    assert out[("2024-01-31", "total")]["d181_365"] == 9


def test_a_later_zero_never_replaces_an_earlier_count():
    old = d.merge_newest([], [{"group": "g", "country": "", "measure": "arrests", "fy": 2025, "value": 6341}], ["group", "country", "measure", "fy"], "FY25")
    new = d.merge_newest(old, [{"group": "g", "country": "", "measure": "arrests", "fy": 2025, "value": 0}, {"group": "g", "country": "", "measure": "arrests", "fy": 2024, "value": 9739}], ["group", "country", "measure", "fy"], "FY26")
    by = {r["fy"]: r for r in new}
    assert by[2025]["value"] == 6341 and by[2025]["src"] == "FY25" and by[2025]["zeroed_in"] == "FY26"
    assert by[2024]["value"] == 9739 and by[2024]["src"] == "FY26"
    again = d.merge_newest(new, [{"group": "g", "country": "", "measure": "arrests", "fy": 2024, "value": 9800}], ["group", "country", "measure", "fy"], "FY26")
    assert {r["fy"]: r["value"] for r in again}[2024] == 9800, "a revised count in the newer file wins"
