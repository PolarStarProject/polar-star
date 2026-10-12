"""Removals from ICE detention by destination country and month, from the same detention records the facility pages use.

Usage:  python pipeline/removals_country.py     (reads data/raw/detention-stints-latest.parquet; run by the refresh, step "removed_to")
Writes data/reference/removals_by_country.csv   month|country|removals   (counts of stays, never a person)

A removal is a stay (one continuous time in ICE detention) that ended with "Deported", counted in the month it ended, under the
departure country ICE recorded (citizenship country where no departure country is recorded; the meta file says how often).
The 20 largest countries over the whole file are kept; the rest are "Other". The newest month is partial and left out.
Removals of people never held in detention (for example straight from the border) are not in these records.
"""
import csv, json, sys
from pathlib import Path
import pandas as pd
from arrests_trend import pick

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
TOP = 20
NAME_FIX = {"China, Peoples Republic Of": "China", "Turkiye": "Turkey", "Korea, South": "South Korea", "Burma": "Myanmar"}     # ICE spellings -> common names


def by_country(s):
    """s: one row per stay with o (book-out), r (how it ended), k (departure country), z (citizenship country)."""
    last_seen = s.o.max()
    s = s[(s.r == "Deported") & s.o.notna()].copy()
    s["m"] = s.o.dt.tz_localize(None).dt.to_period("M") if getattr(s.o.dt, "tz", None) is not None else s.o.dt.to_period("M")
    end = (last_seen.tz_localize(None) if getattr(last_seen, "tzinfo", None) else last_seen).to_period("M") - 1
    s = s[s.m <= end]
    fill = s.k.isna() | (s.k.astype(str).str.strip() == "")
    s["country"] = s.k.where(~fill, s.z).fillna("Not recorded").astype(str).str.strip().str.title().replace(NAME_FIX)
    top = set(s.country.value_counts().head(TOP).index)
    s["country"] = s.country.where(s.country.isin(top), "Other")
    rows = [[str(m), c, int(n)] for (m, c), n in s.groupby(["m", "country"]).size().items()]
    return sorted(rows), int(fill.sum()), len(s)


if __name__ == "__main__":
    p = ROOT / "data" / "raw" / "detention-stints-latest.parquet"
    import pyarrow.parquet as pq
    cols = pq.read_schema(p).names
    dep = pick(cols, r"departure_country"); cit = pick(cols, r"citizenship_country", need=False)
    use = ["stay_ID", "stay_book_out_date_time", "stay_release_reason_simple", "duplicate_drop_row", "book_in_date_time", dep] + ([cit] if cit else [])
    d = pd.read_parquet(p, columns=use)
    d = d[d["duplicate_drop_row"] != True].dropna(subset=["stay_ID"])
    g = d.sort_values("book_in_date_time").groupby("stay_ID")
    s = g.agg(o=("stay_book_out_date_time", "last"), r=("stay_release_reason_simple", "last"), k=(dep, "last"), **({"z": (cit, "last")} if cit else {}))
    if "z" not in s: s["z"] = None
    rows, filled, n = by_country(s)
    months = sorted({r[0] for r in rows})
    if len(months) < 12 or not (5000 < sum(r[2] for r in rows if r[0] == months[-1]) < 200000): raise SystemExit(f"Implausible result ({len(months)} months). Nothing written.")
    with open(REF / "removals_by_country.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|"); w.writerow(["month", "country", "removals"]); w.writerows(rows)
    (REF / "removals_by_country_meta.json").write_text(json.dumps({"removals": n, "citizenship_used": filled, "first": months[0], "last": months[-1]}, indent=1), encoding="utf-8")
    print(f"{n:,} removals, {months[0]} to {months[-1]}; {filled:,} with no departure country (citizenship used)", file=sys.stderr)
