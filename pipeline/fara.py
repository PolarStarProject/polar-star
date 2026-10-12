"""Registered foreign agents: every person and firm registered with the Justice Department under the Foreign Agents
Registration Act (FARA), and the foreign governments, parties and other principals each works for.

Usage:  python pipeline/fara.py        (needs internet; runs in GitHub Actions)

From the FARA eFile API (efile.fara.gov): the active registrants, each one's active foreign principals with country,
and the newest Exhibit A/B for each principal (the filing that describes the work). "Foreign" here is the legal status
the registrant reported, not a judgment by this page. Registrants also report political contributions, but only inside
scanned filings, so those are not read here.

Writes data/reference/fara_principals.csv: country | principal | registrant | reg_number | since | exhibit_url, and
fara_meta.json. Nothing is written unless the registrant list and most principal lists come back.
"""
import csv, datetime as dt, json, sys, time, urllib.request
from pathlib import Path
from identity import USER_AGENT

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
API = "https://efile.fara.gov/api/v1"


def get(url):
    """JSON from the API, waiting between calls (it allows about five requests every ten seconds)."""
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}), timeout=90) as r:
                raw = r.read(); time.sleep(2.2)
                try: return json.loads(raw.decode("utf-8"))
                except UnicodeDecodeError: return json.loads(raw.decode("cp1252"))
        except urllib.error.HTTPError as e:
            if e.code == 404: time.sleep(2.2); return {}
            time.sleep(30 if e.code == 429 else 10)
        except Exception: time.sleep(10)
    return None


def rows(j):
    """The list of records in either of the API's two wrappers; a single record comes back as a dict."""
    for outer in (j or {}).values():
        r = (outer or {}).get("ROW") if isinstance(outer, dict) else None
        if r is not None: return r if isinstance(r, list) else [r]
    return []


def main():
    reg = rows(get(f"{API}/Registrants/json/Active"))
    if len(reg) < 100: raise SystemExit(f"FARA returned {len(reg)} active registrants: left the list as it was.")
    out, failed = [], 0
    for i, r in enumerate(reg):
        n = r.get("Registration_Number")
        fp = get(f"{API}/ForeignPrincipals/json/Active/{n}")
        if fp is None: failed += 1; continue
        P = rows(fp)
        if not P: continue
        docs = rows(get(f"{API}/RegDocs/json/{n}"))
        ex = {}
        for d in sorted(docs, key=lambda d: d.get("DATE_STAMPED") or ""):
            if (d.get("DOCUMENT_TYPE") or "").startswith("Exhibit AB") and d.get("FOREIGN_PRINCIPAL_NAME"): ex[d["FOREIGN_PRINCIPAL_NAME"].strip().lower()] = d.get("URL", "")
        for p in P:
            name = (p.get("FP_NAME") or "").strip().strip("'\" ")
            out.append({"country": (p.get("COUNTRY_NAME") or "").strip().title(), "principal": name, "registrant": (p.get("REGISTRANT_NAME") or r.get("Name") or "").strip(),
                        "reg_number": n, "since": (p.get("FP_REG_DATE") or "")[:10], "exhibit_url": ex.get(name.lower(), "")})
        if i % 100 == 0: print(f"{i} of {len(reg)} registrants", file=sys.stderr)
    if failed > len(reg) / 3: raise SystemExit(f"{failed} of {len(reg)} principal lists failed: left the list as it was.")
    out.sort(key=lambda x: (x["country"], x["principal"].lower(), x["registrant"].lower()))
    with open(REF / "fara_principals.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["country", "principal", "registrant", "reg_number", "since", "exhibit_url"], delimiter="|", lineterminator="\n"); w.writeheader()
        for x in out: w.writerow({k: str(v).replace("|", "/") for k, v in x.items()})
    (REF / "fara_meta.json").write_text(json.dumps({"read": str(dt.date.today()), "registrants": len(reg), "failed": failed, "with_principals": len({x["reg_number"] for x in out}), "principals": len(out)}, indent=1), encoding="utf-8")
    print(f"{len(out)} principals for {len({x['reg_number'] for x in out})} registrants", file=sys.stderr)


if __name__ == "__main__": main()
