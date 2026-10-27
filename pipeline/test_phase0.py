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


def test_orders_without_fair_opportunity_are_not_counted_as_competed():
    from money_awards import award_competition
    assert award_competition("C", "ONLY ONE SOURCE - OTHER") == "L" and award_competition("C", " urgency ") == "L"
    assert award_competition("C", "FAIR OPPORTUNITY GIVEN") == "C" and award_competition("C", "COMPETITIVE SET ASIDE") == "C"
    assert award_competition("N", "ONLY ONE SOURCE - OTHER") == "N" and award_competition("", "") == ""


def test_the_built_page_script_parses(tmp):
    """A stray // comment once swallowed the rest of a one-line function and the whole page stopped working. node --check
    catches that before publishing (skipped where node or a built page is missing)."""
    import re, shutil, subprocess
    from pathlib import Path
    page = Path(__file__).resolve().parent.parent / "site" / "index.html"
    if not (shutil.which("node") and page.exists()): return
    for i, js in enumerate(re.findall(r"<script>(.*?)</script>", page.read_text(encoding="utf-8"), re.S)):
        f = tmp / f"s{i}.js"; f.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]


def test_build_stops_on_a_script_that_does_not_parse():
    import shutil
    from build_site import check_script
    if not shutil.which("node"): return
    check_script("<script>function a(){ return 1; }</script>")
    try: check_script("<script>function a(){ return 1; // comment ate the brace }</script>"); assert False
    except ValueError as e: assert "does not parse" in str(e)
