"""todo_report.py lists what needs a person and nothing else."""
import datetime as dt, json
from todo_report import sections, render


def setup(root):
    ref = root / "data" / "reference"; ref.mkdir(parents=True)
    (ref / "ice_local_disputes.csv").write_text("id|date|status_date|final|source_url|status_url\na|2025-01-01|2026-01-01||https://x|\nb|2025-01-01|2026-01-01|Y||\nc|2025-01-01|||https://old-replaced-is-not-here|\nd|2025-01-01|2026-01-01|||\ne|2025-01-01|2026-01-01|||\n", encoding="utf-8")
    (ref / "dispute_dockets.csv").write_text("id|court|docket_number|reviewed_through\na|ilnd|1|\nb|ilnd|2|\nc|ilnd|3|\nd|ilnd|4|\ne|ilnd|5|2026-03-01\n", encoding="utf-8")
    (ref / "dispute_dockets_checked.csv").write_text("id|court|docket_number|cl_id|cl_url|last_filing|entry_date|entry_text|entry_doc|checked\n"
        "a|ilnd|1|5|https://cl/5/|2026-03-01|2026-03-01|ORDER dismissing|https://doc|2026-10-27\n"
        "b|ilnd|2|6|https://cl/6/|2026-03-01|||||\n"
        "c|ilnd|3||||||\n"
        "d|ilnd|4|7|https://cl/7/|2026-03-01|2026-03-01|NOTICE of Withdrawal of Appearance by X||2026-10-27\n"
        "e|ilnd|5|8|https://cl/8/|2026-03-01|2026-03-01|ORDER||2026-10-27\n", encoding="utf-8")
    (ref / "disputes_checked.csv").write_text("url|ok|checked|last_ok\nhttps://x|0|2026-10-27|2026-10-20\nhttps://gone|0|2026-10-27|\nhttps://y|1|2026-10-27|2026-10-27\n", encoding="utf-8")
    (ref / "hotlines_manual.csv").write_text("key|checked|source|note\ndril|2026-10-01|https://ice|n\nciam|2026-10-26|https://gob|n\n", encoding="utf-8")
    (ref / "hotlines_checked.csv").write_text("key|ok|source|checked|last_ok|reason\ndril|0||2026-10-27||no source page could be reached\nffi_out|0||2026-10-27||not found on any source page\norr|1|https://o|2026-10-27|2026-10-27|\n", encoding="utf-8")
    (root / "data" / "health.json").write_text(json.dumps({"stale": ["X (2026-07-20, 99 days)"]}), encoding="utf-8")
    (root / "data" / "refresh_status.json").write_text(json.dumps({"steps": {"tests": "ok", "dockets": "failed"}, "errors": {"dockets": "403"}}), encoding="utf-8")


def test_lists_only_what_needs_a_person(tmp):
    setup(tmp); S = dict(sections(tmp, dt.date(2026, 10, 27)))
    k = {h.split(" (")[0]: v for h, v in S.items()}
    assert k["Refresh steps that failed"] == ["`dockets`: failed — 403"]
    moved = [v for h, v in S.items() if h.startswith("Disputes whose")][0]
    assert len(moved) == 1 and moved[0].startswith("`a`:") and "ORDER dismissing" in moved[0]          # b final, c not found, e already reviewed
    assert [v for h, v in S.items() if h.startswith("Docket filings that look routine")][0][0].startswith("`d`:")
    assert [v for h, v in S.items() if h.startswith("Dispute source links")][0] == ["https://x (failed 2026-10-27, last loaded 2026-10-20)"]
    hand = [v for h, v in S.items() if h.startswith("Help lines checked by hand")][0]
    assert hand == ["`dril`: hides in 4 days — check again on https://ice and update the date in hotlines_manual.csv"]     # ciam has 29 days left
    hid = [v for h, v in S.items() if h.startswith("Help lines hidden")][0]
    assert hid == ["`ffi_out`: not found on any source page"]                                          # dril is covered by the hand check
    assert any(h.startswith("Court dockets not found") for h in S) and any(h.startswith("Sources older") for h in S)


def test_a_quiet_week_says_so(tmp):
    assert "Nothing needs attention" in render([], dt.date(2026, 10, 27))


def test_hidden_organizations_are_listed(tmp):
    ref = tmp / "data" / "reference"; ref.mkdir(parents=True)
    (ref / "family_orgs_checked.csv").write_text("org|ok|reason|checked|last_ok\nA|1||2026-10-28|2026-10-28\nB|0|website now goes to x.com|2026-10-28|\n", encoding="utf-8")
    secs = dict(sections(tmp, dt.date(2026, 10, 28)))
    assert [v for k, v in secs.items() if k.startswith("Organizations hidden")] == [["B: website now goes to x.com"]]
