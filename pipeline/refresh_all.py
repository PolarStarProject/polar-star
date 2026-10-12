"""The whole refresh, in order. Used by the weekly job on GitHub and by run_refresh.ps1 on a PC.

Usage:  python pipeline/refresh_all.py                 (everything)
        python pipeline/refresh_all.py --only tests,build
        python pipeline/refresh_all.py --skip flights

A step marked required stops the run if it fails, and the published page is left as it was. Every other step
may fail (a site is down, a server is blocked): its data stays as it was, the failure is written to
data/refresh_status.json, and the page footer flags that source once it is older than it should be.
The page is rebuilt only after every test passes, and the previous page is put back if the build fails.
"""
import datetime as dt, json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = "data/raw/"
STEPS = [  # name, command after "python", required
    ("records",    ["pipeline/fetch.py"], True),
    ("custody",    ["pipeline/custody_trend.py"], False),
    ("removed_to", ["pipeline/removals_country.py"], False),
    ("arrests",    ["pipeline/arrests_trend.py"], False),
    ("detainers",  ["pipeline/detainers_trend.py"], False),
    ("days",       ["pipeline/person_days.py"], False),
    ("held",       ["pipeline/held_profile.py"], False),
    ("ice_site",   ["pipeline/refresh_contacts.py"], False),
    ("audits",     ["pipeline/prea_audits.py"], False),
    ("stats",      ["pipeline/detention_stats.py"], False),
    ("findings",   ["pipeline/inspection_findings.py"], False),
    ("spending",   ["pipeline/money_usaspending.py"], False),
    ("awards",     ["pipeline/money_awards.py"], False),
    ("others",     ["pipeline/other_agencies.py"], False),
    ("accounts",   ["pipeline/money_object_class.py"], False),
    ("staff",      ["pipeline/staff_opm.py"], False),
    ("court",      ["pipeline/court_outcomes.py"], False),
    ("memos",      ["pipeline/crcl_memos.py"], False),
    ("lobbying",   ["pipeline/money_lobbying.py"], False),
    ("vendorlobby", ["pipeline/vendor_lobbying.py"], False),
    ("fec",        ["pipeline/money_fec.py"], False),
    ("jfc",        ["pipeline/jfc_flows.py"], False),
    ("politicians", ["pipeline/politicians.py"], False),
    ("donors",     ["pipeline/money_donors.py"], False),
    ("membercom",  ["pipeline/member_committees.py"], False),
    ("topdonors",  ["pipeline/member_top_donors.py"], False),
    ("countrypacs", ["pipeline/country_pacs.py"], False),
    ("fara",       ["pipeline/fara.py"], False),
    ("firms",      ["pipeline/firm_profiles.py"], False),
    ("firmbase",   ["pipeline/firm_base.py"], False),
    ("sec",        ["pipeline/sec_watch.py"], False),
    ("social",     ["pipeline/social_check.py"], False),
    ("officials",  ["pipeline/officials_check.py"], False),
    ("hotlines",   ["pipeline/hotlines_check.py"], False),
    ("moa",        ["pipeline/moa_links.py"], False),
    ("signers",    ["pipeline/moa_signers.py"], False),
    ("transfers",  ["pipeline/build_transfers.py", RAW + "detention-stints-latest.parquet", RAW + "facilities-latest.parquet",
                    "data/reference/ice_facility_contacts.csv", "data/reference/ice_field_offices.csv"], True),
    ("police",     ["pipeline/agency_contacts.py"], False),
    ("statements", ["pipeline/visit_statements.py"], False),
    ("districts",  ["pipeline/districts.py"], False),
    ("flights",    ["pipeline/flights.py", "--catchup", "8"], False),
    ("probe",      ["pipeline/probe_sources.py"], False),
    ("tests",      ["pipeline/run_tests.py"], True),
    ("build",      ["pipeline/build_site.py"], True),
]

ON_REQUEST = {"probe"}   # steps that run only when named in --only
MONTHLY = set()          # steps that run only in the first week of a month (none now: the audit check is weekly again)


def pick(names, only, skip):
    """Which steps run, in the fixed order. Unknown names are an error, so a typo cannot silently skip the tests."""
    known = [n for n, _, _ in STEPS]
    bad = [x for x in (only or []) + (skip or []) if x not in known]
    if bad: raise SystemExit(f"unknown step(s): {', '.join(bad)}. Steps are: {', '.join(known)}")
    return [n for n in names if (not only or n in only) and n not in (skip or [])]


def main(argv):
    arg = lambda flag: argv[argv.index(flag) + 1].split(",") if flag in argv else None
    todo = pick([n for n, _, _ in STEPS], arg("--only"), arg("--skip"))
    page, keep = ROOT / "site" / "index.html", ROOT / "site" / "index.previous.html"
    status, ok = {"started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "steps": {}}, True
    for name, cmd, required in STEPS:
        if name not in todo: continue
        if name in ON_REQUEST and not arg("--only"): continue
        if name in MONTHLY and not arg("--only") and dt.date.today().day > 7: print(f"=== {name} === skipped: runs in the first week of each month", flush=True); status["steps"][name] = "not due"; continue
        if name == "build" and page.exists(): shutil.copy2(page, keep)
        print(f"=== {name} ===", flush=True)
        proc = subprocess.Popen([sys.executable, "-u"] + cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        tail = []
        for line in proc.stdout:                                     # shown live, and the last lines are kept so a failure explains itself in refresh_status.json
            print(line, end="", flush=True); tail = (tail + [line.rstrip()])[-6:]
        code = proc.wait()
        status["steps"][name] = "ok" if code == 0 else "failed"
        if code != 0: status.setdefault("errors", {})[name] = " / ".join(t for t in tail if t)[-500:]
        if code != 0:
            print(f"{name} FAILED (exit {code})" + ("; stopping, page left as it was" if required else "; its data is left as it was"), flush=True)
            if name == "build" and keep.exists(): shutil.copy2(keep, page)
            if required: ok = False; break
    status["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"); status["page_rebuilt"] = status["steps"].get("build") == "ok"
    (ROOT / "data" / "refresh_status.json").write_text(json.dumps(status, indent=1), encoding="utf-8")
    print(json.dumps(status["steps"]), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
