import pandas as pd
import build_transfers as b

C = ["stay_ID", "detention_facility_code", "book_in_date_time", "book_out_date_time", "detention_release_reason", "duplicate_drop_row", "detention_facility", "city", "state"]
def S(rows): return pd.DataFrame([r + (False, r[1], "X", "TX") if len(r) == 5 else r for r in rows], columns=C)

def test_transfer_rules():
    st, log = b.prepare(S([
        ("s1", "A", "2026-01-01", "2026-01-05", "Transferred"), ("s1", "B", "2026-01-05 06:00", "2026-01-09", "Removed"),      # A->B
        ("s2", "A", "2026-01-01", "2026-01-02", "Transferred"), ("s2", "A", "2026-01-02 01:00", "2026-01-03", "Paroled"),      # same facility
        ("s3", "A", "2026-01-01", "2026-01-02", "Paroled"), ("s3b", "B", "2026-03-01", "2026-03-02", "Removed"),              # separate stays
        ("s4", "A", "2026-01-01", "2026-01-04", "Transferred"), ("s4", "C", "2026-01-03 20:00", "2026-01-06", "Removed"),      # overlap, kept
        ("s5", "A", "2026-01-01", None, None),                                                                                # still held
        ("s6", "A", "2026-01-01", "2026-01-02", "Transferred", True, "A", "X", "TX"), (None, "A", "2026-01-01", "2026-01-02", "Removed"),
    ]))
    t = b.transfers(st, log)
    assert sorted(zip(t.facility, t.dest)) == [("A", "B"), ("A", "C")]
    assert log["flagged_duplicates_dropped"] == 1 and log["missing_stay_facility_or_book_in_dropped"] == 1
    assert log["same_facility_rebooking_ignored"] == 1 and log["overlap_in_two_places_at_once_kept"] == 1
    assert round(t[t.dest == "B"].held_days.iloc[0]) == 4

def _agg(counts, removed=0):
    rows, i = [], 0
    for dest, n in counts.items():
        for _ in range(n):
            i += 1; rows += [(f"s{i}", "A", "2026-01-01", "2026-01-04", "Transferred"), (f"s{i}", dest, "2026-01-04 05:00", None, None)]
    for _ in range(removed):
        i += 1; rows.append((f"s{i}", "A", "2026-01-01", "2026-01-04", "Removed"))
    st, log = b.prepare(S(rows)); t = b.transfers(st, log)
    fac = pd.DataFrame([(c, c, "X", "TX", "1 St", "Off") for c in ["A", *counts]], columns=["detention_facility_code", "name", "city", "state", "address_full", "field_office"])
    return b.aggregate(st, t, fac)[0]

def test_small_origin_publishes_nothing():
    r = _agg({"B": 20, "C": 9})["A"]
    assert r["enough"] is False and "dests" not in r and "outcome" not in r

def test_small_cells_folded_and_not_derivable():
    r = _agg({"B": 40, "C": 12, "D": 3})["A"]        # D alone would be recoverable by subtraction
    assert [d["code"] for d in r["dests"]] == ["B"] and r["other_pct"] == round(100 * 15 / 55)

def test_outcomes_and_no_counts():
    out = _agg({"B": 40, "C": 30}, removed=30); r = out["A"]
    assert r["outcome"] == [{"k": "moved", "pct": 70}, {"k": "deported", "pct": 30}] and r["other_pct"] == 0
    assert set(r) == {"name", "city", "state", "address", "office", "county", "enough", "outcome", "dests", "other_pct", "median_days"}
    assert out["B"]["enough"] is False and out["B"]["name"] == "B"   # destinations stay nameable

def test_shares_sum_to_100_and_hide_small_groups():
    s = b.shares({"moved": 333, "deported": 333, "released": 334, "died": 3, "escaped": 2})
    assert sum(d["pct"] for d in s) == 100 and s[-1]["k"] == "other"
    keys = {d["k"] for d in s}
    assert "died" not in keys and "escaped" not in keys          # under 10: never shown on their own
    assert "other" in keys and len(keys) == 3                    # folded with the smallest shown group
    assert b.REASON_TO_GROUP["U.S. Marshals or other agency (explain in Detention Comments)"] == "other_agency"
    assert b.REASON_TO_GROUP["Processing Disposition Changed Locally"] == "processing_changed"   # ICE's unclear term is never counted as a release
    assert "Some New Reason" not in b.REASON_TO_GROUP                                          # unknown reasons are never a release

