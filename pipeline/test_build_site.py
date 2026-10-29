import build_site as b

def leg(hexid, date, dep, arr, o, oc, d, dc, d_sure=True, o_sure=True, kind="international"):
    return dict(hex=hexid, date=date, departed_utc=dep, arrived_utc=arr, origin=o, origin_country=oc, dest=d, dest_country=dc,
                origin_certain=o_sure, dest_certain=d_sure, kind=kind, basis="contractor aircraft; day includes AEX (Alexandria, LA)")

def test_lost_signal_is_never_counted_as_a_landing():
    legs = [leg("a", "2026-10-01", "13:00", "15:30", "AEX", "US", "VSA", "MX", d_sure=False),
            leg("a", "2026-10-01", "19:00", "21:30", "VSA", "MX", "AEX", "US", o_sure=False),
            leg("b", "2026-10-01", "10:00", "13:00", "AEX", "US", "GUA", "GT", d_sure=True),
            leg("c", "2026-10-01", "23:00", "01:00", "AEX", "US", "MID", "MX", d_sure=False)]          # never seen coming back
    t = b.trends(legs)
    mx = next(c for c in t["countries"] if c["country"] == "Mexico")
    assert (mx["landed"], mx["lost"], mx["back"]) == (0, 2, 1)
    assert next(c for c in t["countries"] if c["country"] == "Guatemala")["landed"] == 1
    assert t["left"] == 3 and t["returned_within_12h"] == 1 and t["median_hours_before_return"] == 3.5

def test_join_marks_only_facilities_beside_the_airport():
    air = {"AEX": {"latitude_deg": "31.3274", "longitude_deg": "-92.5498"}, "HRL": {"latitude_deg": "26.2285", "longitude_deg": "-97.6544"},
           "AZA": {"latitude_deg": "33.3078", "longitude_deg": "-111.655"}}
    site = {"facilities": {"beside": {"lat": 31.33, "lon": -92.55}, "30km": {"lat": 26.05, "lon": -97.35}, "far": {"lat": 40.0, "lon": -80.0}, "nocoords": {}}}
    st = b.join(site, [leg("a", "2026-10-01", "13:00", "15:30", "AEX", "US", "VSA", "MX", d_sure=False)], air)
    f = site["facilities"]
    assert f["beside"]["near"] == "AEX" and f["30km"]["close"][0] == "HRL" and 25 < f["30km"]["close"][1] < 45
    assert "near" not in f["far"] and "close" not in f["far"] and "near" not in f["nocoords"]
    assert st["AEX"]["flights"] == 1 and st["AEX"]["countries"] == []          # lost signal names no country

def test_287g_joins_on_state_and_county_only():
    site = {"facilities": {"a": {"state": "LA", "county": "Rapides"}, "b": {"state": "TX", "county": "Rapides"}, "c": {"state": "LA"}}}
    rows = [{"state": "LOUISIANA", "agency": "Rapides Parish Sheriff's Office", "county": "Rapides Parish ", "model": "Task Force Model"},
            {"state": "LOUISIANA", "agency": "Statewide agency", "county": "", "model": "Task Force Model"}]
    assert b.attach_287g(site, rows) == 1
    assert site["facilities"]["a"]["agreements"] == {"n": 1, "list": [["Rapides Parish Sheriff's Office", "Task Force Model"]]}
    assert "agreements" not in site["facilities"]["b"] and "agreements" not in site["facilities"]["c"]      # same county name, other state: no match

def test_inspections_match_on_city_and_name_and_skip_doubtful_ones():
    site = {"facilities": {"adl": {"name": "Adelanto ICE Processing Center", "city": "Adelanto", "state": "CA"},
                           "dva": {"name": "Desert View Annex", "city": "Adelanto", "state": "CA"},
                           "x1": {"name": "Clinton County Jail", "city": "Plattsburgh", "state": "NY"}}}
    rows = [{"fiscal_year": "2026", "facility": "Adelanto ICE Processing Center", "city": "Adelanto", "state": "CA", "dates": "Jul. 14-16, 2026", "url": "u1"},
            {"fiscal_year": "2025", "facility": "Adelanto ICE Processing Center", "city": "Adelanto", "state": "CA", "dates": "Sep. 16-18, 2025", "url": "u0"},
            {"fiscal_year": "2026", "facility": "Desert View Annex", "city": "Adelanto", "state": "CA", "dates": "Jun. 9-11, 2026", "url": "u2"},
            {"fiscal_year": "2026", "facility": "Clinton County Correctional Facility", "city": "McElhatten", "state": "PA", "dates": "x", "url": "u3"},
            {"fiscal_year": "2026", "facility": "Some Other Jail", "city": "Adelanto", "state": "CA", "dates": "x", "url": "u4"}]
    assert b.attach_inspections(site, rows) == 3
    f = site["facilities"]
    assert [i[2] for i in f["adl"]["inspections"]] == ["u1", "u0"] and [i[2] for i in f["dva"]["inspections"]] == ["u2"] and "inspections" not in f["x1"]


def test_agreements_index_places_counties_and_carries_contacts():
    rows = [{"state": "GEORGIA", "agency": "Stewart County Sheriff's Department", "county": "Stewart County", "model": "Task Force Model", "signed": "2026-01-02", "source_sheet": "sheets/sheets_20261002_1/x.xlsx"},
            {"state": "GEORGIA", "agency": "Lumpkin Police Department", "county": "Stewart Couny", "model": "Jail Enforcement Model", "signed": "", "source_sheet": "s"},
            {"state": "NEW HAMSPHIRE", "agency": "State Police", "county": "", "model": "Warrant Service Officer", "signed": "", "source_sheet": "s"},
            {"state": "MISSOURI", "agency": "X", "county": "Saint Louis County", "model": "Task Force Model", "signed": "", "source_sheet": "s"}]
    cen = [{"fips": "13259", "county": "Stewart", "state": "Georgia", "lat": "32.07", "lon": "-84.83"},
           {"fips": "29510", "county": "St. Louis", "state": "Missouri", "lat": "38.63", "lon": "-90.24"}, {"fips": "29189", "county": "St. Louis", "state": "Missouri", "lat": "38.64", "lon": "-90.44"}]
    con = [{"state": "GEORGIA", "agency": "Lumpkin Police Department", "phone": "(229) 838-4333", "address": "1 Main St", "checked": "2018-03-06"}]
    a, _ = b.agreements_index(rows, con, cen, [{"state": "CA", "source": "u"}])
    assert a["points"][0][:3] == [32.07, -84.83, 2] and a["off_map"] == 1 and set(a["states"]) == {"GA", "NH", "MO"}
    assert [p for p in a["points"] if p[4] == "MO"][0][1] == -90.44                       # the county, not the city
    lump = [x for x in a["states"]["GA"] if x[0].startswith("Lumpkin")][0]
    assert lump[4:] == ["(229) 838-4333", "1 Main St", "2018", "", ""] and a["phones"] == 1 and a["bans"] == {"CA": "u"}


def test_facility_kind_from_name_and_code():
    k = b.facility_kind
    assert k("DALHOLD", "Dallas FO Hold") == "H" and k("X", "Alexandria Staging Facility") == "S" and k("BOPMIM", "Miami Fed Det Center") == "F"
    assert k("X", "Adelanto ICE Processing Center") == "D" and k("X", "Etowah County Detention Center") == "J" and k("X", "Stewart Detention Center") == "D"
    assert k("X", "Larkin Community Hospital") == "O" and k("X", "Something Else") == "O"


def test_prea_keeps_floor_counts_apart_from_stated_and_rejects_a_count_without_a_basis():
    import build_site as b
    site = {"facilities": {"A": {"name": "A"}, "B": {"name": "B"}}}
    rows = [{"facility_code": "A", "audit_start": "2025-01-01", "allegations": "0", "basis": "stated", "substantiated": "", "report_url": "u"},
            {"facility_code": "A", "audit_start": "2024-01-01", "allegations": "4", "basis": "files reviewed", "substantiated": "", "report_url": "u"},
            {"facility_code": "B", "audit_start": "2024-01-01", "allegations": "", "basis": "not stated", "substantiated": "", "report_url": "u"},
            {"facility_code": "ZZ", "audit_start": "2024-01-01", "allegations": "1", "basis": "stated", "substantiated": "", "report_url": "u"}]
    assert b.attach_prea(site, rows) == 3
    assert site["facilities"]["A"]["prea"] == [["2025-01-01", 0, "S", None, "u", None, None], ["2024-01-01", 4, "F", None, "u", None, None]]
    assert site["facilities"]["B"]["prea"][0][1] is None
    try: b.attach_prea(site, [dict(rows[2], allegations="3")]); assert False
    except ValueError: pass


