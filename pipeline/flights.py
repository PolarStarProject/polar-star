"""One day of public aircraft positions -> legs flown by ICE Air contractor aircraft on an ICE pattern.

Usage:  python pipeline/flights.py 2026-10-02            (downloads about 4 GB to a temp folder, then deletes it)
        python pipeline/flights.py --catchup 7           (every day in the last 7 not yet processed)
        python pipeline/flights.py --since 2024-01-01    (backfill, newest day first; about 1,000 days of 2-4 GB each)
        python pipeline/flights.py 2026-10-02 --tar X    (use a day file already on disk)

Source: adsb.lol daily history, Open Database License. Anything derived from it (data/flights/*) carries
the same license and must credit "adsb.lol contributors".

What counts, and why it is labelled "derived":
  * only aircraft using a contractor callsign prefix (PREFIXES) are read at all
  * an aircraft's day is kept only if one of its legs starts or ends at an ICE staging airport (STAGING)
  * contractor aircraft also fly ordinary charters; those days are dropped, and some ICE flights that
    never touch a staging airport are missed. The result is a documented minimum, not a total.
  * every contractor leg of the day, kept or not, is also saved to data/flights/all_DAY.json.gz, so the rule
    for what counts can be changed later without downloading the day again. Those files are NOT ICE flights:
    they include scheduled passenger services and military charters by the same operators.
"""
import csv, gzip, io, json, math, os, re, shutil, sys, tarfile, tempfile, urllib.request, urllib.error
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).parent.parent
PREFIXES = ("GXA", "VXP", "WAL", "OAE", "BBQ", "EAL", "LYM")     # contractor callsign prefixes scanned
# El Paso is left out on purpose: it sits beside a military airfield whose troop charters use the same operators.
STAGING = {"AEX": "Alexandria, LA", "HRL": "Harlingen, TX", "AZA": "Mesa, AZ"}
NEAR_KM, LOW_FT = 25, 6000        # a leg end counts as "at" an airport only if this close and this low
LOST_KM = 90                      # signal lost before landing: still credited to a staging airport this close
GAP_S = 2700                      # 45 minutes without a position splits a leg
RELEASE = "https://github.com/adsblol/globe_history_{y}/releases/download/v{d}-planes-readsb-prod-0/v{d}-planes-readsb-prod-0.tar.{part}"


def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    return 6371 * math.hypot((lon2 - lon1) * p * math.cos((lat1 + lat2) * p / 2), (lat2 - lat1) * p)


def load_airports(path):
    rows = csv.DictReader(open(path, encoding="utf-8"))
    return [(r["iata_code"], float(r["latitude_deg"]), float(r["longitude_deg"]), r["iso_country"], r["municipality"])
            for r in rows if r["iata_code"] and r["type"] in ("large_airport", "medium_airport", "small_airport")]


def nearest(airports, lat, lon):
    a = min(airports, key=lambda a: km(lat, lon, a[1], a[2]))
    return a, km(lat, lon, a[1], a[2])


def main_call(leg):
    """The callsign most positions in this leg carry (the first few can still show the previous flight's)."""
    calls = [x[4] for x in leg if x[4]]
    return max(set(calls), key=calls.count) if calls else ""


def split_legs(trace):
    """Airborne runs of positions. Position = (unix time, lat, lon, altitude ft, callsign)."""
    t0, legs, cur, last, cs = trace["timestamp"], [], [], None, None
    for p in trace["trace"]:
        ts, air = t0 + p[0], (p[3] != "ground" and p[3] is not None)
        if isinstance(p[8], dict) and p[8].get("flight"): cs = p[8]["flight"].strip()
        if air and (last is None or ts - last < GAP_S):
            cur.append((ts, p[1], p[2], p[3], cs))
        else:
            if len(cur) > 5: legs.append(cur)
            cur = [(ts, p[1], p[2], p[3], cs)] if air else []
        last = ts
    if len(cur) > 5: legs.append(cur)
    # A signal lost in the air and picked up again later is one flight, not two: join pieces with the same callsign.
    joined = []
    for l in legs:
        if joined and joined[-1][-1][3] >= LOW_FT and l[0][3] >= LOW_FT and main_call(joined[-1]) == main_call(l) and l[0][0] - joined[-1][-1][0] < 6 * 3600:
            joined[-1] = joined[-1] + l
        else:
            joined.append(l)
    return [l for l in joined if km(l[0][1], l[0][2], l[-1][1], l[-1][2]) >= 80]


