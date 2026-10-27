"""Alerts from the records (formerly the watch list): figures that stand out, worked out from the page's own data on every build.

Two kinds of alert:
  overdue    a publication the government is required to make, or makes on a fixed schedule, is late.
             Published on the page as soon as it is triggered: it is a plain fact anyone can check.
  facility   a facility whose rate of deaths, or of sexual abuse allegations, is well above the rate across all
             listed facilities over the same period. Worked out every build but kept off the page (and out of the
             feed and the briefs) until data/reference/watch_rules.json says "facility_published": true, so the
             thresholds can be reviewed first. Refusals of officials at the same site are listed beside it as
             facts; the alert never says one thing caused another.

Nothing here is about a person: alerts name facilities, agencies and the bodies that oversee them.
Outputs, all rebuilt each time:
  site["watch"]                        what the page shows (published alerts only)
  data/watch/briefs/<id>.md            a one-page brief per published alert, for the publisher to send by hand
  data/watch/candidates.json           every facility alert worked out, published or not, for review
  site/watch.xml                       an Atom feed of published alerts
  data/reference/watch_log.csv         when each alert first opened and, if it did, closed (kept between builds)
"""
import csv, datetime as dt, json
from pathlib import Path
from xml.sax.saxutils import escape

# Who oversees what. Bodies and their public pages only; never a person's name or a private contact.
OVERSIGHT = {
    "appropriations": [("House Appropriations Committee, Homeland Security Subcommittee", "https://appropriations.house.gov/"),
                       ("Senate Appropriations Committee, Homeland Security Subcommittee", "https://www.appropriations.senate.gov/")],
    "homeland": [("House Committee on Homeland Security", "https://homeland.house.gov/"),
                 ("Senate Committee on Homeland Security and Governmental Affairs", "https://www.hsgac.senate.gov/")],
    "oig": [("DHS Office of Inspector General (hotline)", "https://www.oig.dhs.gov/hotline")],
    "crcl": [("DHS Office for Civil Rights and Civil Liberties (complaints)", "https://www.dhs.gov/file-civil-rights-complaint")],
    "judiciary": [("House Judiciary Committee", "https://judiciary.house.gov/"), ("Senate Judiciary Committee", "https://www.judiciary.senate.gov/")],
}
STATE_AG_INSPECTS = {"CA": ("California Attorney General (inspects immigration detention in the state)", "https://oag.ca.gov/")}
ICE_EVERY = 14            # days between the detention statistics files Congress asks for
RULES_DEFAULT = {"facility_published": False, "window_months": 12, "min_avg_held": 50,
                 "deaths_min": 3, "deaths_ratio": 2.0, "max_p": 0.05, "alleg_min": 5, "alleg_ratio": 2.0, "audit_max_age_years": 3, "long_min": 10, "long_ratio": 2.0, "long_published": True}


def ice_overdue(as_of, today, every=ICE_EVERY):
    """ICE's detention statistics file. Open once more than one full cycle has passed with no new file.
    today: the day ICE's page was last checked (the page uses the same day)."""
    if not as_of: return None
    days = (dt.date.fromisoformat(today) - dt.date.fromisoformat(as_of)).days
    if days <= every + 7: return None                                       # a week's grace past the next due date
    return {"id": "ice-detention-stats", "kind": "overdue", "d": {"days": days, "missed": days // every, "last": as_of, "checked": today},
            "title": "ICE has not posted its required detention statistics",
            "facts": [f"ICE's last detention statistics file is dated {_d(as_of)}: {days} days with no new file when ICE's page was checked on {_d(today)}.",
                      f"Congress asked for this file every two weeks, so about {days // every} updates have been missed.",
                      "The requirement was added in the fiscal 2020 DHS appropriations law; reporting has noted debate over whether it still binds ICE."],
            "sources": [("ICE detention statistics page", "https://www.ice.gov/detain/detention-management"),
                        ("The Marshall Project, Jul 15, 2026, on the requirement and the gap", "https://www.themarshallproject.org/2026/07/15/ice-data-immigration-detention-transparency")],
            "to": OVERSIGHT["appropriations"] + OVERSIGHT["homeland"] + OVERSIGHT["oig"]}


def _d(s):
    """'2026-07-20' -> 'July 20, 2026'; '2025-08' -> 'August 2025'."""
    if len(s) == 7: return dt.date.fromisoformat(s + "-01").strftime("%B %Y")
    x = dt.date.fromisoformat(s); return f"{x.strftime('%B')} {x.day}, {x.year}"


def poisson_tail(k, mean):
    """Chance of k or more events if the site had the same rate as everywhere else: how surprising the count is."""
    import math
    if mean <= 0: return 0.0 if k > 0 else 1.0
    lm = math.log(mean)
    return max(0.0, 1 - sum(math.exp(i * lm - mean - math.lgamma(i + 1)) for i in range(k)))      # in logs, so large counts do not overflow


def _months_back(last, n):
    y, m = int(last[:4]), int(last[5:7]); out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}"); y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return sorted(out)