def test_removal_countries_only_when_enough_and_never_small():
    rows = [(f"s{i}", "A", "2026-01-01", "2026-01-04", "Removed", False, "A", "X", "TX", c) for i, c in enumerate(["MEXICO"] * 40 + ["GUATEMALA"] * 15 + ["PERU"] * 3)]
    df = pd.DataFrame(rows, columns=C + ["departure_country"])
    st, log = b.prepare(df); t = b.transfers(st, log)
    fac = pd.DataFrame([("A", "A", "X", "TX", "1 St", "Off")], columns=["detention_facility_code", "name", "city", "state", "address_full", "field_office"])
    r = b.aggregate(st, t, fac)[0]["A"]["removed_to"]
    assert [d["k"] for d in r] == ["Mexico", "other"] and sum(d["pct"] for d in r) == 100      # Guatemala folded so Peru's 3 cannot be derived

def test_deaths_are_counted_even_when_small():
    rows = [(f"s{i}", "A", "2026-01-01", "2026-01-04", "Removed") for i in range(40)] + [("d1", "A", "2026-01-01", "2026-01-03", "Died"), ("d0", "A", "2022-01-01", "2022-01-03", "Died")]
    st, log = b.prepare(S(rows)); t = b.transfers(st, log)
    fac = pd.DataFrame([("A", "A", "X", "TX", "1 St", "Off")], columns=["detention_facility_code", "name", "city", "state", "address_full", "field_office"])
    r = b.aggregate(st, t, fac)[0]["A"]
    assert r["deaths_recorded"]["year"] == 1 and r["deaths_recorded"]["all"] == 2          # the 2022 death is outside the one-year window
    assert all(o["k"] != "died" for o in r["outcome"])                                    # still not a percentage bar


def test_small_groups_are_named_when_combined():
    folded = []
    s = b.shares({"moved": 500, "deported": 400, "died": 3, "escaped": 2, "processing_changed": 7}, folded)
    assert sorted(folded) == ["died", "escaped", "processing_changed"] and s[-1]["k"] == "other" and sum(x["pct"] for x in s) == 100
    assert "Processing Disposition Changed Locally" in b.REASON_TO_GROUP


def test_women_custody_counts_stays_not_stints(tmp_path=None):
    import pandas as pd, tempfile, os
    rows = [("Female", "s1", "2025-01-01", "2026-01-01", False), ("Female", "s1", "2025-01-01", "2026-01-01", False),   # one 365-day stay, two stints
            ("Female", "s2", "2026-07-01", "2026-07-11", False), ("Male", "s3", "2025-01-01", "2026-07-01", False),
            ("Female", "s4", "2025-09-01", None, False), ("Female", "s5", "2026-07-01", "2026-07-21", True)]
    df = pd.DataFrame(rows, columns=["gender", "stay_ID", "stay_book_in_date_time", "stay_book_out_date_time", "duplicate_drop_row"])
    p = os.path.join(tempfile.mkdtemp(), "s.parquet"); df.to_parquet(p)
    w = b.women_custody(p)
    assert w["ended"] == {"n": 2, "bands": [1, 0, 0, 1], "median_days": 187} and w["open"]["n"] == 1 and w["open"]["bands"] == [0, 0, 1, 0] and w["as_of"] == "2026-07-11"
    df["book_in_date_time"] = df["stay_book_in_date_time"]; df["book_out_date_time"] = df["stay_book_out_date_time"]; df.loc[3, "book_in_date_time"] = "2026-07-30"     # a newer stint (any gender) sets the day
    df.to_parquet(p); w2 = b.women_custody(p)
    assert w2["as_of"] == "2026-07-30" and w2["open"]["n"] == 1


def test_contact_matched_through_hand_kept_alias():
    import pandas as pd
    from build_transfers import attach_contacts
    facs = {"EROFCB": {"name": "Enforcement and Removal Operations El Paso Camp East Montana", "state": "TX"},
            "EPC": {"name": "El Paso Service Processing Center", "state": "TX"}}
    contacts = pd.DataFrame([{"name": "ERO El Paso Camp East Montana", "phone": "(915) 280-2270", "source": "https://www.ice.gov/x"}])
    log = {}
    attach_contacts(facs, contacts, log)                                            # without the alias: no confident match, no number
    assert "phone" not in facs["EROFCB"] and log["contacts_not_matched"] == ["ERO El Paso Camp East Montana"]
    attach_contacts(facs, contacts, log, {"ERO EL PASO CAMP EAST MONTANA": "EROFCB"})
    assert facs["EROFCB"]["phone"] == "(915) 280-2270" and "phone" not in facs["EPC"]


def test_alias_to_missing_facility_or_wrong_state_gets_no_number():
    import pandas as pd
    from build_transfers import attach_contacts
    facs = {"EROFCB": {"name": "Camp East Montana", "state": "NM"}}
    contacts = pd.DataFrame([{"name": "ERO El Paso Camp East Montana", "phone": "(915) 280-2270", "source": ""}])
    log = {}
    attach_contacts(facs, contacts, log, {"ERO EL PASO CAMP EAST MONTANA": "NOPE"})   # alias to a code that does not exist
    assert "phone" not in facs["EROFCB"]
    attach_contacts(facs, contacts, log, {"ERO EL PASO CAMP EAST MONTANA": "EROFCB"}) # area code is Texas, facility says NM
    assert "phone" not in facs["EROFCB"] and log["contacts_area_code_in_other_state"]


