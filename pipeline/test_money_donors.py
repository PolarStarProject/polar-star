"""Named donors: which reported employers count, what is dropped as a double count, what is kept, and that no address survives."""
import money_donors as m


def test_employer_must_start_with_the_company():
    assert m.company_of("The GEO Group, Inc.") == "GEO" and m.company_of("GEO GROUP") == "GEO" and m.company_of("Geo Secure Services LLC") == "GEO"
    assert m.company_of("CoreCivic") == "CC" and m.company_of("Core Civic Inc") == "CC" and m.company_of("Corrections Corp. of America") == "CC"
    assert m.company_of("Management & Training Corp") == "MTC" and m.company_of("LaSalle Corrections") == "LAS"
    for e in ("GEOLOGY ASSOCIATES", "GEO", "FORMER GEO GROUP", "SELF-EMPLOYED", "RETIRED", "", None, "TRAINING MANAGEMENT CORP"):
        assert m.company_of(e) is None, e


def _r(**k):
    r = {"committee_id": "C1", "memo_code": None, "entity_type": "IND", "contributor_employer": "GEO GROUP", "contributor_name": "DOE, JANE",
         "contribution_receipt_date": "2025-03-01T00:00:00", "contribution_receipt_amount": 500.0, "contributor_street_1": "1 MAIN ST",
         "contributor_city": "BOCA RATON", "contributor_zip": "33431", "contributor_state": "FL", "image_number": "202503019000"}
    r.update(k); return r


def test_conduits_memos_organisations_and_repeats_are_dropped():
    rows = [_r(), _r(), _r(committee_id="C00694323"), _r(memo_code="X"), _r(entity_type="ORG"), _r(contributor_employer="GEOLOGY INC"), _r(contribution_receipt_amount=250.0)]
    k = m.keep(rows)
    assert len(k) == 2 and all(co == "GEO" for co, _ in k)


def test_row_keeps_state_but_no_street_city_or_zip_and_links_the_filing():
    co, r = m.keep([_r(contributor_name="DOE | JANE")])[0]
    out = m.row(co, 2026, r, {"C1": ("H", "R", "SMITH FOR CONGRESS")}, {"C1": "S000001"})
    assert list(out) == m.FIELDS and out["state"] == "FL" and out["name"] == "DOE / JANE" and out["bioguide"] == "S000001"
    assert not any(v in str(out.values()) for v in ("MAIN ST", "BOCA", "33431"))
    assert out["url"] == "https://docquery.fec.gov/cgi-bin/fecimg/?202503019000"


def test_member_link_only_for_candidate_committees_and_leadership_funds_tied_to_one_person():
    by = {"H1": "A1", "S1": "B1", "H2": "C1"}
    recs = {"CA": {"committee_type": "H", "candidate_ids": ["H1"]}, "CB": {"committee_type": "Q", "designation": "D", "sponsor_candidate_ids": ["S1"]},
            "CC": {"committee_type": "Y", "candidate_ids": ["H1"]}, "CD": {"committee_type": "H", "candidate_ids": ["H1", "H2"]}, "CE": {"committee_type": "S", "candidate_ids": ["X9"]}}
    assert m.member_links(recs, by) == {"CA": "A1", "CB": "B1"}


def _write(tmp, rows, total):
    import json
    hdr = "|".join(m.FIELDS)
    (tmp / "fec_donors.csv").write_text(hdr + "\n" + "\n".join("|".join(str(r[k]) for k in m.FIELDS) for r in rows) + "\n", encoding="utf-8")
    (tmp / "fec_donors_meta.json").write_text(json.dumps({"read": "2026-10-10", "cycles": [2024, 2026], "total": total}), encoding="utf-8")


def _d(**k):
    r = {"co": "GEO", "cycle": 2026, "date": "2026-01-02", "name": "DOE, JANE", "employer": "GEO GROUP", "occupation": "OFFICER", "state": "FL", "usd": 250.0,
         "committee_id": "C1", "committee": "X FOR CONGRESS", "ctype": "H", "party": "R", "bioguide": "", "url": "https://docquery.fec.gov/cgi-bin/fecimg/?1"}
    r.update(k); return r


def test_build_marks_the_company_pac_and_checks_the_total(tmp_path):
    import build_site as b
    _write(tmp_path, [_d(), _d(committee_id="C00382150", committee="GEO PAC", ctype="Q", usd=100.0)], 350.0)
    out = b.donors_section(tmp_path)
    assert [r[8] for r in out["rows"]] == ["H", "O"] and out["total"] == 350.0
    for rows, tot in (([_d()], 999.0), ([_d(url="https://example.com/x")], 250.0)):
        _write(tmp_path, rows, tot)
        try: b.donors_section(tmp_path); assert False, "should refuse"
        except ValueError: pass
