"""Checks for reading a lobbying firm's clients, political money and former officials out of lda.gov records."""
from firm_profiles import core, qname, recipient, clients_of, money_of, former_of

KEY = core("Holland & Knight LLP")


def filing(client, cid, period, posted, income, ents=(), issue="", reg="HOLLAND & KNIGHT LLP", ftype="Q1", lob=()):
    return {"registrant": {"name": reg}, "client": {"name": client, "id": cid}, "filing_year": 2026, "filing_period": period, "filing_type": ftype,
            "dt_posted": posted, "income": income,
            "lobbying_activities": [{"general_issue_code": issue, "government_entities": [{"name": e} for e in ents], "lobbyists": list(lob)}]}


def test_names():
    assert core("Capitol Counsel, LLC") == core("Capitol Counsel LLC") == "CAPITOL COUNSEL"
    assert core("Holland & Knight") == core("Holland & Knight LLP")
    assert core("Squire Patton Boggs") == core("Squire Patton Boggs, LLP")
    assert core("Sonoran Policy Group, LLC D/B/A Stryk Global Diplomacy") == "SONORAN POLICY GROUP"
    assert qname("Holland & Knight LLP") == "Holland & Knight" and qname("Continental Strategy, LLC") == "Continental Strategy"
    assert recipient("Senator John Cornyn") == recipient("JOHN CORNYN") == "John Cornyn"
    assert recipient("Rep. Jane Doe") == "Jane Doe"


def test_clients_latest_version_and_flags():
    fl = [filing("ACME CORP", 1, "first_quarter", "2026-04-10", "10000.00"),
          filing("ACME CORP", 1, "first_quarter", "2026-05-01", "20000.00", ents=["U.S. Immigration & Customs Enforcement (ICE)", "Homeland Security, Dept of (DHS)"], issue="IMM"),   # amendment replaces the first
          filing("ACME CORP", 1, "second_quarter", "2026-07-10", "5000.00"),
          filing("OTHER CO", 2, "first_quarter", "2026-04-10", "1000.00", reg="HOLLAND PARTNERS GROUP"),            # another firm whose name contains the search
          filing("NEW CLIENT", 3, "first_quarter", "2026-02-01", None, ftype="RR")]                              # a registration: no amounts
    c = clients_of(fl, KEY)
    assert set(c) == {"ACME CORP"}
    a = c["ACME CORP"]
    assert a["usd"] == 25000 and a["filings"] == 2 and a["ice"] == 1 and a["dhs"] == 1 and a["imm"] == 1
    assert a["first"] == "2026 Q1" and a["last"] == "2026 Q2"


def test_money_by_recipient_never_contributor():
    rep = {"registrant": {"name": "Holland & Knight LLP"}, "filing_uuid": "u1", "contribution_items": [
        {"contribution_type": "feca", "contributor_name": "DOE, JANE", "payee_name": "CORNYN FOR SENATE", "honoree_name": "Senator John Cornyn", "amount": "500.00"},
        {"contribution_type": "feca", "contributor_name": "ROE, RICH", "payee_name": "CORNYN FOR SENATE", "honoree_name": "John Cornyn", "amount": "1000.00"},
        {"contribution_type": "he", "contributor_name": "HOLLAND & KNIGHT", "payee_name": "Some Foundation", "honoree_name": "Rep. Jane Smith", "amount": "2500"},
        {"contribution_type": "feca", "contributor_name": "X", "payee_name": "A PAC", "honoree_name": "", "amount": "0"}]}
    m = money_of([rep, dict(rep)], KEY)                       # the same report twice is counted once
    assert m == {("John Cornyn", "campaign"): [1500.0, 2], ("Jane Smith", "honorary"): [2500.0, 1]}
    assert not any("DOE" in k[0] or "ROE" in k[0] for k in m)
    assert money_of([dict(rep, registrant={"name": "Other Firm LLC"})], KEY) == {}


def test_former_officials_keep_post_only():
    lob = [{"covered_position": "Former Chief of Staff, Rep. A", "lobbyist": {"first_name": "JOHN", "last_name": "DOE"}},
           {"covered_position": "N/A", "lobbyist": {"first_name": "MARY", "last_name": "ROE"}},
           {"covered_position": "", "lobbyist": {"first_name": "PAT", "last_name": "POE"}}]
    f = former_of([filing("ACME CORP", 1, "first_quarter", "2026-04-10", "1", lob=lob)], KEY)
    assert f == {"John Doe": "Former Chief of Staff, Rep. A"}


def test_private_people_are_never_named():
    from firm_profiles import is_person, PERSONAL
    for n in ["SMITH, JOHN A.", "KAREN BACARDI", "STEVE POLLOCK", "TRISTAN THOMPSON"]: assert is_person(n), n
    for n in ["MORGAN STANLEY", "PALANTIR TECHNOLOGIES, INC.", "DENVER WATER", "GILA RIVER INDIAN COMMUNITY", "STANLEY BLACK & DECKER", "HOUSTON AIRPORT SYSTEM", "SHERPA 6", "ISSUE ONE"]: assert not is_person(n), n
    assert is_person("NOBODY KNOWNNAME", "Individual")
    fl = [filing("SMITH, JOHN", 9, "first_quarter", "2026-04-10", "30000"), filing("DOE, JANE", 8, "first_quarter", "2026-04-10", "10000")]
    c = clients_of(fl, KEY)
    assert all(k.startswith(PERSONAL) for k in c) and len(c) == 2 and not any("SMITH" in k or "DOE" in k for k in c)


def test_recipient_last_first_and_acronyms():
    assert recipient("Cornyn, John") == "John Cornyn" and recipient("King Jr., Angus") == "Angus King Jr."
    assert recipient("NRSC") == "NRSC" and recipient("DSCC") == "DSCC"
