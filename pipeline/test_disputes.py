"""ice_local_disputes.csv: rows that break the inclusion rules are rejected at build time, never shown."""
import re
from pathlib import Path
from build_site import disputes_list, DISPUTE_COLS

FAC = {"DLNYHNJ": {}}
GOOD = {"id": "nj-1", "date": "2025-05-09", "state": "NJ", "place": "Newark", "kind": "charge", "started_by": "federal",
        "federal_party": "Justice Department", "local_party": "Mayor of Newark", "officials": "Ras Baraka (Mayor of Newark / alcalde de Newark)", "what_en": "A charge.", "what_es": "Un cargo.",
        "status_en": "Dismissed.", "status_es": "Desestimado.", "status_date": "2025-05-21", "facility_codes": "DLNYHNJ",
        "source_url": "https://www.justice.gov/x", "status_url": "https://www.courtlistener.com/y", "final": ""}


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
    assert rejects(tmp, final="yes")
    assert rejects(tmp, final="Y", status_en="", status_es="", status_date="", status_url="")
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


def test_source_kind():
    from build_site import source_kind
    assert source_kind("https://www.justice.gov/opa/pr/x") == "official" and source_kind("https://www.ded.uscourts.gov/x.pdf") == "official"
    assert source_kind("https://www.hennepinattorney.org/news/x") == "official" and source_kind("https://www.nj.gov/governor/x") == "official"
    assert source_kind("https://clearinghouse.net/case/1/") == "copy" and source_kind("https://kmph.com/resources/pdf/x.pdf") == "copy"
    assert source_kind("https://ny1.com/nyc/x") == "news" and source_kind("") == ""


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


def test_person_key_drops_middle_names_nicknames_and_accents():
    from build_site import person_key
    assert person_key('Jesús G. "Chuy" García') == person_key("Jesús García") == "jesus garcia"
    assert person_key("Katie Boyd Britt") == person_key("Katie Britt") == "katie britt"
    assert person_key("Jodey C. Arrington (TX-19)".replace(" (TX-19)", "")) == "jodey arrington"
    assert person_key("Thomas H. Kean, Jr.") == "thomas kean"
    assert person_key("Madonna") == ""


def test_former_staff_needs_the_first_name_and_skips_interns():
    from build_site import staff_hit
    assert staff_hit("Chief of Staff, Rep. Vince Fong; Chief of Staff, Rep. Bill Thomas.", "vince", "fong")
    assert staff_hit("LA, Sen. Debbie Stabenow; Staff Asst., Sen. Cory Booker", "cory", "booker")
    assert not staff_hit("Comm Drctr, Rep Gallego, Dec 13- Jan 15", "ruben", "gallego")          # Pete Gallego, not Ruben
    assert not staff_hit("Congressman Barry Moore, Legislative Assistant.", "wes", "moore")
    assert not staff_hit("Intern, Sen. Richard Blumenthal", "richard", "blumenthal")


def test_vote_summary():
    from build_site import vote_summary
    assert vote_summary("Y--Y-Y") == ["for", 3, 0] and vote_summary("-NN-N-") == ["ag", 0, 3]
    assert vote_summary("Y--Y-N") == ["mix", 2, 1] and vote_summary("--X---") is None


