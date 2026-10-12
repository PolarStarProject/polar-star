"""Roll-call records: reading the House and Senate formats, and refusing votes that do not add up."""
import politicians as p

HOUSE = b"""<rollcall-vote><vote-metadata><legis-num>S 5</legis-num><vote-question>On Passage</vote-question><action-date>22-Jan-2025</action-date>
<vote-totals><totals-by-vote><yea-total>2</yea-total><nay-total>1</nay-total><present-total>0</present-total><not-voting-total>1</not-voting-total></totals-by-vote></vote-totals></vote-metadata>
<vote-data><recorded-vote><legislator name-id="A000001" party="R" state="TX">A</legislator><vote>Yea</vote></recorded-vote>
<recorded-vote><legislator name-id="B000002" party="D" state="CA">B</legislator><vote>Yea</vote></recorded-vote>
<recorded-vote><legislator name-id="C000003" party="D" state="NY">C</legislator><vote>Nay</vote></recorded-vote>
<recorded-vote><legislator name-id="D000004" party="D" state="IL">D</legislator><vote>Not Voting</vote></recorded-vote></vote-data></rollcall-vote>"""
SENATE = b"""<roll_call_vote><congress>119</congress><session>1</session><vote_number>7</vote_number><vote_date>January 20, 2025, 06:57 PM</vote_date>
<question>On Passage of the Bill</question><document><document_type>S.</document_type><document_number>5</document_number></document>
<count><yeas>1</yeas><nays>1</nays><present></present><absent>0</absent></count>
<members><member><last_name>X</last_name><party>R</party><state>KY</state><vote_cast>Yea</vote_cast><lis_member_id>S001</lis_member_id></member>
<member><last_name>Y</last_name><party>D</party><state>VT</state><vote_cast>Nay</vote_cast><lis_member_id>S002</lis_member_id></member></members></roll_call_vote>"""


def test_house_record():
    meta, v = p.parse_house(HOUSE)
    assert meta["date"] == "2025-01-22" and meta["bill"] == "S 5" and (meta["yeas"], meta["nays"], meta["not_voting"]) == (2, 1, 1)
    assert v == {"A000001": ("Y", "R"), "B000002": ("Y", "D"), "C000003": ("N", "D"), "D000004": ("X", "D")}
    p.check(meta, v, {"id": "t"}); assert p.passage(meta, "S 5")


def test_senate_record_maps_lis_ids_to_bioguide():
    meta, v = p.parse_senate(SENATE, {"S001": "M000355", "S002": "S000033"})
    assert meta["date"] == "2025-01-20" and meta["bill"] == "S 5" and v == {"M000355": ("Y", "R"), "S000033": ("N", "D")}
    p.check(meta, v, {"id": "t", "expect": (1, 1)})


def test_votes_that_do_not_add_up_are_refused():
    meta, v = p.parse_house(HOUSE)
    for bad in ({"id": "t", "expect": (3, 1)}, None):
        try:
            if bad: p.check(meta, v, bad)
            else: p.check({**meta, "yeas": 9}, v, {"id": "t"})
            assert False, "should have refused"
        except ValueError: pass


def test_member_committees_keep_campaign_joint_and_leadership_funds():
    import member_committees as mc
    rows = mc.rows_for("X1", [{"committee_id": "C1", "name": "SMITH  FOR CONGRESS", "designation": "P"}, {"committee_id": "C2", "name": "SMITH VICTORY", "designation": "J"},
                              {"committee_id": "C3", "name": "OLD", "designation": "U"}], [{"committee_id": "C4", "name": "SMITH PAC", "designation": "B"}])
    assert [(r["committee_id"], r["name"], r["designation"]) for r in rows] == [("C1", "SMITH FOR CONGRESS", "P"), ("C2", "SMITH VICTORY", "J"), ("C4", "SMITH PAC", "D")]


def test_official_flags_one_rule_for_everyone_and_a_floor():
    import build_site as b
    m = lambda bg, com, pac, cur=1: [bg, bg, "H", "R", "TX", "1", "", com, "Y--", pac, 0, cur, "R--", 0, 0]
    P = {"m": [m("A", ["House Committee on Homeland Security"], 5000), m("B", ["House Committee on the Judiciary"], 500), m("C", [], 3000), m("D", ["X"], 9000, cur=0)]}
    cards = {"A": {"pac": [["G", "A FOR CONGRESS", 5000, "C"]]}, "B": {"pac": [["C", "B FOR CONGRESS", 500, "C"]], "don": [["DOE, J", "GEO", 600, 2]]}, "C": {"pac": [["G", "C FOR CONGRESS", 3000, "C"]], "fac": [["F1", "Big Center", "GEO", 900, 0, 0], ["F2", "County Jail", "", 50, 0, 0]]}}
    out = {f["bg"]: f for f in b.official_flags(P, cards, {"officials_min_usd": 1000})}
    assert set(out) == {"A", "B", "C"}                           # D has left Congress
    P["m"].append(m("J", ["House Committee on the Judiciary"], 2500)); cards["J"] = {"jfc": [["J VICTORY", 2500, 2, [], ["G"], 1]]}
    assert "J" not in {f["bg"] for f in b.official_flags(P, cards, {"officials_min_usd": 1000})}   # money to a joint fundraiser alone does not count
    P["m"].append(m("E", ["X"], 0)); cards["E"] = {"don": [["ROE, R", "CC", 10, 1]]}
    assert "E" in {f["bg"] for f in b.official_flags(P, cards, {"officials_min_usd": 0})}          # no floor: a $10 gift counts
    assert out["A"]["why"] == ["com"] and out["B"]["why"] == ["com"] and out["B"]["don"] == 600
    assert out["C"]["why"] == ["local"] and out["C"]["local"] == [["F1", "Big Center", "GEO"]]


def test_top_donors_keep_ten_largest_per_member_and_kind():
    import member_top_donors as t
    g = {}
    for i in range(22): t.add(g, "A", "G", f"C{i}", f"PAC {i}", 100 * (i + 1))
    t.add(g, "A", "G", "C0", "PAC 0", 5000); t.add(g, "A", "O", "S1", "SUPER PAC", 250000, 3); t.add(g, "B", "G", "C9", "REFUNDED", -200)
    rows = t.top(g)
    gave = [r for r in rows if r["kind"] == "G"]
    assert len(gave) == 20 and gave[0] == {"bioguide": "A", "kind": "G", "committee_id": "C0", "name": "PAC 0", "usd": 5100, "count": 2}
    g2 = {}                                                        # 30 committees at the legal maximum: no alphabetical pick, a count instead
    for i in range(40): t.add(g2, "Z", "G", f"K{i}", f"AAA {i}" if i < 3 else f"ZZZ {i}", 10000)
    t.add(g2, "Z", "G", "BIG", "BIG PAC", 12000)
    r2 = t.top(g2)
    assert [r["name"] for r in r2 if r["kind"] == "G"] == ["BIG PAC"] and [(r["kind"], r["usd"], r["count"]) for r in r2 if r["kind"] == "TG"] == [("TG", 10000, 40)]
    g3 = {}
    for i in range(27): t.add(g3, "Y", "G", f"K{i}", f"P{i}", 10000)
    assert len([r for r in t.top(g3) if r["kind"] == "G"]) == 27               # a short tie is shown in full
    assert [r["kind"] for r in rows if r["bioguide"] == "A"].count("O") == 1 and not [r for r in rows if r["bioguide"] == "B"]