def test_contract_match_needs_the_city_or_nearly_the_whole_name_and_hand_codes_win():
    import build_site as b
    site = {"facilities": {"JACK": {"name": "Jackson Parish Correctional Center", "city": "Jonesboro", "state": "LA"},
                           "PIKE": {"name": "Pike County Correctional Facility", "city": "Lords Valley", "state": "PA"},
                           "EAZ": {"name": "Eloy Detention Center", "city": "Eloy", "state": "AZ"}}}
    row = lambda **k: dict({"guaranteed_minimum": "", "last_inspection": "", "last_rating": "", "facility_code": ""}, **k)
    out = b.match_contracts(site, [row(name="LAFAYETTE PARISH CORRECTIONAL CENTER", city="LAFAYETTE", state="LA", type="IGSA"),
                                   row(name="PIKE COUNTY JAIL", city="LORDS VALLEY", state="PA", type="IGSA", guaranteed_minimum="285", last_rating="Pass"),
                                   row(name="ELOY FEDERAL CONTRACT FACILITY", city="ELOY", state="AZ", type="DIGSA", facility_code="EAZ")])
    assert [o[7] for o in out] == ["", "PIKE", "EAZ"]            # a similar name in another town is not a match
    assert site["facilities"]["PIKE"]["contract"] == ["IGSA", 285, "", "Pass"] and "contract" not in site["facilities"]["JACK"]
    try: b.match_contracts(site, [row(name="X", city="Y", state="AZ", type="CDF", facility_code="NOPE")]); assert False
    except ValueError: pass


def test_airports_used_counts_only_confirmed_ends():
    import build_site as b
    ap = {"AEX": {"municipality": "Alexandria", "iso_country": "US", "iso_region": "US-LA", "latitude_deg": "31.3274", "longitude_deg": "-92.5498"},
          "GUA": {"municipality": "Guatemala City", "iso_country": "GT", "iso_region": "GT-GU", "latitude_deg": "14.58", "longitude_deg": "-90.53"}}
    legs = [{"origin": "AEX", "origin_certain": True, "dest": "GUA", "dest_certain": False},
            {"origin": "GUA", "origin_certain": True, "dest": "AEX", "dest_certain": True}]
    rows, seen, lost = b.airports_used(legs, ap)
    assert rows == [["AEX", "Alexandria", "US", "LA", 1, 1, 31.33, -92.55], ["GUA", "Guatemala City", "GT", "", 1, 0, 14.58, -90.53]] and (seen, lost) == (3, 1)


def test_money_flow_groups_must_add_to_the_total():
    import build_site as b
    rows = [{"group": "GUARD", "group_total_musd": "70", "recipient": "A", "musd": "50"}, {"group": "GUARD", "group_total_musd": "70", "recipient": "B", "musd": "10"},
            {"group": "OTHER", "group_total_musd": "30", "recipient": "", "musd": ""}]
    m = b.money_flow(rows, 100)
    assert m["groups"] == [["GUARD", 70, [["A", 50], ["B", 10]]], ["OTHER", 30, []]]
    for bad_total in (99,):
        try: b.money_flow(rows, bad_total); assert False
        except ValueError: pass
    try: b.money_flow([dict(rows[0], musd="80"), rows[2]], 100); assert False
    except ValueError: pass


def test_pac_money_must_add_up_and_drops_odd_party_codes():
    rows = [dict(pac="G", cycle_2024="100", cycle_2026="50", recipient="A FOR CONGRESS", type="H", party="REP", state="TX"),
            dict(pac="M", cycle_2024="-20", cycle_2026="0", recipient="B FOR SENATE", type="S", party="FEP", state="AZ")]
    m = b.pac_money(rows, 130)
    assert m["per"] == {"G": [100, 50], "M": [-20, 0]} and m["rows"][1][5] == "" and m["rows"][0][3] == "A FOR CONGRESS"
    try: b.pac_money(rows, 150); assert False
    except ValueError: pass
    try: b.pac_money([dict(rows[0], type="X")], 150); assert False
    except ValueError: pass


def test_lobby_money_firms_must_add_to_outside_total():
    y = [dict(company="X", year="2025", own_usd="10", outside_usd="30")]; f = [dict(company="X", firm="A", usd="10"), dict(company="X", firm="B", usd="20")]
    m = b.lobby_money(y, f, [dict(company="X", target="Senate", filings="3")])
    assert m["X"]["firms"][0] == ["B", 20] and m["X"]["y"] == [["2025", 10, 30]]
    try: b.lobby_money(y, f[:1], []); assert False
    except ValueError: pass


def test_pac_votes_uses_party_on_the_day_and_refuses_wrong_totals():
    import pac_votes as pv
    mk = lambda bg, party, kind="rep", st="CA", **kw: {"id": {"bioguide": bg, "fec": [bg]}, "name": {"first": "A", "last": bg}, "terms": [dict(type=kind, start="2025-01-03", end="2027-01-03", state=st, party=party, **kw)]}
    sw = mk("K1", "Independent", party_affiliations=[dict(start="2025-01-03", end="2026-03-08", party="Republican"), dict(start="2026-03-09", end="2027-01-03", party="Independent")])
    assert pv.vote_of(sw) == ("H", "R", "CA", "Y")
    assert pv.vote_of(mk("M001184", "Republican"))[3] == "N" and pv.vote_of(mk("D1", "Democrat"))[3] == "N"
    assert pv.vote_of(mk("X1", "Democrat", st="DC")) is None
    try: pv.build([sw], [], []); assert False
    except ValueError: pass


def test_287g_renames_and_state_typos_are_not_counted_as_ended():
    import agreements_history as h
    T, W = "Task Force Model", "Warrant Service Officer"
    seen = {("FLORIDA", "ZEPHYRHILLS POLICE DEPARTMENT", T): ("2026-10-02", "2025-04-14", "Zephyrhills Police Department", ""),
            ("FLORIDA", "CITY OF ZEPHYRHILLS POLICE DEPARTMENT", T): ("2025-07-02", "2025-04-14", "City of Zephyrhills Police Department", ""),   # renamed
            ("FLORDIA", "ZEPHYRHILLS POLICE DEPARTMENT", T): ("2025-06-01", "2025-04-14", "Zephyrhills Police Department", ""),                   # state typo
            ("FLORIDA", "ZEPHYRHILLS POLICE DEPARTMENT", W): ("2025-08-01", "2025-03-01", "Zephyrhills Police Department", ""),                   # other model really gone
            ("FLORIDA", "CLAY COUNTY SHERIFF'S OFFICE", T): ("2026-07-21", "2025-02-24", "Clay County Sheriff's Office", "Clay County")}          # gone
    got = h.no_longer_listed(seen, "2026-10-02")
    assert [(r[1], r[3], r[5]) for r in got] == [("Clay County Sheriff's Office", "T", "2026-07-21"), ("Zephyrhills Police Department", "W", "2025-08-01")]


def test_custody_by_month_counts_open_stays_and_drops_the_partial_month():
    import pandas as pd, custody_trend as c
    ts = lambda x: pd.Timestamp(x, tz="UTC") if x else pd.NaT
    s = pd.DataFrame({"i": [ts("2026-01-10"), ts("2026-02-05"), ts("2026-02-20"), ts("2026-03-02")], "o": [ts("2026-02-15"), ts("2026-02-25"), ts(None), ts("2026-04-03")],
                      "r": ["Deported", "Released", "Not released", "Deported"], "c": ["1 Convicted Criminal", "3 Other Immigration Violator", "3 Other Immigration Violator", "2 Pending"]})
    rows = c.by_month(s, "2026-02")
    assert [r[0] for r in rows] == ["2026-02", "2026-03"]          # April is partial and dropped
    assert rows[0] == ["2026-02", 1, 0, 2, 1, 1] and rows[1] == ["2026-03", 1, 100, 1, 0, 0]


