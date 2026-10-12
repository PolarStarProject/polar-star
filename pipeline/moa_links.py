"""Where to read each 287(g) agreement: the newest signed agreement on file for every agency on ICE's current list.

Usage:  python pipeline/moa_links.py        (needs git; runs in GitHub Actions)

ICE posts each signed memorandum of agreement on its 287(g) page. github.com/appelson/Tracking_287g (MIT) keeps every
one it has downloaded, by download date, state and agency. Only the file list is read here (no PDFs are downloaded),
and each agency on ICE's list is matched to the folder with its name. The agency head who signed is named in the
agreement itself; the page links the document rather than retyping names from scans.

Writes data/reference/287g_agreements.csv: state | agency | model | pdf (path inside that repository), and
287g_agreements_meta.json with the repository version the paths belong to.
"""
import csv, datetime as dt, json, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
REPO = "https://github.com/appelson/Tracking_287g"


def key(s):
    """Agency names compared without case, punctuation, apostrophes or the folder name's underscores; a sheriff's
    "department" and "office" are the same agency."""
    s = s.replace("_", " ").replace("%20", " ").replace("’", "'").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s.replace("'s ", "s ").replace("'", "")).strip()
    return re.sub(r"\bsheriffs? (department|dept)\b", "sheriffs office", s)


MODEL = {"Task Force Model": "TFM", "Jail Enforcement Model": "JEM", "Warrant Service Officer": "WSO"}


def newest(paths, agencies):
    """{(state, agency, model): path of the newest agreement for that agency and model}. The model is read from the file
    name (TFM, JEM, WSO); an agreement of another model is never linked in its place."""
    files = {}
    for p in paths:
        parts = p.split("/")
        if len(parts) < 4 or not p.lower().endswith(".pdf"): continue
        m = re.search(r"(TFM|JEM|WSO)", parts[-1].upper())
        if not m: continue
        k = (parts[-3].upper().replace("_", " "), key(parts[-2]), m.group(1))
        stamp = re.sub(r"\D", "", parts[-4])
        if k not in files or stamp > files[k][0]: files[k] = (stamp, p)
    out = {}
    for a in agencies:
        hit = files.get((a["state"].upper(), key(a["agency"]), MODEL.get(a["model"], "")))
        if hit: out[(a["state"], a["agency"], a["model"])] = hit[1]
    return out


def main():
    agencies = list(csv.DictReader(open(REF / "287g_agencies.csv", encoding="utf-8")))
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1", "--quiet", REPO, d], check=True, timeout=900)
        paths = subprocess.run(["git", "-c", "core.quotepath=off", "-C", d, "ls-tree", "-r", "--name-only", "HEAD"], capture_output=True, text=True, check=True).stdout.splitlines()
        sha = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    pick = newest([p for p in paths if p.startswith(("agreements/", "archived_data/"))], agencies)
    if len(pick) < len(agencies) * 0.3: raise SystemExit(f"Only {len(pick)} of {len(agencies)} agencies matched an agreement: left the list as it was.")
    with open(REF / "287g_agreements.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|", lineterminator="\n"); w.writerow(["state", "agency", "model", "pdf"])
        for (s, a, mo), p in sorted(pick.items()): w.writerow([s, a, mo, p])
    (REF / "287g_agreements_meta.json").write_text(json.dumps({"commit": sha, "read": str(dt.date.today())}) + "\n", encoding="utf-8")      # links name this exact version, so they do not break if the repository moves files
    print(f"{len(pick)} of {len(agencies)} agencies matched to a signed agreement", file=sys.stderr)


if __name__ == "__main__": main()