def end_point(airports, pos):
    """(airport code, country, certain?, staging code or '') for one end of a leg."""
    a, d = nearest(airports, pos[1], pos[2])
    certain = d < NEAR_KM and pos[3] < LOW_FT
    stage = a[0] if (certain and a[0] in STAGING) else ""
    if not certain:                                   # signal lost in the air: credit a staging airport only if close
        for code in STAGING:
            s = next(x for x in airports if x[0] == code)
            if km(pos[1], pos[2], s[1], s[2]) < LOST_KM: stage = code
    return a[0], a[3], certain, stage


def describe(trace, airports):
    out = []
    for leg in split_legs(trace):
        o, d = end_point(airports, leg[0]), end_point(airports, leg[-1])
        step = max(1, len(leg) // 60)
        out.append({
            "date": dt.datetime.fromtimestamp(leg[0][0], dt.timezone.utc).strftime("%Y-%m-%d"),
            "registration": trace.get("r", ""), "hex": trace["icao"], "aircraft_type": trace.get("t", ""),
            "callsign": main_call(leg),
            "departed_utc": dt.datetime.fromtimestamp(leg[0][0], dt.timezone.utc).strftime("%H:%M"),
            "arrived_utc": dt.datetime.fromtimestamp(leg[-1][0], dt.timezone.utc).strftime("%H:%M"),
            "origin": o[0], "origin_country": o[1], "origin_certain": o[2],
            "dest": d[0], "dest_country": d[1], "dest_certain": d[2],
            "staging": o[3] or d[3],
            "track": [[round(x[1], 2), round(x[2], 2)] for x in leg[::step]] + [[round(leg[-1][1], 2), round(leg[-1][2], 2)]],
        })
    return out


def all_path(day): return ROOT / "data" / "flights" / f"all_{day}.json.gz"


def save_all(legs, path):
    """Every contractor leg of the day, before any ICE rule. Written to a temp name first so a crash never leaves a half file that looks done."""
    for l in legs: l["kind"] = "domestic" if l["origin_country"] == l["dest_country"] == "US" else "international"
    tmp = str(path) + ".part"
    with gzip.open(tmp, "wt", encoding="utf-8") as f: json.dump(legs, f)
    os.replace(tmp, path)


def keep_ice_pattern(legs):
    """Keep every leg of an aircraft's day if any leg that day touches a staging airport."""
    days = {(l["hex"], l["date"]) for l in legs if l["staging"]}
    kept = [l for l in legs if (l["hex"], l["date"]) in days]
    for l in kept:
        l["kind"] = "domestic" if l["origin_country"] == l["dest_country"] == "US" else "international"
        code = next(x["staging"] for x in legs if (x["hex"], x["date"]) == (l["hex"], l["date"]) and x["staging"])
        l["basis"] = f"contractor aircraft; day includes {code} ({STAGING[code]})"
    return kept


def fleet_extra(all_legs, window=14, min_days=2, min_share=0.5):
    """Legs the staging-airport rule misses, found from the aircraft itself. all_legs: every contractor leg (the all_DAY files).
    An aircraft that flew an ICE pattern (a day touching a staging airport) on at least min_days days within `window` days,
    and on at least min_share of the days it flew in that time, is treated as working for ICE on its other days in the window too.
    Returns those other-day legs, labelled. Scheduled airline services by the same operators never qualify: their aircraft do not touch staging airports."""
    days = {}
    for l in all_legs: days.setdefault(l["hex"], {}).setdefault(l["date"], []).append(l)
    out = []
    for h, dd in days.items():
        ice = sorted(d for d, ls in dd.items() if any(l["staging"] for l in ls))
        if len(ice) < min_days: continue
        for d, ls in dd.items():
            if d in ice: continue
            d0 = dt.date.fromisoformat(d); near = [x for x in dd if abs((dt.date.fromisoformat(x) - d0).days) <= window // 2]
            n = sum(1 for x in near if x in ice)
            if n >= min_days and n >= min_share * len(near):
                for l in ls:
                    l = dict(l); l["kind"] = "domestic" if l["origin_country"] == l["dest_country"] == "US" else "international"
                    l["basis"] = f"same aircraft flew an ICE pattern on {n} other days within a week of this one"; out.append(l)
    return out


class Parts(io.RawIOBase):
    """Read split tar parts as one stream."""
    def __init__(self, paths): self.fs, self.i = [open(p, "rb") for p in paths], 0
    def readable(self): return True
    def readinto(self, b):
        while self.i < len(self.fs):
            n = self.fs[self.i].readinto(b)
            if n: return n
            self.i += 1
        return 0


def scan(paths):
    pat = re.compile(rb'"flight":"(' + "|".join(PREFIXES).encode() + rb')')
    n = 0
    with tarfile.open(fileobj=io.BufferedReader(Parts(paths), 1 << 20), mode="r|") as t:
        for m in t:
            if not m.isfile() or "trace_full_" not in m.name: continue
            n += 1
            raw = t.extractfile(m).read()
            try: data = gzip.decompress(raw)
            except OSError: data = raw
            if pat.search(data): yield json.loads(data)
    if n < 20000:                                     # a normal day holds tens of thousands of aircraft
        raise SystemExit(f"Only {n} aircraft in the day file. It is incomplete; nothing written.")


def download(url, dest):
    """Download with resume: a 2 GB part that drops halfway picks up where it stopped. Returns False if the file does not exist upstream."""
    done = dest + ".ok"
    if os.path.exists(done): return True
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    try:
        r = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        if e.code == 404: return False
        if e.code == 416: open(done, "w").close(); return True       # already complete
        raise
    if have and r.status != 206: have = 0                            # server ignored the range: start over
    total = have + int(r.headers.get("Content-Length", 0))
    with open(dest, "ab" if have else "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    if os.path.getsize(dest) != total:
        raise SystemExit(f"{dest}: got {os.path.getsize(dest):,} of {total:,} bytes. Run again to resume.")
    open(done, "w").close(); return True


def main():
    if sys.argv[1] == "--catchup":                    # every complete day in the last N that has no legs file yet
        n = int(sys.argv[2]); today = dt.datetime.now(dt.timezone.utc).date()
        for back in range(n + 1, 1, -1):
            day = str(today - dt.timedelta(days=back))
            if not all_path(day).exists():
                try: run(day, None)
                except SystemExit as e: print(e)
        return
    if sys.argv[1] == "--since":                      # backfill: every day back to a date, newest first, skipping days already done
        first = dt.date.fromisoformat(sys.argv[2]); today = dt.datetime.now(dt.timezone.utc).date()
        days = [str(today - dt.timedelta(days=b)) for b in range(2, (today - first).days + 1)]
        todo = [d for d in days if not all_path(d).exists()]          # "done" means the all-legs file exists; days read before it was added are read again
        print(f"{len(todo)} of {len(days)} days to read back to {first}. Each day is a 2-4 GB download; stop any time and run again to continue.", flush=True)
        for i, day in enumerate(todo, 1):
            try: run(day, None)
            except SystemExit as e: print(e, flush=True)
            except Exception as e: print(f"{day}: failed ({e}); will retry on the next run", flush=True)
            if i % 10 == 0: print(f"  {i} of {len(todo)} days done", flush=True)
        return
    run(sys.argv[1], sys.argv[sys.argv.index("--tar") + 1] if "--tar" in sys.argv else None)


def run(day, tar):
    airports_path = ROOT / "data" / "reference" / "airports.csv"
    if not airports_path.exists():
        urllib.request.urlretrieve("https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv", airports_path)
    airports = load_airports(airports_path)
    tmp = None
    if tar:
        paths = [tar]
    else:
        tmp = os.path.join(os.environ.get("ADSB_WORK", tempfile.gettempdir()), f"adsb_{day}"); os.makedirs(tmp, exist_ok=True); paths = []
        for part in ("aa", "ab", "ac"):
            dest = os.path.join(tmp, part)
            if download(RELEASE.format(y=day[:4], d=day.replace("-", "."), part=part), dest): paths.append(dest)
            elif part == "aa": raise SystemExit(f"No day file published for {day}")
            else: break
    legs = [l for tr in scan(paths) for l in describe(tr, airports)]
    if tmp: shutil.rmtree(tmp, ignore_errors=True)                   # only after a complete read, so a failed run can resume
    legs = [l for l in legs if l["date"] == day]
    out = ROOT / "data" / "flights"; out.mkdir(parents=True, exist_ok=True)
    kept = keep_ice_pattern(legs)
    save_all(legs, all_path(day))
    cols = ["date", "registration", "hex", "aircraft_type", "callsign", "departed_utc", "arrived_utc", "origin", "origin_country",
            "origin_certain", "dest", "dest_country", "dest_certain", "kind", "basis"]
    with open(out / f"legs_{day}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(kept)
    json.dump(kept, open(out / f"legs_{day}.json", "w"))
    print(f"{day}: {len(legs)} contractor legs read, {len(kept)} kept on an ICE pattern, {len({l['hex'] for l in kept})} aircraft")


if __name__ == "__main__":
    main()
