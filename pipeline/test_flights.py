import flights as f

AIR = [("AEX", 31.33, -92.55, "US", "Alexandria"), ("HRL", 26.23, -97.65, "US", "Harlingen"), ("AZA", 33.31, -111.66, "US", "Mesa"),
       ("MIA", 25.79, -80.29, "US", "Miami"), ("VSA", 17.99, -92.82, "MX", "Villahermosa"), ("NAS", 25.04, -77.47, "BS", "Nassau")]

def trace(points, cs="GXA6131", hexid="a1"):
    """points: (seconds, lat, lon, alt). Callsign rides on every point."""
    return {"icao": hexid, "r": "N1", "t": "A320", "timestamp": 1790899200.0,
            "trace": [[s, la, lo, alt, 400, 180, 0, 0, {"flight": cs + " "}] for s, la, lo, alt in points]}

def line(t0, a, b, n=8, low_ends=(True, True)):
    out = []
    for i in range(n):
        k = i / (n - 1); alt = 3000 if (i == 0 and low_ends[0]) or (i == n - 1 and low_ends[1]) else 34000
        out.append((t0 + i * 600, a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, alt))
    return out

def test_leg_between_two_airports():
    legs = f.describe(trace(line(0, (31.33, -92.55), (17.99, -92.82))), AIR)
    assert len(legs) == 1 and (legs[0]["origin"], legs[0]["dest"], legs[0]["origin_certain"], legs[0]["dest_certain"]) == ("AEX", "VSA", True, True)
    assert f.keep_ice_pattern(legs)[0]["kind"] == "international"

def test_signal_lost_mid_flight_is_one_leg():
    a = line(0, (31.33, -92.55), (26.0, -93.0), low_ends=(True, False))          # climbs out of AEX, signal lost over the Gulf
    b = line(9000, (20.0, -92.9), (17.99, -92.82), low_ends=(False, True))       # picked up again 70 minutes later, lands
    legs = f.describe(trace(a + b), AIR)
    assert len(legs) == 1 and (legs[0]["origin"], legs[0]["dest"]) == ("AEX", "VSA")

def test_ground_stop_separates_legs():
    a = line(0, (33.31, -111.66), (31.33, -92.55)); stop = [(a[-1][0] + 300, 31.33, -92.55, "ground")]
    b = line(a[-1][0] + 4000, (31.33, -92.55), (26.23, -97.65))
    legs = f.describe(trace(a + stop + b), AIR)
    assert [(l["origin"], l["dest"]) for l in legs] == [("AZA", "AEX"), ("AEX", "HRL")] and all(l["kind"] == "domestic" for l in f.keep_ice_pattern(legs))

def test_ordinary_charter_day_is_dropped():
    legs = f.describe(trace(line(0, (25.79, -80.29), (25.04, -77.47)), cs="GXA613"), AIR)
    assert len(legs) == 1 and f.keep_ice_pattern(legs) == []

def test_out_and_back_with_lost_signal_stay_two_legs():
    out = [(s, la, lo, alt, "GXA6138") for s, la, lo, alt in line(0, (31.33, -92.55), (18.6, -92.8), low_ends=(True, False))]
    back = [(s, la, lo, alt, "GXA6139") for s, la, lo, alt in line(9000, (18.6, -92.8), (31.33, -92.55), low_ends=(False, True))]
    back[0] = back[0][:4] + ("GXA6138",)                      # the first position back still shows the outbound callsign
    tr = {"icao": "a1", "r": "N1", "t": "A320", "timestamp": 1790899200.0,
          "trace": [[s, la, lo, alt, 400, 180, 0, 0, {"flight": cs}] for s, la, lo, alt, cs in out + back]}
    legs = f.describe(tr, AIR)
    assert [(l["origin"], l["dest"], l["callsign"]) for l in legs] == [("AEX", "VSA", "GXA6138"), ("VSA", "AEX", "GXA6139")]


def test_save_all_keeps_every_leg_and_leaves_no_part_file(tmp_path=None):
    import gzip, json, tempfile, pathlib, os
    import flights as f
    d = pathlib.Path(tempfile.mkdtemp()); p = d / "all_2026-01-01.json.gz"
    legs = [dict(origin_country="US", dest_country="US", staging=None), dict(origin_country="US", dest_country="MX", staging="HRL")]
    f.save_all(legs, p)
    back = json.load(gzip.open(p, "rt", encoding="utf-8"))
    assert [l["kind"] for l in back] == ["domestic", "international"] and os.listdir(d) == ["all_2026-01-01.json.gz"]


def test_fleet_extra_adds_other_days_only_for_aircraft_mostly_on_ice_patterns():
    import flights as f
    leg = lambda h, d, st="": {"hex": h, "date": d, "staging": st, "origin_country": "US", "dest_country": "US", "departed_utc": "10:00"}
    legs = [leg("ice", "2026-09-26", "AEX"), leg("ice", "2026-09-27", "HRL"), leg("ice", "2026-09-28"),            # 2 of 3 days on a pattern: the third counts
            leg("mix", "2026-09-26", "AEX"), leg("mix", "2026-09-27", "AEX")] + [leg("mix", f"2026-09-{d}") for d in (28, 29, 30)] + \
           [leg("air", f"2026-09-{d}") for d in (26, 27, 28)] + [leg("one", "2026-09-26", "AZA"), leg("one", "2026-09-27")]   # mix: 2 of 5; air: never; one: a single day
    out = f.fleet_extra(legs)
    assert [(l["hex"], l["date"]) for l in out] == [("ice", "2026-09-28")] and "2 other days" in out[0]["basis"] and out[0]["kind"] == "domestic"
