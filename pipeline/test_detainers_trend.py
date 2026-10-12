import pandas as pd
import detainers_trend as dt


def test_detainers_counted_by_month_kind_state_and_lift_without_the_partial_month():
    rows = [("2025-10-03", "Detainer request", "TX", "None", None)] * 70 + [("2025-10-09", "Request for advance notification of release", "ca", "Violent crime", "Removed")] * 30 + \
           [("2025-11-02", "Detainer request", "TX", "Nonviolent crime", "Released by LEA")] * 99 + [("2025-11-04", "Other", "FL", "None", "Rare reason")] + \
           [("2025-12-01", "Detainer request", "TX", "None", None)] * 5          # newest month: partial, left out
    d = pd.DataFrame(rows, columns=["detainer_prepare_date", "detainer_type", "facility_state", "conviction", "detainer_lift_reason"])
    months, states, lifts, first, last = dt.summarize(d, "detainer_prepare_date", "detainer_type", "facility_state", "conviction", "detainer_lift_reason")
    assert months == [["2025-10", 100, 70, 30, 70, 30], ["2025-11", 100, 99, 0, 1, 0]]
    assert [2026, "TX", 169] in states and [2026, "CA", 30] in states
    assert [2026, "Other", 1] in lifts and [2026, "Not lifted or not recorded", 70] in lifts and not any(r[1] == "Rare reason" for r in lifts)
    assert str(last.date()) == "2025-12-01"


def test_a_month_cut_off_early_is_left_out():
    rows = []
    for m, n in [("2025-01", 100), ("2025-02", 100), ("2025-03", 100), ("2025-04", 100), ("2025-05", 100), ("2025-06", 100), ("2025-07", 100), ("2025-08", 20), ("2025-09", 2)]:
        rows += [(f"{m}-05", "Detainer request", "TX", "None", None)] * n
    d = pd.DataFrame(rows, columns=["detainer_prepare_date", "detainer_type", "facility_state", "conviction", "detainer_lift_reason"])
    months, states, _, _, _ = dt.summarize(d, "detainer_prepare_date", "detainer_type", "facility_state", "conviction", None)
    assert months[-1][0] == "2025-07" and [2025, "TX", 700] in states
