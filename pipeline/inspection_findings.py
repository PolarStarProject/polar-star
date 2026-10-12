"""Count the deficiencies ICE's own inspectors cite in each published inspection report.

Usage:  python pipeline/inspection_findings.py [--max 400]
Reads data/reference/ice_inspections.csv (kept current by refresh_contacts.py) and reads only reports not read before.
Writes data/reference/ice_inspection_findings.csv ("|" separated):
  url | read (text, ocr, or unreadable) | deficiencies | stated | standards | checked

  stated        the report's own total, from its summary sentence "ODO found N deficiencies in M standards" (the figure the page uses)
  deficiencies  distinct citations of the form "(Deficiency MC-27)" that could be read; often fewer than the total, because
                scanned pages do not always read cleanly. Used only to show which standards are cited most.
  standards     citations per standard, e.g. "MC:3;FSC:2" (MC = medical care, FSC = facility security and control, ...)

Many reports are scanned images with no text, so those pages are read by character recognition (OCR), which can
misread a code. A report where nothing about findings could be read is marked unreadable, never counted as zero.
Needs: pip install pymupdf pytesseract, and the tesseract program (apt-get install tesseract-ocr).
"""
import csv, datetime as dt, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
FIELDS = ["url", "read", "deficiencies", "stated", "standards", "checked", "evidence"]
WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
WORDS["no"] = 0


def parse(text):
    """Report text -> (deficiencies or None, stated or None, 'MC:3;FSC:2'). None means nothing about findings could be read."""
    x = re.sub(r"\s+", " ", text)
    # "(Deficiency MC-27 7F 8 )": a standard's letters, a dash, the line number, then a footnote mark. OCR may read the dash as a long dash.
    codes = {(m.group(1).upper().replace("&", ""), int(m.group(2))) for m in re.finditer(r"\(\s?Deficienc(?:y|ies)\s+([A-Za-z&]{1,6})\s?[-\u2010-\u2015]\s?(\d{1,4})", x)}
    # The report's own total is in its summary: "found the facility in compliance with 20 of those standards. ODO found
    # three deficiencies in the remaining standard." Only the FIRST such sentence counts: later ones describe earlier inspections.
    stated = None
    for m in re.finditer(r"found\s+(?:a\s+total\s+of\s+)?(\d{1,3}|[a-z]+)\s+deficienc(?:y|ies)\s+in\s+(?:the\s+)?(?:(?:\d{1,2}|[a-z]+)\s+)?(?:remaining\s+)?(?:(?:\d{1,2}|[a-z]+)\s+)?standards?", x, re.I):
        if re.search(r"\blast\b[^.]{0,60}\binspection", x[max(0, m.start() - 160):m.start()], re.I): continue      # "During its last inspection ... ODO found 6 deficiencies"
        w = m.group(1).lower(); stated = int(w) if w.isdigit() else WORDS.get(w)
        if stated is not None: break
    clean = re.search(r"(found\s+no\s+deficienc|did\s+not\s+(?:find|identify)\s+any\s+deficienc|in\s+compliance\s+with\s+all\s+(?:\d+\s+)?standards)", x, re.I)
    if not codes and stated is None and not clean: return None, None, ""
    by = {}
    for s, _ in codes: by[s] = by.get(s, 0) + 1
    return len(codes), stated, ";".join(f"{k}:{v}" for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0])))


def evidence(text):
    """The sentences the counts rest on, so a person can check them: up to four that give a number of deficiencies or say there were none."""
    x = re.sub(r"\s+", " ", text).replace("|", "/")
    hits = [m.group(0).strip() for m in re.finditer(r"[^.]{0,140}(?:\b(?:\d{1,3}|no|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+deficienc|did\s+not\s+(?:find|identify)|in\s+compliance\s+with\s+all)[^.]{0,120}\.?", x, re.I)]
    return " // ".join(h[:260] for h in hits[:4])


def pdf_text(data, ocr=True):
    """PDF bytes -> (text, how). Pages with almost no text are rendered and read by OCR."""
    import pymupdf as fitz
    doc, parts, used = fitz.open(stream=data, filetype="pdf"), [], False
    for page in doc:
        t = page.get_text()
        if len(t.strip()) < 200 and ocr and page.get_images():
            try:
                import pytesseract
                from PIL import Image
                pix = page.get_pixmap(dpi=200); img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                t = t + "\n" + pytesseract.image_to_string(img); used = True
            except Exception as e:
                print(f"    OCR failed on a page: {str(e)[:100]}")
        parts.append(t)
    return "\n".join(parts), ("ocr" if used else "text")


def main(argv):
    sys.path.insert(0, str(Path(__file__).parent)); from icefetch import fetch_bytes
    cap = int(argv[argv.index("--max") + 1]) if "--max" in argv else 400
    rd = lambda p: list(csv.DictReader(open(p, encoding="utf-8", newline=""), delimiter="|")) if p.exists() else []
    urls = [r["url"] for r in csv.DictReader(open(REF / "ice_inspections.csv", encoding="utf-8"))]
    done = {r["url"]: r for r in rd(REF / "ice_inspection_findings.csv")}
    if "--redo" in argv: done = {}
    todo = [u for u in urls if u not in done or (done[u]["read"] == "unreadable" and done[u]["checked"] < str(dt.date.today() - dt.timedelta(days=90)))][:cap]
    print(f"{len(urls)} inspection reports listed; {len(todo)} to read", flush=True)
    today = str(dt.date.today()); got = {}
    for i in range(0, len(todo), 20):                              # in batches, saving as we go, so a long first run loses nothing if cut short
        batch = todo[i:i + 20]; got = fetch_bytes([u.replace(" ", "%20") for u in batch], pause=0.5)
        for u in batch:
            data = got.get(u.replace(" ", "%20"))
            if not data or data[:4] != b"%PDF": print(f"  not downloaded: {u}"); continue
            try: text, how = pdf_text(data); n, stated, by = parse(text)
            except Exception as e: print(f"  could not read {u}: {str(e)[:100]}"); continue
            done[u] = {"url": u, "read": how if n is not None else "unreadable", "deficiencies": "" if n is None else n, "stated": "" if stated is None else stated, "standards": by, "checked": today, "evidence": evidence(text)}
        with open(REF / "ice_inspection_findings.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows({k: done[u].get(k, "") for k in FIELDS} for u in sorted(done))
        print(f"  {min(i + 20, len(todo))} of {len(todo)}", flush=True)
    rows = list(done.values()); bad = sum(r["read"] == "unreadable" for r in rows)
    differ = sum(1 for r in rows if r["stated"] != "" and r["deficiencies"] != "" and int(r["stated"]) != int(r["deficiencies"]))
    print(f"{len(rows)} reports on file: {len(rows) - bad} read ({sum(r['read'] == 'ocr' for r in rows)} by OCR), {bad} unreadable; {differ} where the citations found differ from the report's own total")


if __name__ == "__main__": main(sys.argv)
