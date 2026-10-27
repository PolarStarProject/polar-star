"""A help line the weekly check cannot confirm is shown after a check by hand, for 30 days, and says so."""
from build_site import hotlines


def setup(tmp, checked_ok, manual):
    (tmp / "hotlines.csv").write_text("key|label|number|match|sources\ndril|ICE line|1-888-351-4024|8883514024|https://www.ice.gov/x\norr|ORR|1-800-203-7001|8002037001|https://acf.gov/x\n", encoding="utf-8")
    (tmp / "hotlines_checked.csv").write_text("key|ok|source|checked|last_ok|reason\n" + "".join(f"{k}|{o}|https://s/{k}|2026-10-26|2026-10-26|\n" for k, o in checked_ok.items()), encoding="utf-8")
    (tmp / "hotlines_manual.csv").write_text("key|checked|source|note\n" + "".join(f"{k}|{d}|https://www.ice.gov/page|n\n" for k, d in manual.items()), encoding="utf-8")


def test_hand_check_shows_a_blocked_line_for_30_days(tmp):
    setup(tmp, {"dril": "0", "orr": "1"}, {"dril": "2026-10-27"})
    h = hotlines(tmp, "2026-11-10")
    assert h["dril"] == ["1-888-351-4024", "https://www.ice.gov/page", "2026-10-27", "hand"] and h["orr"][0] == "1-800-203-7001"
    assert "dril" not in hotlines(tmp, "2026-11-27")                    # 31 days: hidden until checked again


def test_the_automatic_check_wins_and_bad_rows_are_refused(tmp):
    setup(tmp, {"dril": "1"}, {"dril": "2026-10-27"})
    assert len(hotlines(tmp, "2026-10-28")["dril"]) == 3                # no "hand" label when the weekly check passed
    setup(tmp, {}, {"nope": "2026-10-27"})
    try: hotlines(tmp, "2026-10-28"); assert False
    except ValueError: pass