def test_source_rows_take_dates_from_the_data_and_flag_stale_ones():
    rows = [dict(what_en="Flights", what_es="Vuelos", publisher="p", url="", key="flights", read="2026-01-01", max_age_days="14"),
            dict(what_en="Votes", what_es="Votos", publisher="p", url="", key="", read="2025-07-03", max_age_days="0"),
            dict(what_en="FEC", what_es="FEC", publisher="p", url="", key="", read="2026-01-01", max_age_days="120")]
    out, stale = b.source_rows(rows, {"flights": "2026-10-03"}, "2026-10-05")
    assert out[0][3] == "2026-10-03" and out[0][6] == 0          # dynamic date wins and is fresh
    assert out[1][6] == 0                                         # max age 0 never goes stale
    assert out[2][6] == 1 and len(stale) == 1 and stale[0].startswith("FEC")


def test_write_layers_makes_valid_geojson_without_unplaced_facilities():
    import json, tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    site = {"facilities": {"A": {"name": "A", "lat": 1.0, "lon": 2.0, "state": "TX"}, "B": {"name": "B", "lat": None, "lon": None}}}
    fl = {"coords": {"AEX": [31.3, -92.5], "HRL": [26.2, -97.7]}, "used": {"rows": [["AEX", "Alexandria", "US", "LA", 3, 2, 31.3, -92.5]]},
          "all": [["2026-10-01", "01:00", "02:00", "AEX", 1, "HRL", 1, 0, "N1"], ["2026-10-02", "01:00", "02:00", "HRL", 1, "AEX", 1, 0, "N1"], ["2026-10-02", "01:00", "02:00", "AEX", 1, "ZZZ", 0, 1, "N1"]],
          "legs": [{"track": [[31.3, -92.5], [26.2, -97.7]], "date": "2026-10-02", "departed_utc": "01:00", "arrived_utc": "02:00", "origin": "AEX", "dest": "HRL", "kind": "domestic", "registration": "N1"}]}
    n = b.write_layers(site, fl, d)
    assert n == {"facilities": 1, "airports": 1, "flight_routes": 1, "flight_tracks_recent": 1}
    r = json.load(open(d / "flight_routes.geojson"))["features"][0]
    assert r["properties"]["flights"] == 2 and r["geometry"]["coordinates"][0] == [-92.5, 31.3]      # GeoJSON is lon, lat


def test_refresh_steps_keep_order_and_reject_unknown_names():
    import refresh_all as r
    names = [n for n, _, _ in r.STEPS]
    assert names.index("tests") < names.index("build") and names[-1] == "build"      # the page is never rebuilt before the tests
    assert r.pick(names, ["build", "tests"], None) == ["tests", "build"]
    assert "flights" not in r.pick(names, None, ["flights"])
    try: r.pick(names, ["test"], None); assert False
    except SystemExit: pass


def test_conduct_rates_use_only_stated_audits_whose_stated_period_is_inside_the_day_counts():
    import build_site as b
    months = [f"{y}-{m:02d}" for y in (2023, 2024) for m in range(1, 13)]
    fac = lambda prea, **k: dict({"name": "x", "prea": prea}, **k)
    P = ["2023-01-10", "2024-01-09"]                             # 365 days
    site = {"contracts": [[0, 0, 0, 0, 0, 0, "Pass", c] for c in "ABCDE"], "operators": {"A": ["GEO", "operates", "u", "high"]},
            "facilities": {"A": fac([["2024-01-10", 10, "S", 2, "u", *P], ["2023-06-01", 99, "S", None, "u", "2022-06-01", "2023-06-01"]], death_reports=[["2023-05-01", "P", "u"], ["2022-01-01", "P", "u"]], watchdog=[1], visits=[["d", "o", "denied", "", ""]]),
                           "B": fac([["2024-01-10", 7, "F", None, "u", *P]]), "C": fac([["2024-01-10", 1, "S", None, "u", *P]]),
                           "D": fac([["2024-06-10", 1, "S", None, "u", "2023-01-01", "2024-12-31"]]), "E": fac([["2024-06-10", 50, "S", None, "u", None, None]])}}
    days = {c: {m: (310 if c == "C" else 3100) for m in months} for c in "ABCDE"}
    c = b.conduct_rates(site, days)
    # A's 2023 audit covers months before the day counts; B is a floor; C averages under 50 held; E states no period
    assert c["audits_used"] == 2 and c["skipped"] == {"no_period": 1, "outside": 1, "small": 1, "changed": 0}
    g = c["ops"]["GEO"]; assert g[:3] == [1, 1, 10] and abs(g[3] - 37200) < 1 and g[4:7] == [1, 2, 1]   # the 2022 death is before the day counts begin
    assert c["sites"][0][:3] == ["A", "2024-01-10", 10] and c["sites"][0][6] == 12 and 98 < c["sites"][0][4] < 102
    d = [r for r in c["sites"] if r[0] == "D"][0]; assert d[6] == 24 and 4.8 < d[4] < 5.1        # 1 allegation over two years at about 100 held
    assert [r[0] for r in c["overlap"]] == ["A"]


def test_person_days_split_a_stint_across_months_and_count_open_stints_to_the_newest_timestamp():
    import pandas as pd, person_days as p
    ts = lambda x: pd.Timestamp(x, tz="UTC")
    d = pd.DataFrame({"code": ["A", "A", "B"], "i": [ts("2024-01-30"), ts("2023-12-01"), ts("2024-02-10")], "o": [ts("2024-02-03"), ts("2024-01-02"), pd.NaT]})
    d.loc[3] = ["B", ts("2024-04-02"), ts("2024-04-03")]         # makes April the newest, partial month
    out = p.person_days(d, first="2024-01")
    assert out == {("A", "2024-01"): 3, ("A", "2024-02"): 2, ("B", "2024-02"): 20, ("B", "2024-03"): 31}


def test_inspection_findings_use_the_reports_own_first_total_and_never_turn_an_unread_report_into_zero():
    import inspection_findings as f
    t = ("ODO found the facility in compliance with 20 of those standards. ODO found three deficiencies in the remaining standard. Since the last inspection in 2024, when ODO found 12 deficiencies in 5 standards, "
         "MEDICAL CARE (MC) staff did not obtain consent (Deficiency MC-93 8F 9 ) . Also (Deficiency MC-27 7F 8). FOOD (Deficiency FS-12 3). again (Deficiency MC-27 7F 8).")
    assert f.parse(t) == (3, 3, "MC:2;FS:1")
    assert f.parse("ODO found 13 deficiencies in 4 standards. (Deficiency EHS-1 6F 7 )") == (1, 13, "EHS:1")
    assert f.parse("ODO found 28 deficiencies in the 8 remaining standards.")[1] == 28 and f.parse("ODO found 4 deficiencies in the 1 remaining standard.")[1] == 4
    assert f.parse("During its last rated inspection, in Fiscal Year (FY) 2024, ODO found 13 deficiencies in 4 standards. INSPECTION FINDINGS ODO found no deficiencies during this inspection.") == (0, None, "")
    assert f.parse("Only the cover page and boilerplate about compliance could be read.") == (None, None, "")
    assert f.parse("ODO found no deficiencies during this inspection.") == (0, None, "")


def test_detention_stats_read_population_and_segregation_from_the_sheets():
    import datetime as dt, detention_stats as d
    H = ["Name", "Address", "City", "State", "Zip", "AOR", "Type Detailed", "Male/Female", "FY26 ALOS", "Level A", "Level B", "Level C", "Level D", "Guaranteed Minimum", "Last Inspection End Date", "Last Final Rating"]
    rows = [["These statistics"], [], H, ["STEWART  DETENTION CENTER", "x", "LUMPKIN", "GA", 1, "ATL", "DIGSA", "Male", 44.8, 1150.2, 315.0, 237.8, 207.5, 1600, dt.datetime(2026, 5, 7), "Pass"], ["Total", "", "", "", None]]
    assert d.parse_facilities(rows) == [{"name": "STEWART DETENTION CENTER", "city": "LUMPKIN", "state": "GA", "type": "DIGSA", "adp": 1910.5, "gm": "1600", "insp": "2026-05-07", "rating": "Pass"}]
    seg = d.parse_segregation([["U.S. Immigration"], ["June 2026\n"], ["Facilities", "Placement Count"], ["SOUTH TEXAS", 110], ["Grand Total", 864], ["May 2026", None], ["A  B", 3.0]])
    assert seg == [("2026-06", "SOUTH TEXAS", 110), ("2026-05", "A B", 3)]
    books = d.find_workbooks('<a href="/doclib/detention/FY26_detentionStats07202026.xlsx"><a href="/doclib/detention/FY22-detentionStats.xlsx"><a href="/doclib/detention/Over72HourFacilities.xlsx">')
    assert sorted(books) == ["FY22", "FY26"] and books["FY22"].startswith("https://www.ice.gov/")