def _n365(p):
    """People held more than a year so far at one place: the count when the profile carries it, else from the rounded share."""
    if p.get("n365") is not None: return p["n365"]
    return round(p["n"] * p["over365"] / 100) if p.get("over365") else 0


def long_national(hp, ice_los=None):
    """Everyone held more than a year (and more than six months) on the newest day in the records. Open while anyone is."""
    if not hp: return None
    N = hp["national"]; n = N["n"]; n365 = _n365(N); n180 = N.get("n180") if N.get("n180") is not None else round(n * (N.get("over180") or 0) / 100)
    if not n365: return None
    d = {"n": n, "n365": n365, "n180": n180, "p365": round(100 * n365 / n, 1), "p180": round(100 * n180 / n, 1), "as_of": hp["as_of"]}
    if ice_los: d.update(ice_day=ice_los[0], ice365=ice_los[1])
    return {"id": "long-detention", "kind": "long", "d": d,
            "title": "Share of people in ICE detention held more than a year",
            "facts": [f"{n365:,} people in ICE detention on {_d(hp['as_of'])} had been held more than a year, and {n180:,} more than six months ({d['p365']}% and {d['p180']}% of the {n:,} held).",
                      "Long stays often come from cases still before a judge or on appeal, which can take more than a year. ICE's records do not say why any one stay has lasted this long, whether it has been reviewed, or whether the person has a final removal order.",
                      *([f"ICE's own twice-monthly file gives a lower figure, {ice_los[1]:,} held more than a year on {_d(ice_los[0])}. This count runs from the start of each continuous stay in ICE detention, across transfers; ICE's file does not say how it measures, so the two are not directly comparable."] if ice_los else []),
                      "For people with a final removal order, the Supreme Court set six months as the presumptively reasonable limit when removal is not reasonably foreseeable (Zadvydas v. Davis, 2001). The records cannot show how many of these stays that applies to; that is the question for the bodies below."],
            "sources": [("ICE detention records released to the Deportation Data Project", "https://github.com/deportationdata/ice"),
                        ("Zadvydas v. Davis, 533 U.S. 678 (2001)", "https://supreme.justia.com/cases/federal/us/533/678/")],
            "to": OVERSIGHT["judiciary"] + OVERSIGHT["homeland"] + OVERSIGHT["oig"] + OVERSIGHT["crcl"]}


def bh_cut(tests, q):
    """The Benjamini-Hochberg cut-off: with many facilities and measures tested at once, keep the expected share of chance
    flags at or below q. Returns the largest p-value that still counts (0 when none does)."""
    ps = sorted(t[0] for t in tests); m = len(ps); cut = 0
    for i, p in enumerate(ps, 1):
        if p <= q * i / m: cut = p
    return cut


