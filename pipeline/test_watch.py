"""The watch list: when an alert opens and closes, how facility alerts are worked out, and what a brief contains."""
import watch as w


def test_ice_overdue_waits_a_cycle_plus_a_week():
    assert w.ice_overdue("2026-07-20", "2026-08-10") is None                 # 21 days: inside the grace week
    a = w.ice_overdue("2026-07-20", "2026-10-09")
    assert a["d"] == {"days": 81, "missed": 5, "last": "2026-07-20", "checked": "2026-10-09"} and a["kind"] == "overdue"
    assert "July 20, 2026" in a["facts"][0]
    assert w.ice_overdue("", "2026-10-09") is None


def test_log_keeps_the_opening_day_closes_and_reopens():
    log = w.update_log([], {"a"}, "2026-10-01")
    log = w.update_log(log, {"a"}, "2026-10-08")
    assert log == [{"id": "a", "opened": "2026-10-01", "closed": ""}]
    log = w.update_log(log, set(), "2026-10-15")
    assert log[0]["closed"] == "2026-10-15"
    log = w.update_log(log, {"a"}, "2026-11-01")
    assert len(log) == 2 and log[1] == {"id": "a", "opened": "2026-11-01", "closed": ""}


def test_poisson_tail():
    assert w.poisson_tail(0, 3) == 1
    assert abs(w.poisson_tail(1, 1) - (1 - 2.718281828 ** -1)) < 1e-6
    assert w.poisson_tail(4, 1.01) < 0.03 < w.poisson_tail(2, 1.0)


def _site():
    F = {"BIG": {"name": "Big Center", "state": "CA", "death_reports": [["2026-01-05", "B", "x"], ["2026-03-02", "B", "y"], ["2026-05-02", "B", "z"]],
                 "visits": [["2026-02-01", "U.S. Representative A", "denied", "", ""]]},
         "OTHER": {"name": "Other Center", "state": "TX", "death_reports": [["2026-04-01", "B", "q"]], "visits": []},
         "TINY": {"name": "Tiny Jail", "state": "TX", "death_reports": [["2026-02-01", "B", "r"], ["2026-03-01", "B", "s"]], "visits": []}}
    contracts = [[None] * 7 + [c] for c in F]
    months = [f"2025-{m:02d}" for m in range(8, 13)] + [f"2026-{m:02d}" for m in range(1, 8)]
    pdm = {"BIG": {m: 300 * 30 for m in months}, "OTHER": {m: 20000 * 30 for m in months}, "TINY": {m: 20 * 30 for m in months}}
    return {"facilities": F, "contracts": contracts, "conduct": {"overall": 9.4, "sites": []}}, pdm


def test_facility_alert_needs_rate_count_size_and_chance():
    site, pdm = _site()
    out = w.facility_alerts(site, pdm, w.RULES_DEFAULT)
    assert [a["code"] for a in out] == ["BIG"]                               # TINY holds too few people; OTHER is at the overall rate
    a = out[0]
    assert a["d"]["dead"] == 3 and a["d"]["denied"] == 1 and a["d"]["p"] < 0.05
    assert any("does not show that one caused the other" in x for x in a["facts"])
    assert any(n.startswith("California Attorney General") for n, _ in a["to"]) and any(n == "@members:CA" for n, _ in a["to"])


def test_brief_names_bodies_not_people_and_no_death_report_files():
    site, pdm = _site()
    a = w.facility_alerts(site, pdm, w.RULES_DEFAULT)[0]
    b = w.brief(a, "2026-10-09", "Polar Star Project")
    assert "Members of Congress from CA, both parties" in b and "ddr_" not in b and "U.S. Representative A" not in b
    assert "regardless of party" in b


def test_facility_alerts_stay_off_the_page_until_approved(tmp_path):
    import json, pathlib
    site, pdm = _site(); root = pathlib.Path(tmp_path); ref = root / "ref"; (root / "site").mkdir(); ref.mkdir()
    site["contracts_meta"] = {"as_of": "2026-07-20"}
    out = w.build(site, pdm, "2026-10-09", ref, root, "P")
    assert [a["id"] for a in out["alerts"]] == ["ice-detention-stats"] and out["candidates"] == 1
    assert (root / "data" / "watch" / "briefs" / "ice-detention-stats.md").exists() and not (root / "data" / "watch" / "briefs" / "facility-big.md").exists()
    assert "facility-big" not in (root / "site" / "watch.xml").read_text()
    (ref / "watch_rules.json").write_text(json.dumps({"facility_published": True}))
    out = w.build(site, pdm, "2026-10-10", ref, root, "P")
    assert {a["id"] for a in out["alerts"]} == {"ice-detention-stats", "facility-big"}
    assert [r["opened"] for r in out["alerts"]] == ["2026-10-09", "2026-10-10"]


def _hp():
    return {"as_of": "2026-08-06", "national": {"n": 10000, "over180": 19, "over365": 6, "n180": 1900, "n365": 600},
            "facilities": {"BIG": {"n": 200, "over365": 20, "n365": 40}, "OTHER": {"n": 5000, "over365": 6, "n365": 300}, "TINY": {"n": 40, "over365": 22, "n365": None}}}


def test_long_detention_national_item_counts_and_says_no_reason_is_recorded():
    a = w.long_national(_hp())
    assert a["d"] == {"n": 10000, "n365": 600, "n180": 1900, "p365": 6.0, "p180": 19.0, "as_of": "2026-08-06"}
    assert "do not say why" in a["facts"][1] and "Zadvydas" in a["facts"][2]
    assert any(n == "House Judiciary Committee" for n, _ in a["to"])
    assert w.long_national(None) is None


def test_long_stay_facility_needs_double_the_share_ten_people_and_low_chance():
    site, pdm = _site()
    out = {a["code"]: a for a in w.facility_alerts(site, pdm, w.RULES_DEFAULT, _hp())}
    assert "long" in out["BIG"]["why"] and out["BIG"]["d"]["n365"] == 40 and out["BIG"]["d"]["lnat"] == 6.0
    assert "OTHER" not in out and "TINY" not in out                         # at the national share; and under ten people (count withheld)
    assert any("on appeal" in x for x in out["BIG"]["facts"])


def test_many_tests_need_a_stricter_cut():
    import watch as w
    T = [(0.001, "a", "deaths", True, {}), (0.04, "b", "deaths", True, {}), (0.3, "c", "deaths", True, {}), (0.5, "d", "long", True, {})]
    assert w.bh_cut(T, 0.05) == 0.001                      # 0.04 would pass on its own, but not once four tests are run
    assert w.bh_cut([(0.2, "a", "x", True, {})], 0.05) == 0
