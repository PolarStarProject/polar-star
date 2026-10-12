"""Stint records -> aggregated transfer patterns -> data/site_data.json (then run build_site.py)

Usage:  python pipeline/build_transfers.py STINTS FACILITIES [CONTACTS] [FIELD_OFFICES] [--sample]
STINTS: the Deportation Data Project "detention facility stints" file
        (one row per booking at one facility; a stay is one continuous detention).

Privacy rules enforced here, not in the page:
  * nothing per person leaves this script
  * a facility with fewer than MIN_ORIGIN departures publishes no pattern
  * a destination with fewer than MIN_CELL moves is folded into "other"
  * only rounded percentages are published, never counts
"""
import json, sys
from pathlib import Path
import pandas as pd

COL = dict(stay="stay_ID", facility="detention_facility_code", book_in="book_in_date_time",
           book_out="book_out_date_time", reason="detention_release_reason", dup="duplicate_drop_row",
           fname="detention_facility", fcity="city", fstate="state", country="departure_country")
FCOL = dict(code="detention_facility_code", name="name", city="city", state="state",
            address="address_full", office="field_office", lat="latitude", lon="longitude", county="county")
WINDOW_DAYS = 365   # pattern window, counted back from the newest book-out
MIN_CELL = 10
MIN_ORIGIN = 30
TOP_N = 5           # destinations named per facility; the rest go to "other"
# Every release reason in the records is assigned to exactly one plain-language group.
# Anything not listed lands in "other", so a new reason upstream is never silently counted as a release.
GROUPS = {
    "deported": {"Removed", "Title 42 Return"},
    "left_voluntarily": {"Voluntary departure", "Voluntary Return", "Withdrawal"},
    "released": {"Bonded Out - IJ", "Bonded Out - Field Office", "Order of recognizance", "Order of Recognizance - Humanitarian",
                 "Order of supervision", "Order of Supervision - Re-Release", "Order of Supervision - Humanitarian",
                 "Order of Supervision - No SLRRFF", "Paroled", "Paroled - Humanitarian", "Paroled - Public Benefit",
                 "Paroled - Fear Found", "Court Ordered", "Relief Granted by IJ", "Proceedings Terminated"},
    "other_agency": {"U.S. Marshals or other agency (explain in Detention Comments)", "ORR - Office of Refugee Resettlement"},
    "transfer_unrecorded": {"Transferred"},   # marked transferred, but no next booking appears in the records
    "died": {"Died"},
    "escaped": {"Escaped"},
    "processing_changed": {"Processing Disposition Changed Locally"},   # ICE's own term; it does not say where the person went
}
# Two more groups are assigned in code: "no_reason" (ICE left the reason blank) and "unlisted" (a reason not in this table).
REASON_TO_GROUP = {r: g for g, rs in GROUPS.items() for r in rs}


def women_custody(stints_path):
    """How long women were held, counted per continuous stay in ICE custody (a stay can span several facilities).
    National totals only. Days: under 30, 30-89, 90-364, a year (365) or more."""
    import pyarrow.parquet as pq
    extra = [c for c in ("book_in_date_time", "book_out_date_time") if c in pq.read_schema(stints_path).names]
    d = pd.read_parquet(stints_path, columns=["gender", "stay_ID", "stay_book_in_date_time", "stay_book_out_date_time", "duplicate_drop_row", *extra])
    newest = max([pd.to_datetime(d[c], format="mixed", errors="coerce").max() for c in extra] or [pd.NaT])      # the newest timestamp of any stint (any gender): the "as of" day held_profile uses
    d = d[~d["duplicate_drop_row"].fillna(False).astype(bool) & (d["gender"] == "Female")].drop_duplicates("stay_ID")
    out = pd.to_datetime(d["stay_book_out_date_time"], format="mixed", errors="coerce"); inn = pd.to_datetime(d["stay_book_in_date_time"], format="mixed", errors="coerce")
    last = max(x for x in (out.max(), inn.max(), newest) if pd.notna(x))
    EDGES = ((0, 29), (30, 89), (90, 364), (365, 10 ** 6))
    def bands(days): return [int(((days >= a) & (days <= b)).sum()) for a, b in EDGES]
    ended = out > last - pd.Timedelta(days=365)
    le = (out[ended] - inn[ended]).dt.days; lo = (last - inn[out.isna()]).dt.days
    return {"as_of": str(last.date()), "edges": [list(e) for e in EDGES], "ended": {"n": int(ended.sum()), "bands": bands(le), "median_days": int(le.median())},
            "open": {"n": int(out.isna().sum()), "bands": bands(lo)}}