def test_segregation_counts_days_in_months_with_no_placements_and_leaves_unknown_names_out():
    import build_site as b
    site = {"facilities": {"A": {"name": "Alpha Detention Center", "state": "TX"}, "B": {"name": "Beta County Jail", "state": "TX"}}, "contracts": [[0] * 7 + ["A"]], "operators": {"A": ["GEO", "operates", "u", "high"]}}
    rows = [{"month": "2025-01", "name": "ALPHA DETENTION CENTER", "placements": "10"}, {"month": "2025-03", "name": "ALPHA DET CTR", "placements": "5"},
            {"month": "2025-01", "name": "SOMEWHERE ELSE", "placements": "7"}, {"month": "2025-02", "name": "BETA COUNTY JAIL", "placements": "1"}]
    days = {"A": {"2025-01": 3100, "2025-02": 2800, "2025-03": 3100, "2024-12": 9999}, "B": {"2025-02": 280}}
    g = b.segregation_rates(site, rows, days, min_avg=0)
    assert g["total"] == 23 and g["unmatched"] == 7 and g["ops"] == {"GEO": [15, 9000, 1], "OTH": [1, 280, 1]}     # February's days count for A though it had no placements
    assert g["months"] == [["2025-01", 17], ["2025-02", 1], ["2025-03", 5]]


def test_audit_rates_use_yearly_averages_before_the_day_counts_and_skip_a_year_ice_does_not_list():
    import build_site as b
    months = [f"2023-{m:02d}" for m in range(1, 13)]
    site = {"contracts": [[0] * 7 + [c] for c in "AB"], "operators": {},
            "facilities": {c: {"name": c, "prea": [["2023-07-10", 6, "S", None, "u", "2022-07-01", "2023-06-30"]]} for c in "AB"}}
    days = {c: {m: 3000 for m in months} for c in "AB"}
    c = b.conduct_rates(site, days, history={"A": {"FY22": 100.0}})                 # July-December 2022: A has FY22 only, so October-December (FY23) are missing
    assert c["audits_used"] == 0 and c["skipped"]["outside"] == 2
    c = b.conduct_rates(site, days, history={"A": {"FY22": 100.0, "FY23": 100.0}})
    assert c["audits_used"] == 1 and c["sites"][0][0] == "A" and c["sites"][0][7] is True and c["sites"][0][6] == 12
    assert abs(c["ops"]["PUB"][3] - (100 * 184 + 3000 * 6)) < 1                    # 184 days July-December at 100 a day, then six counted months


def test_held_profile_hides_small_groups_and_counts_time_across_the_whole_stay():
    import pandas as pd, held_profile as h
    ts = lambda x: pd.Timestamp(x, tz="UTC")
    rows = [["A", "Male", "MEXICO", 30, ts("2025-01-01"), ts("2026-01-01"), pd.NaT]] * 20 + [["A", "Female", "CUBA", 40, ts("2026-01-20"), ts("2026-01-20"), pd.NaT]] * 12 \
         + [["A", "Female", "PERU", 17, ts("2026-01-25"), ts("2026-01-25"), pd.NaT]] * 3 + [["B", "Male", "MEXICO", 30, ts("2026-01-01"), ts("2026-01-01"), pd.NaT]] * 5 \
         + [["A", "Male", "MEXICO", 30, ts("2025-01-01"), ts("2025-01-01"), ts("2026-02-01")]]
    out = h.build(pd.DataFrame(rows, columns=["code", "gender", "country", "age", "stay_in", "stint_in", "out"]))
    a = out["facilities"]["A"]
    assert out["as_of"] == "2026-02-01" and "B" not in out["facilities"] and a["n"] == 35
    assert a["over365"] == 57 and a["women"] == 43                  # the 20 arrived at A in January 2026 but their stay began a year earlier
    assert a["countries"] == [["Mexico", 57], ["Cuba", 34]] and ["under 18", 9] not in a["ages"] and all(x[0] != "under 18" for x in a["ages"])   # 3 people: not shown


def test_prea_collector_reads_titles_and_periods_but_never_a_count():
    import prea_audits as p
    assert p.parse_title("Florence Service Processing Center — Aug. 12-14, 2025") == ("Florence Service Processing Center", "2025-08-12")
    assert p.parse_title("Baker County Sherriff’s Office – Dec. 2-4, 2025")[1] == "2025-12-02" and p.parse_title("Alexandria Staging - Oct. 31-Nov. 2, 2023")[1] == "2023-10-31"
    assert p.parse_title("Some Report")[1] == ""
    html = '<li><a href="https://www.ice.gov/doclib/foia/prea_audit/FlorenceSPC_Aug12-14_2025.pdf">Florence <b>SPC</b> — Aug. 12-14, 2025</a></li><a href="/doclib/other/x.pdf">x</a>'
    assert p.parse_listing(html) == [("Florence SPC — Aug. 12-14, 2025", "https://www.ice.gov/doclib/foia/prea_audit/FlorenceSPC_Aug12-14_2025.pdf")]
    t = "The audit is the third DHS PREA audit and includes a review period between July 18, 2023, and July 18, 2024. There were five allegations of sexual abuse reported during the audit period."
    ps, pe, pb, ev = p.parse_report(t, "2024-07-16")
    assert (ps, pe, pb) == ("2023-07-18", "2024-07-18", "stated") and "five allegations" in ev
    assert p.parse_report("The audit period is from October 30, 2024, to October 30, 2026.", "2026-01-06")[:2] == ("2024-10-30", "2026-01-08")
    assert p.parse_report("A corrective action period which began on January 11, 2024, through July 10, 2024.", "2023-11-14")[:3] == ("", "", "not stated")


def test_usaspending_window_groups_and_subcontract_totals():
    import datetime as dt, money_usaspending as m
    assert m.window(dt.date(2026, 10, 5)) == ("2023-10-01", "2026-09-30", [2024, 2025, 2026]) and m.window(dt.date(2026, 9, 30))[1] == "2025-09-30"
    rows = m.flow_rows(1000e6, [("GUARD", ["S206"], 600e6, [("A", 400e6), ("B", 8e6), ("C", 20e6)]), ("AIR", ["V211"], 100e6, [])])
    assert [(r["group"], r["group_total_musd"], r["recipient"], r["musd"]) for r in rows] == [("GUARD", 600, "A", 400), ("GUARD", 600, "C", 20), ("AIR", 100, "", ""), ("OTHER", 300, "", "")]
    try: m.flow_rows(100e6, [("GUARD", ["S206"], 600e6, [])]); assert False
    except ValueError: pass
    recs = [{"Prime Recipient Name": "P", "Sub-Awardee Name": "S", "Sub-Award Amount": 1500000.0, "Sub-Award Description": "GUARD  SERVICES"}, {"Prime Recipient Name": "P", "Sub-Awardee Name": "S", "Sub-Award Amount": 500000, "Sub-Award Description": "x"},
            {"Prime Recipient Name": "P", "Sub-Awardee Name": "T", "Sub-Award Amount": 250000, "Sub-Award Description": "food"}]
    assert m.sub_rows(recs, {("P", "T"): "Meals"}) == [{"prime": "P", "sub": "S", "musd": "2.000", "for": "Guard services", "n": 2}, {"prime": "P", "sub": "T", "musd": "0.250", "for": "Meals", "n": 1}]


