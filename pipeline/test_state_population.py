"""state_population.csv: a mistyped number fails the build, because the 50 states and DC must add up to the US row."""
import shutil
from pathlib import Path
from build_site import state_population

REF = Path(__file__).resolve().parent.parent / "data" / "reference" / "state_population.csv"

def test_the_file_on_disk_adds_up(tmp):
    shutil.copy(REF, tmp / "state_population.csv"); p = state_population(tmp)
    assert p["n"]["TX"] == 31709821 and "US" not in p["n"] and p["as_of"] == "2025-07-01"

def test_a_mistyped_state_fails(tmp):
    (tmp / "state_population.csv").write_text(REF.read_text(encoding="utf-8").replace("TX|31709821", "TX|31709812"), encoding="utf-8")
    try: state_population(tmp)
    except ValueError: return
    raise AssertionError("a mistyped number got through")

def test_puerto_rico_is_kept_but_outside_the_us_total(tmp):
    shutil.copy(REF, tmp / "state_population.csv"); p = state_population(tmp)
    assert p["n"]["PR"] == 3184835 and sum(v for k, v in p["n"].items() if k != "PR") == 341784857