def shares(counts, folded=None):
    """Rounded percentages that sum to 100 (largest remainder). Groups under MIN_CELL are folded into 'other'.
    If `folded` is a list, the names of the groups that were folded are appended to it."""
    counts = {k: int(v) for k, v in counts.items() if v > 0}
    other = counts.pop("other", 0)
    for k in [k for k, v in counts.items() if v < MIN_CELL]:
        other += counts.pop(k)
        if folded is not None: folded.append(k)
    if 0 < other < MIN_CELL and counts:                      # a lone small "other" could be worked out by subtraction
        k = min(counts, key=counts.get); other += counts.pop(k)
        if folded is not None: folded.append(k)
    if other: counts["other"] = other
    total = sum(counts.values())
    exact = {k: 100 * v / total for k, v in counts.items()}
    out = {k: int(x) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: exact[k] - out[k], reverse=True)[: 100 - sum(out.values())]:
        out[k] += 1
    order = sorted((k for k in out if k != "other"), key=lambda k: -counts[k]) + (["other"] if "other" in out else [])
    return [{"k": k, "pct": out[k]} for k in order]



def read(path, columns=None):
    p = str(path).lower()
    if p.endswith(".parquet"): return pd.read_parquet(path, columns=columns)
    df = pd.read_excel(path) if p.endswith((".xlsx", ".xls")) else pd.read_csv(path)
    return df[columns] if columns else df


def prepare(st):
    """Clean stints and attach each one's next facility within the same stay."""
    st = st.rename(columns={v: k for k, v in COL.items()})
    log = {"rows_in": len(st)}
    dup = st["dup"].fillna(False).astype(bool)
    log["flagged_duplicates_dropped"] = int(dup.sum()); st = st[~dup]
    bad = st["stay"].isna() | st["facility"].isna() | st["book_in"].isna()
    log["missing_stay_facility_or_book_in_dropped"] = int(bad.sum()); st = st[~bad].copy()
    for c in ("book_in", "book_out"):
        if not pd.api.types.is_datetime64_any_dtype(st[c]):   # text dates in mixed formats must not silently become blank
            st[c] = pd.to_datetime(st[c], format="mixed", utc=True)
        elif st[c].dt.tz is None:
            st[c] = st[c].dt.tz_localize("UTC")
    st = st.sort_values(["stay", "book_in", "book_out"], kind="stable")
    g = st.groupby("stay", sort=False)
    st["dest"] = g["facility"].shift(-1)
    st["next_in"] = g["book_in"].shift(-1)
    return st, log


def transfers(st, log):
    t = st[st["dest"].notna() & st["book_out"].notna()]
    log["same_facility_rebooking_ignored"] = int((t["dest"] == t["facility"]).sum())
    t = t[t["dest"] != t["facility"]]
    log["overlap_in_two_places_at_once_kept"] = int((t["next_in"] < t["book_out"]).sum())
    log["transfers"] = len(t)
    return t.assign(held_days=(t["book_out"] - t["book_in"]).dt.total_seconds() / 86400)


def pct(n, d): return round(100 * n / d)


