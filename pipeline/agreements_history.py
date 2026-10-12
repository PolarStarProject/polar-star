"""287(g) agreements that were on ICE's list and no longer are -> data/reference/287g_no_longer_listed.csv

Usage:  python pipeline/agreements_history.py PATH_TO_CLONE
        (PATH_TO_CLONE is a local clone of github.com/appelson/Tracking_287g, MIT; about 10 GB. It keeps a dated
         copy of ICE's participating-agencies sheet for most days since 19 May 2025.)

An agreement counts as "no longer listed" when it appears in an earlier sheet and nothing in the newest sheet matches it.
ICE retypes names and misspells states, so a plain name comparison invents hundreds of endings. A row is treated as
still listed if the newest sheet has, in the same state and model, an agency of the same type whose name has the same
key words, or the same signing date and at least half the key words. What is left can still include a few renames.
ICE gives no reason and no end date: "last_listed" is the last sheet the row was seen in.
"""
import collections, csv, difflib, glob, re, sys, warnings
from pathlib import Path

STOP = {"CITY", "OF", "TOWN", "VILLAGE", "THE", "COUNTY", "DEPARTMENT", "DEPT", "OFFICE", "POLICE", "SHERIFF", "SHERIFFS", "S", "PD", "SO", "BOROUGH", "TOWNSHIP", "AND"}
def toks(n): return {w for w in re.sub(r"[^A-Z0-9 ]", " ", n.upper().replace("'", "")).split() if w not in STOP}
def kind(n): n = n.upper(); return "S" if "SHERIFF" in n else "P" if ("POLICE" in n or "MARSHAL" in n or "PUBLIC SAFETY" in n) else "O"


def no_longer_listed(seen, last):
    """seen: {(STATE, AGENCY UPPER, model): (last day seen, signed, agency as typed, county)}; last: day of the newest sheet."""
    states = sorted({k[0] for k, v in seen.items() if v[0] == last})
    def st(s):
        if s in states: return s
        m = difflib.get_close_matches(s, states, 1, 0.8); return m[0] if m else s
    cur = collections.defaultdict(list)
    for k, v in seen.items():
        if v[0] == last: cur[(k[0], k[2][0])].append((toks(k[1]), kind(k[1]), v[1]))
    gone = {}
    for k, v in seen.items():
        if v[0] == last: continue
        S, t, kd = st(k[0]), toks(k[1]), kind(k[1])
        if any(ck == kd and ((t and t == ct) or (cs == v[1] and len(t & ct) / max(1, len(t | ct)) >= 0.5)) for ct, ck, cs in cur[(S, k[2][0])]): continue
        key = (S, frozenset(t), kd, k[2][0])
        if key not in gone or v[0] > gone[key][5]: gone[key] = [S, v[2], "" if v[3] == "nan" else v[3], k[2][0], v[1], v[0]]
    return sorted(gone.values())


if __name__ == "__main__":
    import pandas as pd
    warnings.filterwarnings("ignore"); seen, days = {}, []
    for d in sorted(glob.glob(str(Path(sys.argv[1]) / "sheets" / "sheets_*"))):
        day = re.search(r"sheets_(\d{4})(\d{2})(\d{2})", d); day = "-".join(day.groups())
        fs = [f for f in glob.glob(d + "/*.xlsx") if "articipating" in f]
        try: df = pd.read_excel(fs[0])
        except Exception: continue
        df.columns = [str(c).strip().upper() for c in df.columns]
        if any(c not in df.columns for c in ("STATE", "LAW ENFORCEMENT AGENCY", "SUPPORT TYPE", "SIGNED")) or len(df) < 50: continue
        days.append(day)
        for r in df.to_dict("records"):
            name = re.sub(r"\s+", " ", str(r["LAW ENFORCEMENT AGENCY"]).strip()); s = pd.to_datetime(r["SIGNED"], errors="coerce")
            seen[(str(r["STATE"]).strip().upper(), name.upper(), str(r["SUPPORT TYPE"]).strip())] = (day, "" if pd.isna(s) else str(s.date()), name, str(r.get("COUNTY", "") or "").strip())
    if len(days) < 100: raise SystemExit(f"Only {len(days)} readable sheets; expected about 190. Nothing written.")
    rows = no_longer_listed(seen, days[-1])
    out = Path(__file__).resolve().parent.parent / "data" / "reference" / "287g_no_longer_listed.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["state", "agency", "county", "model", "signed", "last_listed"]); w.writerows(rows)
    print(f"{len(rows)} agreements no longer listed, from {len(days)} sheets {days[0]} to {days[-1]}")
