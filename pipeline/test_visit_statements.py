import visit_statements as vs

ROW = '<div class="views-row evo-views-row"><div class="media-body"><div class="h5"><a href="%s">%s</a></div><div class="row"><div class="col-auto">%s </div><div class="col-auto"><a href="/media/press-releases">Press Release</a></div></div><div class="evo-press-release__body"><p>%s</p></div></div></div>'
LIST = "<html><body>" + ROW % ("/media/press-releases/denied-entry-adelanto", "Rep. Doe Denied Entry at Adelanto ICE Processing Center", "June 8, 2025", "They locked the gate.") \
     + ROW % ("/media/press-releases/farm-bill-intro", "Rep. Doe Introduces Farm Bill", "June 9, 2025", "ICE was denied access to nothing here.") \
     + ROW % ("/media/press-releases/visit-stewart-det", "Rep. Doe Conducts Oversight Visit of Stewart Detention Center", "June 10, 2025", "x") \
     + '<div class="views-row"><a href="/contact/offices/dc">Washington DC Office</a></div></body></html>'
OLD = "<html><body>" + ROW % ("/media/press-releases/old-denied-2019", "Rep. Doe Denied Entry to ICE Detention Center in 2019", "March 3, 2019", "x") + "</body></html>"
DQ = '<html><body><ul><li><time>09/29/2026</time> <a href="/news/documentsingle.aspx?DocumentID=2938">Rep. Poe Refused Entry to ICE Processing Center in Conroe</a></li></ul></body></html>'
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Senator Roe blocked from entering immigration detention facility</title><link href="https://www.roe.senate.gov/news/1"/><updated>2026-01-10T12:00:00Z</updated><summary>s</summary></entry></feed>"""
FAC = {"ADLNTCA": {"name": "Adelanto ICE Processing Center"}, "STWRTGA": {"name": "Stewart Detention Center"},
       "A1": {"name": "Adams County Detention Center"}, "A2": {"name": "Adams County Jail"}, "RND": {"name": "Randall County Jail"}}
REP = {"full_name": "Jane Doe", "type": "rep", "state": "CA", "party": "Democrat", "url": "https://doe.house.gov", "rss_url": ""}
POE = {"full_name": "Pat Poe", "type": "rep", "state": "TX", "party": "Republican", "url": "https://poe.house.gov", "rss_url": ""}
SEN = {"full_name": "Rick Roe", "type": "sen", "state": "MN", "party": "Democrat", "url": "https://www.roe.senate.gov", "rss_url": "http://www.roe.senate.gov/rss/"}

def fetch(u):
    if "doe.house.gov/media/press-releases" in u: return LIST if "page=" not in u else (OLD if "page=1" in u else "<html></html>")
    if "poe.house.gov/news/documentquery" in u: return DQ if "Page=" not in u else "<html></html>"
    if "roe.senate.gov/rss" in u: return ATOM
    raise OSError("404")

def test_parse_feed_atom():
    assert vs.parse_feed(ATOM)[0][1:3] == ("https://www.roe.senate.gov/news/1", "2026-01-10")

def test_listing_two_layouts_and_dates():
    rows = vs.parse_listing(LIST, "https://doe.house.gov")
    assert len(rows) == 3 and rows[0][1:3] == ("https://doe.house.gov/media/press-releases/denied-entry-adelanto", "2025-06-08") and "locked" in rows[0][3]
    dq = vs.parse_listing(DQ, "https://poe.house.gov")
    assert dq[0][1:3] == ("https://poe.house.gov/news/documentsingle.aspx?DocumentID=2938", "2026-09-29")
    assert vs.to_day("Sept. 5, 2024") == "2024-09-05" and vs.to_day("no date") == ""

def test_page_addresses():
    assert vs.page_url("https://doe.house.gov/", "/media/press-releases", 2) == "https://doe.house.gov/media/press-releases?page=2"
    assert vs.page_url("https://poe.house.gov", "/news/documentquery.aspx?DocumentTypeID=27", 1).endswith("DocumentTypeID=27&Page=2")

def test_classify_title_only():
    assert vs.classify("Rep. Doe Denied Entry to Adelanto ICE Processing Center", "") == "denied"
    assert vs.classify("Pou Leads 27 Colleagues Calling on DHS to Protect Religious Rights in ICE Detention", "detainees denied access to clergy") is None
    assert vs.classify("Randall, Advocates Hold Community Vigil at Tacoma NW ICE Detention Center", "members were denied entry") is None
    assert vs.classify("Rep. Doe Conducts Oversight Visit of Stewart Detention Center", "") == "visit"
    assert vs.classify("Demand Answers After Congressional Access Blocked at Immigration Courtroom", "") == "denied"
    assert vs.classify("Rep. Doe Introduces Farm Bill", "ICE was denied access") is None

def test_facility_match_rules():
    ix = vs.facility_index(FAC)
    assert vs.match_facility("Denied Entry to Adelanto ICE Processing Center", ix) == "ADLNTCA"
    assert vs.match_facility("visit to Adams County Jail", ix) == ""                                 # two facilities share the name
    assert vs.match_facility("Adelanto ICE facility and Stewart Detention visits", ix) == ""
    assert vs.match_facility("Randall, Advocates Hold Vigil at Tacoma ICE Detention Center", ix, "Emily Randall") == ""   # the member's own name
    assert vs.match_facility("Statement on Adelanto mayor", ix) == ""                                   # no detention word after it

def test_collect_party_coverage_and_since():
    have = set()
    rows, stats, cover = vs.collect([REP, POE, SEN, {"full_name": "No Site", "type": "sen", "state": "TX", "party": "Republican", "url": "", "rss_url": ""}],
                                    fetch, vs.facility_index(FAC), have, "2026-10-04", pages=5, since="2020-01-01")
    assert [(r["kind"], r["party"]) for r in rows] == [("denied", "Democrat"), ("visit", "Democrat"), ("denied", "Republican"), ("denied", "Democrat")]
    assert rows[0]["facility_code"] == "ADLNTCA" and all(r["date"] >= "2020" for r in rows)       # the 2019 release is read but not kept
    assert [c["status"] for c in cover] == ["read", "read", "read", "no_site"] and cover[0]["oldest"] == "2019-03-03" and cover[1]["listing"].startswith("/news/documentquery")
    assert stats["feeds_read"] == 3 and stats["no_feed"] == 1
    again, _, _ = vs.collect([REP], fetch, vs.facility_index(FAC), have, "2026-10-05", since="2020-01-01")
    assert again == []

def test_only_government_hosts():
    assert vs.feeds_for({"type": "sen", "url": "https://doe.example.com", "rss_url": "http://feeds.feedburner.com/doe"}) == []
    assert vs.parse_listing('<a href="https://evil.example.com/press-releases/fake-denied-entry">Rep. Doe Denied Entry to ICE Detention</a>', "https://doe.house.gov") == []
    assert vs.read_member({"type": "rep", "url": "https://doe.example.com", "rss_url": ""}, fetch, 3, "")[1] == "unreadable"

def test_recheck_drops_and_fixes_old_rows():
    old = [{"date": "2026-07-14", "official": "U.S. Representative Nellie Pou (NJ)", "kind": "denied", "title": "Pou Leads 27 Colleagues Calling on DHS to Protect Religious Rights in ICE Detention", "link": "l1", "facility_code": "", "collected": "d"},
           {"date": "2025-04-24", "official": "U.S. Representative Emily Randall (WA)", "kind": "visit", "title": "Randall Conducts Oversight Visit at Northwest ICE Detention Center", "link": "l2", "facility_code": "RND", "collected": "d"}]
    out = vs.recheck(old, vs.facility_index(FAC), {"U.S. Representative Emily Randall (WA)": "Democrat"})
    assert len(out) == 1 and out[0]["facility_code"] == "" and out[0]["party"] == "Democrat"

def test_facility_in_another_state_is_not_attached():
    ix = vs.facility_index({"BLG": {"name": "Bowling Green Hold Room"}}); fs = {"BLG": "KY"}
    assert vs.match_facility("Visits ICE Detention Facility in Bowling Green Detention, Virginia", ix, "Suhas Subramanyam", "VA", fs) == ""
    assert vs.match_facility("Visits Bowling Green Detention site", ix, "A B", "KY", fs) == "BLG"
    assert vs.match_facility("Virginia member visits Bowling Green Detention site in Kentucky", ix, "A B", "VA", fs) == "BLG"


def test_press_link_is_found_on_the_home_page_and_more_release_addresses_are_recognised():
    import visit_statements as v
    home = '<a href="/about">About</a><a href="https://www.example.senate.gov/newsroom/press">Press Releases</a>'
    assert v.discover(home, "https://www.example.senate.gov") == "/newsroom/press" and v.discover("<a href='/x'>Contact</a>", "https://www.example.senate.gov") == ""
    for good in ["/press-releases/senator-visits-ice-facility", "/news/releases/statement-on-detention-center", "/public/index.cfm/press-releases?ID=5E0B5A2C-1234",
                 "/newsroom/2026/9/member-denied-entry-to-ice-facility", "/news/documentsingle.aspx?DocumentID=1234"]:
        assert v.RELEASE.search(good), good
    for bad in ["/about", "/newsroom", "/news/2026", "/contact/email-me"]:
        assert not v.RELEASE.search(bad), bad


def test_classify_leaves_out_what_is_not_a_visit_to_a_detention_site():
    assert vs.classify("SCHUMER RECOGNIZES HISTORIC MIRACLE ON ICE 1980 OLYMPIC ICE HOCKEY TEAM, VISITS MT VAN HOEVENBERG", "") is None
    assert vs.classify("Newhouse Visits Southern Border, Sees Illegal Immigration Crisis Firsthand", "") is None
    assert vs.classify("Hoyer Visits U.S. Citizenship and Immigration Services (USCIS) Headquarters", "") is None
    assert vs.classify("Espaillat and Menendez Plan Wellness and Oversight Visit to Delaney Hall Detention Center", "") is None
    assert vs.classify("Rep. Doe and Colleagues Demand ICE Reverse New Restrictions on Oversight Visits to Detention Facilities", "") is None
    assert vs.classify("Scanlon's Oversight Visit to Moshannon Valley Processing Center Unlawfully Blocked by ICE", "") == "denied"
    assert vs.classify("ICYMI: Congresswoman Wilson Visits I.C.E. Krome Detention Center", "") == "visit"


def test_headlines_are_never_stored():
    import csv, pathlib
    rows = list(csv.DictReader(open(pathlib.Path(vs.__file__).resolve().parent.parent / "data" / "reference" / "oversight_statements.csv", encoding="utf-8")))
    assert rows and all(r["title"] == "" for r in rows)              # a headline once named a detained child
    kept = vs.recheck([{"date": "2026-01-01", "official": "U.S. Representative A B (TX)", "party": "", "kind": "visit", "title": "", "link": "https://b.house.gov/x", "facility_code": "PIC", "collected": "2026-01-02"}], {}, {})
    assert len(kept) == 1 and kept[0]["kind"] == "visit" and kept[0]["facility_code"] == "PIC"      # a row with no headline is kept, not re-judged