def aggregate(st, t, fac):
    end = st["book_out"].max()
    startw = end - pd.Timedelta(days=WINDOW_DAYS)
    left = st[(st["book_out"] > startw)]            # every departure from a facility in the window
    t = t[t["book_out"] > startw]
    moved_idx = set(t.index)
    meta = fac[[c for c in FCOL.values() if c in fac.columns]].rename(columns={v: k for k, v in FCOL.items()}).drop_duplicates("code").set_index("code")
    fallback = st.drop_duplicates("facility").set_index("facility")
    out = {}
    order = left["facility"].value_counts()          # busiest first; counts are not published
    for code in order.index:
        if code in meta.index:
            m = meta.loc[code]; rec = {"name": m["name"], "city": m.get("city"), "state": m.get("state"),
                                      "address": m.get("address"), "office": m.get("office"), "county": m.get("county")}
        else:
            m = fallback.loc[code]; rec = {"name": m["fname"], "city": m["fcity"], "state": m["fstate"]}
        rec = {k: (None if pd.isna(v) else str(v)) for k, v in rec.items()}
        if code in meta.index and "lat" in meta.columns and pd.notna(meta.at[code, "lat"]):
            rec["lat"], rec["lon"] = round(float(meta.at[code, "lat"]), 3), round(float(meta.at[code, "lon"]), 3)
        rec["enough"] = False
        dep = left[left["facility"] == code]
        if len(dep) >= MIN_ORIGIN:
            grp = dep["reason"].map(REASON_TO_GROUP)
            grp[grp.isna() & dep["reason"].isna()] = "no_reason"
            grp = grp.fillna("unlisted")
            grp[dep.index.isin(moved_idx)] = "moved"
            folded = []
            rec["outcome"] = shares(grp.value_counts().to_dict(), folded)
            for o in rec["outcome"]:
                if o["k"] == "other": o["of"] = sorted(folded)        # which small groups were combined; no counts
            if "country" in dep.columns:                 # where people deported straight from here were sent, as ICE recorded it
                c = dep.loc[(grp == "deported").values, "country"].dropna().str.title().value_counts()
                if c.sum() >= MIN_ORIGIN:
                    top = c.iloc[:TOP_N].to_dict(); top["other"] = int(c.iloc[TOP_N:].sum())
                    rec["removed_to"] = shares(top)
        # Deaths are shown as plain counts, with no minimum. ICE itself publishes every death in custody by name,
        # so hiding small numbers here would shield the agency, not the people held.
        died_all = int(((st["facility"] == code) & (st["reason"] == "Died")).sum())
        if died_all:
            rec["deaths_recorded"] = {"year": int((dep["reason"] == "Died").sum()), "all": died_all, "since": str(st["book_in"].min().date())[:7]}
        o = t[t["facility"] == code]
        if len(o) >= MIN_ORIGIN:
            c = o["dest"].value_counts()
            listed = c[c >= MIN_CELL].iloc[:TOP_N]
            other = int(len(o) - listed.sum())
            # a leftover "other" of 1-9 could be worked out by subtraction: fold in the smallest listed cell
            while 0 < other < MIN_CELL and len(listed) > 1:
                other += int(listed.iloc[-1]); listed = listed.iloc[:-1]
            rec.update(enough=True, dests=[{"code": k, "pct": pct(v, len(o))} for k, v in listed.items()],
                       other_pct=pct(other, len(o)),
                       median_days=round(float(o["held_days"].clip(lower=0).median())))
        out[code] = rec
    # a destination must be nameable even if it had no departures of its own
    for code in {d["code"] for r in out.values() for d in r.get("dests", [])} - set(out):
        m = meta.loc[code] if code in meta.index else None
        out[code] = {"name": str(m["name"]) if m is not None else code,
                     "city": None if m is None or pd.isna(m.get("city")) else str(m["city"]),
                     "state": None if m is None or pd.isna(m.get("state")) else str(m["state"]), "enough": False}
    return out, startw, end