def test_same_name_in_two_states_decided_by_area_code():
    import pandas as pd
    from build_transfers import attach_contacts
    facs = {"PHELPMO": {"name": "Phelps County Jail", "state": "MO"}, "PHELPNE": {"name": "Phelps County Jail", "state": "NE"},
            "POLKJFL": {"name": "Polk County Jail", "state": "FL"}, "POLKJIA": {"name": "Polk County Jail", "state": "IA"}}
    contacts = pd.DataFrame([{"name": "Phelps County Jail", "phone": "(308) 995-5692", "source": ""},
                             {"name": "Phelps County Jail", "phone": "(573) 426-3860", "source": ""},
                             {"name": "Polk County Jail", "phone": "(515) 323-5400", "source": ""}])
    log = {}
    attach_contacts(facs, contacts, log)
    assert facs["PHELPNE"]["phone"] == "(308) 995-5692" and facs["PHELPMO"]["phone"] == "(573) 426-3860"
    assert facs["POLKJIA"]["phone"] == "(515) 323-5400" and "phone" not in facs["POLKJFL"]


def test_two_same_named_places_in_one_state_get_no_number():
    import pandas as pd
    from build_transfers import attach_contacts
    facs = {"A": {"name": "Cass County Jail", "state": "TX"}, "B": {"name": "Cass County Jail", "state": "TX"}}
    log = {}
    attach_contacts(facs, pd.DataFrame([{"name": "Cass County Jail", "phone": "(903) 756-7511", "source": ""}]), log)
    assert "phone" not in facs["A"] and "phone" not in facs["B"] and log["contacts_not_matched"] == ["Cass County Jail"]


def test_two_numbers_for_one_facility_give_none():
    import pandas as pd
    from build_transfers import attach_contacts
    facs = {"X": {"name": "Lake County Jail", "state": "FL"}}
    contacts = pd.DataFrame([{"name": "Lake County Jail", "phone": "(352) 742-4000", "source": ""},
                             {"name": "Lake County Jail", "phone": "(352) 343-2101", "source": ""}])
    log = {}
    attach_contacts(facs, contacts, log)
    assert "phone" not in facs["X"]


def test_bracketed_alias_and_federal_abbreviations():
    import pandas as pd
    from build_transfers import attach_contacts
    facs = {"FIPCMGA": {"name": "Folkston ICE Processing Center (Main)", "state": "GA"},
            "FIPCAGA": {"name": "Folkston ICE Processing Center (Annex)", "state": "GA"},
            "BOPMIM": {"name": "Federal Detention Center Miami", "state": "FL"}}
    contacts = pd.DataFrame([{"name": "Folkston ICE Processing Center (Main)", "phone": "(912) 496-6905", "source": ""},
                             {"name": "Folkston ICE Processing Center (Annex)", "phone": "(912) 496-6905", "source": ""},
                             {"name": "FDC Miami", "phone": "(305) 577-0010", "source": ""}])
    log = {}
    attach_contacts(facs, contacts, log)                             # without the aliases the two Folkston names look alike
    assert "phone" not in facs["FIPCMGA"] and "phone" not in facs["FIPCAGA"] and facs["BOPMIM"]["phone"] == "(305) 577-0010"
    attach_contacts(facs, contacts, log, {"FOLKSTON ICE PROCESSING CENTER (MAIN)": "FIPCMGA", "FOLKSTON ICE PROCESSING CENTER (ANNEX)": "FIPCAGA"})
    assert facs["FIPCMGA"]["phone"] == "(912) 496-6905" and facs["FIPCAGA"]["phone"] == "(912) 496-6905"


def test_toll_free_number_passes_the_state_check_only_on_a_unique_name():
    import pandas as pd
    from build_transfers import attach_contacts
    facs = {"OKDBACK": {"name": "Diamondback Correctional Facility", "state": "OK"},
            "A": {"name": "Cass County Jail", "state": "ND"}, "B": {"name": "Cass County Jail", "state": "NE"}}
    contacts = pd.DataFrame([{"name": "Diamondback Correctional Facility", "phone": "(888) 351-4024", "source": ""},
                             {"name": "Cass County Jail", "phone": "(800) 555-0100", "source": ""}])
    log = {}
    attach_contacts(facs, contacts, log)
    assert facs["OKDBACK"]["phone"] == "(888) 351-4024" and "phone" not in facs["A"] and "phone" not in facs["B"]