def test_court_outcomes_count_each_case_once_inside_the_window_and_by_location():
    import datetime as dt, pandas as pd, court_outcomes as c
    row = lambda **k: dict({"custody_code": "D", "represented": False, "case_outcome": None, "hearing_location_code_last": None, "hearing_location_last": None, "ij_completion_date_last": None,
                            "bond_hearing_location_code_last": None, "bond_hearing_location_last": None, "bond_completion_date_last": None, "bond_decision_last": None}, **k)
    d = pd.DataFrame([row(case_outcome="Remove", hearing_location_code_last="A", hearing_location_last="Alpha", ij_completion_date_last=dt.date(2026, 8, 1), represented=True),
                      row(case_outcome="Relief Granted", hearing_location_code_last="A", hearing_location_last="Alpha", ij_completion_date_last=dt.date(2026, 9, 1)),
                      row(case_outcome="Remove", hearing_location_code_last="A", hearing_location_last="Alpha", ij_completion_date_last=dt.date(2026, 7, 1), custody_code="N"),      # never detained: not counted
                      row(case_outcome="Remove", hearing_location_code_last="A", hearing_location_last="Alpha", ij_completion_date_last=dt.date(2023, 1, 1)),                         # before the window
                      row(case_outcome="Remove", hearing_location_code_last="A", hearing_location_last="Alpha", ij_completion_date_last=dt.date(2031, 1, 1)),                         # a date in the future: ignored
                      row(bond_hearing_location_code_last="B", bond_hearing_location_last="Beta", bond_completion_date_last=dt.date(2026, 3, 1), bond_decision_last="Bond Denied-No Jurisdiction"),
                      row(bond_hearing_location_code_last="B", bond_hearing_location_last="Beta", bond_completion_date_last=dt.date(2026, 3, 2), bond_decision_last="Bond Granted-Amount Decreased")])
    rows, start, end = c.summarise(d, dt.date(2026, 10, 5))
    by = {r["code"]: r for r in rows}
    assert (start, end) == ("2024-09-02", "2026-09-01")
    assert (by["A"]["cases_n"], by["A"]["removed"], by["A"]["relief"], by["A"]["represented"]) == (2, 1, 1, 1)
    assert (by["B"]["bond_n"], by["B"]["granted"], by["B"]["no_jurisdiction"], by["B"]["denied"]) == (2, 1, 1, 0)


def test_crcl_memo_names_give_a_date_and_a_kind_and_other_documents_are_skipped():
    import crcl_memos as c
    r = c.parse({"id": 25866590, "slug": "24-0208-crcl-winn-correctional-center-close-summary-508", "title": "Summary of CRCL Recommendation Memorandum: Winn Correctional Center", "canonical_url": "https://www.documentcloud.org/documents/25866590-x/"})
    assert (r["published"], r["kind"], r["slug"]) == ("2024-02-08", "close summary", "winn-correctional-center-close-summary") and r["url"].endswith("25866590-x/")
    assert c.parse({"id": 1, "slug": "22-1108-crcl-rec-memo-to-ice-moshannon-valley-processing-center-redacted-foia-508", "title": ""})["kind"] == "recommendation memo"
    assert c.parse({"id": 2, "slug": "2021-crli-00001-april-2023-records-_part5", "title": "x"}) is None and c.parse({"id": 3, "slug": "24-1399-crcl-x", "title": "x"}) is None


def test_lobbying_takes_the_latest_version_per_quarter_and_names_a_personal_registrant():
    import money_lobbying as m
    F = lambda typ, reg, rid, client, period, posted, income=None, expenses=None, ents=(): {"filing_type": typ, "registrant": {"id": rid, "name": reg}, "client": {"id": 9, "name": client}, "filing_period": period,
                                                                                                 "dt_posted": posted, "income": income, "expenses": expenses, "lobbying_activities": [{"government_entities": [{"name": e} for e in ents]}]}
    fl = [F("Q1", "THE GEO GROUP, INC.", 1, "THE GEO GROUP, INC.", "first_quarter", "2025-04-20", expenses="300000.00", ents=("SENATE", "SENATE")),
          F("Q1", "NAVIGATORS GLOBAL LLC (FORMERLY DC NAVIGATORS, LLC)", 2, "THE GEO GROUP, INC.", "first_quarter", "2025-04-16", income="100000.00", ents=("HOUSE OF REPRESENTATIVES",)),
          F("1A", "NAVIGATORS GLOBAL LLC (FORMERLY DC NAVIGATORS, LLC)", 2, "THE GEO GROUP, INC.", "first_quarter", "2025-05-01", income="140000.00", ents=("HOUSE OF REPRESENTATIVES",)),      # amended: replaces the first
          F("Q2", "JANE Q. PUBLIC", 3, "THE GEO GROUP INC.", "second_quarter", "2025-07-16", income="15000.00"),
          F("RR", "NEW FIRM LLC", 4, "THE GEO GROUP, INC.", "second_quarter", "2025-06-01"),                                                                                                 # a registration: no amount
          F("Q1", "TIBER CREEK GROUP", 5, "GEORGIALINK PUBLIC AFFAIRS GROUP, LLC", "first_quarter", "2025-04-16", income="50000.00")]                                                       # not the company
    own, out, firms, targets, last = m.summarise(fl, m.COMPANIES["GEO"][1], {"NAVIGATORS GLOBAL LLC": "Navigators Global LLC"})
    assert (own, out, last) == (300000, 155000, "Q2") and firms == {"Navigators Global LLC": 140000, "Jane Q. Public": 15000}      # a lobbyist paid by the company is on the trail: named as filed
    assert targets == {"Senate": 1, "House of Representatives": 1} and sum(firms.values()) == out


def test_fec_cycles_and_rows_and_sec_newer_filings():
    import datetime as dt, money_fec as f, sec_watch as s
    assert f.cycles(dt.date(2026, 10, 5)) == [2024, 2026] and f.cycles(dt.date(2027, 1, 5)) == [2026, 2028]
    rows, total = f.merge({("G", "C1"): {"name": "NRCC", 2024: 30000.0, 2026: 15000.0, "n": 6}, ("G", "C2"): {"name": "X|Y PAC", 2026: -500.0}, ("C", "C3"): {"name": "ZERO", 2024: 0}}, {"C1": ("P", "REP", "DC")}, [2024, 2026])
    assert total == 44500 and rows[0] == {"pac": "G", "cycle_2024": 30000, "cycle_2026": 15000, "recipient": "NRCC", "type": "P", "party": "REP", "state": "DC", "gifts": 6, "recipient_id": "C1"} and rows[1]["recipient"] == "X/Y PAC" and len(rows) == 2
    recent = {"form": ["8-K", "10-K", "DEF 14A", "10-K"], "filingDate": ["2027-03-01", "2027-02-24", "2026-03-19", "2026-02-25"], "accessionNumber": ["a", "b", "c", "d"], "primaryDocument": ["w", "x", "y", "z"]}
    assert s.newer(recent, {"10-K": "2026-02-25", "DEF 14A": "2026-03-19"}) == [{"form": "10-K", "filed": "2027-02-24", "accession": "b", "document": "x"}]


def test_records_go_to_whoever_ran_the_site_on_that_date():
    import build_site as b
    months = [f"{y}-{m:02d}" for y in (2023, 2024) for m in range(1, 13)]
    site = {"contracts": [[0, 0, 0, 0, 0, 0, "Pass", "A"]], "operators": {"A": ["NEW", "operates", "u", "high"]},
            "facilities": {"A": {"name": "x", "death_reports": [["2023-06-30", "P", "u"], ["2023-07-01", "P", "u"]],
                                 "prea": [["2024-07-01", 4, "S", None, "u", "2023-07-01", "2024-06-30"], ["2023-07-10", 9, "S", None, "u", "2023-01-01", "2023-12-31"]]},
                           "Z": {"name": "not on the list"}}}
    assert b.load_operator_history(site, [{"facility_code": "A", "operator": "OLD", "from": "", "to": "2023-06-30", "url": "http://s", "sure": "high"}]) == 1
    at = b.operator_on(site)
    assert at("A", "2023-06-30") == "OLD" and at("A", "2023-07-01") == "NEW" and at("A") == "NEW" and at("A", "2019-01-01") == "OLD"
    assert at("A", "2023-06") == "OLD" and at("A", "2023-07") == "NEW" and at("Z", "2023-01-01") == "OTH"      # a month is judged by its 15th
    c = b.conduct_rates(site, {"A": {m: 3100 for m in months}})
    old, new = c["ops"]["OLD"], c["ops"]["NEW"]
    assert old[0] == 0 and new[0] == 1 and old[6] == 1 and new[6] == 1 and old[7] == 6 * 3100 and new[7] == 18 * 3100
    assert new[1:3] == [1, 4] and old[1] == 0 and c["skipped"]["changed"] == 1      # the audit that spans the change is in neither rate
    assert sorted(r[8] for r in c["sites"]) == ["CHG", "NEW"] and c["audits_used"] == 2
    s = b.segregation_rates(dict(site, facilities={"A": {"name": "Alpha Jail"}}), [{"month": "2023-03", "name": "Alpha Jail", "placements": "5"}, {"month": "2024-03", "name": "Alpha Jail", "placements": "7"}], {"A": {m: 3100 for m in months}})
    assert s["ops"]["OLD"][0] == 5 and s["ops"]["NEW"][0] == 7 and s["ops"]["OLD"][1] + s["ops"]["NEW"][1] == 2 * 3100
    crt = b.court_summary(site, [dict({"code": "L", "name": "x"}, **{k: "50" for k in ["bond_n", "granted", "denied", "no_jurisdiction", "withdrawn", "cases_n", "removed", "voluntary", "relief", "ended_other", "represented"]})], {"L": "A"}, {"from": "2023-01-01", "to": "2024-12-31"})
    assert list(crt["ops"]) == ["CHG"]                             # one total for the whole period cannot be split between two operators


