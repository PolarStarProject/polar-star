"""Join contractor-committee money (fec_pac_recipients.csv) to members of Congress and their vote on H.R. 1 (119th).

Run by hand when the FEC file is re-read:  python pipeline/pac_votes.py
Needs network for the congress-legislators files (public domain, github.com/unitedstates/congress-legislators).

Votes are NOT downloaded per member. Both roll calls were party-line with five exceptions, read from the official
records on 4 Oct 2026 (House roll 190, 3 Jul 2025, 218-214; Senate vote 372, 1 Jul 2025, 50-50, Vice President Yea).
The script rebuilds every seated member's vote from party + exceptions and REFUSES to write unless the totals match.
"""
import csv, json, sys, urllib.request
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
SRC = "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/"
HOUSE_DAY, SENATE_DAY = "2025-07-03", "2025-07-01"
R_NO = {"F000466", "M001184", "C001035", "P000603", "T000476"}   # Fitzpatrick, Massie; Collins, Paul, Tillis
NONVOTING = {"DC", "PR", "GU", "VI", "AS", "MP"}


def term_on(leg, day, kind):
    for t in leg["terms"]:
        if t["type"] == kind and t["start"] <= day <= t["end"]: return t


def vote_of(leg):
    """(chamber, party, state, vote) on the day, or None if not a voting member then."""
    for kind, day in (("rep", HOUSE_DAY), ("sen", SENATE_DAY)):
        t = term_on(leg, day, kind)
        if t and not (kind == "rep" and t["state"] in NONVOTING):
            party = next((a["party"] for a in t.get("party_affiliations", []) if a["start"] <= day <= a["end"]), t["party"])   # party ON THE DAY, not today's
            yes = party == "Republican" and leg["id"]["bioguide"] not in R_NO
            return ("H" if kind == "rep" else "S", party[0], t["state"], "Y" if yes else "N")


def build(legs, pac_rows, links):
    tally = {}
    for l in legs:
        v = vote_of(l)
        if v: tally[v[0] + v[3]] = tally.get(v[0] + v[3], 0) + 1
    if tally != {"HY": 218, "HN": 214, "SY": 50, "SN": 50}: raise ValueError(f"rebuilt votes do not match the official totals: {tally}")
    byfec = {f: l for l in legs for f in l["id"].get("fec", [])}
    link = {r["recipient"]: r for r in links}
    out, loose = {}, 0
    for r in pac_rows:
        amt = int(r["cycle_2024"]) + int(r["cycle_2026"]); k = link.get(r["recipient"])
        who = {byfec[c]["id"]["bioguide"]: byfec[c] for c in k["candidate_ids"].split(",") if c in byfec} if k else {}
        if len(who) != 1: loose += amt; continue            # no member, or more than one: leave it with the committee
        (bg, l), = who.items(); v = vote_of(l) or ("", "", "", "")
        o = out.setdefault(bg, {"bioguide": bg, "name": l["name"].get("official_full") or f'{l["name"]["first"]} {l["name"]["last"]}',
                                "chamber": v[0], "party": v[1], "state": v[2], "vote": v[3], "campaign_usd": 0, "leadership_usd": 0})
        o["campaign_usd" if k["link"] == "C" else "leadership_usd"] += amt
    return sorted(out.values(), key=lambda o: -(o["campaign_usd"] + o["leadership_usd"])), loose


if __name__ == "__main__":
    legs = [l for f in ("legislators-current.json", "legislators-historical.json") for l in json.load(urllib.request.urlopen(SRC + f))]
    rd = lambda n: list(csv.DictReader(open(REF / n, encoding="utf-8"), delimiter="|"))
    rows, loose = build(legs, rd("fec_pac_recipients.csv"), rd("fec_committee_candidates.csv"))
    with open(REF / "pac_members_votes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="|"); w.writeheader(); w.writerows(rows)
    tot = sum(r["campaign_usd"] + r["leadership_usd"] for r in rows)
    print(f"{len(rows)} members, ${tot:,} linked to a member, ${loose:,} left with committees", file=sys.stderr)
