"""The weekly to-do: everything the refresh found that needs a person, in one Markdown file.

Usage:  python pipeline/todo_report.py          (after the refresh; writes data/watch/todo.md)

The workflow posts the file as a comment on one open GitHub issue ("Weekly to-do"), so the publisher gets one
notification a week. Nothing here changes the page: it only lists what to check, each item with the link to check it.
The issue is public, like the repository; the list holds only public records and links.
"""
import csv, datetime as dt, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
HAND_WARN = 7
ROUTINE = ("withdrawal", "appearance", "transcript", "notice of attorney", "pro hac vice", "cjra", "certificate of service", "corporate disclosure")
# Docket entries that rarely change a case's status: listed apart so the substantive ones stand out.


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8"), delimiter="|")) if p.exists() else []


def jload(p):
    try: return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError: return {}


def sections(root, today):
    ref = root / "data" / "reference"; out = []
    st = jload(root / "data" / "refresh_status.json")
    bad = {k: v for k, v in (st.get("steps") or {}).items() if v not in ("ok", "not due")}
    if bad:
        out.append(("Refresh steps that failed", [f"`{k}`: {v}" + (f" — {(st.get('errors') or {}).get(k, '')[-300:]}" if (st.get("errors") or {}).get(k) else "") for k, v in sorted(bad.items())]))
    disp = {r["id"]: r for r in rd(ref / "ice_local_disputes.csv")}
    seen = {r["id"]: r.get("reviewed_through", "") for r in rd(ref / "dispute_dockets.csv")}     # newest filing already looked at by hand
    moved, routine, missing = [], [], []
    for k in rd(ref / "dispute_dockets_checked.csv"):
        r = disp.get(k["id"])
        if not r: continue
        if not k["cl_id"]: missing.append(f"`{k['id']}`: {k['court']} {k['docket_number']} not found on CourtListener yet"); continue
        if r.get("final") == "Y": continue
        since = max(r.get("status_date") or r.get("date") or "", seen.get(k["id"], ""))
        if k["last_filing"] and k["last_filing"] > since:
            line = f"`{k['id']}`: status on file {since or 'none'}, docket's newest filing {k['last_filing']} — [docket]({k['cl_url']})"
            if k.get("entry_date"): line += f"<br>newest entry {k['entry_date']}: {k['entry_text'][:240]}" + (f" ([document]({k['entry_doc']}))" if k.get("entry_doc") else "")
            (routine if any(w in (k.get("entry_text") or "").lower() for w in ROUTINE) else moved).append(line)
    if moved: out.append(("Disputes whose court docket moved past the status on the page (rewrite the status if the step matters, or set reviewed_through in dispute_dockets.csv)", moved))
    if routine: out.append(("Docket filings that look routine (lawyers joining or leaving, transcripts)", routine))
    used = {u for r in disp.values() for u in (r.get("source_url"), r.get("status_url")) if u}           # a link already replaced is not listed
    dead = [f"{r['url']} (failed {r['checked']}" + (f", last loaded {r['last_ok']})" if r.get("last_ok") else ")") for r in rd(ref / "disputes_checked.csv") if r["ok"] == "0" and (not used or r["url"] in used)]
    if dead: out.append(("Dispute source links that did not load", dead))
    hand = []
    for r in rd(ref / "hotlines_manual.csv"):
        left = 30 - (today - dt.date.fromisoformat(r["checked"])).days
        if left <= HAND_WARN: hand.append(f"`{r['key']}`: " + (f"expired {-left} days ago" if left < 0 else f"hides in {left} days") + f" — check again on {r['source']} and update the date in hotlines_manual.csv")
    if hand: out.append(("Help lines checked by hand that need checking again", hand))
    auto = {r["key"]: r for r in rd(ref / "hotlines_checked.csv")}
    manual = {r["key"] for r in rd(ref / "hotlines_manual.csv")}
    hid = [f"`{k}`: {r['reason'] or 'not confirmed'}" for k, r in sorted(auto.items()) if r["ok"] != "1" and k not in manual]
    if hid: out.append(("Help lines hidden this week (not confirmed, no check by hand)", hid))
    orgs = [f"{r['org']}: {r['reason'] or 'not confirmed'}" for r in rd(ref / "family_orgs_checked.csv") if r["ok"] != "1"]
    if orgs: out.append(("Organizations hidden on the Organizations tab (fix the row in family_orgs.csv, or remove it)", orgs))
    stale = jload(root / "data" / "health.json").get("stale") or []
    if stale: out.append(("Sources older than they should be", stale))
    if missing: out.append(("Court dockets not found yet (they are retried each week)", missing))
    return out


def render(secs, today):
    if not secs: return f"# Weekly to-do, {today}\n\nNothing needs attention this week.\n"
    L = [f"# Weekly to-do, {today}", "", f"{sum(len(i) for _, i in secs)} items. Nothing here changes the page by itself.", ""]
    for h, items in secs: L += [f"## {h} ({len(items)})", ""] + [f"- {x}" for x in items] + [""]
    return "\n".join(L)


def main():
    today = dt.date.today()
    text = render(sections(ROOT, today), today)
    (ROOT / "data" / "watch").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "watch" / "todo.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__": main()
