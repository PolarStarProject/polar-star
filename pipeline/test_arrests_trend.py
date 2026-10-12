import pandas as pd
import arrests_trend as a


def test_arrests_counted_by_month_method_and_state_without_the_partial_month():
    rows = [("2025-10-03", "287(g) Program", "TX", "3 Other Immigration Violator")] * 60 + [("2025-10-20", "Located", "CA", "1 Convicted Criminal")] * 40 + \
           [("2025-11-02", "CAP Local Incarceration", "tx", "3 Other Immigration Violator")] * 99 + [("2025-11-03", "Rare", "FL", "2 Pending Criminal Charges")] + \
           [("2025-12-01", "Located", "CA", "3 Other Immigration Violator")] * 5           # newest month: partial, left out
    d = pd.DataFrame(rows, columns=["apprehension_date", "apprehension_method", "apprehension_state", "apprehension_criminality"])
    months, methods, states, first, last = a.summarize(d, "apprehension_date", "apprehension_method", "apprehension_state", "apprehension_criminality")
    assert months == [["2025-10", 100, 60], ["2025-11", 100, 99]]
    assert ["2025-11", "Other", 1] in methods and not any(m[1] == "Rare" for m in methods)      # 1 of 200 is under 1%
    assert [2026, "TX", 159] in states and [2026, "CA", 40] in states
    assert str(first.date()) == "2025-10-03" and str(last.date()) == "2025-12-01"


def test_rare_methods_are_grouped():
    rows = [("2025-10-03", "Big")] * 200 + [("2025-10-04", "Tiny")] + [("2025-11-01", "Big")]
    d = pd.DataFrame(rows, columns=["apprehension_date", "apprehension_method"])
    _, methods, _, _, _ = a.summarize(d, "apprehension_date", "apprehension_method", None, None)
    assert methods == [["2025-10", "Big", 200], ["2025-10", "Other", 1]]


def test_pick_stops_when_a_needed_column_is_missing():
    try: a.pick(["x", "y"], r"apprehension_date"); assert False
    except SystemExit: pass
    assert a.pick(["Apprehension_Date_Time"], r"apprehension_date(_time)?") == "Apprehension_Date_Time"
