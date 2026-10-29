"""people_index: one card per named person. Records join by Bioguide id or by first and last name, and say so when the join is by name only."""
from build_site import people_index, donor_key, dispute_people

def mem(bg, name, st, votes="YY", current=True):
    return [bg, name, "H", "R", st, 1, "", [], votes, 0, 0, current, "", 0, 0]

def site(**kw):
    s = {"pol": {"m": [mem("A1", "Mike Rogers", "AL"), mem("B2", "Mike Rogers", "MI"), mem("C3", 'Jesús "Chuy" García', "IL"), mem("D4", "Mikie Sherrill", "NJ", "NN", False)],
                 "gov": [["NJ", "Mikie Sherrill", "D", "2026-01-20", "https://nj.gov", 0, [], False, [], 0, ""]],
                 "local": [["FAC1", "County Jail", "TX", "John Doe", "Sheriff", "Doe County Sheriff's Office", "https://x", "2026-10-01"]],
                 "rev": [["GEO", "Jane Roe", "Chief of Staff, Rep. Jesús García", "SOME FIRM", 2024, 2025]]}}
    s.update(kw); return s

def test_two_members_with_one_name_stay_apart_and_others_do_not_join_them():
    x = people_index(site(local=None, disputes=[[ "2026-01-01", "AL", "Town", 0,0,0,0,0,0,0,0,0,0,0,0,0, [["Mike Rogers", "Mayor", "alcalde"]], [], False, [], []]]), {}, None)
    assert "A1" in x["p"] and "B2" in x["p"] and x["p"]["A1"]["r"] == [["m", "A1"]]
    assert x["nk"]["Mike Rogers"] == "mike rogers" and x["p"]["mike rogers"]["r"][0][0] == "d"

def test_nickname_member_joins_by_first_and_last_name():
    x = people_index(site(disputes=[["2026-01-01", "IL", "Chicago", 0,0,0,0,0,0,0,0,0,0,0,0,0, [["Jesús García", "Rep.", "rep."]], [], False, [], []]]), {}, None)
    assert x["nk"]["Jesús García"] == "C3" and [r[0] for r in x["p"]["C3"]["r"]] == ["m", "d"] and "x" not in x["p"]["C3"]

def test_member_who_became_governor_is_one_card_without_a_warning():
    e = people_index(site(), {}, None)["p"]["D4"]
    assert [r[0] for r in e["r"]] == ["m", "g"] and "x" not in e and e["v"][0] == "ag"

def test_287g_signer_only_when_signed_by_the_agency():
    st = {"TX": [["Doe PD", "", "T", "2025-06-18", "", "", "", "a.pdf", ["John Doe", "Chief", "s"]], ["Roe PD", "", "T", "2025-06-18", "", "", "", "", ["Ann Contact", "Lt", "c"]]]}
    x = people_index(site(), st, None)
    assert [r[0] for r in x["p"]["john doe"]["r"]] == ["l", "a"] and "ann contact" not in x["p"]
    assert x["p"]["john doe"]["x"] == 1     # a sheriff and an agency signer are different lists: joined by name, so flagged

def test_sheriff_and_signer_in_different_states_are_flagged():
    st = {"FL": [["Doe PD", "", "T", "2025-06-18", "", "", "", "", ["John Doe", "Chief", "s"]]]}
    assert people_index(site(), st, None)["p"]["john doe"]["x"] == 1

def test_donor_names_join_last_first_and_are_always_flagged():
    assert donor_key("ROE, JANE M. MRS.") == "jane roe" and donor_key("DOE, DR. JOHN") == "john doe"
    rows = [["GEO", "2024-01-01", "ROE, JANE", "GEO GROUP", "VP", "DC", 500, "A PAC", "", "", "", "", 2024], ["GEO", "2024-02-01", "ROE, JANE", "GEO GROUP", "VP", "DC", 250, "B PAC", "", "", "", "", 2024],
            ["GEO", "2024-02-01", "SMITH, AL", "GEO GROUP", "VP", "DC", 250, "B PAC", "", "", "", "", 2024]]
    x = people_index(site(), {}, {"rows": rows})
    g = [r for r in x["p"]["jane roe"]["r"] if r[0] == "$"][0]
    assert g[1:4] == [2, 750, [["A PAC", 500], ["B PAC", 250]]] and x["p"]["jane roe"]["x"] == 1 and x["dn"] == {"ROE, JANE": "jane roe"}
    assert "al smith" not in x["p"]                  # a donor named nowhere else gets no card of their own

def test_lobbyist_past_post_ties_to_the_member():
    e = people_index(site(firms={"cards": {"SOME FIRM": {"money": [], "former": [["Jane Roe", "Chief of Staff, Rep. Jesús García", []]]}}}), {}, None)["p"]["C3"]
    assert ["fs", [["SOME FIRM", []]]] in e["t"]

def test_dispute_people_unchanged_by_the_shared_tie_code():
    s = site(disputes=[["2026-01-01", "IL", "Chicago", 0,0,0,0,0,0,0,0,0,0,0,0,0, [["Jesús García", "Rep.", "rep."]], [], False, [], []]],
             firms={"cards": {"SOME FIRM": {"money": [], "former": [["Jane Roe", "Chief of Staff, Rep. Jesús García", []]]}}})
    d = dispute_people(s)["Jesús García"]
    assert d["bg"] == "C3" and d["t"] == [["fs", [["SOME FIRM", []]]]]

def test_governor_in_office_when_a_dispute_began_gets_it_on_their_card():
    D = [["2026-03-01", "NJ", "Newark", 0,0,0,0,0,0,0,0,0,0,0,0,0, [], [], False, [], []], ["2025-06-01", "NJ", "Elizabeth", 0,0,0,0,0,0,0,0,0,0,0,0,0, [], [], False, [], []]]
    x = people_index(site(disputes=D, gov_terms={"NJ": [["Phil Murphy", "D", "2018-01-16", "2026-01-20"]]}), {}, None)["p"]
    assert [r[1] for r in x["D4"]["r"] if r[0] == "d"] == ["2026-03-01"] and [r[1] for r in x["phil murphy"]["r"] if r[0] == "d"] == ["2025-06-01"]
