import pandas as pd
import staff_opm as s


def test_staff_counted_by_agency_with_pay_and_series():
    df = pd.DataFrame({"agency_subelement": ["U.S. IMMIGRATION AND CUSTOMS ENFORCEMENT"] * 3 + ["U.S. CUSTOMS AND BORDER PROTECTION", "BUREAU OF LAND MANAGEMENT"],
                       "annualized_adjusted_basic_pay": ["100000", "50000.5", "", "80000", "70000"], "occupational_series_code": ["1801", "1801", "343", "1896", "401"], "count": [1, 1, 1, 1, 1]})
    by, series = s.summarize_employment(df, "2026-07")
    assert by == [["2026-07", "CBP", 1], ["2026-07", "ICE", 3]]
    assert ["2026-07", "ICE", "1801", 2] in series and ["2026-07", "ICE", "0343", 1] in series


def test_files_wanted_are_recent_months_and_old_septembers_newest_version():
    L = [{"current": True, "year": "2024", "month": "08", "version": 1, "filename": "a"}, {"current": True, "year": "2024", "month": "09", "version": 1, "filename": "b"},
         {"current": True, "year": "2024", "month": "09", "version": 2, "filename": "c"}, {"current": True, "year": "2021", "month": "09", "version": 1, "filename": "d"},
         {"current": True, "year": "2021", "month": "03", "version": 1, "filename": "e"}, {"current": False, "year": "2026", "month": "01", "version": 1, "filename": "f"}]
    assert {k: v["filename"] for k, v in s.months_wanted(L, "2026-10-08").items()} == {"2021-09": "d", "2024-09": "c"}


def test_agency_names_matched_by_pattern():
    assert s.agency_of("EXECUTIVE OFFICE FOR IMMIGRATION REVIEW") == "EOIR" and s.agency_of("U.S. MARSHALS SERVICE") == "USMS" and s.agency_of("NASA") is None


def test_fiscal_year_dates_follow_the_reporting_period():
    import money_object_class as m
    assert m.fy_dates(2026, 9) == ("2025-10-01", "2026-06-30") and m.fy_dates(2025, 12) == ("2024-10-01", "2025-09-30") and m.fy_dates(2026, 3) == ("2025-10-01", "2025-12-31")