def test_operator_history_refuses_bad_rows():
    import build_site as b
    site = {"facilities": {"A": {}}, "operators": {"A": ["NEW", "", "", ""]}}
    row = lambda **k: dict({"facility_code": "A", "operator": "OLD", "from": "", "to": "2023-06-30", "url": "http://s", "sure": "high"}, **k)
    for bad in ([row(facility_code="Q")], [row(operator="NEW")], [row(to="June 2023")], [row(url="")], [row(**{"from": "2024-01-01"})],
                [row(), row(operator="MID", **{"from": "2023-06-30", "to": "2023-12-31"})]):
        try: b.load_operator_history(site, bad); assert False, bad
        except (ValueError, KeyError): pass


def test_inspection_dates_as_ice_writes_them():
    import build_site as b
    assert b._insp_date("Dec. 10-12, 2024") == "2024-12-10" and b._insp_date("Sept. 30-Oct. 2, 2025") == "2025-09-30"
    assert b._insp_date("Dec. 30-Jan. 2, 2025") == "2024-12-30" and b._insp_date("Jun, 23-25, 2026") == "2026-06-23"
    assert b._insp_date("May 27 - Jun. 26, 26") == "2026-05-27" and b._insp_date("soon") is None


def test_built_page_and_its_flight_file_carry_the_same_stamp():
    import re, pathlib
    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    if not (site / "index.html").exists() or not (site / "flights-data.js").exists(): return      # nothing built yet
    page = re.search(r'"more":"([0-9a-f]{12})"', (site / "index.html").read_text(encoding="utf-8"))
    more = (site / "flights-data.js").read_text(encoding="utf-8")[:60]
    assert page and f'"v":"{page.group(1)}"' in more          # a page beside a flight file from another build would show no flights


def test_built_page_and_its_second_data_file_carry_the_same_stamp():
    import re, pathlib
    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    if not (site / "index.html").exists() or not (site / "more-data.js").exists(): return        # nothing built yet
    page = re.search(r'"lazy":"([0-9a-f]{12})"', (site / "index.html").read_text(encoding="utf-8"))
    assert page and f'"v":"{page.group(1)}"' in (site / "more-data.js").read_text(encoding="utf-8")[:60]     # else the agreements list and contract records would not load


def test_built_page_and_its_person_file_carry_the_same_stamp():
    import re, pathlib
    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    if not (site / "index.html").exists() or not (site / "persons-data.js").exists(): return     # nothing built yet
    page = re.search(r'"plazy":"([0-9a-f]{12})"', (site / "index.html").read_text(encoding="utf-8"))
    assert page and f'"v":"{page.group(1)}"' in (site / "persons-data.js").read_text(encoding="utf-8")[:60]   # else no name would open its card


def test_everything_else_is_listed_by_code_and_always_adds_up():
    import money_usaspending as m
    codes = [("S206", "GUARD", 9e9), ("R425", "ENGINEERING  SUPPORT", 400e6), ("Z1AA", "REPAIR OF OFFICES", 30e6), ("9999", "TINY", 1e6), ("8888", "CANCELLED", -6e6), (None, "x", 5)]
    rest, rows = m.other_codes(codes, 425)
    assert rest == ["R425", "Z1AA", "9999", "8888"]                              # S206 belongs to a named group
    assert [(r["code"], r["musd"]) for r in rows] == [("R425", 400), ("Z1AA", 30), ("", -5)] and rows[-1]["n_codes"] == 2
    assert rows[0]["name"] == "Engineering support" and sum(r["musd"] for r in rows) == 425
    flow = m.flow_rows(10e9, [("GUARD", ["S206"], 9e9, [("A", 5e9)])], [("B", 300e6), ("C", 1e6)])
    o = [r for r in flow if r["group"] == "OTHER"]; assert [(r["recipient"], r["musd"], r["group_total_musd"]) for r in o] == [("B", 300, 1000)]


def test_bed_revenue_spreads_the_stated_yearly_figure_over_the_companys_own_beds_and_rejects_bad_rows():
    import build_site as b
    site = {"facilities": {"A": {}, "B": {}}}
    row = lambda **k: {**{"facility_code": "A", "company": "CC", "annual_musd": "180", "annual_max_musd": "", "at_least": "0", "beds": "2400", "payment": "fixed", "doc": "annual", "doc_date": "2025", "url": "https://x/y", "sold": "", "sold_url": ""}, **k}
    r = b.bed_revenue(site, [row(), row(facility_code="B", annual_musd="70", at_least="1", beds="1800", payment="")])
    assert r["A"][:5] == [180.0, 0, 2400, 205, "fixed"] and r["B"][:4] == [70.0, 1, 1800, 107]     # 180e6 / 2400 / 365 = 205.5 rounds to 205; dollars, per bed, per day
    assert b.bed_revenue(site, [row(annual_musd="30", annual_max_musd="35", beds="600")])["A"][11:] == [35.0, 160] and b.bed_revenue(site, [row()])["A"][11:] == [None, None]     # a stated range keeps both ends
    for bad in (row(annual_max_musd="100"), row(annual_max_musd="200", at_least="1"), row(facility_code="Z"), row(annual_musd="180000000"), row(beds="0"), row(url="x"), row(payment="perdiem"), row(sold="2026-08-04")):
        try: b.bed_revenue(site, [bad]); raise AssertionError(f"accepted a bad row: {bad}")
        except ValueError: pass
    try: b.bed_revenue(site, [row(), row()]); raise AssertionError("accepted a duplicate")
    except ValueError: pass


def test_awards_are_grouped_by_recipient_in_millions_and_a_mismatched_file_is_rejected():
    import build_site as b, money_awards as m
    src = [{"generated_internal_id": "U1", "Recipient Name": "Acme, Inc.", "Award Amount": 2_540_000.4, "Award ID": "70CDCR1", "Start Date": "2019-03-01", "End Date": "2027-01-01", "Description": "DETENTION  | SERVICES", "Contract Award Type": "DELIVERY ORDER"},
           {"generated_internal_id": "U1", "Recipient Name": "Acme, Inc.", "Award Amount": 2_000_000, "Award ID": "70CDCR1"}, {"generated_internal_id": "U2", "Recipient Name": "Acme, Inc.", "Award Amount": 999_999},
           {"generated_internal_id": "U3", "Recipient Name": "REDACTED DUE TO PII", "Award Amount": 5e6}, {"generated_internal_id": "", "Recipient Name": "B", "Award Amount": 5e6}, {"generated_internal_id": "U4", "Recipient Name": "Beta LLC", "Award Amount": 9e6}]
    rows = m.clean_rows(src)
    assert [(r["uid"], r["amount_usd"]) for r in rows] == [("U4", 9000000), ("U1", 2540000)] and rows[1]["what"] == "DETENTION / SERVICES"     # under the floor, masked, no id: dropped; duplicate keeps the larger
    tx = [{"action_date": "2023-09-30", "federal_action_obligation": 5e6}, {"action_date": "2023-10-01", "federal_action_obligation": 2e6}, {"action_date": "2026-09-30T00:00", "federal_action_obligation": -500000.4}, {"action_date": "2026-10-01", "federal_action_obligation": 9e6}, {"action_date": None, "federal_action_obligation": 1}]
    assert m.window_sum(tx, "2023-10-01", "2026-09-30") == 1500000                                              # both end dates count; outside and undated do not; money taken back subtracts
    assert [m.offers_int(x) for x in ("1", " 12 ", None, "", "many", "-3", 0)] == [1, 12, "", "", "", "", 0]               # not recorded stays blank, never 0
    G = {"competed": ["A", "CDO"], "not_competed": ["C", "NDO"]}; assert [m.competed_code(x, G) for x in ("A", "NDO", None, "ZZ")] == ["C", "N", "", ""]
    meta = {"from": "a", "to": "b", "read": "c", "floor_usd": 1000000, "awards": 2, "recipients": 2}
    A = b.awards_by_recipient([{k: str(v) for k, v in r.items()} for r in rows], meta)
    assert A["by"]["ACME, INC."] == [["70CDCR1", 2.5, "2019-03-01", "2027-01-01", "DELIVERY ORDER", "DETENTION / SERVICES", "U1", None, "", None, "", ""]]                 # whole dollars in the file, millions on the page
    try: b.awards_by_recipient([{k: str(v) for k, v in r.items()} for r in rows], {**meta, "awards": 3}); raise AssertionError("accepted a file that does not match its meta")
    except ValueError: pass


