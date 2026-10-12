"""Who signed each 287(g) agreement for the local agency, read from the agreement PDF itself.

Usage:  python pipeline/moa_signers.py        (needs internet and pdftotext; runs in GitHub Actions)

Each agreement in 287g_agreements.csv is a scan that ICE published. Near the end it has a two-column signature block,
"For the LEA:" on the left and "For ICE:" on the right, each with Name and Title lines. The text layer is the scanner's
own character recognition, so a handwritten or smudged name comes out as noise. A name is published only when every
check passes:
  1. it sits in the left (agency) column of the signature block, on the Name line;
  2. it is two to four words, each a capitalised word or an initial, with no digits or stray symbols;
  3. the Title line under it names a local office (Sheriff, Chief, Director, ...), and nothing that belongs to ICE;
  4. the surname appears again somewhere else in the same agreement, outside the signature block (the agency's own
     contact listing in Appendix A, as a rule). Two places in the agency's own document is the confirmation;
  5. it is not a name that signs on the ICE side of agreements.
Anything else is left out, and the page shows the agreement with no name: the PDF link is always there to read it.
Results are kept by PDF path, so a later run reads only new agreements.
Separately, Appendix A of each agreement types out the agency's point of contact (name and title). When that reads
cleanly it is kept as "contact": who the agreement names for the agency, labelled as such, not as the signer.
Writes data/reference/287g_signers.csv: pdf | name | title | status (named, or why not) | contact | contact_title,
and 287g_signers_meta.json.
"""
import csv, datetime as dt, json, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
PARSER = 2          # bump when the reading rules change, so every agreement is read again
FIELDS = ["pdf", "name", "title", "status", "contact", "contact_title"]
LEA_TITLE = re.compile(r"\b(SHERIFF|UNDERSHERIFF|CHIEF|DIRECTOR|COMMISSIONER|SECRETARY|SUPERINTENDENT|COLONEL|WARDEN|ADMINISTRATOR|"
                       r"MARSHAL|CONSTABLE|COMMANDER|EXECUTIVE|MAYOR|MANAGER|GOVERNOR|ATTORNEY GENERAL|ADJUTANT|PRESIDENT|JUDGE|SUPERVISOR)\b")
ICE_WORDS = re.compile(r"\b(ICE|IMMIGRATION|CUSTOMS|HOMELAND|ENFORCEMENT AND REMOVAL|ERO|HSI|DEPUTY DIRECTOR|ACTING DIRECTOR|FIELD OFFICE)\b")
ICE_SIGNERS = {"MADISON SHEAHAN", "RUSSELL HOTT", "CHARLES WALL", "TODD LYONS", "TAE JOHNSON", "THOMAS HOMAN", "MATTHEW ALBENCE",
               "TONY PHAM", "TIMOTHY ROBBINS", "PAUL BLACKMAN", "KENNETH GENALO", "GARRETT RIPA", "PATRICK LECHLEITNER", "CALEB VITELLO"}
is_ice = lambda name: f"{name.split()[0]} {surname(name)}".upper() in ICE_SIGNERS
ORG_WORDS = re.compile(r"\b(POLICE|DEPARTMENT|DEPT|COUNTY|OFFICE|SHERIFF|SHERIFFS|CITY|BOROUGH|TOWNSHIP|STATE|PATROL|CORRECTIONS|"
                       r"AGENCY|DIVISION|BUREAU|PUBLIC|SAFETY|CONSTABLE|PRECINCT|COMMISSION|TOWN|VILLAGE|PARISH)\b")
NAME_LINE = re.compile(r"^\s*N\s*a\s*[mt]\s*n?\s*e\s*[:·.;,]?\s*(.*)$", re.I)
TITLE_LINE = re.compile(r"^\s*T\s*i\s*t\s*l\s*e\s*[:·.;,]?\s*(.*)$", re.I)
WORD = re.compile(r"^(?:[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*|[A-Z]\.?|Mc[A-Z][a-z]+|Mac[A-Z][a-z]+|(?:Jr|Sr|II|III|IV)\.?)$")


