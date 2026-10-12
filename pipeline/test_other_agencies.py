import json, tempfile
from pathlib import Path
import other_agencies as o
import build_site as b


def row(fy, mon, region, n, title="Title 8", demo="Single Adults"):
    return {"Fiscal Year": fy, "Month (abbv)": mon, "Land Border Region": region, "Title of Authority": title, "Demographic": demo, "Encounter Count": n}


def test_encounters_put_october_in_the_previous_calendar_year_and_count_events():
    rows = [row("2026 (FYTD)", "OCT", "Southwest Land Border", "1,000"), row("2026 (FYTD)", "OCT", "Northern Land Border", "10", demo="UAC"),
            row("2026 (FYTD)", "JAN", "Other", "5", title="Title 42")]
    rows += [row(str(2023 + i // 12), "FEB", "Other", "1") for i in range(0)]
    months = {f"{y}-{m:02d}": [row(str(y if m < 10 else y + 1), ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"][m - 1], "Other", "1")]
              for y in (2022, 2023) for m in range(1, 13)}
    out = o.encounters_by_month(rows + [r for v in months.values() for r in v])
    oct25 = next(x for x in out if x["month"] == "2025-10")
    assert (oct25["fy"], oct25["total"], oct25["southwest"], oct25["northern"], oct25["uac"]) == (2026, 1010, 1000, 10, 10)
    assert next(x for x in out if x["month"] == "2026-01")["title42"] == 5


def test_newest_encounter_file_is_chosen_by_upload_folder():
    links = ["https://www.cbp.gov/sites/default/files/2025-08/nationwide-encounters-fy22-fy25-jul-state_1.csv",
             "https://www.cbp.gov/sites/default/files/2026-09/nationwide-encounters-fy23-fy26-aug-state.csv",
             "https://www.cbp.gov/sites/default/files/2026-09/nationwide-encounters-fy23-fy26-aug-aor.csv"]
    assert o.newest_encounter_csv(links).endswith("2026-09/nationwide-encounters-fy23-fy26-aug-state.csv")


CUSTODY = """<table><tr><th>Sector</th><th>Oct-25</th><th>Nov-25</th><th>Dec-25</th></tr><tr><td>Yuma</td><td>15</td><td>32</td><td>-</td></tr>
<tr><td>Total</td><td>884</td><td>806</td><td>-</td></tr></table>
<table><tr><th>Transfer Destination</th><th>Oct-25</th><th>Nov-25</th></tr><tr><td>Federal (ERO, ORR, Other) 2</td><td>4,643</td><td>4,583</td></tr></table>
<table><tr><th>Detention Capacity</th><th>Oct-25</th></tr><tr><td>% 2</td><td>57 (6.32%)</td></tr></table>"""


def test_custody_tables_read_by_their_row_labels_and_keep_old_months():
    got = o.custody_by_month(CUSTODY)
    assert got["2025-10"] == {"usbp_in_custody": 884, "usbp_to_federal": 4643, "ofo_sw_in_custody": 57} and "2025-12" not in got
    merged = o.merge_months([{"month": "2025-09", "usbp_apprehended": "1", "usbp_in_custody": "2", "usbp_to_federal": "3", "ofo_sw_in_custody": "4"}], got)
    assert [r["month"] for r in merged] == ["2025-09", "2025-10", "2025-11"] and merged[0]["usbp_in_custody"] == "2"


T39 = "<table><tr><th>Year</th><th>Administrative Returns [1]</th><th>Enforcement Returns [2]</th><th>Removals [3]</th><th>Expulsions [4]</th><th>Total removals and returns [5]</th><th>Total enforcement repatriations [6]</th><th>Total repatriations [7]</th></tr>{rows}</table>"


def test_table39_checks_its_parts_against_the_total():
    rows = "".join(f"<tr><td>{y}</td><td>10</td><td>20</td><td>30</td><td>X</td><td>60</td><td>50</td><td>60</td></tr>" for y in range(2010, 2024))
    out = o.table39(T39.format(rows=rows))
    assert out[-1] == {"fy": 2023, "removals": 30, "enforcement_returns": 20, "administrative_returns": 10, "expulsions": 0, "total": 60}
    bad = rows.replace("<td>2023</td><td>10</td><td>20</td><td>30</td><td>X</td><td>60</td><td>50</td><td>60</td>", "<td>2023</td><td>10</td><td>20</td><td>30</td><td>X</td><td>60</td><td>50</td><td>900</td>")
    try: o.table39(T39.format(rows=bad)); assert False
    except ValueError: pass


def test_private_people_are_never_listed():
    kept, n, amt = o.drop_people([("JANE Q PUBLIC", 9e6), ("ACME LLC", 5e6), ("REDACTED DUE TO PII", 1e6), ("DR. SOMEONE & ASSOCIATES, P.A.", 2e6),
                                  ("SMALL SHOP", 1e6), ("JOHN DOE", 3e6), ("BANCO DO BRASIL", 4e6)], {"JOHN DOE"}, {"JANE Q PUBLIC", "ACME LLC", "SMALL SHOP"})
    assert [k for k, _ in kept] == ["ACME LLC", "BANCO DO BRASIL"] and n == 5 and amt == 16e6       # a sole proprietorship without a business word in its name is left out too


def test_money_rows_add_up_and_show_money_taken_back():
    rows = o.money_rows("FEMA", "x", -201.4e6, [("A", 27.5e6), ("B", -150e6), ("C", -78.9e6), ("tiny", 1e4)], True)
    assert [r["recipient"] for r in rows] == ["B", "C", "A", ""] and abs(sum(r["musd"] for r in rows) + 201.4) < 0.05
    try: o.money_rows("X", "y", 100e6, [("A", 10e6)], True); assert False
    except ValueError: pass


def test_orr_sheet_takes_the_year_from_the_description_line():
    rows = [["Released to Sponsors"], ["Total monthly discharges by category, in FY2026."],
            ["CATEGORY", "OCT", "NOV", "DEC", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP"], ["Total\xa0", 106, 16, 57, 42, 119, 228, 255, 262, 146, 153, 164, 133]]
    m, _ = o.orr_sheet(rows)
    assert m["2025-10"] == {"released": 106} and m["2026-09"] == {"released": 133}
    rows = [["Statistic related to unaccompanied alien children in FY2026", "OCT", "NOV", "DEC", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP"],
            ["Average Number of Children in Care", 2244] + [None] * 11, ["Average Length of Care by FY"], ["FY2025", "FY2024"], [117, 30]]
    m, d = o.orr_sheet(rows)
    assert m == {"2025-10": {"in_care": 2244}} and d == {2025: 117, 2024: 30}


def _ref(files):
    d = Path(tempfile.mkdtemp())
    for name, text in files.items(): (d / name).write_text(text, encoding="utf-8")
    return d


def test_gov_section_refuses_text_without_spanish_and_bad_sources():
    site = {"facilities": {"BOPX": {"name": "x"}}, "es": {"Line": "Línea"}}
    ok = "section|text|source|url|kind|as_of\ndod|Line|S|https://a.gov/x|official|2026\n"
    g = b.gov_section(site, _ref({"gov_facts.csv": ok}))
    assert g["facts"]["dod"][0][0] == "Line" and g["bop"] == ["BOPX"]
    for bad in [ok.replace("|Line|", "|No Spanish here|"), ok.replace("official", "blog"), ok.replace("https://a.gov", "http://a.gov"), ok.replace("dod|", "xyz|")]:
        try: b.gov_section(site, _ref({"gov_facts.csv": bad})); assert False, bad
        except ValueError: pass
    st = "name|place|state|run_by|facility_code|status|source|url|kind\nN|P|FL|Line|NOPE|Line|S|https://a.gov|official\n"
    try: b.gov_section(site, _ref({"state_sites.csv": st})); assert False
    except ValueError: pass


def test_gov_money_must_add_up_to_the_source_total():
    meta = {"from": "2023-10-01", "to": "2026-09-30", "read": "2026-10-08", "fys": [2024, 2025, 2026], "programs": {"CBP/holding": {"total_musd": 10.0, "by_fy_musd": {}}}}
    site = {"facilities": {}, "es": {}}
    good = "agency|program|recipient|musd\nCBP|holding|A|7.0\nCBP|holding||3.0\n"
    g = b.gov_section(site, _ref({"other_money.csv": good, "other_money_meta.json": json.dumps(meta)}))
    assert g["money"]["progs"]["CBP/holding"]["rows"] == [["A", 7.0], ["", 3.0]]
    try: b.gov_section(site, _ref({"other_money.csv": good.replace("3.0", "1.0"), "other_money_meta.json": json.dumps(meta)})); assert False
    except ValueError: pass


def test_shared_payees_match_names_and_parents_across_agencies():
    lists = {"ICE": [("Akima Infrastructure Protection, LLC", 444.8), ("B.I. INCORPORATED", 100.0), ("ONLY ICE INC", 50.0)],
             "CBP": [("AKIMA INFRASTRUCTURE PROTECTION LLC", 14.4), ("THE GEO GROUP, INC.", 3.0), ("TINY CO", 0.4)],
             "HHS": [("Tiny Co.", 2.0)]}
    out = b.shared_payees(lists, {"B.I. INCORPORATED": "THE GEO GROUP, INC."})
    names = [r[0] for r in out]
    assert names[0].upper().startswith("AKIMA") and out[0][2] == [("ICE", 444.8), ("CBP", 14.4)] and out[0][3] == 459.2
    assert "THE GEO GROUP, INC." in names                       # ICE paid it through its unit B.I., CBP directly
    assert not any("ONLY ICE" in n for n in names) and not any("TINY" in n.upper() for n in names)    # one payer, or under $1M at one


def test_money_wide_fills_gap_numbers_and_needs_spanish():
    site = {"es": {"Gap with {offers_missing} of {awards_n}.": "x", "Beds": "Camas"}, "money": {"total": 16136, "subs": [["a", "b", 480.3, ""]]}, "gov": {}}
    ref = _ref({"money_gaps.csv": "text|source|url|kind\nGap with {offers_missing} of {awards_n}.|S|https://a.gov|official\n",
                "ice_awards.csv": "award_id|recipient|offers\n1|A|\n2|B|3\n",
                "budget_laws.csv": "law|signed|section|to|musd|what|until|kind|url\nP.L. 1|2025-07-04|1|ICE|45000|Beds|2029-09-30|detention|https://congress.gov/x\n"})
    w = b.money_wide(site, ref)
    assert w["fill"]["{offers_missing}"] == "1" and w["fill"]["{awards_n}"] == "2" and w["laws"][0][4] == 45000
    site["es"].pop("Beds")
    try: b.money_wide(site, ref); assert False
    except ValueError: pass


def test_page_functions_have_unique_names():
    """Two functions with one name: the later one silently replaces the earlier (this once hid a whole card)."""
    import re, collections
    src = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text(encoding="utf-8")
    dup = [n for n, c in collections.Counter(re.findall(r"^\s*function\s+([A-Za-z_$][\w$]*)\s*\(", src, re.M)).items() if c > 1]
    assert not dup, f"functions defined twice: {dup}"
