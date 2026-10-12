"""Other ICE contractors: grouped by what they are paid for, detention operators left to the Companies tab, lobbying matched by name."""
import vendor_lobbying as vl
import build_site as bs


def test_company_core_name():
    assert vl.core("CACI, INC. - FEDERAL") == "CACI"
    assert vl.core("PALANTIR TECHNOLOGIES INC.") == "PALANTIR TECHNOLOGIES"
    assert vl.core("THE GEO GROUP, INC.") == "GEO"
    assert vl.same_client("Palantir Technologies Inc.", "PALANTIR TECHNOLOGIES")
    assert not vl.same_client("Palantirians LLC", "PALANTIR")
    assert not vl.same_client("ITC Holdings Corp.", "ITC") and not vl.same_client("Acuity Brands, Inc.", "ACUITY")
    assert vl.same_client("Salient CRGT Inc (formerly Salient Federal)", "SALIENT CRGT")


def test_lobbying_tally_counts_latest_version_and_ice_contacts():
    f = lambda posted, ice, imm, income="10000": {"client": {"name": "ACME CORP", "id": 1}, "registrant": {"id": 2}, "filing_year": 2025, "filing_period": "first_quarter", "filing_type": "Q1", "dt_posted": posted,
        "income": income, "expenses": None, "filing_document_url": "u" + posted,
        "lobbying_activities": [{"general_issue_code": "IMM" if imm else "DEF", "government_entities": [{"name": "U.S. Immigration & Customs Enforcement (ICE)"}] if ice else [{"name": "SENATE"}]}]}
    t = vl.tally([f("2025-04-01", False, False), f("2025-04-20", True, True, "20000")], "ACME")
    assert t == {"usd": 20000, "filings": 1, "ice_filings": 1, "imm_filings": 1, "example": "u2025-04-20"}      # the amended report replaces the first


def test_vendor_categories():
    assert bs.vendor_cat("DA01") == "tech" and bs.vendor_cat("7A21") == "tech" and bs.vendor_cat("V211") == "move"
    assert bs.vendor_cat("1005") == "gear" and bs.vendor_cat("Q201") == "med" and bs.vendor_cat("R408") == "prof"
    assert bs.vendor_cat("Z1AA") == "build" and bs.vendor_cat("S206") == "guard" and bs.vendor_cat("") == "other"


def test_jfc_flows_estimate_and_kinds():
    from build_site import jfc_flows, jfc_kind
    totals = [{"jfc_id": "J1", "jfc": "A VICTORY", "cycle": "2024", "receipts": "1000000", "contractor": "10000"},
              {"jfc_id": "J2", "jfc": "B FUND", "cycle": "2024", "receipts": "0", "contractor": "5000"}]
    flows = [{"jfc_id": "J1", "cycle": "2024", "recipient_id": "C1", "recipient": "NRCC", "usd": "500000", "party": "REP", "ctype": "Y", "designation": "U"},
             {"jfc_id": "J1", "cycle": "2024", "recipient_id": "C2", "recipient": "JANE DOE FOR CONGRESS", "usd": "300000", "party": "REP", "ctype": "H", "designation": "P"},
             {"jfc_id": "J2", "cycle": "2024", "recipient_id": "C1", "recipient": "NRCC", "usd": "200000", "party": "REP", "ctype": "Y", "designation": "U"}]
    j = jfc_flows(totals, flows, [{"pac": "G", "recipient_id": "J1"}], {"read": "2026-10-11", "cycles": [2024]})
    assert j["co"] == 15000 and j["sent"] == 1000000 and j["est"] == 8000          # 1% of J1's payments; J2 has no total, so no estimate
    assert j["top"][0][:4] == ["NRCC", 700000, 5000, 2] and j["shared"][0][:2] == ["NRCC", 2]
    assert [f[6] for f in j["funds"]] == [True, False] and j["funds"][0][4] == ["G"]
    assert jfc_kind("DONALD J. TRUMP FOR PRESIDENT 2024, INC.", "N", "D") == "cand" and jfc_kind("SAVE AMERICA", "N", "D") == "lead"
