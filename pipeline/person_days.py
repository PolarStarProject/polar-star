"""Days of detention served at each facility in each month, from the detention records. This is the denominator for rates.

Usage:  python pipeline/person_days.py     (reads data/raw/detention-stints-latest.parquet, about a minute)
Writes data/reference/facility_person_days.csv: facility_code, month, person_days. Counts only, never a person.

One stint is one continuous time at one facility. Its days are split across the months it spans. A stint with no
book-out is counted up to the newest timestamp in the file. Only complete months are written, starting October 2022:
the file holds stays open on or after 1 October 2022, so earlier months would be undercounted.
"""
import csv, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIRST = "2022-10"


def person_days(d, first=FIRST, last=None):
    """d: columns code, i (book-in), o (book-out or NaT), all UTC. Returns {(code, 'YYYY-MM'): days} for complete months."""
    seen = max(d.i.max(), d.o.max())
    end = pd.Period(last, "M") if last else seen.tz_localize(None).to_period("M") - 1
    ns = lambda x: x.dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()
    i, o = ns(d.i), ns(d.o.fillna(seen)); cat = pd.Categorical(d.code); cc = cat.codes; out = {}
    for m in pd.period_range(first, end, freq="M"):
        a, b = m.start_time.value, (m + 1).start_time.value
        days = np.clip(np.minimum(o, b) - np.maximum(i, a), 0, None) / 86400e9
        for k, v in zip(cat.categories, np.bincount(cc, weights=days, minlength=len(cat.categories))):
            if v >= 0.5: out[(k, str(m))] = round(float(v))
    return out


if __name__ == "__main__":
    d = pd.read_parquet(ROOT / "data" / "raw" / "detention-stints-latest.parquet",
                        columns=["detention_facility_code", "book_in_date_time", "book_out_date_time", "duplicate_drop_row"])
    d = d[d["duplicate_drop_row"] != True].dropna(subset=["detention_facility_code", "book_in_date_time"])
    d = d.rename(columns={"detention_facility_code": "code", "book_in_date_time": "i", "book_out_date_time": "o"})
    bad = int((d.o < d.i).sum()); d = d[~(d.o < d.i)]
    pd_ = person_days(d)
    months = sorted({m for _, m in pd_}); tot = sum(v for (_, m), v in pd_.items() if m == months[-1]) / pd.Period(months[-1], "M").days_in_month
    if len(months) < 12 or not (20000 < tot < 200000): raise SystemExit(f"Implausible result ({len(months)} months, last month average {tot:.0f} held). Nothing written.")
    with open(ROOT / "data" / "reference" / "facility_person_days.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["facility_code", "month", "person_days"])
        for (k, m), v in sorted(pd_.items()): w.writerow([k, m, v])
    print(f"{len(pd_)} rows, {len({k for k, _ in pd_})} facilities, {months[0]} to {months[-1]}; last month average {tot:,.0f} held a day; {bad} stints ending before they began left out")
