"""ICE arrests by month, by how the person came to ICE, and by state, from the Deportation Data Project's ICE arrest records.

Usage:  python pipeline/arrests_trend.py      (reads data/raw/arrests-latest.parquet; run by the refresh, step "arrests")
Writes, in data/reference/ (all "|" separated, counts only, never a person):
  arrests_by_month.csv         month|arrests|no_conviction_pct     no_conviction_pct: share ICE records as having no criminal conviction
  arrests_by_method.csv        month|method|arrests                how ICE recorded the arrest (e.g. 287(g) program, jail transfer, located)
  arrests_by_state_fy.csv      fy|state|arrests                    fiscal year runs October to September
  arrests_meta.json            the columns used, the first and last day in the file, rows dropped as likely duplicates

Likely duplicates (the same person within 24 hours, flagged by the project) are dropped. The newest month is partial and is
left out. Methods under 1% of all arrests are grouped as "Other". Column names change between releases, so each one is
looked for by pattern, and the run stops if a needed column is not found rather than guessing.
"""
import csv, json, re, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"


def pick(cols, *patterns, need=True):
    for p in patterns:
        hit = [c for c in cols if re.fullmatch(p, c, re.I)]
        if hit: return hit[0]
    if need: raise SystemExit(f"no column matching {patterns} in {sorted(cols)}")
    return None


def fy_of(ts):
    return ts.year + (1 if ts.month >= 10 else 0)


def summarize(d, date, method, state, crim):
    """d: one row per arrest. Returns (months, methods, states, first, last). Only complete months."""
    d = d.dropna(subset=[date])
    when = pd.to_datetime(d[date], errors="coerce", utc=True).dt.tz_localize(None)
    d = d.assign(_w=when).dropna(subset=["_w"])
    first, last = d["_w"].min(), d["_w"].max()
    end = last.to_period("M") - 1                                   # newest month is partial
    d = d[d["_w"].dt.to_period("M") <= end]
    d = d.assign(_m=d["_w"].dt.to_period("M").astype(str))
    months = []
    for m, g in d.groupby("_m"):
        nc = round(100 * g[crim].astype(str).str.match(r"\s*3\b|.*other immigration violator", case=False).mean()) if crim else ""
        months.append([m, len(g), nc])
    methods = []
    if method:
        lab = d[method].fillna("Not recorded").astype(str).str.strip().replace("", "Not recorded")
        share = lab.value_counts(normalize=True)
        keep = set(share[share >= 0.01].index)
        lab = lab.where(lab.isin(keep), "Other")
        for (m, k), n in d.assign(_k=lab).groupby(["_m", "_k"]).size().items(): methods.append([m, k, int(n)])
    states = []
    if state:
        st = d[state].fillna("").astype(str).str.strip().str.upper().replace("", "Not recorded")
        for (y, s), n in d.assign(_fy=d["_w"].map(fy_of), _s=st).groupby(["_fy", "_s"]).size().items(): states.append([int(y), s, int(n)])
    return months, methods, states, first, last


def write(name, rows, header):
    with open(REF / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|"); w.writerow(header); w.writerows(rows)


if __name__ == "__main__":
    d = pd.read_parquet(ROOT / "data" / "raw" / "arrests-latest.parquet")
    cols = list(d.columns)
    print("columns:", ", ".join(cols), file=sys.stderr)       # names only, for the log
    date = pick(cols, r"apprehension_date(_time)?", r"arrest_date(_time)?", r".*apprehension.*date.*")
    method = pick(cols, r"apprehension_method", r"arrest_method", r".*apprehension_method.*", need=False)
    state = pick(cols, r"apprehension_state_filled_in", r"apprehension_state", r"arrest_state", need=False)
    crim = pick(cols, r"apprehension_criminality", r".*criminality.*", need=False)
    dup = pick(cols, r"duplicate_drop_row", need=False)
    n0 = len(d)
    if dup: d = d[d[dup] != True]
    months, methods, states, first, last = summarize(d, date, method, state, crim)
    if len(months) < 6 or not (5000 < months[-1][1] < 500000): raise SystemExit(f"Implausible result ({len(months)} months, last {months[-1] if months else None}). Nothing written.")
    write("arrests_by_month.csv", months, ["month", "arrests", "no_conviction_pct"])
    write("arrests_by_method.csv", methods, ["month", "method", "arrests"])
    write("arrests_by_state_fy.csv", states, ["fy", "state", "arrests"])
    (REF / "arrests_meta.json").write_text(json.dumps({"columns": {"date": date, "method": method, "state": state, "criminality": crim},
        "first": str(first.date()), "last": str(last.date()), "rows": n0, "dropped_duplicates": n0 - len(d), "source": "https://github.com/deportationdata/ice"}, indent=1), encoding="utf-8")
    print(f"{len(months)} months, {months[0][0]} to {months[-1][0]}; last month {months[-1][1]:,} arrests; methods {sorted({m[1] for m in methods})}", file=sys.stderr)