def test_changes_are_recorded_once_a_day_and_a_missing_count_is_not_a_fall_to_zero():
    import build_site as b
    assert b.headline({"custody": [["2026-06", 5, 0, 0, 0, 0], ["2026-07", 7, 0, 0, 0, 0]], "deaths": {"years": [["2026", 3], ["2025", 2]]}}) == {"held": 7, "deaths": 5}       # no agreements file: no key, not 0
    h, c = b.record_changes([], "2026-10-01", {"held": 7, "deaths": 5}); assert c is None and len(h) == 1
    h, c = b.record_changes(h, "2026-10-08", {"held": 9, "deaths": 5, "refusals": 4}); assert c == {"date": "2026-10-08", "since": "2026-10-01", "rows": [["held", 7, 9]]}   # new key has no "before": not listed
    h, c = b.record_changes(h, "2026-10-08", {"held": 10, "deaths": 5, "refusals": 4}); assert len(h) == 2 and c["rows"] == [["held", 7, 10]]                             # same day again replaces the day's entry
    h, c = b.record_changes(h, "2026-10-09", {"held": 10, "deaths": 5, "refusals": 4}); assert len(h) == 2 and c["date"] == "2026-10-08"                                 # nothing changed: nothing added


def test_guard_contracts_are_placed_only_where_one_listed_facility_is_in_the_city():
    import build_site as b
    site = {"contracts": [[0, 0, 0, "CDF", 1, 0, "", "A"], [0, 0, 0, "CDF", 1, 0, "", "B"], [0, 0, 0, "CDF", 1, 0, "", "C"], [0, 0, 0, "CDF", 1, 0, "", ""]],
            "facilities": {"A": {"city": "Tacoma", "state": "WA"}, "B": {"city": "Adelanto", "state": "CA"}, "C": {"city": "Adelanto", "state": "CA"}, "X": {"city": "Mesa", "state": "AZ"}}}
    row = lambda **k: {**{"recipient": "ACME", "award_id": "1", "amount_usd": "9000000", "window_usd": "2500000", "start": "s", "end": "e", "competed": "N", "psc": "S206", "pop_city": "TACOMA", "pop_state": "WA", "uid": "U"}, **k}
    out, n = b.facility_awards(site, [row(), row(uid="U2", window_usd="", amount_usd="4000000"), row(pop_city="ADELANTO", pop_state="CA"), row(pop_city="MESA", pop_state="AZ"), row(psc="V211"), row(pop_city="TACOMA", pop_state="OR")])
    assert n == {"guard": 5, "placed": 2, "shared": 1, "nowhere": 2}                       # two listed sites in Adelanto: not placed; Mesa's site is not on ICE's list; flights code ignored; same city name in another state is nowhere
    assert out == {"A": [["ACME", "1", 9.0, 2.5, "s", "e", "N", "U2"], ["ACME", "1", 9.0, 2.5, "s", "e", "N", "U"]][::-1][:0] or out["A"]} and [a[2:4] for a in out["A"]] == [[4.0, None], [9.0, 2.5]]     # whole dollars in, millions out; an unread window amount stays None, sorted by its lifetime amount


def test_a_flight_between_two_foreign_airports_is_not_counted_as_leaving_or_entering_the_us():
    import build_site as b
    assert [b.leg_kind(*x) for x in (("US", "US"), ("US", "MX"), ("GT", "US"), ("MX", "MX"), ("PE", "PE"), ("MX", "GT"))] == ["domestic", "international", "international", "abroad", "abroad", "abroad"]


def test_facility_name_slips_are_corrected_for_display():
    import build_site as b
    assert b.fix_name("Bakerfield Corecivic Annex (Nwipc), Mcfarland") == "Bakersfield CoreCivic Annex (NWIPC), McFarland" and b.fix_name("Laredo Processing Center") == "Laredo Processing Center"


def test_bed_use_compares_the_guarantee_with_ices_own_average_for_the_newest_year():
    import build_site as b
    site = {"contracts": [[0, 0, 0, "CDF", 1000, 0, "", "A"], [0, 0, 0, "CDF", 500, 0, "", "B"], [0, 0, 0, "IGSA", None, 0, "", "C"], [0, 0, 0, "CDF", 300, 0, "", "D"], [0, 0, 0, "CDF", 50, 0, "", ""]]}
    u = b.bed_use(site, {"A": {"FY25": 990, "FY26": 400.4}, "B": {"FY26": 650}, "C": {"FY26": 10}, "D": {"FY25": 100}})
    assert u["fy"] == "FY26" and u["n"] == 2 and u["beds"] == 1500            # C has no guarantee; D has no figure for the newest year: neither is counted as empty
    assert u["below"] == [["A", 1000, 400, 600]] and u["empty"] == 600        # B is over its guarantee: nothing empty, and its surplus does not offset A
    assert b.bed_use(site, {}) is None


def test_fec_committee_detail_reads_leadership_funds_and_joint_fundraisers():
    import money_fec as m
    assert m.detail({"designation": "D", "sponsor_candidate_ids": ["H1", None], "jfc_committee": None}) == ("D", ["H1"], [])
    assert m.detail({"designation": "J", "jfc_committee": [{"joint_committee_name": "B  PAC"}, {"joint_committee_name": "A FOR SENATE"}, {"joint_committee_name": None}]}) == ("J", [], ["A FOR SENATE", "B PAC"])
    assert m.detail({"designation": "U", "leadership_pac": True}) == ("D", [], []) and m.detail({"designation": "U"}) == ("", [], [])


def test_page_text_keys_are_not_defined_twice_and_the_script_parses():
    import re, collections, pathlib, shutil, subprocess, tempfile
    root = pathlib.Path(__file__).resolve().parent.parent
    lines = (root / "site" / "template.html").read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("const T = {")); cur, blocks = None, {}
    for l in lines[start:]:
        m = re.match(r"^\s{0,2}(en|es):\s*\{", l)
        if m: cur = m.group(1); blocks[cur] = []
        if cur: blocks[cur].append(l)
        if l.startswith("};"): break
    nested = {"left_voluntarily", "other_agency", "no_reason", "transfer_unrecorded"}          # keys of small maps inside a text entry, repeated on purpose
    for lang, b in blocks.items():
        c = collections.Counter(re.findall(r'(?:^|[\s,{])([a-z][a-z0-9]{1,5}_[a-z0-9_]+):(?=[\s"`(\[{a-zA-Z])', "\n".join(b)))
        twice = sorted(k for k, n in c.items() if n > 1 and k not in nested)
        assert not twice, f"{lang}: text keys defined twice, the later one silently wins: {twice}"       # this put a court sentence on the contract list
    assert set(re.findall(r"[\s,{]([a-z]{2,5}_[a-z0-9_]+):", "\n".join(blocks["en"]))) == set(re.findall(r"[\s,{]([a-z]{2,5}_[a-z0-9_]+):", "\n".join(blocks["es"]))), "English and Spanish text keys differ"
    page = root / "site" / "index.html"
    if shutil.which("node") and page.exists():                      # one stray comment inside a one-line function stops the whole page
        js = max(re.findall(r"<script>(.*?)</script>", page.read_text(encoding="utf-8"), re.S), key=len)
        f = pathlib.Path(tempfile.mkdtemp()) / "page.js"; f.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True); assert r.returncode == 0, r.stderr[-300:]


