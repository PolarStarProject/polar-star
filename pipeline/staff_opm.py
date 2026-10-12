"""Staff and base pay at the agencies that arrest, hold, judge and remove people, from OPM's federal workforce files.

Usage:  python pipeline/staff_opm.py        (run by the refresh, step "staff"; downloads about 30 monthly files, a few minutes)
Source: https://data.opm.gov  (OPM, Federal Workforce Data; monthly snapshots of everyone on the federal civilian rolls, no names)
Writes, in data/reference/ (all "|" separated, counts and sums only):
  staff_by_month.csv     month|agency|employees                  everyone on the rolls on the last day of the month
Pay is not summed: OPM withholds pay for law enforcement jobs (most of ICE and CBP), so a sum would be far too low.
Payroll comes from the agencies' account reports instead (money_object_class.py).
  staff_by_series.csv    month|agency|series|employees            the largest job series at each agency (e.g. 1801 deportation officers, 1896 Border Patrol agents)
  staff_flows.csv        month|agency|hires|separations           people who joined and left in the month
  staff_meta.json        which files were read, and when

Agencies are found by name in OPM's "agency subelement" field, so a renamed office is noticed (the run stops) rather than silently missed.
A file is downloaded again only when OPM posts a new version of it.
"""
import csv, datetime as dt, io, json, re, sys, time
from pathlib import Path
from identity import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://data.opm.gov/api/v1/files"
AGENCIES = {"ICE": r"IMMIGRATION AND CUSTOMS ENFORCEMENT", "CBP": r"CUSTOMS AND BORDER PROTECTION", "USCIS": r"CITIZENSHIP AND IMMIGRATION",
            "EOIR": r"IMMIGRATION REVIEW", "USMS": r"MARSHALS SERVICE"}
SERIES_TOP = 6          # job series kept per agency; the rest are added together as "other"


def agency_of(subelement):
    s = (subelement or "").upper()
    for k, pat in AGENCIES.items():
        if re.search(pat, s): return k
    return None


def months_wanted(listing, today):
    """The files to read: every month from September 2024 on, and each September from 2019 to 2023 for a baseline. Newest version only."""
    best = {}
    for f in listing:
        if not f.get("current"): continue
        ym = f"{f['year']}-{int(f['month']):02d}"
        if ym >= "2024-09" or (f["month"] in ("09", "9") and "2019" <= f["year"] <= "2023"):
            if ym not in best or f["version"] > best[ym]["version"]: best[ym] = f
    return dict(sorted(best.items()))


def summarize_employment(df, ym):
    """df: one row per employee, with agency_subelement, occupational_series_code (and count)."""
    df = df.assign(_a=df["agency_subelement"].map(agency_of)).dropna(subset=["_a"])
    n = df["count"].astype(float) if "count" in df else 1.0
    df = df.assign(_n=n)
    by, series = [], []
    for a, g in df.groupby("_a"):
        by.append([ym, a, int(g["_n"].sum())])
        s = g.groupby(g["occupational_series_code"].astype(str).str.zfill(4))["_n"].sum().sort_values(ascending=False)
        top = s.head(SERIES_TOP)
        series += [[ym, a, k, int(v)] for k, v in top.items()]
        if len(s) > SERIES_TOP: series.append([ym, a, "other", int(s.iloc[SERIES_TOP:].sum())])
    return by, series


def flows(df, ym):
    df = df.assign(_a=df["agency_subelement"].map(agency_of)).dropna(subset=["_a"])
    n = df["count"].astype(float) if "count" in df else 1.0
    return {a: int(v) for a, v in df.assign(_n=n).groupby("_a")["_n"].sum().items()}


def read_csv(name):
    p = REF / name
    return list(csv.DictReader(open(p, encoding="utf-8"), delimiter="|")) if p.exists() else []


def write_csv(name, rows, header):
    with open(REF / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|"); w.writerow(header); w.writerows(rows)


def main():
    import requests, pandas as pd
    s = requests.Session(); s.headers["User-Agent"] = USER_AGENT
    meta_p = REF / "staff_meta.json"; meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {"files": {}}
    def get(url, tries=4):
        for i in range(tries):
            try:
                r = s.get(url, timeout=300)
                if r.status_code == 200: return r
                err = f"{r.status_code} {r.text[:120]}"
            except Exception as e: err = str(e)[:120]
            time.sleep(10 * (i + 1))
        raise RuntimeError(f"OPM did not answer {url}: {err}")
    def download(dataset, f):
        for base in (API, "https://data.opm.gov/v1/files"):
            try:
                r = get(f"{base}/{dataset}/{f['year']}/{int(f['month'])}/{f['version']}/download", tries=2)
                if r.content[:4] == b"PAR1": return r.content
            except RuntimeError: continue
        raise RuntimeError(f"{dataset} {f['year']}-{f['month']}: no parquet file")
    cols_emp = ["agency_subelement", "occupational_series_code", "count"]
    by, series, fl = read_csv("staff_by_month.csv"), read_csv("staff_by_series.csv"), {(r["month"], r["agency"]): r for r in read_csv("staff_flows.csv")}
    today = dt.date.today().isoformat(); done = 0
    for dataset in ("employment", "accessions", "separations"):
        want = months_wanted(get(f"{API}/{dataset}?current=true").json(), today)
        if dataset != "employment": want = {k: v for k, v in want.items() if k >= "2024-10"}
        for ym, f in want.items():
            key = f"{dataset}/{ym}"
            if meta["files"].get(key) == f["filename"]: continue
            import pyarrow.parquet as pq
            buf = io.BytesIO(download(dataset, f)); have = pq.read_schema(buf).names; buf.seek(0)
            names = [c for c in cols_emp if c in have]
            if "agency_subelement" not in names: raise SystemExit(f"{key}: no agency_subelement column in {have[:40]}")
            df = pq.read_table(buf, columns=names).to_pandas()          # only the three columns used; nothing else is kept
            if dataset == "employment":
                b, sr = summarize_employment(df, ym)
                if not any(r[1] == "ICE" for r in b): raise SystemExit(f"{key}: no ICE staff found; OPM may have renamed the office. Nothing written.")
                by = [r for r in by if r["month"] != ym] + [dict(zip(["month", "agency", "employees"], r)) for r in b]
                series = [r for r in series if r["month"] != ym] + [dict(zip(["month", "agency", "series", "employees"], r)) for r in sr]
            else:
                for a, n in flows(df, ym).items():
                    row = fl.setdefault((ym, a), {"month": ym, "agency": a, "hires": "", "separations": ""})
                    row["hires" if dataset == "accessions" else "separations"] = n
            meta["files"][key] = f["filename"]; done += 1
            print(f"{key}: read", flush=True)
    write_csv("staff_by_month.csv", [[r["month"], r["agency"], r["employees"]] for r in sorted(by, key=lambda r: (r["month"], r["agency"]))], ["month", "agency", "employees"])
    write_csv("staff_by_series.csv", [[r["month"], r["agency"], r["series"], r["employees"]] for r in sorted(series, key=lambda r: (r["month"], r["agency"], -int(r["employees"])))], ["month", "agency", "series", "employees"])
    write_csv("staff_flows.csv", [[r["month"], r["agency"], r["hires"], r["separations"]] for k, r in sorted(fl.items())], ["month", "agency", "hires", "separations"])
    meta["read"] = today; meta_p.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"staff: {done} files read; {len({r['month'] for r in by})} months on file", flush=True)


if __name__ == "__main__": main()
