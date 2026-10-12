"""Immigration court results for people in detention, by hearing location. Counts only, never a person.

Usage:  python pipeline/court_outcomes.py [--file cases.parquet]
Source: the Deportation Data Project's cleaned copy of the immigration courts' (EOIR) case data, public domain (CC0):
https://github.com/deportationdata/eoir  (one row per removal case; rebuilt when EOIR posts its monthly file).
Window: the 24 months up to the newest court completion date in the file.
Writes data/reference/court_by_location.csv ("|" separated), one row per hearing location:
  bond_n       cases whose LAST bond decision fell in the window, then how it ended:
               granted / denied (on the merits) / no_jurisdiction (the judge ruled there was no power to set bond) / withdrawn (or moot)
  cases_n      cases completed in the window while the person was detained, then:
               removed / voluntary (departure) / relief (allowed to stay or protected from return) / ended_other (dropped, closed, moved)
  represented  of cases_n, how many had a lawyer on record at any point
and data/reference/court_meta.json (window, source version). The download is skipped when the source file has not changed.
"""
import csv, datetime as dt, json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
URL = "https://media.githubusercontent.com/media/deportationdata/eoir/main/data/cases.parquet"
BOND = {"Bond Granted-Amount Decreased": "granted", "Bond Granted-Own Recognizance": "granted", "Amelioration Granted": "granted", "Flores - Release": "granted",
        "Bond Denied- No Change (No Bond Set By DHS)": "denied", "Bond Denied- No Change (DHS Bond Amount Unchanged)": "denied", "Amelioration Denied": "denied", "Bond Amount Increased": "denied", "Flores - No Release": "denied",
        "Bond Denied-No Jurisdiction": "no_jurisdiction", "Amelioration Denied-No Jurisdiction": "no_jurisdiction",
        "Bond Request Withdrawn": "withdrawn", "Bond Denied-Moot": "withdrawn"}
OUT = {"Remove": "removed", "Voluntary Departure": "voluntary",
       "Relief Granted": "relief", "Grant": "relief", "Remove-INA Withholding Granted": "relief", "Remove-CAT Withholding Granted": "relief", "Remove-CAT Deferral Granted": "relief", "Grant-CAT Deferral": "relief", "Grant-CAT Withholding": "relief"}
FIELDS = ["code", "name", "bond_n", "granted", "denied", "no_jurisdiction", "withdrawn", "cases_n", "removed", "voluntary", "relief", "ended_other", "represented"]


def summarise(d, today):
    """d: one row per case with the columns read in main(). Returns (rows, window start, window end)."""
    import pandas as pd
    for k in ("ij_completion_date_last", "bond_completion_date_last"): d[k] = pd.to_datetime(d[k], errors="coerce")
    end = d.ij_completion_date_last[d.ij_completion_date_last <= pd.Timestamp(today)].max()      # a few rows carry dates in the future: ignored
    start = end - pd.DateOffset(months=24) + pd.Timedelta(days=1)
    rows = {}
    def row(code, name): return rows.setdefault(code, dict({k: 0 for k in FIELDS}, code=code, name=name or ""))
    b = d[(d.bond_completion_date_last >= start) & (d.bond_completion_date_last <= end) & d.bond_hearing_location_code_last.notna()]
    b = b.assign(kind=b.bond_decision_last.map(BOND))
    for (code, name, kind), n in b.dropna(subset=["kind"]).groupby(["bond_hearing_location_code_last", "bond_hearing_location_last", "kind"], dropna=False).size().items():
        r = row(code, name); r[kind] += int(n); r["bond_n"] += int(n)
    c = d[(d.ij_completion_date_last >= start) & (d.ij_completion_date_last <= end) & (d.custody_code == "D") & d.hearing_location_code_last.notna() & d.case_outcome.notna()]
    c = c.assign(kind=c.case_outcome.map(OUT).fillna("ended_other"))
    for (code, name, kind), n in c.groupby(["hearing_location_code_last", "hearing_location_last", "kind"], dropna=False).size().items():
        r = row(code, name); r[kind] += int(n); r["cases_n"] += int(n)
    for (code, name), n in c[c.represented == True].groupby(["hearing_location_code_last", "hearing_location_last"], dropna=False).size().items():
        row(code, name)["represented"] += int(n)
    return sorted(rows.values(), key=lambda r: -(r["cases_n"] + r["bond_n"])), start.date().isoformat(), end.date().isoformat()


def main(argv):
    import pandas as pd
    meta_p = REF / "court_meta.json"; meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    path = argv[argv.index("--file") + 1] if "--file" in argv else None
    etag = ""
    if not path:
        head = urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=60)
        etag = head.headers.get("ETag", "") or head.headers.get("Content-Length", "")
        if etag and etag == meta.get("etag") and (REF / "court_by_location.csv").exists():
            meta["checked"] = str(dt.date.today()); meta_p.write_text(json.dumps(meta, indent=1), encoding="utf-8"); print("source unchanged since the last read; nothing to do"); return
        path = str(ROOT / "data" / "raw" / "eoir_cases.parquet"); Path(path).parent.mkdir(parents=True, exist_ok=True)
        print("downloading the case file (about 470 MB)", flush=True); urllib.request.urlretrieve(URL, path)
    d = pd.read_parquet(path, columns=["custody_code", "represented", "case_outcome", "hearing_location_code_last", "hearing_location_last", "ij_completion_date_last",
                                       "bond_hearing_location_code_last", "bond_hearing_location_last", "bond_completion_date_last", "bond_decision_last"])
    rows, start, end = summarise(d, dt.date.today())
    tb, tc = sum(r["bond_n"] for r in rows), sum(r["cases_n"] for r in rows)
    if tb < 20000 or tc < 50000 or (dt.date.today() - dt.date.fromisoformat(end)).days > 200: raise SystemExit(f"Implausible result ({tb} bond decisions, {tc} cases, window ends {end}). Nothing written.")
    with open(REF / "court_by_location.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    meta_p.write_text(json.dumps({"from": start, "to": end, "etag": etag, "read": str(dt.date.today()), "checked": str(dt.date.today()), "bond_n": tb, "cases_n": tc}, indent=1), encoding="utf-8")
    print(f"{start} to {end}: {tb:,} bond decisions and {tc:,} detained cases at {len(rows)} hearing locations")


if __name__ == "__main__": main(sys.argv)
