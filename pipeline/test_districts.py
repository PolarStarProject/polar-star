import districts as d

REPLY = {"result": {"geographies": {"States": [{"STUSAB": "LA"}], "Counties": [{"NAME": "Rapides Parish"}],
         "120th Congressional Districts": [{"CD120": "05", "GEOID": "2205", "CDSESSN": "120", "STATE": "22", "BASENAME": "5", "NAME": "Congressional District 5"}]}}}

def test_reply_from_the_real_geocoder():
    assert d.parse(REPLY) == ("LA", "5", 120)            # this is the next Congress's map: districts.py must flag it, not show it

def test_at_large_and_empty():
    at_large = {"result": {"geographies": {"States": [{"STUSAB": "WY"}], "119th Congressional Districts": [{"BASENAME": "Congressional District (at Large)"}]}}}
    assert d.parse(at_large) == ("WY", "0", 119)
    assert d.parse({"result": {"geographies": {}}}) is None
