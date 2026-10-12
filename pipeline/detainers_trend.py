"""ICE detainers by month, by kind, by state and by how they ended, from the Deportation Data Project's ICE detainer records.

A detainer is ICE asking a jail or prison to hold someone, or to tell ICE before releasing them, so ICE can take custody.

Usage:  python pipeline/detainers_trend.py     (reads data/raw/detainers-latest.parquet; run by the refresh, step "detainers")
Writes, in data/reference/ (all "|" separated, counts only, never a person):
  detainers_by_month.csv     month|detainers|hold_requests|notice_requests|no_conviction_pct|violent_pct
  detainers_by_state_fy.csv  fy|state|detainers                 the state of the jail or prison that received it
  detainers_by_lift.csv      fy|reason|detainers                how detainers ended (lift reason as ICE records it); reasons under 1% are "Other"
  detainers_meta.json        columns used, first and last day in the file, rows dropped as likely duplicates

Likely duplicates (same person, same facility, within 24 hours, flagged by the project) are dropped. The newest month is partial
and left out, and so is any trailing month under half the median of the six before it (a release cut off mid-month). Columns are found by pattern; the run stops if the date column is missing rather than guessing.
"""
import json, re, sys
from pathlib import Path
import pandas as pd
from arrests_trend import pick, fy_of, write

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"


def summarize(d, date, kind, state, conv, lift):
    """d: one row per detainer -> (months, states, lifts, first, last). Only complete months."""
    when = pd.to_datetime(d[date], errors="coerce", utc=True).dt.tz_localize(None)
    d = d.assign(_w=when).dropna(subset=["_w"])
    first, last = d["_w"].min(), d["_w"].max()
    d = d[d["_w"].dt.to_period("M") <= last.to_period("M") - 1]
    d = d.assign(_m=d["_w"].dt.to_period("M").astype(str))
    n = d["_m"].value_counts().sort_index()                 # a release can stop early in a month and carry a few later records:
    while len(n) > 7 and n.iloc[-1] < 0.5 * n.iloc[-7:-1].median(): n = n.iloc[:-1]     # trailing months far below the months before are cut
    d = d[d["_m"] <= n.index[-1]]
    months = []
    for m, g in d.groupby("_m"):
        k = g[kind].fillna("").astype(str) if kind else pd.Series([""] * len(g))
        hold, notice = int(k.str.contains("detainer request", case=False).sum()), int(k.str.contains("notification", case=False).sum())
        c = g[conv].fillna("").astype(str).str.lower() if conv else None
        months.append([m, len(g), hold if kind else "", notice if kind else "",
                       round(100 * (c == "none").mean()) if conv else "", round(100 * (c == "violent crime").mean()) if conv else ""])
    states = []
    if state:
        st = d[state].fillna("").astype(str).str.strip().str.upper().replace("", "Not recorded")
        for (y, s), n in d.assign(_fy=d["_w"].map(fy_of), _s=st).groupby(["_fy", "_s"]).size().items(): states.append([int(y), s, int(n)])
    lifts = []
    if lift:
        lab = d[lift].fillna("Not lifted or not recorded").astype(str).str.strip().replace("", "Not lifted or not recorded")
        share = lab.value_counts(normalize=True); keep = set(share[share >= 0.01].index)
        lab = lab.where(lab.isin(keep), "Other")
        for (y, r), n in d.assign(_fy=d["_w"].map(fy_of), _r=lab).groupby(["_fy", "_r"]).size().items(): lifts.append([int(y), r, int(n)])
    return months, states, lifts, first, last


if __name__ == "__main__":
    d = pd.read_parquet(ROOT / "data" / "raw" / "detainers-latest.parquet")
    cols = list(d.columns)
    print("columns:", ", ".join(cols), file=sys.stderr)       # names only, for the log
    date = pick(cols, r"detainer_prepare_date", r"detainer_prepared_date", r".*detainer.*date.*")
    kind = pick(cols, r"detainer_type", need=False)
    state = pick(cols, r"facility_state", r"state", need=False)
    conv = pick(cols, r"conviction", need=False)
    lift = pick(cols, r"detainer_lift_reason", r".*lift_reason.*", need=False)
    dup = pick(cols, r"duplicate_drop_row", need=False)
    n0 = len(d)
    if dup: d = d[d[dup] != True]
    months, states, lifts, first, last = summarize(d, date, kind, state, conv, lift)
    if len(months) < 6 or not (1000 < months[-1][1] < 500000): raise SystemExit(f"Implausible result ({len(months)} months, last {months[-1] if months else None}). Nothing written.")
    write("detainers_by_month.csv", months, ["month", "detainers", "hold_requests", "notice_requests", "no_conviction_pct", "violent_pct"])
    write("detainers_by_state_fy.csv", states, ["fy", "state", "detainers"])
    write("detainers_by_lift.csv", lifts, ["fy", "reason", "detainers"])
    (REF / "detainers_meta.json").write_text(json.dumps({"columns": {"date": date, "kind": kind, "state": state, "conviction": conv, "lift": lift},
        "first": str(first.date()), "last": str(last.date()), "rows": n0, "dropped_duplicates": n0 - len(d), "source": "https://github.com/deportationdata/ice"}, indent=1), encoding="utf-8")
    print(f"{len(months)} months, {months[0][0]} to {months[-1][0]}; last month {months[-1][1]:,} detainers", file=sys.stderr)
