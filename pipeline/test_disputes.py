"""ice_local_disputes.csv: rows that break the inclusion rules are rejected at build time, never shown."""
import re
from pathlib import Path
from build_site import disputes_list, DISPUTE_COLS

FAC = {"DLNYHNJ": {}}
GOOD = {"id": "nj-1", "date": "2025-05-09", "state": "NJ", "place": "Newark", "kind": "charge", "started_by": "federal",
        "federal_party": "Justice Department", "local_party": "Mayor of Newark", "officials": "Ras Baraka (Mayor of Newark / alcalde de Newark)", "what_en": "A charge.", "what_es": "Un cargo.",
        "status_en": "Dismissed.", "status_es": "Desestimado.", "status_date": "2025-05-21", "facility_codes": "DLNYHNJ",
        "source_url": "https://www.justice.gov/x", "status_url": "https://www.courtlistener.com/y"}


def write(tmp, rows):
    (tmp / "ice_local_disputes.csv").write_text("|".join(DISPUTE_COLS) + "\n" + "".join("|".join(r[c] for c in DISPUTE_COLS) + "\n" for r in rows), encoding="utf-8")


def rejects(tmp, **change):
    write(tmp, [{**GOOD, **change}])
    try: disputes_list(tmp, FAC, today="2026-10-25")
    except ValueError: return True
    return False


def test_a_good_row_comes_through_newest_first(tmp):
    write(tmp, [GOOD, {**GOOD, "id": "il-1", "date": "2025-10-06", "state": "IL", "facility_codes": "", "status_en": "", "status_es": "", "status_date": "", "status_url": ""}])
    out = disputes_list(tmp, FAC, today="2026-10-25")
    assert [r[1] for r in out] == ["IL", "NJ"] and out[1][12] == ["DLNYHNJ"] and out[1][16] == [["Ras Baraka", "Mayor of Newark", "alcalde de Newark"]]


def test_missing_file_is_empty(tmp):
    assert disputes_list(tmp, FAC) == []


def test_bad_rows_are_rejected(tmp):
    assert rejects(tmp, source_url="")                      # no source, no entry
    assert rejects(tmp, source_url="http://insecure.example")
    assert rejects(tmp, kind="protest")
    assert rejects(tmp, started_by="ice")
    assert rejects(tmp, state="XX")
    assert rejects(tmp, facility_codes="NOPE")
    assert rejects(tmp, date="2027-01-01")                  # future
    assert rejects(tmp, status_url="")                      # a status needs its own source
    assert rejects(tmp, status_es="")                       # and both languages
    assert rejects(tmp, status_date="2025-01-01")           # before the dispute began
    assert rejects(tmp, what_es="")
    assert rejects(tmp, officials="Ras Baraka")                # role is required
    assert rejects(tmp, officials="Ras Baraka (Mayor of Newark)")   # in both languages


def test_repeated_id_is_rejected(tmp):
    write(tmp, [GOOD, GOOD])
    try: disputes_list(tmp, FAC, today="2026-10-25"); assert False
    except ValueError: pass


def test_page_has_the_tab_in_both_languages():
    s = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text(encoding="utf-8")
    for i in ('id="v-disp"', 'id="tab-disp"', 'id="dp-list"', '"disp"'): assert i in s, i
    for k in ("tab_disp", "dp_lead", "dp_how", "dp_note", "dp_kind", "dp_sum", "xl_dp_ref"): assert len(re.findall(r"[\s,{]" + k + r":", s)) == 2, k
    lead = re.findall(r'dp_lead:"([^"]*)"', s)
    for w in ("defied", "attack", "crack", "illegal"): assert all(w not in x.lower() for x in lead), w   # neutral wording


def test_disputed_laws(tmp):
    write(tmp, [GOOD])
    (tmp / "disputed_laws.csv").write_text("dispute_id|law_en|law_es|law_url|authors\nnj-1|Law|Ley|https://x|Ann Lee (State Senator / senadora estatal)\n", encoding="utf-8")
    assert disputes_list(tmp, FAC, today="2026-10-25")[0][17] == [["Law", "Ley", "https://x", [["Ann Lee", "State Senator", "senadora estatal"]]]]
    for bad in ("nope|Law|Ley|https://x|", "nj-1|Law||https://x|", "nj-1|Law|Ley|http://x|", "nj-1|Law|Ley|https://x|Ann Lee"):
        (tmp / "disputed_laws.csv").write_text("dispute_id|law_en|law_es|law_url|authors\n" + bad + "\n", encoding="utf-8")
        try: disputes_list(tmp, FAC, today="2026-10-25"); assert False, bad
        except ValueError: pass


def test_governor_terms(tmp):
    from build_site import governor_terms
    (tmp / "governor_terms.csv").write_text("state|name|party|start|end|source\nNJ|Phil Murphy|D|2018-01-16|2026-01-20|https://x\n", encoding="utf-8")
    assert governor_terms(tmp) == {"NJ": [["Phil Murphy", "D", "2018-01-16", "2026-01-20"]]}
    (tmp / "governor_terms.csv").write_text("state|name|party|start|end|source\nNJ|Phil Murphy|D|2026-01-20|2018-01-16|https://x\n", encoding="utf-8")
    try: governor_terms(tmp); assert False
    except ValueError: pass


def test_link_check_flags_but_keeps(tmp):
    from disputes_check import check, links
    out = check(["https://a", "https://b"], {"https://b": {"last_ok": "2026-10-01"}}, "2026-10-25", lambda u: None if u.endswith("b") else "page")
    assert [r["ok"] for r in out] == ["1", "0"] and out[1]["last_ok"] == "2026-10-01"
    assert links([GOOD, {**GOOD, "status_url": ""}]) == ["https://www.courtlistener.com/y", "https://www.justice.gov/x"]
    write(tmp, [GOOD]); (tmp / "disputes_checked.csv").write_text("url|ok|checked|last_ok\nhttps://www.justice.gov/x|0|2026-10-20|\n", encoding="utf-8")
    assert disputes_list(tmp, FAC, today="2026-10-25")[0][15] == "2026-10-20"
