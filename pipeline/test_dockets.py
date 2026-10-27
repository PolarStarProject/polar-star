"""dockets.py: finds each case once, keeps what it found, stays inside CourtListener's request limits."""
from dockets import run, find_docket, newest_entry

ROWS = [{"id": "a", "court": "ilnd", "docket_number": "1:25-cv-01285"}, {"id": "b", "court": "mad", "docket_number": "1:25-cv-12456"}]


def fake(calls):
    def g(url):
        calls.append(url)
        if "dockets/?" in url and "ilnd" in url: return {"results": [{"id": 11, "absolute_url": "/docket/11/us-v-illinois/", "date_last_filing": "2026-10-20"}]}
        if "dockets/?" in url: return {"results": []}
        if "search/?" in url: return {"results": [{"docket_id": 22, "docketNumber": "25-cv-12456", "docket_absolute_url": "/docket/22/us-v-boston/", "dateLastFiling": "2026-07-23"}]}
        if "docket-entries/" in url and "docket=11" in url: return {"results": [{"date_filed": "2026-10-20", "description": "ORDER  setting argument", "recap_documents": [{"filepath_local": "recap/gov.uscourts.ilnd.1/x.pdf"}]}]}
        if "docket-entries/" in url: return None                     # not allowed for this account
        if "dockets/11/" in url: return {"id": 11, "date_last_filing": "2026-10-25"}
        return None
    return g


def test_first_run_finds_dockets_and_entries():
    calls = []; out, used = run(ROWS, {}, fake(calls), "2026-10-26")
    a, b = out
    assert a["cl_id"] == "11" and a["cl_url"] == "https://www.courtlistener.com/docket/11/us-v-illinois/" and a["last_filing"] == "2026-10-20"
    assert a["entry_date"] == "2026-10-20" and a["entry_text"] == "ORDER setting argument" and a["entry_doc"].startswith("https://storage.courtlistener.com/recap/")
    assert b["cl_id"] == "22" and b["last_filing"] == "2026-07-23" and b["entry_date"] == ""     # found through search; entries not readable
    assert used == len(calls) == 5


def test_next_run_reuses_the_id_and_respects_the_budget():
    prev = {o["id"]: o for o in run(ROWS, {}, fake([]), "2026-10-26")[0]}
    calls = []; out, used = run(ROWS, prev, fake(calls), "2026-11-02", budget=1)
    assert used == 1 and calls == ["https://www.courtlistener.com/api/rest/v4/dockets/11/"]
    assert out[0]["last_filing"] == "2026-10-25" and out[1]["cl_id"] == "22" and out[1]["checked"] == "2026-10-26"   # kept, not lost


def test_a_changed_hand_entry_is_looked_up_again():
    prev = {o["id"]: o for o in run(ROWS, {}, fake([]), "2026-10-26")[0]}
    rows = [{**ROWS[0], "docket_number": "1:25-cv-09999"}, ROWS[1]]
    calls = []; out, _ = run(rows, prev, fake(calls), "2026-11-02")
    assert any("1%3A25-cv-09999" in c for c in calls)
