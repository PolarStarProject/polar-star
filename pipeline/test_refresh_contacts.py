import refresh_contacts as r

ADELANTO = """ Adelanto ICE Processing Center Los Angeles Field Office Contacting a Detainee Legal & Case Information
Contacting a Detainee If you need information about a detainee that is housed at this facility, you may call
(760) 561-6100 between the hours of 7:30 a.m. and 3 p.m., 7 days a week. If you need to get in touch with a detainee
you must call (760) 561-6100 and leave the detainee's full name. Report Crimes: Call 1-866-DHS-2-ICE"""

def test_facility_phone_is_the_detainee_information_line():
    assert r.parse_facility(ADELANTO, "\n Adelanto ICE Processing Center\n") == ("Adelanto ICE Processing Center", "(760) 561-6100")
    assert r.parse_facility("Virtual Attorney Visitation Program. Report Crimes: Call 1-866-347-2423", "VAV")[1] == ""   # never the tip line

def test_facility_links():
    html = '<a href="/detain/detention-facilities/stewart-detention-center">x</a><a href="/detain/detention-facilities/stewart-detention-center">y</a><a href="/detention-facilities?page=2">n</a>'
    assert r.parse_facility_links(html) == ["/detain/detention-facilities/stewart-detention-center"]

def test_field_offices():
    lis = ["Atlanta - ERO Atlanta Field Office180 Ted Turner Dr. SW Suite 522 Atlanta, GA 30303 United States(404) 893-1290Area of Responsibility: Georgia",
           "Atlanta - HSI HSI Atlanta 1100 Centre Pkwy (404) 346-2300",
           "Miramar - ERO Miramar Sub Office2805 SW 145th Ave Miramar, FL 33027 United States(954) 843-5800Area of Responsibility: Florida",
           "St. Rose - ERO New Orleans Field Office181 James Drive W St. Rose, LA 70087 United StatesArea of Responsibility: Alabama"]
    assert r.parse_field_offices(lis) == {"Atlanta": ("Atlanta Field Office", "(404) 893-1290"), "Miami": ("Miramar Sub Office", "(954) 843-5800")}

def test_merge_never_drops_a_number_and_logs_changes():
    old = [{"slug": "a", "phone": "(111) 111-1111", "retrieved": "2026-01-01"}, {"slug": "b", "phone": "(222) 222-2222", "retrieved": "2026-01-01"},
           {"slug": "gone", "phone": "(333) 333-3333", "retrieved": "2026-01-01"}]
    new = {"a": {"slug": "a", "phone": "(111) 111-9999"}, "b": {"slug": "b", "phone": ""}, "c": {"slug": "c", "phone": "(444) 444-4444"}}
    log = []; out = {x["slug"]: x for x in r.merge(old, new, "slug", "2026-10-03", log)}
    assert out["a"]["phone"] == "(111) 111-9999" and out["a"]["retrieved"] == "2026-10-03"
    assert out["b"]["phone"] == "(222) 222-2222" and out["b"]["retrieved"] == "2026-01-01"   # blank page result keeps the old number
    assert out["gone"]["phone"] == "(333) 333-3333" and out["c"]["phone"] == "(444) 444-4444"
    assert len(log) == 3 and any("CHANGED a" in l for l in log) and any("MISSING-ON-PAGE b" in l for l in log)

EDEN = """ Eden Detention Center Dallas Field Office Contacting a Detainee Legal & Case Information Hours of Visitation
Press & Media Feedback or Complaints Contacting a Detainee Contacting a Detainee To identify if the detainee is currently
housed at Eden Detention Center, you can call (325) 869-2704, 24 hours a day. Staff can only release housing information."""

def test_facility_phone_when_the_page_uses_other_wording():
    assert r.parse_facility(EDEN, "Eden Detention Center")[1] == "(325) 869-2704"

def test_inspection_titles_as_ice_writes_them():
    a = r.parse_inspection("2026 Adelanto ICE Processing Center, Adelanto, CA - Jul. 14-16, 2026", "/doclib/foia/odo-compliance-inspections/AdelantoIPC_Adelanto%20CA_Jul14-16_2026.pdf")
    assert (a["fiscal_year"], a["facility"], a["city"], a["state"], a["dates"]) == ("2026", "Adelanto ICE Processing Center", "Adelanto", "CA", "Jul. 14-16, 2026")
    assert a["url"].startswith("https://www.ice.gov/doclib/")
    b = r.parse_inspection("2026 Finney County Jail, Garden City, KS \u2013 Jul. 15-Aug. 13, 2026", "/x.pdf")            # en dash
    assert (b["facility"], b["city"], b["state"]) == ("Finney County Jail", "Garden City", "KS")
    c = r.parse_inspection("2026 Tulsa County Jail (David L Moss Justice Center), Tulsa, OK - Jul. 15-Aug. 13, 2026", "/x.pdf")
    assert c["facility"] == "Tulsa County Jail (David L Moss Justice Center)" and c["city"] == "Tulsa"
    d = r.parse_inspection("2026 Dallas County Jail \u2013 Lew Sterrett, Dallas, TX - Apr. 16, 2026", "/x.pdf")                # dash inside the name
    assert (d["facility"], d["city"], d["state"], d["dates"]) == ("Dallas County Jail \u2013 Lew Sterrett", "Dallas", "TX", "Apr. 16, 2026")
    assert r.parse_inspection("FOIA Logs 2026", "/x.pdf") is None

def test_death_counts_need_headings_and_tables_to_line_up():
    assert r.parse_death_counts(["Reporting", "FY 2026", "FY 2025"], [37, 25]) == {"2026": 36, "2025": 24}
    assert r.parse_death_counts(["FY 2026", "FY 2025"], [37]) == {}
