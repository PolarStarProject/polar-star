"""Members of Congress: how each voted on the laws that fund and expand immigration enforcement, the committees that
oversee ICE they sit on, and money from detention and ICE contractor committees that reached them.

Usage:  python pipeline/politicians.py          (run by the refresh, step "politicians"; needs the network)
Reads   clerk.house.gov and senate.gov roll-call XML (official records), and the public-domain congress-legislators files
        (github.com/unitedstates/congress-legislators) for names, ids, official sites and committee membership.
Writes, in data/reference/ ("|" separated):
  roll_calls.csv     vote_id|chamber|date|bill|law|question|yeas|nays|present|not_voting|url
  member_votes.csv   vote_id|bioguide|vote|party    vote: Y yes, N no, P present, X not voting; party as the record gives it on the day
  members.csv        bioguide|name|chamber|party|state|district|url|committees    every member who cast any of these votes
                     or sits in Congress now; committees = ";"-joined names of committees and subcommittees that oversee ICE

Every roll call is checked against the totals printed in its own record; the run stops, writing nothing, if they differ.
Only officials acting in office appear here. Votes are public records; nothing is inferred about anyone's views.
A roll call already read is not fetched again (votes do not change), so later runs only add new ones.
"""
import csv, json, re, sys, time, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from identity import USER_AGENT

REF = Path(__file__).resolve().parent.parent / "data" / "reference"
LEG = "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/"
# the laws, by the roll calls that passed them. "find" means search that year's roll calls for the bill and question.
VOTES = [
    {"id": "s5-h", "chamber": "H", "year": 2025, "roll": 23, "bill": "S 5", "law": "P.L. 119-1", "expect": (263, 156)},
    {"id": "s5-s", "chamber": "S", "congress": 119, "session": 1, "roll": 7, "bill": "S 5", "law": "P.L. 119-1", "expect": (64, 35)},
    {"id": "hr1-s", "chamber": "S", "congress": 119, "session": 1, "roll": 372, "bill": "H R 1", "law": "P.L. 119-21", "expect": (50, 50)},
    {"id": "hr1-h", "chamber": "H", "year": 2025, "roll": 190, "bill": "H R 1", "law": "P.L. 119-21", "expect": (218, 214)},
    {"id": "s2-s", "chamber": "S", "congress": 119, "session": 2, "find": "S 2", "after": "2026-05-25", "before": "2026-06-10", "law": "P.L. 119-98"},
    {"id": "s2-h", "chamber": "H", "year": 2026, "find": "S 2", "after": "2026-06-01", "before": "2026-06-11", "law": "P.L. 119-98", "expect": (214, 212)},
]
OVERSIGHT = [r"^House Committee on Appropriations.*Homeland Security", r"^Senate Committee on Appropriations.*Homeland Security",
             r"^House Committee on Homeland Security$", r"^Senate Committee on Homeland Security and Governmental Affairs$",
             r"^House Committee on the Judiciary$", r"^Senate Committee on the Judiciary$", r"Judiciary.*Immigration", r"Homeland Security.*Border"]
VMAP = {"Yea": "Y", "Aye": "Y", "Yes": "Y", "Nay": "N", "No": "N", "Present": "P", "Not Voting": "X"}
MON = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=40) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 * (i + 1))
        except Exception: time.sleep(2 * (i + 1))
    raise RuntimeError(f"could not read {url}")


def house_url(year, roll): return f"https://clerk.house.gov/evs/{year}/roll{roll:03d}.xml"
def senate_url(c, s, roll): return f"https://www.senate.gov/legislative/LIS/roll_call_votes/vote{c}{s}/vote_{c}_{s}_{roll:05d}.xml"


def parse_house(xml):
    """House roll-call XML -> (meta, {bioguide: vote})."""
    r = ET.fromstring(xml); m = r.find("vote-metadata")
    d = m.findtext("action-date") or ""                                     # "22-Jan-2025"
    dd, mm, yy = d.split("-") if d.count("-") == 2 else ("1", "Jan", "1900")
    tot = m.find("vote-totals/totals-by-vote")
    meta = {"date": f"{yy}-{MON.get(mm[:3], 1):02d}-{int(dd):02d}", "bill": re.sub(r"\s+", " ", (m.findtext("legis-num") or "").strip()),
            "question": (m.findtext("vote-question") or "").strip(), "yeas": int(tot.findtext("yea-total") or 0), "nays": int(tot.findtext("nay-total") or 0),
            "present": int(tot.findtext("present-total") or 0), "not_voting": int(tot.findtext("not-voting-total") or 0)}
    votes = {}
    for rv in r.findall("vote-data/recorded-vote"):
        lg = rv.find("legislator"); v = VMAP.get((rv.findtext("vote") or "").strip())
        if lg is not None and v and lg.get("name-id"): votes[lg.get("name-id")] = (v, (lg.get("party") or "").strip())
    return meta, votes


