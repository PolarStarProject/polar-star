"""Homeland Security civil rights office (CRCL) memos about detention facilities, from the public mirror kept by the
Project On Government Oversight (POGO) on DocumentCloud. DHS removed most of these from its own site in 2025.

Usage:  python pipeline/crcl_memos.py
Writes data/reference/crcl_memos.csv ("|" separated): published | title | kind | url | slug
Only documents whose name starts with a date and "crcl" (POGO's naming: "24-0208-crcl-winn-correctional-center-close-summary-508")
are kept; the date is that prefix (YY-MMDD), which is the memo's date as DHS filed it. Which facility a memo is about is
worked out in build_site.py from its title; a memo that fits no single facility is listed without one.
"""
import csv, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from identity import USER_AGENT

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
API = "https://api.www.documentcloud.org/api/documents/search/?"
POGO_ORG = 334
KINDS = [("retention", "retention memo"), ("close-summary", "close summary"), ("closure", "close summary"), ("rec-expert", "recommendation memo"), ("rec-memo", "recommendation memo"),
         ("recommendation", "recommendation memo"), ("expert", "expert report"), ("response", "response summary"), ("spot-check", "spot check")]


def parse(doc):
    """One DocumentCloud record -> a row, or None if it is not a dated CRCL memo."""
    slug = (doc.get("slug") or "").lower()
    m = re.match(r"(\d\d)-?(\d\d)(\d\d)-crcl-(.+)", slug)
    if not m or not (1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31): return None
    rest = re.sub(r"-(508|redacted|foia|v\d+|final)\b", "", m.group(4))
    kind = next((k for key, k in KINDS if key in slug), "memo")
    title = " ".join((doc.get("title") or "").split()) or rest.replace("-", " ")
    return {"published": f"20{m.group(1)}-{m.group(2)}-{m.group(3)}", "title": title.replace("|", "/")[:200], "kind": kind,
            "url": doc.get("canonical_url") or f"https://www.documentcloud.org/documents/{doc['id']}-{doc['slug']}/", "slug": rest}


def main():
    url, docs = API + urllib.parse.urlencode({"q": f"organization:{POGO_ORG} crcl", "per_page": 100}), []
    for _ in range(20):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8")); docs += j.get("results", []); url = j.get("next")
        if not url: break
        time.sleep(1)
    rows = sorted(filter(None, map(parse, docs)), key=lambda r: (r["published"], r["slug"]))
    if len(rows) < 40: raise SystemExit(f"Only {len(rows)} dated CRCL memos found among {len(docs)} documents; the mirror or its naming may have changed. Nothing written.")
    with open(REF / "crcl_memos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["published", "title", "kind", "url", "slug"], delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} dated CRCL memos from {len(docs)} documents in POGO's mirror ({rows[0]['published']} to {rows[-1]['published']})")


if __name__ == "__main__": main()
