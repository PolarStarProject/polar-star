import pandas as pd
import removals_country as rc


def test_removals_count_deported_stays_by_month_and_country_and_drop_the_partial_month():
    o = lambda x: pd.Timestamp(x, tz="UTC")
    s = pd.DataFrame([(o("2026-01-10"), "Deported", "MEXICO", "MEXICO")] * 3 + [(o("2026-01-12"), "Deported", None, "GUATEMALA")] +
                     [(o("2026-01-15"), "Released", "HONDURAS", "HONDURAS")] + [(o("2026-02-01"), "Deported", "MEXICO", "MEXICO")] +
                     [(o("2026-03-02"), "Deported", "MEXICO", "MEXICO")], columns=["o", "r", "k", "z"])       # March is the partial month
    rows, filled, n = rc.by_country(s)
    assert rows == [["2026-01", "Guatemala", 1], ["2026-01", "Mexico", 3], ["2026-02", "Mexico", 1]]
    assert filled == 1 and n == 5