def test_ended_agreements_drop_relisted_and_respelled_ones():
    import build_site as b
    cur = [{"state": "NEW HAMPSHIRE", "agency": "South Hampton Police Department", "model": "Task Force Model", "signed": "2026-06-22"},
           {"state": "NEW YORK", "agency": "Cattaraugus County Sheriff's Office", "model": "Warrant Service Officer", "signed": "2025-03-01"}]
    gone = [{"state": "NEW HAMPSHIRE", "agency": "South Hampton Police Department", "model": "T", "signed": "2026-06-22", "last_listed": "2026-09-04"},   # still listed
            {"state": "NEW YORK", "agency": "Cattaraugus Counry Sheriff's Office", "model": "W", "signed": "2025-03-01", "last_listed": "2025-04-01"},      # a typo ICE later fixed
            {"state": "INDIANA", "agency": "Green Forks Police Department", "model": "T", "signed": "2025-05-05", "last_listed": "2025-06-01"},
            {"state": "INDIANA", "agency": "Greens Forks Police Department", "model": "T", "signed": "2025-05-05", "last_listed": "2025-07-01"},            # same ended agreement, respelled
            {"state": "NEBRASKA", "agency": "Red Willow County Sheriff's Office", "model": "J", "signed": "2025-05-05", "last_listed": "2025-07-01"},
            {"state": "NEBRASKA", "agency": "Red Willow County Sheriff's Office", "model": "W", "signed": "2025-05-05", "last_listed": "2025-07-01"}]       # another kind of agreement: a separate one
    out, dropped = b.ended_agreements(gone, cur, {"INDIANA": "IN", "NEBRASKA": "NE"})
    assert dropped == 3 and [(r[0], r[1], r[2]) for r in out] == [("IN", "Green Forks Police Department", "T"), ("NE", "Red Willow County Sheriff's Office", "J"), ("NE", "Red Willow County Sheriff's Office", "W")]
    assert b._near("abc", "abd") and not b._near("abc", "xyzabc")


def test_page_loads_nothing_from_a_third_party():
    import re, pathlib
    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    html = (site / "template.html").read_text(encoding="utf-8")
    loads = re.findall(r'<(?:script|link|img|iframe)[^>]+(?:src|href)="(https?:[^"]+)"', html) + re.findall(r'url\(["\']?(https?:[^)"\']+)', html) + re.findall(r'@import\s+["\'](https?:[^"\']+)', html)
    assert not loads, f"the page promises to collect nothing, so it must not fetch from other sites: {loads}"
    for local in re.findall(r'(?:src|href)="(vendor/[^"]+)"', html) + re.findall(r'url\("(vendor/[^"]+)"\)', html):
        assert (site / local).exists(), f"missing file the page loads: {local}"


def test_money_by_year_by_quarter_and_timeline():
    import money_usaspending as u, money_lobbying as l, money_fec as f
    assert u.year_row("ACME", 30e6, {2024: 0, 2025: 10e6, 2026: 20e6}, [2024, 2025, 2026]) == {"kind": "recipient", "name": "ACME", "fy2024": 0, "fy2025": 10, "fy2026": 20, "checked": "yes"}
    bad = u.year_row("ACME", 30e6, {2025: 10e6, 2026: 90e6}, [2024, 2025, 2026])       # the name search swept in another company: no yearly figures
    assert bad["checked"] == "no" and bad["fy2026"] == ""
    assert set(u.COMPETED["competed"]) & set(u.COMPETED["not_competed"]) == set()
    F = lambda reg, period, posted, income=0, expenses=0, issues=(): {"client": {"name": "THE GEO GROUP", "id": 1}, "registrant": {"name": reg, "id": reg}, "filing_type": "Q1", "filing_period": period,
                                                                    "dt_posted": posted, "income": income, "expenses": expenses, "lobbying_activities": [{"general_issue_code_display": i, "description": "private text"} for i in issues]}
    q, iss = l.by_quarter([F("GEO GROUP INC", "first_quarter", "1", expenses=100, issues=["Immigration", "Immigration"]), F("GEO GROUP INC", "first_quarter", "2", expenses=300, issues=["Immigration"]),
                           F("SOME FIRM LLC", "second_quarter", "1", income=50, issues=["Budget/Appropriations"]), dict(F("X LLC", "first_quarter", "1", income=9), filing_type="RR")], r"GEO GROUP")
    assert q == {"Q1": [300, 0], "Q2": [0, 50]} and iss == {"Immigration": 1, "Budget/Appropriations": 1}      # the amended first-quarter report replaces the earlier one
    R = lambda a, b, v, rec: {"coverage_start_date": a, "coverage_end_date": b, "fed_candidate_committee_contributions_period": v, "receipt_date": rec, "file_number": 1}
    t = f.timeline("G", [R("2025-01-01", "2025-01-31T00:00:00", 1000, "2025-02-10"), R("2025-01-01", "2025-01-31T00:00:00", 1500, "2025-03-01"), R("2025-02-01", "2025-02-28", 500, "2025-03-10"), R("2025-04-01", "2025-06-30", None, "x")])
    assert t == [{"pac": "G", "quarter": "2025 Q1", "usd": 2000}]


def test_atd_and_detention_summary_tables_are_read_by_their_labels():
    import detention_stats as d
    atd = [["ATD Active Population Counts and Daily Cost by Technology"], ["Technology", "Count", "Daily Tech Cost", "Metric"], ["SmartLINK", 100, 96.0], ["Ankle Monitor", 50, 137.5],
           ["Total", 150, 233.5], ["Data from BI Inc. Participants Report, 07.11.2026"]]
    assert d.parse_atd(atd) == {"as_of": "2026-07-11", "total": 150, "cost": 233.5, "tech": {"SmartLINK": 100, "Ankle Monitor": 50}}
    assert d.parse_atd(atd[:3] + [["Total", 999, 1]] + atd[5:]) is None          # parts that do not add up are refused
    det = [["Criminality", "ICE", "Percent ICE", "CBP", "Percent CBP", "Total", "Agency", "Oct", "Nov", "Dec", "Jan"],
           ["Total", 90, .9, 10, .1, 100, "Total", 30, 20, 0, 0], [None] * 6 + ["CBP", 5, 4, 0, 0], [None] * 6 + ["ICE  ", 25, 16, 0, 0],
           ["Facility Type", None, "Removals", None, "Total"], ["Total", None, "Total", None, 77]]
    got = d.parse_detention(det, "FY26")
    assert got["detained"] == [100, 90, 10] and got["bookins"] == {"2025-10": {"CBP": 5, "ICE": 25}, "2025-11": {"CBP": 4, "ICE": 16}} and got["removals"] == 77


def test_prefill_writes_english_text_and_confirmed_numbers_before_the_script():
    from build_site import prefill_text
    html = ('<p data-t="a"></p><b data-t="f"></b><span data-hl="orr"></span><p data-hlp="dril"><span data-hl="dril"></span></p>'
            '<script>const T = {\n en:{a:"Hello & bye", f:x => x},\n es:{a:"Hola"}\n};\n</script>')
    out = prefill_text(html, {"orr": ["1-800-203-7001", "u", "d"]})
    assert '<p data-t="a">Hello &amp; bye</p>' in out and '<b data-t="f"></b>' in out
    assert '<span data-hl="orr">1-800-203-7001</span>' in out and '<p hidden data-hlp="dril">' in out
    assert out[out.find("<script"):] == html[html.find("<script"):]          # the script itself is untouched


def test_display_name_keeps_ice_name_and_rejects_unknown_codes(tmp_path):
    from build_site import display_names
    (tmp_path / "facility_display_names.csv").write_text("facility_code|name|source\nX1|Camp Short|https://www.ice.gov/x\n", encoding="utf-8")
    site = {"facilities": {"X1": {"name": "Enforcement and Removal Operations Long Name"}}}
    display_names(site, tmp_path); display_names(site, tmp_path)          # running twice changes nothing more
    f = site["facilities"]["X1"]
    assert f["name"] == "Camp Short" and f["ice_name"] == "Enforcement and Removal Operations Long Name" and f["name_src"] == "https://www.ice.gov/x"
    try: display_names({"facilities": {}}, tmp_path); assert False, "an unknown code must stop the build"
    except ValueError: pass