def norm_name(x):
    import re
    x = re.sub(r"\(.*?\)", " ", str(x).lower())
    x = re.sub(r"[^a-z0-9 ]", " ", x.replace("\u2019", "").replace("'", ""))
    return " ".join(w for w in x.split() if w not in {"the", "ice", "corecivic"})


US = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT","Delaware":"DE","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY","Guam":"GU","Puerto Rico":"PR","Northern Mariana Islands":"MP","Washington D.C.":"DC","Washington State":"WA"}


def area_state(phone):
    """State a US number's area code belongs to, or None (toll-free, unknown)."""
    import phonenumbers
    from phonenumbers import geocoder
    try:
        d = geocoder.description_for_number(phonenumbers.parse(phone, "US"), "en")
    except Exception:
        return None
    for name, ab in US.items():
        if d == name or d.endswith(", " + ab) or d.endswith(", " + name): return ab
    return None


def attach_contacts(facs, contacts, log):
    """Attach ICE's published phone number to a facility only on a confident, unambiguous name match.
    A wrong number sends a family to the wrong place, so anything doubtful gets no number."""
    import difflib
    by_name = {}
    for code, f in facs.items():
        by_name.setdefault(norm_name(f["name"]), []).append(code)
    matched, skipped, wrong_state = 0, [], []
    for _, c in contacts.iterrows():
        if not isinstance(c["phone"], str) or not c["phone"].strip(): continue
        key = norm_name(c["name"])
        hit = by_name.get(key)
        if hit is None:
            close = difflib.get_close_matches(key, list(by_name), n=2, cutoff=0.9)
            hit = by_name[close[0]] if len(close) == 1 else None
        dup_in_contacts = (contacts["name"].map(norm_name) == key).sum() > 1
        if hit is None or len(hit) != 1 or dup_in_contacts:
            skipped.append(c["name"]); continue
        if area_state(c["phone"]) != facs[hit[0]].get("state"):      # the number's area code must sit in the facility's state
            wrong_state.append(f'{c["name"]} {c["phone"]} vs {facs[hit[0]].get("state")}'); continue
        facs[hit[0]]["phone"] = c["phone"].strip(); matched += 1
        if isinstance(c.get("source"), str): facs[hit[0]]["ice_page"] = c["source"]      # ICE's own page: visiting hours, mail, money
    log["contacts_matched"] = matched
    log["contacts_area_code_in_other_state"] = wrong_state
    log["contacts_not_matched"] = sorted(skipped)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sample = "--sample" in sys.argv
    stints, fac = read(args[0]), read(args[1])
    stints = stints[[c for c in COL.values() if c in stints.columns]]
    st, log = prepare(stints)
    t = transfers(st, log)
    facs, startw, end = aggregate(st, t, fac)
    if len(args) > 2:
        attach_contacts(facs, pd.read_csv(args[2], dtype=str), log)
    if len(args) > 3:
        off = pd.read_csv(args[3], dtype=str).set_index("field_office")
        n = 0
        for f in facs.values():
            if f.get("office") in off.index:
                f["office_phone"], f["office_label"] = off.at[f["office"], "phone"], off.at[f["office"], "office_label"]; n += 1
        log["facilities_with_field_office_phone"] = n
        log["facilities_with_no_phone_at_all"] = sum(1 for f in facs.values() if not f.get("phone") and not f.get("office_phone"))
    log["facilities_published"] = len(facs)
    log["facilities_with_pattern"] = sum(f["enough"] for f in facs.values())
    data = {"sample": sample, "window": [str(startw.date()), str(end.date())], "facilities": facs}
    root = Path(__file__).parent.parent
    if str(sys.argv[1]).endswith(".parquet"):
        try: data["women_custody"] = women_custody(sys.argv[1])
        except Exception as e: log["women_custody_error"] = str(e)
    (root / "data" / "site_data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")   # build_site.py makes the page
    (root / "data" / "build_log.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
