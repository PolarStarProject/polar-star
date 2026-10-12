"""People in ICE detention by month, from the same detention records the facility pages use.

Usage:  python pipeline/custody_trend.py        (reads data/raw/detention-stints-latest.parquet, about a minute)
Writes data/reference/custody_by_month.csv. Counts are stays (one continuous time in ICE detention), never people by name.

  held         stays open at 00:00 UTC on the first day of the month
  pct_no_crim  share of those ICE records as "Other Immigration Violator": no criminal conviction and no pending charge on ICE's record
  book_ins     stays that began in the month;  deported / released: stays that ended that way in the month
Only complete months are written. The file starts in October 2023: it holds stays that were open on or after
1 October 2022, and the first year is left out as a margin.
"""
import csv, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIRST = "2023-10"


def by_month(s, first=FIRST):
    """s: one row per stay with i (book-in), o (book-out or NaT), r (how it ended), c (ICE's criminality label)."""
    last_seen = max(s.i.max(), s.o.max())
    end = (last_seen.tz_localize(None).to_period("M") - 1)            # the newest month is partial: drop it
    rows = []
    for m in pd.period_range(first, end, freq="M"):
        d, e = pd.Timestamp(m.start_time, tz="UTC"), pd.Timestamp((m + 1).start_time, tz="UTC")
        held = s[(s.i < d) & ((s.o >= d) | s.o.isna())]; out = s[(s.o >= d) & (s.o < e)]
        rows.append([str(m), len(held), round(100 * held.c.astype(str).str.startswith("3").mean()) if len(held) else 0,
                     int(((s.i >= d) & (s.i < e)).sum()), int((out.r == "Deported").sum()), int((out.r == "Released").sum())])
    return rows


if __name__ == "__main__":
    d = pd.read_parquet(ROOT / "data" / "raw" / "detention-stints-latest.parquet",
                        columns=["stay_ID", "stay_book_in_date_time", "stay_book_out_date_time", "stay_release_reason_simple", "book_in_criminality", "duplicate_drop_row", "book_in_date_time"])
    d = d[d["duplicate_drop_row"] != True].dropna(subset=["stay_ID", "stay_book_in_date_time"])
    s = d.sort_values("book_in_date_time").groupby("stay_ID").agg(i=("stay_book_in_date_time", "first"), o=("stay_book_out_date_time", "first"), r=("stay_release_reason_simple", "last"), c=("book_in_criminality", "first"))
    rows = by_month(s)
    if len(rows) < 12 or not (20000 < rows[-1][1] < 200000): raise SystemExit(f"Implausible result ({len(rows)} months, last held {rows[-1][1] if rows else None}). Nothing written.")
    with open(ROOT / "data" / "reference" / "custody_by_month.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["month", "held", "pct_no_crim", "book_ins", "deported", "released"]); w.writerows(rows)
    print(f"{len(rows)} months, {rows[0][0]} to {rows[-1][0]}; held on the first of the last month: {rows[-1][1]:,}", file=sys.stderr)
