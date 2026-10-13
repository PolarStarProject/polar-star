"""Checks for reading the Justice Department's pro bono list: two columns of boxes per court page, boxes split on their
drawn borders, names marked * / ** / ***, and boxes that run onto the next page."""
from eoir_probono import court_short, box_fields, parse_pages, merge

HDR = [(43, 21, 8.0, False, "*  Non-Profit Organization"), (176, 20, 16.0, True, "List of Pro Bono Legal Service Providers"),
       (466, 21, 11.0, False, "Updated October 2026")]


def page(court, place, left, right, borders=None):
    """A court page: title, place line, then each column's lines as (y, bold, text)."""
    sp = HDR + [(228, 55, 14.0, True, court), (46, 72, 11.0, True, place)]
    sp += [(46, y, 11.0, b, t) for y, b, t in left] + [(298, y, 11.0, b, t) for y, b, t in right]
    return sorted(sp, key=lambda r: (r[1], r[0])), borders or {0: [73, 88], 1: [73, 88]}


def test_court_names():
    assert court_short("Eloy Immigration Court") == "Eloy"
    assert court_short("Los Angeles Immigration Courts Juvenile Docket") == "Los Angeles juvenile docket"
    assert court_short("Stewart Detention Center Immigration Court") == "Stewart Detention Center"


def test_box_fields_kind_phone_city_and_two_line_names():
    f = box_fields([("Florence Immigrant and Refugee Rights Project*", True), ("P.O. Box 86299", False), ("Tucson, AZ 85754", False), ("Tel: (602) 307-1008", False)])
    assert f == {"name": "Florence Immigrant and Refugee Rights Project", "kind": "nonprofit", "phone": "(602) 307-1008", "city": "Tucson, AZ"}
    f = box_fields([("ABA Commission on Immigration Detention", True), ("Information Hotline**", True), ("Washington, DC 20036", False), ("hotline at 1 (855) 641-6081", False)])
    assert f["name"] == "ABA Commission on Immigration Detention Information Hotline" and f["kind"] == "referral" and f["phone"] == "(855) 641-6081"
    f = box_fields([("Loyola University New Orleans College of Law,", True), ("Stuart H. Smith Law Clinic*", False), ("New Orleans, LA 70118", False)])
    assert f["name"] == "Loyola University New Orleans College of Law, Stuart H. Smith Law Clinic" and f["kind"] == "nonprofit"
    assert box_fields([("The Northwest Immigrant Rights Project* (cont.)", True)])["name"] == "The Northwest Immigrant Rights Project"
    assert box_fields([("no bold name here", False)]) is None


def test_two_columns_never_mix_and_bold_inside_a_box_is_not_a_provider():
    p1 = page("Stewart Detention Center Immigration Court", "Lumpkin, Georgia",
              left=[(88, True, "Amica Center for Immigrant Rights*"), (133, False, "Washington, DC 20036"), (148, False, "Tel: (202) 331-3320"),
                    (208, True, "Families"), (223, False, "• free consultations")],                       # bold words in the notes
              right=[(88, True, "Immigration Justice Campaign**"), (148, False, "Tel: (202) 946-8271"), (163, False, "Washington, DC 20005")],
              borders={0: [73, 88, 400], 1: [73, 88, 300]})
    rows, ed = parse_pages([p1])
    assert ed == "2026-10"
    assert [(st, c, f["name"], f["phone"]) for st, c, f in rows] == [("GA", "Stewart Detention Center", "Amica Center for Immigrant Rights", "(202) 331-3320"),
                                                                     ("GA", "Stewart Detention Center", "Immigration Justice Campaign", "(202) 946-8271")]


def test_box_cut_by_page_break_fills_from_next_page_and_merges_courts():
    p1 = page("El Paso Immigration Court", "El Paso, Texas (page 1 of 2)",
              left=[(88, True, "Las Americas Immigrant Advocacy Center*"), (118, False, "1500 E. Yandell Dr.")], right=[])
    p2 = page("El Paso Immigration Court", "El Paso, Texas (page 2 or 2)",
              left=[(88, False, "El Paso, TX 79902"), (103, False, "Tel: (915) 544-5126")], right=[])
    p3 = page("El Paso Detained Immigration Court", "El Paso, Texas",
              left=[(88, True, "Las Americas Immigrant Advocacy Center*"), (148, False, "Tel: (915) 544-5126")], right=[])
    rows, _ = parse_pages([p1, p2, p3])
    assert len(rows) == 2 and rows[0][2]["phone"] == "(915) 544-5126" and rows[0][2]["city"] == "El Paso, TX"
    m = merge(rows)
    assert len(m) == 1 and m[0]["state"] == "TX" and m[0]["courts"] == "El Paso/El Paso Detained"