def clean_name(s):
    s = re.sub(r"[_~]+", " ", s).strip(" .,:;·-")
    s = re.sub(r"\s{2,}.*$", "", s)                     # stop at the first wide gap: anything after is stray marks
    w = s.split()
    if not 2 <= len(w) <= 4 or not all(WORD.match(x) for x in w): return ""
    if sum(len(x.strip(".")) > 1 for x in w) < 2: return ""     # at least a first name and a surname
    if ORG_WORDS.search(" ".join(w).upper()): return ""
    return " ".join(w)


def surname(name):
    w = [x for x in name.split() if not re.fullmatch(r"(?:Jr|Sr|II|III|IV)\.?", x)]
    return w[-1].strip(".")


def parse(text):
    """(name, title, status) from the text of one agreement (pdftotext -layout)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.search(r"By\s+signing\s+this", l, re.I)), 0)
    hdr = split = None
    for i in range(start, len(lines)):
        if not re.search(r"For\s+the\s+LEA", lines[i], re.I): continue
        for j in range(i, min(i + 12, len(lines))):          # "For ICE:" is on the same line, or a few lines lower in the right column
            m = re.search(r"For\s+ICE", lines[j], re.I)
            if m and m.start() > 20: hdr, split = i, m.start(); break
        break
    if hdr is None: return "", "", "no two-column signature block"
    left = lambda l: l[:max(split - 2, 1)]
    end = next((k for k in range(hdr + 1, min(hdr + 30, len(lines))) if re.search(r"APPENDI\s*X|POINTS?\s+OF\s+CONTACT", lines[k], re.I)), min(hdr + 30, len(lines)))
    block = lines[hdr:end]
    name = title = ""
    for k, l in enumerate(block):
        m = NAME_LINE.match(left(l))
        if m and not name:
            raw = re.sub(r"^[_~.\s]+", "", m.group(1)); h = HONORIFIC.match(raw)
            name = clean_name(raw[h.end():] if h else raw)
            if not name: return "", "", "name not legible"
            for l2 in block[k + 1:k + 8]:
                t = TITLE_LINE.match(left(l2))
                if t: title = re.sub(r"[_~]+", " ", t.group(1)); title = re.sub(r"\s{2,}.*$", "", title.strip()).strip(" .,:;·-"); break
            break
    if not name: return "", "", "no Name line in the agency column"
    T = title.upper()
    if not title or not LEA_TITLE.search(T) or ICE_WORDS.search(T): return "", "", "title missing or not a local office"
    if not re.fullmatch(r"[A-Za-z .,'&-]{3,60}", title) or re.search(r"(?<![A-Za-z])[a-z](?![A-Za-z.])", title): return "", "", "title not legible"
    sn = surname(name)
    if is_ice(name): return "", "", "an ICE signer's name"
    rest = "\n".join(lines[:hdr] + lines[end:])
    if len(sn) < 3 or not re.search(r"(?<![A-Za-z])" + re.escape(sn) + r"(?![a-z])", rest, re.I): return "", "", "surname not found a second time in the agreement"
    return name, tidy_title(title), "named"


HONORIFIC = re.compile(r"^(Sheriff|Chief|Constable|Director|Commissioner|Colonel|Marshal|Mayor|Captain|Major|Lt\.?|Sgt\.?|Mr\.?|Ms\.?|Mrs\.?|Dr\.?)\s+")


def tidy_title(t):
    t = re.sub(r"\s+", " ", t).strip(" .,")
    if t.islower(): t = t.title()
    t = re.sub(r"(?i)^chief\s+of\s+pol\w*$", "Chief of Police", t)
    return t


def contact(text):
    """(name, title) of the agency's point of contact in Appendix A, typed text, when it reads cleanly; else ("", "").
    This is who the agreement names as the agency's contact, not necessarily who signed; the page labels it that way.
    The public affairs contact later in the agreement is never used."""
    lines = text.splitlines()
    i = next((k for k, l in enumerate(lines) if re.search(r"POINTS?\s+OF\s+CONTACT", l, re.I) and k > len(lines) * 0.6), None)
    if i is None: return "", ""
    j = next((k for k in range(i, min(i + 40, len(lines))) if re.search(r"For\s+the\s+LEA", lines[k], re.I)), None)
    if j is None: return "", ""
    first = re.split(r"For\s+the\s+LEA\s*:?", lines[j], flags=re.I)[1]
    cand = [x for x in [first] + lines[j + 1:j + 9] if re.sub(r"[_\s]", "", x)]
    cand = [re.sub(r"\s{2,}.*$", "", re.sub(r"_+", " ", x).strip()) for x in cand][:6]
    if re.search(r"PUBLIC\s+(INFORMATION|AFFAIRS)|\bPIO\b|For\s+ICE", " ".join(cand), re.I): return "", ""
    name = title = ""
    for x in cand:
        h = HONORIFIC.match(x)
        if not name:
            n = clean_name(x[h.end():] if h else x)
            if n and not LEA_TITLE.search(n.upper()): name = n; title = h.group(1) if h and LEA_TITLE.search(h.group(1).upper()) else ""; continue
        elif not title and len(x) <= 40 and LEA_TITLE.search(x.upper()) and not ICE_WORDS.search(x.upper()) and re.fullmatch(r"[A-Za-z .,'&-]+", x): title = x.strip(" .,"); break
        elif name: break
    if not name or not title or is_ice(name): return "", ""
    return name, tidy_title(title)


def main():
    meta = json.loads((REF / "287g_agreements_meta.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(REF / "287g_agreements.csv", encoding="utf-8"), delimiter="|"))
    out_p = REF / "287g_signers.csv"
    old = json.loads((REF / "287g_signers_meta.json").read_text(encoding="utf-8")) if (REF / "287g_signers_meta.json").exists() else {}
    prev = {r["pdf"]: r for r in csv.DictReader(open(out_p, encoding="utf-8"), delimiter="|")} if out_p.exists() and old.get("parser") == PARSER else {}
    out, failed, asked = [], 0, 0
    with tempfile.TemporaryDirectory() as td:
        for r in rows:
            if r["pdf"] in prev and prev[r["pdf"]]["status"] != "download failed": out.append(prev[r["pdf"]]); continue
            asked += 1; url = f"https://raw.githubusercontent.com/appelson/Tracking_287g/{meta['commit']}/" + urllib.parse.quote(r["pdf"])
            f = Path(td) / "a.pdf"; ok = False
            for i in range(3):
                try: urllib.request.urlretrieve(url, f); ok = True; break
                except Exception: time.sleep(10)
            if not ok: failed += 1; out.append({"pdf": r["pdf"], "name": "", "title": "", "status": "download failed", "contact": "", "contact_title": ""}); continue
            t = subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True, timeout=120).stdout
            n, ti, st = parse(t); cn, ct = contact(t)
            out.append({"pdf": r["pdf"], "name": n, "title": ti, "status": st, "contact": cn, "contact_title": ct})
    if asked and failed > asked / 4: raise SystemExit(f"{failed} of {asked} agreements could not be downloaded: left the list as it was.")
    # A name that turns up as the agency signer for many different agencies is not a local official.
    by = {}
    for o in out:
        if o["name"]: by.setdefault(o["name"].upper(), set()).add(o["pdf"].split("/")[-2] if "/" in o["pdf"] else o["pdf"])
    for o in out:
        if o["name"] and len(by[o["name"].upper()]) > 3: o.update(name="", title="", status="same name on many agencies' agreements")
    with open(out_p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(out)
    named = sum(o["status"] == "named" for o in out)
    (REF / "287g_signers_meta.json").write_text(json.dumps({"read": str(dt.date.today()), "agreements": len(out), "named": named, "contacts": sum(bool(o.get("contact")) for o in out), "parser": PARSER, "commit": meta["commit"]}, indent=1), encoding="utf-8")
    print(f"{named} of {len(out)} agreements have a confirmed signer name", file=sys.stderr)


if __name__ == "__main__": main()