def parse_senate(xml, lis2bio):
    """Senate roll-call XML -> (meta, {bioguide: vote}). Senators are keyed by LIS id in the record."""
    r = ET.fromstring(xml)
    m = re.search(r"[A-Za-z]+ \d{1,2}, \d{4}", r.findtext("vote_date") or ""); d = m.group(0) if m else ""      # "January 20, 2025, 06:57 PM"
    try: day = time.strftime("%Y-%m-%d", time.strptime(d, "%B %d, %Y"))
    except ValueError: day = ""
    doc = r.find("document"); bill = ""
    if doc is not None: bill = re.sub(r"\.", " ", (doc.findtext("document_type") or "")).strip().replace("  ", " ") + " " + (doc.findtext("document_number") or "").strip()
    c = r.find("count")
    meta = {"date": day, "bill": re.sub(r"\s+", " ", bill).strip(), "question": (r.findtext("question") or r.findtext("vote_question_text") or "").strip(),
            "yeas": int(c.findtext("yeas") or 0), "nays": int(c.findtext("nays") or 0), "present": int(c.findtext("present") or 0) if c.findtext("present") else 0,
            "not_voting": int(c.findtext("absent") or 0) if c.findtext("absent") else 0}
    votes = {}
    for mb in r.findall("members/member"):
        b = lis2bio.get((mb.findtext("lis_member_id") or "").strip()); v = VMAP.get((mb.findtext("vote_cast") or "").strip())
        if b and v: votes[b] = (v, (mb.findtext("party") or "").strip())
    return meta, votes


def check(meta, votes, cfg):
    """The member votes must add up to the record's own totals, and to the published tally where one is given."""
    y = sum(1 for v, _ in votes.values() if v == "Y"); n = sum(1 for v, _ in votes.values() if v == "N")
    if (y, n) != (meta["yeas"], meta["nays"]): raise ValueError(f"{cfg['id']}: members add to {y}-{n}, record says {meta['yeas']}-{meta['nays']}")
    if cfg.get("expect") and (y, n) != tuple(cfg["expect"]): raise ValueError(f"{cfg['id']}: {y}-{n}, expected {cfg['expect']}")


def passage(meta, bill):
    q = meta["question"].lower(); return meta["bill"].replace(".", "").upper() == bill.upper() and ("passage" in q or "concur" in q or "agree" in q)


def read_vote(cfg, lis2bio):
    """One configured vote -> (meta with url, votes)."""
    H = cfg["chamber"] == "H"
    if "roll" in cfg:
        url = house_url(cfg["year"], cfg["roll"]) if H else senate_url(cfg["congress"], cfg["session"], cfg["roll"])
        x = get(url)
        if x is None: raise RuntimeError(f"{cfg['id']}: no record at {url}")
        meta, votes = parse_house(x) if H else parse_senate(x, lis2bio)
        return {**meta, "url": url}, votes
    found = None; misses = 0
    for roll in range(1, 1200):                                              # search the year's roll calls in order for the last passage vote in the window
        url = house_url(cfg["year"], roll) if H else senate_url(cfg["congress"], cfg["session"], roll)
        x = get(url)
        if x is None:
            misses += 1
            if misses > 3: break
            continue
        misses = 0; meta, votes = parse_house(x) if H else parse_senate(x, lis2bio)
        if meta["date"] > cfg["before"]: break
        if meta["date"] >= cfg["after"] and passage(meta, cfg["find"]): found = ({**meta, "url": url}, votes)
    if not found: raise RuntimeError(f"{cfg['id']}: no passage vote on {cfg['find']} between {cfg['after']} and {cfg['before']}")
    return found