def test_dispute_people_links_records():
    from build_site import dispute_people
    m = [["A1", "Ana B. Cruz", "H", "R", "NJ", "3", "", ["House Committee on the Judiciary"], "Y--Y-Y", 5000, 0, 1, "", 250, 1],
         ["B2", "Ras J. Baraka", "H", "D", "TX", "9", "", [], "------", 0, 0, 0, "", 0, 0]]
    d = [["2025-05-09", "NJ", "Newark", "charge", "federal", "", "", "", "", "", "", "", [], "https://x", "", "", [["Ras J. Baraka", "Mayor", "alcalde"]], []]]
    site = {"disputes": d, "pol": {"m": m, "c": {"A1": {"jfc": [["FUND X", 1, 1, [], [], 1]]}}, "flags": {"list": [{"bg": "A1"}]}, "gov": [["NJ", "Mikie Sherrill", "D"]]},
            "firms": {"cards": {"Firm Q": {"money": [["Ana Cruz", "campaign", 1000, 1]], "former": [["X", "Chief of Staff, Rep. Ana Cruz", ["GEO"]]]}}},
            "denied": [["2025-05-09", "Delaney Hall, Newark, NJ", "Newark Mayor Ras Baraka", "", "", "", ""]], "statements_visits": [], "statements": []}
    P = dispute_people(site)
    assert P["Ras J. Baraka"]["t"] == [["re", [["Delaney Hall, Newark, NJ", "2025-05-09"]]]] and P["Ras J. Baraka"]["v"] is None
    a = dict(P["Ana B. Cruz"]["t"])
    assert P["Ana B. Cruz"]["v"] == ["for", 3, 0] and a["dm"] == [5000, 250] and a["jf"] == ["FUND X"] and a["lf"] == [["Firm Q", 1000]] and a["fs"] == [["Firm Q", ["GEO"]]] and a["ov"] == 1
    assert "Mikie Sherrill" in P and P["Mikie Sherrill"]["t"] == []


def test_governor_change_needs_a_terms_line(tmp):
    from build_site import governor_changes
    (tmp / "governors_known.csv").write_text("state|name\nNJ|Phil Murphy\nVA|Glenn Youngkin\n", encoding="utf-8")
    try: governor_changes(tmp, {"NJ": "Mikie Sherrill", "VA": "Glenn Youngkin"}, {}); assert False
    except ValueError as e: assert "NJ: Phil Murphy -> Mikie Sherrill" in str(e)
    assert governor_changes(tmp, {"NJ": "Mikie Sherrill", "VA": "Glenn Youngkin"}, {"NJ": [["Phil Murphy", "D", "2018-01-16", "2026-01-20"]]}) == [("NJ", "Phil Murphy", "Mikie Sherrill")]
    assert "NJ|Mikie Sherrill" in (tmp / "governors_known.csv").read_text(encoding="utf-8")
    assert governor_changes(tmp, {"NJ": "Mikie Sherrill", "VA": "Glenn Youngkin"}, {}) == []      # clean once recorded


def test_disputes_reach_the_feed(tmp):
    import watch
    (tmp / "site").mkdir(); (tmp / "site" / "watch.xml").write_text('<feed xmlns="http://www.w3.org/2005/Atom">\n<title>x</title>\n</feed>\n', encoding="utf-8")
    d = ["2025-05-09", "NJ", "Newark", "charge", "federal", "", "", "Federal officers arrested the mayor & charged him.", "", "Dropped.", "", "2025-05-19", [], "https://x/1", "", "", [], [], True]
    watch.add_disputes(tmp, [d])
    s = (tmp / "site" / "watch.xml").read_text(encoding="utf-8")
    assert "<title>Criminal charge, Newark, NJ (2025-05-09)</title>" in s and "mayor &amp; charged" in s and "/2025-05-19</id>" in s and s.rstrip().endswith("</feed>")


def test_docket_newer_than_the_step_on_file(tmp):
    write(tmp, [GOOD])
    (tmp / "dispute_dockets.csv").write_text("id|court|docket_number\nnj-1|njd|2:25-cr-1\n", encoding="utf-8")
    assert disputes_list(tmp, FAC, today="2026-10-25")[0][20] == []                     # not found on CourtListener yet: nothing shown
    (tmp / "dispute_dockets_checked.csv").write_text("id|court|docket_number|cl_id|cl_url|last_filing|entry_date|entry_text|entry_doc|checked\nnj-1|njd|2:25-cr-1|5|https://www.courtlistener.com/docket/5/x/|2025-06-02||||2026-10-20\n", encoding="utf-8")
    assert disputes_list(tmp, FAC, today="2026-10-25")[0][20] == ["https://www.courtlistener.com/docket/5/x/", "2025-06-02", True]   # status is 2025-05-19
    (tmp / "dispute_dockets.csv").write_text("id|court|docket_number\nzz|njd|1\n", encoding="utf-8")
    try: disputes_list(tmp, FAC, today="2026-10-25"); assert False
    except ValueError: pass
