"""Download the public Deportation Data Project files into data/raw/.

Usage:  python pipeline/fetch.py            (all files, about 290 MB)
        python pipeline/fetch.py facilities (one file by keyword)
Each run also keeps a dated copy in data/raw/archive/, because "latest" files are replaced upstream.
"""
import shutil, sys, urllib.request
from datetime import date
from pathlib import Path

BASE = "https://media.githubusercontent.com/media/deportationdata/{repo}/main/data/{name}"
RAW = "https://raw.githubusercontent.com/deportationdata/{repo}/main/data/{name}"
FILES = [("ice", "detention-stints-latest.parquet"), ("ice-detention-facilities", "facilities-latest.parquet"),
         ("ice-offices", "ice-offices.parquet"),
         ("ice", "arrests-latest.parquet"),       # arrest records: read only by arrests_trend.py, which writes counts
         ("ice", "detainers-latest.parquet")]     # detainer records: read only by detainers_trend.py, which writes counts
raw = Path(__file__).parent.parent / "data" / "raw"
(raw / "archive").mkdir(parents=True, exist_ok=True)

for repo, name in FILES:
    if len(sys.argv) > 1 and sys.argv[1] not in name: continue
    dest = raw / name
    for url in (RAW, BASE):                      # small files are served directly, large ones from the media host
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(url.format(repo=repo, name=name), timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if tmp.read_bytes()[:4] == b"PAR1": break  # a real parquet file, not a pointer stub
    else:
        raise SystemExit(f"{name}: download was not a parquet file")
    tmp.replace(dest)
    shutil.copy2(dest, raw / "archive" / f"{date.today()}_{name}")
    print(f"{name}: {dest.stat().st_size:,} bytes")


def fetch_287g():
    """Latest list of local agencies with ICE 287(g) agreements, from appelson/Tracking_287g (MIT), saved as CSV."""
    import json, io
    import pandas as pd
    if len(sys.argv) > 1 and sys.argv[1] not in "287g": return
    ref = raw.parent / "reference"; ref.mkdir(exist_ok=True)
    req = urllib.request.Request("https://api.github.com/repos/appelson/Tracking_287g/git/trees/HEAD?recursive=1", headers={"User-Agent": "detention-map"})
    tree = json.load(urllib.request.urlopen(req, timeout=60))["tree"]
    sheets = sorted(t["path"] for t in tree if t["path"].startswith("sheets/sheets_") and "articipating" in t["path"] and t["path"].endswith(".xlsx"))
    if not sheets: raise SystemExit("287(g): no participating-agencies sheet found; keeping the file on disk")
    latest = sheets[-1]                      # folders are named sheets_YYYYMMDD_HHMMSS, so the last one is the newest
    data = urllib.request.urlopen("https://raw.githubusercontent.com/appelson/Tracking_287g/HEAD/" + urllib.request.quote(latest), timeout=120).read()
    df = pd.read_excel(io.BytesIO(data))
    need = ["STATE", "LAW ENFORCEMENT AGENCY", "COUNTY", "SUPPORT TYPE", "SIGNED"]
    if [c for c in need if c not in df.columns] or len(df) < 500:
        raise SystemExit(f"287(g): unexpected sheet ({len(df)} rows, columns {list(df.columns)}); keeping the file on disk")
    out = df[need].copy(); out.columns = ["state", "agency", "county", "model", "signed"]
    for c in ("state", "agency", "county", "model"): out[c] = out[c].astype("string").str.strip()
    out["signed"] = pd.to_datetime(out["signed"], errors="coerce").dt.date
    out["source_sheet"] = latest
    out.to_csv(ref / "287g_agencies.csv", index=False)
    print(f"287(g): {len(out):,} agreements from {latest}")


fetch_287g()