def oversight_committees(comms, members):
    """{bioguide: [committee or subcommittee names]} for the committees that oversee ICE."""
    names = {}
    for c in comms:
        top = f"{'House' if c['type'] == 'house' else 'Senate' if c['type'] == 'senate' else 'Joint'} Committee on {re.sub(r'^(House|Senate) (Committee on )?', '', c['name'])}" if not c["name"].startswith(("House", "Senate")) else c["name"]
        names[c["thomas_id"]] = top
        for s in c.get("subcommittees", []): names[c["thomas_id"] + s["thomas_id"]] = f"{top}: {s['name']}"
    out = {}
    for cid, mem in members.items():
        nm = names.get(cid, "")
        if not any(re.search(p, nm) for p in OVERSIGHT): continue
        for m in mem:
            if m.get("bioguide"): out.setdefault(m["bioguide"], []).append(nm + (f" ({m['title']})" if m.get("title") else ""))
    return out


def run():
    legs = json.loads(get(LEG + "legislators-current.json")); old = json.loads(get(LEG + "legislators-historical.json"))
    allleg = legs + [l for l in old if any(t["end"] >= "2025-01-03" for t in l["terms"])]
    lis2bio = {l["id"]["lis"]: l["id"]["bioguide"] for l in allleg if l["id"].get("lis")}
    rd = lambda n: list(csv.DictReader(open(REF / n, encoding="utf-8"), delimiter="|")) if (REF / n).exists() else []
    mv = rd("member_votes.csv")
    have = {r["vote_id"]: r for r in rd("roll_calls.csv")} if mv and "party" in mv[0] else {}      # an older file without the party on the day is read again
    mv = [r for r in mv if r["vote_id"] in have]
    calls = []
    for cfg in VOTES:
        if cfg["id"] in have: calls.append(have[cfg["id"]]); continue
        meta, votes = read_vote(cfg, lis2bio); check(meta, votes, cfg)
        calls.append({"vote_id": cfg["id"], "chamber": cfg["chamber"], "date": meta["date"], "bill": meta["bill"], "law": cfg["law"], "question": meta["question"],
                      "yeas": meta["yeas"], "nays": meta["nays"], "present": meta["present"], "not_voting": meta["not_voting"], "url": meta["url"]})
        mv += [{"vote_id": cfg["id"], "bioguide": b, "vote": v, "party": pa} for b, (v, pa) in sorted(votes.items())]
        print(f"{cfg['id']}: {meta['date']} {meta['bill']} {meta['question']} {meta['yeas']}-{meta['nays']} ({len(votes)} members)", file=sys.stderr)
    com = oversight_committees(json.loads(get(LEG + "committees-current.json")), json.loads(get(LEG + "committee-membership-current.json")))
    voters = {r["bioguide"] for r in mv}; cur = {l["id"]["bioguide"] for l in legs}
    rows = []
    for l in allleg:
        b = l["id"]["bioguide"]
        if b not in voters and b not in cur: continue
        t = l["terms"][-1]; party = t.get("party", "")
        rows.append({"bioguide": b, "name": l["name"].get("official_full") or f"{l['name']['first']} {l['name']['last']}", "chamber": "S" if t["type"] == "sen" else "H",
                     "party": {"Republican": "R", "Democrat": "D", "Independent": "I"}.get(party, party[:1]), "state": t["state"], "district": t.get("district", "") if t["type"] == "rep" else "",
                     "url": t.get("url", ""), "committees": ";".join(sorted(set(com.get(b, [])))) if b in cur else "", "current": "1" if b in cur else ""})
    def write(name, rows, fields):
        with open(REF / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    write("roll_calls.csv", calls, ["vote_id", "chamber", "date", "bill", "law", "question", "yeas", "nays", "present", "not_voting", "url"])
    write("member_votes.csv", sorted(mv, key=lambda r: (r["vote_id"], r["bioguide"])), ["vote_id", "bioguide", "vote", "party"])
    write("members.csv", sorted(rows, key=lambda r: r["name"]), ["bioguide", "name", "chamber", "party", "state", "district", "url", "committees", "current"])
    print(f"{len(calls)} roll calls, {len(mv)} member votes, {len(rows)} members ({sum(1 for r in rows if r['committees'])} on committees that oversee ICE)", file=sys.stderr)


if __name__ == "__main__":
    run()