def facility_alerts(site, pdm, rules, hp=None):
    """Facilities where deaths, the latest audited allegations, or the share of people held more than a year are far above
    the rate across all facilities, on a count that is unlikely by chance. pdm: {code: {"YYYY-MM": person_days}}."""
    F = site["facilities"]; why, ctx, tests = {}, {}, []
    ws = we = None
    if pdm:
        last = max(m for v in pdm.values() for m in v); win = _months_back(last, rules["window_months"]); ws, we = win[0], win[-1]
        listed = {c[7] for c in site.get("contracts", []) if c[7]}
        days = {c: sum(pdm.get(c, {}).get(m, 0) for m in win) for c in listed}
        dead = {c: sum(1 for d in F[c].get("death_reports", []) if ws <= d[0][:7] <= we) for c in listed}
        all_days, all_dead = sum(days.values()), sum(dead.values())
        nat = all_dead / all_days * 3_650_000 if all_days else 0           # deaths for every 10,000 people held for a year
        cond = site.get("conduct") or {}; nat_a = cond.get("overall") or 0 # allegations for every 1,000 people held for a year
        newest = {}
        for r in cond.get("sites", []):                                     # [code, audit date, allegations, avg held, rate, url, months, before, operator]
            if r[0] not in newest or r[1] > newest[r[0]][1]: newest[r[0]] = r
        cutoff = f"{int(we[:4]) - rules['audit_max_age_years']}{we[4:]}"
        for c in listed:
            avg = days[c] / (30.44 * len(win))
            if avg >= rules["min_avg_held"] and dead[c] >= rules["deaths_min"] and nat:
                rate = dead[c] / days[c] * 3_650_000; p = poisson_tail(dead[c], all_dead / all_days * days[c])
                tests.append((p, c, "deaths", rate >= rules["deaths_ratio"] * nat, {"dead": dead[c], "drate": round(rate, 1), "dnat": round(nat, 1), "p": round(p, 3), "avg": round(avg)}))
            a = newest.get(c)
            if a and a[2] >= rules["alleg_min"] and nat_a and a[4] >= rules["alleg_ratio"] * nat_a and a[1][:7] >= cutoff:
                pa = poisson_tail(a[2], nat_a / 365000 * a[3] * a[6] * 30.44)      # expected allegations at the overall rate, same people and period
                tests.append((pa, c, "allegations", True, {"alleg": a[2], "arate": a[4], "anat": nat_a, "audit": a[1], "pa": round(pa, 4), "aavg": a[3], "url": a[5]}))
    if hp:
        N = hp["national"]; share = _n365(N) / N["n"] if N["n"] else 0
        for c, p in (hp.get("facilities") or {}).items():
            if c not in F or F[c].get("kind") == "F": continue      # federal prisons hold people serving sentences; their stays are not comparable with ICE sites
            k = _n365(p)
            if k >= rules["long_min"] and share and k / p["n"] >= rules["long_ratio"] * share:
                pl = poisson_tail(k, share * p["n"])
                tests.append((pl, c, "long", True, {"n365": k, "lheld": p["n"], "lpct": round(100 * k / p["n"]), "lnat": round(100 * share, 1), "pl": round(pl, 4), "as_of": hp["as_of"]}))
    for p, c, kind, ratio_ok, info in tests:
        if ratio_ok and p <= bh_cut(tests, rules["max_p"]): why.setdefault(c, {})[kind] = info
    out = []
    for c in sorted(why):
        f = F[c]; W = why[c]; facts = []; d = {"ws": ws, "we": we}
        for x in W.values(): d.update({k: v for k, v in x.items() if k != "url"})
        chance = lambda p: "less than once" if p < 0.01 else f"about {max(1, round(100 * p))} times"
        if "deaths" in W: facts.append(f"{d['dead']} deaths ICE reported here from {_d(ws)} to {_d(we)}: {d['drate']} for every 10,000 people held for a year, against {d['dnat']} across all facilities on ICE's list over the same months. At the overall rate, a count this high would come up by chance {chance(d['p'])} in 100.")
        if "allegations" in W: facts.append(f"ICE's audit of {_d(d['audit'])} counted {d['alleg']} sexual abuse allegations (reports made, not findings that abuse happened): {d['arate']} for every 1,000 people held for a year, against {d['anat']} across audited facilities. At the overall rate, a count this high would come up by chance {chance(d['pa'])} in 100.")
        if "long" in W: facts.append(f"{d['n365']:,} of the {d['lheld']:,} people held here on {_d(d['as_of'])} had been in ICE detention more than a year ({d['lpct']}%), against {d['lnat']}% of everyone held. At the national share, a count this high would come up by chance {chance(d['pl'])} in 100. Long stays often come from cases still in court or on appeal; the records do not say which.")
        denied = [v for v in f.get("visits", []) if v[2] == "denied" and (not ws or v[0][:7] >= ws)]; d["denied"] = len(denied)
        if denied: facts.append(f"Officials were refused entry here {len(denied)} time{'s' if len(denied) != 1 else ''}{f' since {_d(ws)}' if ws else ''}. This is listed beside the figures above as a fact; it does not show that one caused the other.")
        d["avg"], d["avgk"] = (W["deaths"]["avg"], "d") if "deaths" in W else (W["allegations"]["aavg"], "a") if "allegations" in W else (W["long"]["lheld"], "l")
        if d["avgk"] == "d": facts.append(f"About {d['avg']:,} people a day were held here from {_d(ws)} to {_d(we)}." + (" Rates from a handful of deaths move a lot with one event." if d["dead"] < 5 else ""))
        elif d["avgk"] == "a": facts.append(f"About {d['avg']:,} people a day were held here over the audit's period.")
        to = OVERSIGHT["oig"] + OVERSIGHT["crcl"] + ([STATE_AG_INSPECTS[f["state"]]] if f.get("state") in STATE_AG_INSPECTS else [])
        to = to + [(f"@members:{f.get('state', '')}", "https://www.congress.gov/members")]       # the page words this in the reader's language
        src = [("ICE detention death reporting", "https://www.ice.gov/detain/detainee-death-reporting")] if "deaths" in W else []
        if "allegations" in W: src.append(("ICE audit report", W["allegations"]["url"]))
        if "long" in W: src.append(("ICE detention records released to the Deportation Data Project", "https://github.com/deportationdata/ice"))
        out.append({"id": f"facility-{c.lower()}", "kind": "facility", "code": c, "name": f.get("name", c), "state": f.get("state", ""), "d": d,
                    "title": f"{f.get('name', c)}: {' and '.join({'deaths': 'deaths', 'allegations': 'sexual abuse allegations', 'long': 'share held more than a year'}[k] for k in W)} well above other facilities", "facts": facts, "sources": src, "to": to, "why": list(W), "window": [ws, we]})
    return out


