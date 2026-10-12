import agency_contacts as ac

ABBR = {"GEORGIA": "GA", "TEXAS": "TX", "NEW HAMPSHIRE": "NH"}
def office(name, st, county, phone="(229) 838-4311", lat=32.05, lon=-84.79, status="OPEN"):
    return {"NAME": name, "STATE": st, "COUNTY": county, "TELEPHONE": phone, "LATITUDE": lat, "LONGITUDE": lon, "STATUS": status,
            "ADDRESS": "1980 BROAD ST", "CITY": "LUMPKIN", "ZIP": "31815", "WEBSITE": "NOT AVAILABLE", "VAL_DATE": 1520294400000}
def ag(name, state="GEORGIA", county="Stewart County"): return {"state": state, "agency": name, "county": county}

def test_name_forms_match():
    assert ac.agency_key("Stewart County Sheriff's Department") == ac.agency_key("STEWART COUNTY SHERIFFS OFFICE")
    assert ac.agency_key("Lumpkin Police Department") == ac.agency_key("LUMPKIN POLICE DEPT")
    assert ac.agency_key("Lumpkin Police Department") != ac.agency_key("LUMPKIN POLICE DEPARTMENT - NORTH SUBSTATION")

def test_match_gives_phone_address_date():
    rows, why = ac.match([ag("Stewart County Sheriff's Department")], [office("STEWART COUNTY SHERIFFS OFFICE", "GA", "STEWART")], ABBR)
    assert rows[0]["phone"] == "(229) 838-4311" and rows[0]["address"] == "1980 Broad St, Lumpkin, GA 31815"
    assert rows[0]["checked"] == "2018-03-06" and rows[0]["website"] == "" and why["matched"] == 1

def test_same_name_other_state_is_not_matched():
    rows, why = ac.match([ag("Stewart County Sheriff's Department")], [office("STEWART COUNTY SHERIFFS OFFICE", "TN", "STEWART")], ABBR)
    assert rows == [] and why["no_office_with_that_name"] == 1

def test_county_disagreement_rejected():
    rows, why = ac.match([ag("Franklin Police Department", county="Heard County")], [office("FRANKLIN POLICE DEPARTMENT", "GA", "MACON")], ABBR)
    assert rows == [] and why["county_disagrees"] == 1

def test_two_offices_same_name_rejected_unless_county_settles_it():
    offs = [office("FRANKLIN POLICE DEPARTMENT", "GA", "HEARD"), office("FRANKLIN POLICE DEPARTMENT", "GA", "MACON")]
    rows, _ = ac.match([ag("Franklin Police Department", county="Heard County")], offs, ABBR)
    assert len(rows) == 1 and rows[0]["matched_name"] == "FRANKLIN POLICE DEPARTMENT"
    rows, why = ac.match([ag("Franklin Police Department", county="")], offs, ABBR)
    assert rows == [] and why["several_offices_with_that_name"] == 1

def test_closed_office_ignored_and_bad_phone_blank():
    rows, _ = ac.match([ag("Lumpkin Police Department")], [office("LUMPKIN POLICE DEPARTMENT", "GA", "STEWART", status="CLOSED")], ABBR)
    assert rows == []
    rows, _ = ac.match([ag("Lumpkin Police Department")], [office("LUMPKIN POLICE DEPARTMENT", "GA", "STEWART", phone="NOT AVAILABLE")], ABBR)
    assert rows[0]["phone"] == ""

def test_phone_from_another_state_dropped_but_row_kept():
    rows, why = ac.match([ag("Lumpkin Police Department")], [office("LUMPKIN POLICE DEPARTMENT", "GA", "STEWART")], ABBR, area_state=lambda p: "MI")
    assert rows[0]["phone"] == "" and rows[0]["address"] and why["phone_area_code_in_another_state"] == 1

def test_positive_longitude_is_not_mapped():
    rows, why = ac.match([ag("Lumpkin Police Department")], [office("LUMPKIN POLICE DEPARTMENT", "GA", "STEWART", lon=84.79)], ABBR)
    assert rows[0]["lat"] == "" and why["position_outside_state_box"] == 1

def test_state_typo_in_ice_list():
    rows, _ = ac.match([ag("Derry Police Department", state="NEW HAMSPHIRE", county="")], [office("DERRY POLICE DEPARTMENT", "NH", "ROCKINGHAM")], ABBR)
    assert len(rows) == 1 and rows[0]["state"] == "NEW HAMPSHIRE"

def test_real_name_shapes_from_the_federal_list():
    offs = [office("WASHAKIE COUNTY SHERIFFS DEPARTMENT / WASHAKIE COUNTY JAIL", "GA", "WASHAKIE"),
            office("HOT SPRINGS COUNTY SHERIFFS OFFICE AND HOT SPRINGS COUNTY DETENTION CENTER", "GA", "HOT SPRINGS"),
            office("ALLENSTOWN POLICE DEPARTMENT HEADQUARTERS", "GA", "MERRIMACK"), office("CARBON COUNTY SHERIFF'S OFFICE", "GA", "CARBON"),
            office("HOLLIS TOWN POLICE DEPARTMENT", "GA", "HILLSBOROUGH"),
            office("SWEETWATER COUNTY SHERIFFS OFFICE - ROCK SPRINGS", "GA", "SWEETWATER"), office("SWEETWATER COUNTY SHERIFFS OFFICE - GREEN RIVER", "GA", "SWEETWATER")]
    ags = [ag("Washakie County Sheriff's Office", county="Washakie County"), ag("Hot Springs County Sheriff's Office", county="Hot Springs County"),
           ag("Allenstown Police Department", county="Merrimack County"), ag("Carbon County Sheriff's Office", county="Carbon County"),
           ag("Hollis Police Department", county="Hillsborough County"), ag("Sweetwater County Sheriff's Office", county="Sweetwater County")]
    rows, why = ac.match(ags, offs, ABBR)
    assert [r["agency"].split()[0] for r in rows] == ["Washakie", "Hot", "Allenstown", "Carbon", "Hollis"]
    assert why["several_offices_with_that_name"] == 1          # two Sweetwater branches: no way to know which number is the main one
