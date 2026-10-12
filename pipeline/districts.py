"""Which congressional district each facility is in, from the Census Bureau's public geocoder.

Usage (on Windows):  python pipeline\\districts.py
Writes data/reference/facility_districts.csv. About 800 lookups, a few minutes. Safe to re-run: finished rows are kept.

The geocoder's "current" answer can be the map for the NEXT Congress once a state has redrawn its lines, which
would name the wrong member. CONGRESS says which map to accept; rows from any other map are written but flagged.
"""
import csv, json, sys, time, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent
CONGRESS = 119                    # the Congress whose members are in legislators-current.csv; 120th is seated January 2027
VINTAGES = ["Current_Current", "ACS2024_Current", "ACS2023_Current"]
URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates?"


def parse(payload):
    """(state, district, congress number) from a geocoder reply, or None."""
    geo = payload.get("result", {}).get("geographies", {})
    key = next((k for k in geo if k.endswith("Congressional Districts")), None)
    if not key or not geo[key] or not geo.get("States"): return None
    cd = geo[key][0]
    num = cd.get("BASENAME", "")
    district = "0" if not num.isdigit() else str(int(num))           # at-large and delegate seats have no number
    return geo["States"][0]["STUSAB"], district, int(key.split("th")[0])


def lookup(lat, lon):
    best = None
    for v in VINTAGES:
        q = urllib.parse.urlencode({"x": lon, "y": lat, "benchmark": "Public_AR_Current", "vintage": v, "layers": "all", "format": "json"})
        try:
            got = parse(json.load(urllib.request.urlopen(URL + q, timeout=60)))
        except Exception:
            continue
        if got and got[2] == CONGRESS: return got
        best = best or got
    return best


def main():
    out = ROOT / "data" / "reference" / "facility_districts.csv"
    done = {r["code"]: r for r in csv.DictReader(open(out, encoding="utf-8"))} if out.exists() else {}
    fac = pd.read_parquet(ROOT / "data" / "raw" / "facilities-latest.parquet", columns=["detention_facility_code", "latitude", "longitude"]).dropna()
    for i, (code, lat, lon) in enumerate(fac.itertuples(index=False)):
        if code in done and done[code]["congress"] == str(CONGRESS): continue
        got = lookup(lat, lon)
        if got: done[code] = {"code": code, "state": got[0], "district": got[1], "congress": got[2]}
        if i % 50 == 0:
            print(i, "of", len(fac)); _write(out, done)
        time.sleep(0.2)
    _write(out, done)
    wrong = sum(1 for r in done.values() if str(r["congress"]) != str(CONGRESS))
    print(f"{len(done)} facilities placed in a district; {wrong} came back on a different Congress's map and will not be shown")


def _write(out, done):
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "state", "district", "congress"]); w.writeheader(); w.writerows(done[k] for k in sorted(done))


if __name__ == "__main__":
    main()