def update_log(rows, open_ids, today):
    """rows: [{id, opened, closed}]. An alert keeps the day it first opened; it closes when it is no longer triggered and
    reopens with a new row if it comes back."""
    live = {r["id"]: r for r in rows if not r["closed"]}
    for i in open_ids:
        if i not in live: rows.append({"id": i, "opened": today, "closed": ""}); live[i] = rows[-1]
    for i, r in live.items():
        if i not in open_ids: r["closed"] = today
    return rows


def brief(a, opened, pub):
    """A one-page brief, in plain words, for the publisher to send by hand."""
    L = [f"# {a['title']}", "", f"Open since {_d(opened)}. From {pub}, a public-interest data page; the figures are counts from public records, never about a person.", "", "## What the records show", ""]
    L += [f"- {x}" for x in a["facts"]] + ["", "## Sources", ""] + [f"- {n}: {u}" for n, u in a["sources"]] + ["", "## Who oversees this", ""]
    L += [f"- {('Members of Congress from ' + n[9:] + ', both parties (each member’s own site)') if n.startswith('@members:') else n}: {u}" for n, u in a["to"]] + ["", "Send to every body listed, regardless of party. Check each figure against its source before sending.", ""]
    return "\n".join(L)


def atom(alerts, log, built, pub):
    opened = {r["id"]: r["opened"] for r in log if not r["closed"]}
    E = [f'<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">', f"<title>{escape(pub)}: alerts from the records</title>",
         f"<id>tag:polar-star,2026:watch</id>", f"<updated>{built}T00:00:00Z</updated>", '<link rel="alternate" href="./"/>', f"<author><name>{escape(pub)}</name></author>"]
    for a in alerts:
        E += ["<entry>", f"<title>{escape(a['title'])}</title>", f"<id>tag:polar-star,2026:watch/{a['id']}/{opened.get(a['id'], built)}</id>",
              f"<updated>{opened.get(a['id'], built)}T00:00:00Z</updated>", '<link href="./"/>',
              f"<summary>{escape(' '.join(a['facts']))}</summary>", "</entry>"]
    return "\n".join(E + ["</feed>", ""])


