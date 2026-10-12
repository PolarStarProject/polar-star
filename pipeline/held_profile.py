"""Who is held right now, and for how long, from the detention records. Counts only, never a person.

Usage:  python pipeline/held_profile.py     (reads data/raw/detention-stints-latest.parquet, a few seconds)
Writes data/reference/held_profile.json:
  as_of        the newest timestamp in the records; "held now" means not booked out by then
  national     the whole country;  facilities: one entry per facility holding at least MIN_SITE people
  each entry   n, women (%), ages (% in each band), countries (largest five, %), over180 / over365 (% held that long so far), n180 / n365 (how many),
               median_days (so far, across the whole stay, not just this facility)
A share that rests on fewer than MIN_CELL people is left out, so no small group can be picked out at one site.
"""
import json, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MIN_SITE, MIN_CELL = 30, 10
BANDS = [("under 18", 0, 17), ("18-24", 18, 24), ("25-34", 25, 34), ("35-44", 35, 44), ("45-54", 45, 54), ("55 and over", 55, 200)]


def profile(g, seen):
    """g: rows held now, with gender, country, age, stay_in. Returns the entry described above."""
    n = len(g); pct = lambda k: round(100 * k / n) if k >= MIN_CELL else None; cnt = lambda k: k if k >= MIN_CELL else None
    days = (seen - g.stay_in).dt.total_seconds() / 86400
    ages = [[name, pct(int(((g.age >= lo) & (g.age <= hi)).sum()))] for name, lo, hi in BANDS]
    top = g.country.value_counts().head(5)
    return {"n": n, "women": pct(int((g.gender == "Female").sum())), "ages": [a for a in ages if a[1] is not None],
            "countries": [[str(k).title(), pct(int(v))] for k, v in top.items() if v >= MIN_CELL and str(k) not in ("nan", "None", "")],
            "over180": pct(int((days > 180).sum())), "over365": pct(int((days > 365).sum())), "median_days": int(round(days.median())),
            "n180": cnt(int((days > 180).sum())), "n365": cnt(int((days > 365).sum()))}


def death_timing(d):
    """Stays ICE's records end with "Died": how long the person had been in ICE detention. d: stay_id, stay_in, stay_out, reason.
    Fewer than the deaths ICE lists; the two sources count differently (a person moved to a hospital may be recorded as released before dying)."""
    s = d[d.reason == "Died"].drop_duplicates("stay_id")
    days = ((s.stay_out - s.stay_in).dt.total_seconds() / 86400).dropna()
    if len(days) < MIN_CELL: return None
    pct = lambda k: round(100 * k / len(days)) if k >= MIN_CELL else None
    return {"n": int(len(days)), "from": s.stay_out.min().date().isoformat()[:7], "median_days": int(round(days.median())),
            "within30": pct(int((days <= 30).sum())), "over180": pct(int((days > 180).sum()))}


def build(d):
    """d: columns code, gender, country, age, stay_in, stint_in, out (NaT while held)."""
    seen = max(d.stint_in.max(), d.out.max()); cur = d[d.out.isna()]
    fac = {str(c): profile(g, seen) for c, g in cur.groupby("code") if len(g) >= MIN_SITE}
    return {"as_of": seen.date().isoformat(), "min_site": MIN_SITE, "min_cell": MIN_CELL, "national": profile(cur, seen), "facilities": fac}


if __name__ == "__main__":
    d = pd.read_parquet(ROOT / "data" / "raw" / "detention-stints-latest.parquet",
                        columns=["detention_facility_code", "gender", "citizenship_country", "age_at_stint_book_in_approximate", "stay_book_in_date_time", "book_in_date_time", "book_out_date_time", "duplicate_drop_row", "stay_ID", "stay_book_out_date_time", "stay_release_reason"])
    d = d[d["duplicate_drop_row"] != True].dropna(subset=["detention_facility_code", "book_in_date_time"])
    d = d.rename(columns={"detention_facility_code": "code", "citizenship_country": "country", "age_at_stint_book_in_approximate": "age", "stay_book_in_date_time": "stay_in", "book_in_date_time": "stint_in", "book_out_date_time": "out"})
    d["stay_in"] = d["stay_in"].fillna(d["stint_in"])
    out = build(d)
    out["deaths"] = death_timing(d.rename(columns={"stay_ID": "stay_id", "stay_book_out_date_time": "stay_out", "stay_release_reason": "reason"}))
    if not (20000 < out["national"]["n"] < 200000): raise SystemExit(f"Implausible result ({out['national']['n']} held). Nothing written.")
    (ROOT / "data" / "reference" / "held_profile.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{out['national']['n']:,} held on {out['as_of']}; {out['national']['over180']}% over 180 days, {out['national']['over365']}% over a year; {len(out['facilities'])} facilities profiled")