DISPUTE_KIND = {"lawsuit": "Lawsuit", "law": "Law and federal response", "order": "Order, letter or subpoena", "charge": "Criminal charge", "investigation": "Criminal investigation"}


def dispute_entries(disputes, n=30):
    """The newest disputes between ICE and state or local governments, as feed entries. An entry's id carries its
    latest step's date, so a new step shows up in a reader as an update."""
    import hashlib
    E = []
    for d in sorted(disputes, key=lambda d: d[11] or d[0], reverse=True)[:n]:
        k = hashlib.sha1(d[13].encode()).hexdigest()[:10]; when = d[11] or d[0]
        where = d[2] if d[1] == "US" or d[1] in d[2] else f"{d[2]}, {d[1]}"
        summ = d[7] + (f" Latest on record ({d[11]}): {d[9]}" if d[9] else "") + f" Source: {d[13]}"
        E += ["<entry>", f"<title>{escape(DISPUTE_KIND.get(d[3], d[3]))}, {escape(where)} ({d[0]})</title>", f"<id>tag:polar-star,2026:dispute/{k}/{when}</id>",
              f"<updated>{when}T00:00:00Z</updated>", '<link href="./#disp"/>', f"<summary>{escape(summ)}</summary>", "</entry>"]
    return E


def add_disputes(root, disputes):
    """Adds the disputes to site/watch.xml, written by build() before the disputes are read."""
    p = root / "site" / "watch.xml"
    if not (disputes and p.exists()): return
    s = p.read_text(encoding="utf-8")
    p.write_text(s.replace("</feed>", "\n".join(dispute_entries(disputes)) + "\n</feed>", 1), encoding="utf-8")


def build(site, pdm, today, ref, root, pub):
    """Works out every alert, keeps the log, writes the briefs, candidates and feed; returns what the page shows."""
    rp = ref / "watch_rules.json"; rules = {**RULES_DEFAULT, **(json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {})}
    cm = site.get("contracts_meta") or {}; alerts = [a for a in [ice_overdue(cm.get("as_of"), cm.get("checked") or today)] if a]
    hpp = ref / "held_profile.json"; hp = json.loads(hpp.read_text(encoding="utf-8")) if hpp.exists() else None
    los = [r for r in csv.DictReader(open(ref / "ice_length_of_stay.csv", encoding="utf-8"), delimiter="|") if r["population"] == "total" and r["d366_730"]] if (ref / "ice_length_of_stay.csv").exists() else []
    ice_los = (los[-1]["day"], int(los[-1]["d366_730"]) + int(los[-1]["d730p"] or 0)) if los else None
    if rules["long_published"]: alerts += [a for a in [long_national(hp, ice_los)] if a]
    fac = facility_alerts(site, pdm, rules, hp)
    (root / "data" / "watch").mkdir(parents=True, exist_ok=True)
    (root / "data" / "watch" / "candidates.json").write_text(json.dumps({"rules": rules, "built": today, "alerts": fac}, indent=1), encoding="utf-8")
    if rules["facility_published"]: alerts += fac
    lp = ref / "watch_log.csv"
    log = list(csv.DictReader(open(lp, encoding="utf-8"), delimiter="|")) if lp.exists() else []
    log = update_log(log, {a["id"] for a in alerts}, today)
    with open(lp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["id", "opened", "closed"], delimiter="|", lineterminator="\n"); w.writeheader(); w.writerows(log)
    opened = {r["id"]: r["opened"] for r in log if not r["closed"]}
    bd = root / "data" / "watch" / "briefs"; bd.mkdir(parents=True, exist_ok=True)
    for p in bd.glob("*.md"): p.unlink()
    for a in alerts: (bd / f"{a['id']}.md").write_text(brief(a, opened[a["id"]], pub), encoding="utf-8")
    (root / "site" / "watch.xml").write_text(atom(alerts, log, today, pub), encoding="utf-8")
    closed = [r for r in log if r["closed"]]
    return {"alerts": [{**a, "opened": opened[a["id"]]} for a in alerts], "closed": closed[-10:], "candidates": len(fac), "published_facility": rules["facility_published"]}
