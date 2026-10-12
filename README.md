# Polar Star (Estrella Polar)

Navigate immigration detention and find your family. Free. Never Commercial. Not affiliated with any government agency.
Published by the Polar Star Project.

Free. Never commercial. For families, nonprofits, and researchers.
Nothing about a named person is ever stored, accepted, or shown.

## What is here

    pipeline/make_sample.py          invented stint records, for testing only
    pipeline/build_transfers.py      stint records -> transfer patterns -> site/index.html
    pipeline/test_build_transfers.py tests for the transfer and privacy rules
    site/template.html               the phone-first family page (English / Spanish)
    site/index.html                  built page with data embedded (generated)
    data/sample/                     invented data (generated)
    data/raw/                        real downloads go here; never commit them
    data/build_log.json              what the last build kept and dropped

## Run it (PowerShell)

    python -m venv .venv; .\.venv\Scripts\Activate.ps1
    pip install pandas pyarrow openpyxl pytest phonenumbers
    python pipeline\make_sample.py
    python pipeline\build_transfers.py data\sample\stints_sample.csv data\sample\facilities_sample.csv --sample
    cd pipeline; pytest -q; cd ..
    start site\index.html

## Real records

    pip install requests beautifulsoup4 phonenumbers
    powershell -ExecutionPolicy Bypass -File .\run_refresh.ps1
    start site\index.html

run_refresh.ps1 downloads the latest records (about 290 MB, with a dated archive copy),
re-reads ICE's phone numbers, and rebuilds the page. Output goes to data\refresh_log.txt.
To run it every Monday at 06:00:  powershell -ExecutionPolicy Bypass -File .\register_task.ps1

Phone changes are listed in data\reference\contacts_changes.log. A number is never
dropped because a page failed to load, and nothing is written if far fewer pages parse
than last time.

## Flights

    python pipeline\flights.py 2026-10-02
    python pipeline\build_site.py
    start site\index.html

flights.py downloads one day of public aircraft positions from adsb.lol (about 4 GB, resumed if
it drops, deleted afterwards), keeps contractor aircraft whose day touches Alexandria, Harlingen
or Mesa, and writes data\flights\legs_DATE.csv and .json. run_refresh.ps1 catches up the last
7 days. Everything under data\flights is derived from adsb.lol and carries its Open Database
License: credit "adsb.lol contributors" and share under the same terms.

build_site.py joins the two: a facility within 5 km of a staging airport is "next to" it, one
within 45 km gets the nearest staging airport and distance, and the Flights tab can be opened
from a facility page already filtered to that airport. Tapping a facility dot on the globe
opens its page.

Limits: a documented minimum, not a total. El Paso is excluded because military charters use
the same operators next door. A country counts as a destination only when the aircraft was
seen low and close to an airport there. Over southern Mexico and Central America the signal is
usually lost in the air, so most international flights have no confirmed destination. Positions
cannot show who or how many people were on board.

### Backfill to 2024

`powershell -ExecutionPolicy Bypass -File .\run_flights_backfill.ps1` (or `python pipeline\flights.py --since 2024-01-01` directly) reads every day back to that date, newest first, skipping days already done.
Stop and restart freely. About 1,000 days at 2-4 GB each: roughly 3 TB of download in total and several days of running.
Each day's download is deleted once read, so it needs only a few GB of free disk at a time (set `ADSB_WORK` to choose where).
The page shows single flights and paths for the latest 14 days and monthly counts for everything else.
Silent-error risks for older dates: the rule keeps a contractor aircraft's day only if it touches Alexandria, Harlingen or
Mesa, and only for today's contractor callsigns. Contractors and hubs were different in 2024, so older months will
undercount, by an unknown amount. A month with few days read looks quiet; the page shows days read beside each month.

## Other layers on a facility page

| Layer | File in data\reference | Where it comes from | Refreshed by |
| --- | --- | --- | --- |
| Local police agreements, 287(g) | 287g_agencies.csv | appelson/Tracking_287g (MIT), joined on state and county | fetch.py |
| ICE inspection reports | ice_inspections.csv | ICE FOIA library, matched on city, state and name | refresh_contacts.py |
| Deaths per fiscal year, national | ice_deaths_by_year.csv | ICE's death reporting page; no names stored | refresh_contacts.py |
| Legal help sections by state | legal_aid_sections.csv | contents page of the Justice Department pro bono list | by hand |

ice_inspections.csv does not exist until refresh_contacts.py has run once on Windows.
Deaths are shown as national totals only. ICE's death reports are narratives that name several
facilities each, so assigning a death to one facility needs a person to read each report.
outreach\ holds a draft request to Freedom for Immigrants for visiting and phone rules. It has not been sent.

## Oversight, legal help and police agreements (added 2026-10-04)

| File | What | How it is refreshed |
|---|---|---|
| `data/reference/legal_aid_providers.csv` | Free legal providers by state, from the Justice Department list. Pipe-delimited. **Partial hand copy: 128 providers, 29 states.** | By hand from the PDF. The page says it is partial and links the full list. |
| `data/reference/oversight_visits.csv` | Visits by officials, including denied entry. One row per visit, each with a public source link. 2 rows so far. | By hand. Add a row only with a source. |
| `data/reference/legislators-current.csv` | Members of Congress (unitedstates/congress-legislators, public domain). | Re-download when Congress changes. |
| `data/reference/facility_districts.csv` | House district per facility. | `python pipeline\districts.py` on Windows (Census geocoder is not reachable from the cloud). |
| `data/reference/ice_inspections.csv` | Links to ICE inspection reports per facility. | `python pipeline\refresh_contacts.py` on Windows. Untested live. |
| `deaths_recorded` in `site_data.json` | Deaths where "Died" is the release reason. Not subject to the small-number floor. | `build_transfers.py` |

Silent-error risks:
- Census "Current" vintage returns the next Congress's districts. `districts.py` records the congress number and `build_site.py` shows a House member only when it equals 119. After January 2027 change `CONGRESS` in `districts.py`.
- 287(g) join is by county name and state. A city agency is attached to its county only if the sheet's county column is filled; state-wide agencies appear only on the Police agreements tab.
- Death counts undercount ICE's public reports (see `outreach/death-data-request.md`).
- Inspection reports are linked, not rated: the rating pages are scans.
- The 287(g) list shows who signed and which model, not what it costs. No spending data is in it.

Visit log sources (`oversight_visits.csv`): a news report, an official statement or press release, or a post on the
official's own verified account (their .gov-linked or platform-verified account, not a campaign, fan or staff account).
Link the post itself. A post is the official's own account of what happened: record "reason_given" as what they say they
were told, and keep ICE's stated reason only when the source quotes it. Posts get deleted, so save an archive link too.

Automatic collection: `pipeline\visit_statements.py` (run on Windows, in `run_refresh.ps1`) reads each member's press-release
listing on their .house.gov / .senate.gov site (several common layouts are tried) plus senators' feeds, and keeps releases
whose **title** is about a detention site and says entry was refused, or reports a visit.
- Weekly: newest 3 pages per member. Backfill: `--since 2024-01-01` (the agreed start) pages back until that date (many hours; saves as it goes).
- `--recheck` re-applies the current rules to rows already collected, without reading any site.
- Writes `oversight_statements.csv` (with the member's party) and `oversight_coverage.csv`: one row per member with
  whether their page was read, which layout, how many releases and the oldest date. **Read the coverage file by party
  before drawing any comparison**: an unread party looks like a party with no refusals.
- First live run (2026-10-04, 15 pages): 164 of 539 members read, back to April 2025, 9 refusal statements, all from
  Democratic members. The other layouts were added after that run and have not run live.
- Limits that bias history: members who left office are not in the file and their sites are gone, so earlier years are
  under-covered no matter how far back the run pages. A release is one member's account. A facility is attached only when
  one facility's distinctive name appears, a detention word follows it, and the state agrees.
- 2020 to January 2025: see `data/reference/oversight_history_search.md` (no verified refusal found for either party).

Deaths per facility (added 2026-10-04): `data/reference/ice_death_reports.csv`, one row per death on ICE's public list for
fiscal years 2023-2026 (76 rows): date, facility, how the report named it (`stated` = the report says where the person was
held; `listed` = the last detention facility named in the report's first two pages; `unclear`), evidence, and ICE's report link.
No names are stored; the link is ICE's own document.
- Rule: a death belongs to the facility that had custody of the person when they died or were sent out to a hospital
  (the last detention facility in the report's custody history), not to the hospital and not to earlier facilities.
- Evidence `report and record`: the facility named in the report also has a "Died" detention record within 3 days (14 if
  it is the same facility). `record`: report unclear or unreadable, facility taken from the one record on that date.
- The page shows a death on a facility only for `report and record`, `record`, or `report` + `stated`. `report` + `listed`
  rows are held back: one such guess was wrong on checking (2023-04-04, Alamance vs Stewart).
- All 76 reports were read in full (every page) on 2026-10-04, from text pulled through the browser; one report (2025-08-05)
  is a scan with no text and is placed from the detention record alone. Still unplaced: 1 (2026-02-16, held across several hospitals).
- Built by hand. **Not automated**: new deaths need the same reading.
- `ice_death_records_unmatched.csv`: 11 "Died" detention records since October 2022 with no public report matched,
  six at hold rooms. Unexplained; could be coding errors in ICE's data or unreported deaths. Not on the page.

Maps and patterns (added 2026-10-04): the Find a facility tab has a map coloured by kind of facility, and the Visits and
inspections tab has a map plus a "Patterns in the record" section computed from the page's own data.
- **Facility kind is a guess from the name and code** (`facility_kind` in `build_site.py`): ICE's facility-type field is not
  in the DDP files. County-owned sites that ICE uses as dedicated detention (Irwin County, for one) land in "local jail".
  Replace with ICE's own type column if a source turns up.
- 76 facilities have no coordinates and are not on any map. `geoAlbersUsa` drops territories (Guam, CNMI, Puerto Rico).
- Patterns are counts of small, incomplete sets. "No inspection report linked" includes name-match failures (Eloy is one
  to check), so it is a lead, not a finding.

Outreach drafts, none sent: `outreach/`.

## Agency contacts, the agreements map, state bans (added 2026-10-04)

- `pipeline\agency_contacts.py` (run on Windows) downloads the federal Local Law Enforcement Locations list (HIFLD, public domain; a public ArcGIS copy, since the federal site closed in August 2025) and writes `data/reference/287g_agency_contacts.csv`. **Not yet run against the full list.** The matcher was tested against real rows for three states.
- A contact is attached only on an exact name + state match with one open office, county agreeing, phone area code in that state. Otherwise no number. The script prints how many rows fell out for each reason.
- Silent-error risks: the federal list was last checked in 2018-2019, so numbers can be dead or reassigned (the page says so). State agencies are not in it. A sheriff with several branch offices gets no number rather than a guessed one. ICE's sheet misspells counties and one state name; common misspellings are handled, the rest are left off the map and counted.
- `data/reference/county_centroids.csv`: county centre points computed from Census shapes (us-atlas). Order is lat, lon. The map is one dot per county, not per agency.
- `data/reference/state_287g_bans.csv`: states with a law against these agreements, each with a source. By hand.
- Spending: no national source found. USAspending shows no grants or direct payments tagged 287(g) (checked 2026-10-04; 4 contracts only). See `outreach/287g-spending-records-request.md`.

## Rules the pipeline enforces

- Rows the source flags as duplicates are dropped.
- A transfer = two consecutive bookings in the same stay at different facilities.
- Pattern window: the 365 days before the newest book-out in the file.
- A facility with fewer than 30 departures shows no pattern.
- Only the top 5 destinations with 10 or more moves are named. Everything else
  is "other". Only rounded percentages are published, never counts.
- Every release reason maps to one named group (see GROUPS in build_transfers.py).
  "Released in the US" covers only bond, parole, supervision, recognizance and court
  or judge orders. Handovers to other agencies are their own group. A reason not in
  the list is "Other or not recorded", never a release.
- An outcome group with fewer than 10 people at a facility is folded into "other".
  This hides most facility-level deaths; show those from ICE's death reports instead.
- Phone numbers come from ICE's own facility pages (data\reference\ice_facility_contacts.csv,
  retrieved 2026-10-03). A number attaches only on an unambiguous name match whose
  area code is in the facility's state. Doubtful matches get no number and are
  listed in build_log.json.

## Pregnancies and births (added 2026-10-04)

- `data/reference/pregnancy_reports.csv`: national figures the government has given, each with period and source. By hand.
  No facility-level figure exists. DHS's twice-yearly reports to Congress stopped in 2025; births are not reported.
- `women_custody` in `site_data.json` (from `build_transfers.py`): how long women were held, per continuous stay
  (`stay_ID`), national totals in four bands. 280 days = full-term pregnancy. The records have no pregnancy field.
- **Boundary kept:** the page does not attempt to work out when any individual's pregnancy began. That would need a
  person's medical record joined to her custody dates; no public source has both, and it is information about an
  identifiable private person, which this project does not hold or show. The page states the limit and shows only how
  many women were held longer than 280 days.

## Outcome groups (changed 2026-10-04)

There is no "other or not recorded" group any more. Every departure in the past-year window (1.4 million) has a reason in
ICE's records; none is blank. The old "other" was two things, now shown separately:
- **"Processing Disposition Changed Locally"** (2,327 departures): ICE's own release-reason code. It does not say where the
  person went. Shown under ICE's wording as its own group. Its meaning should be asked of ICE or the Deportation Data Project.
- **Small groups combined**: any outcome with fewer than 10 people at a facility is added into one line, and the page now
  names which outcomes were combined (no counts). 373 of 439 facilities have such a line.
Two guard groups exist in code and are empty today: `no_reason` (blank reason) and `unlisted` (a reason not in `GROUPS`).
If either shows up on the page, ICE's data changed and `GROUPS` needs a look.

## Known limits

- The outcome groups are unreviewed by anyone who works with these records.
- refresh_contacts.py, run_refresh.ps1 and register_task.ps1 have not been run on Windows yet.
  ICE's site refused automated requests from two other networks; if it refuses yours,
  the script falls back to a real browser (pip install playwright; playwright install chromium).
- ICE publishes no phone number for the New Orleans or Baltimore field offices.
- build_transfers.py needs: pip install phonenumbers
- Timestamps are UTC; a move near midnight can land on the neighbouring day.
- Records showing a person in two places at once are kept and counted in the log.
- Spanish text is unreviewed.

## Sexual abuse allegations (ICE's PREA audits)

`data/reference/prea_audits.csv` holds one row per audit report ICE published under the Prison Rape
Elimination Act, 2017 to 2026 (229 reports; ICE's list has 234 links, 5 of them duplicates). The counts were read by hand from each report; there
is no collector, so new audits must be added by hand from https://www.ice.gov/prea.

What can silently mislead:

- `basis` matters. `stated` is the total the report gives. `files reviewed` is only the investigation
  files the auditor read, so it is a floor and the page says "at least". Never add the two kinds together.
- The count covers only the audit period (usually the prior 12 months), so facilities are not comparable
  by raw count, and an unaudited facility has no dot. No dot does not mean no abuse.
- These are allegations. `substantiated` is filled only where the report says it plainly.
- The map uses each facility's most recent audit only; older audits show on the facility's own page.
- Facility codes were matched by name by hand (for example "Eloy Federal Contract Facility" to EAZ,
  "Adams County Detention Center" to ADAMSMS, "LaSalle Processing Center" to JENADLA, "Orange County
  Jail" to ORANGNY). A wrong match puts the dot on the wrong facility. 28 audits have no code (hold rooms,
  closed facilities) and are listed on the page but not mapped.
- Three ICE links carry a file name that disagrees with the listed audit date (Berks 2019, Buffalo 2021,
  Laredo 2024); the listed date was used. ICE's "Caroline, Feb. 2020" link serves the Sept. 2019 report,
  so that audit is missing. Three 2017 reports are scans with no readable text.

## Who holds people for ICE, and who ICE pays

Two hand-saved files in `data/reference/`, both pipe-delimited:

- `ice_facility_contracts.csv`: the "Facilities FY26" sheet of ICE's detention statistics file
  (`FY26_detentionStats07202026.xlsx`, from https://www.ice.gov/detain/detention-management): contract type,
  guaranteed minimum beds, last inspection date and rating. 208 facilities.
- `ice_contract_recipients.csv`: the 60 largest recipients of ICE contracts, 1 Oct 2024 to 30 Sep 2026, from the
  USAspending.gov API (`/api/v2/search/spending_by_category/recipient/`, awarding sub-agency "U.S. Immigration
  and Customs Enforcement", award types A to D), read 4 Oct 2026. `detention_guard_musd` is the same query limited
  to NAICS 561612 and 561210.

Neither updates itself. What can silently mislead:

- Units: both money columns are millions of dollars, rounded. They are obligations, not payments.
- The NAICS label is the contract's filing code, not a description of the work. CSI Aviation (charter flights) is
  the largest recipient and carries no label because its contracts are filed under other codes.
- ICE's list covers only facilities in use on the file date, and does not name the operator. "DIGSA" and "IGSA"
  are agreements with a government body even where a company runs the site.
- Facility matching is by state plus name and city (`match_contracts`); 19 rows carry a hand-set `facility_code`.
  One row (Lafayette Parish Correctional Center) is left unmatched on purpose.
- The organisation filter on the 287(g) list sorts by words in the agency name (`orgType` in the template), so an
  oddly named agency lands in "Other".

### Follow the money

`data/reference/ice_money_flow.csv` (pipe-delimited, millions of dollars) feeds the "Follow the money" section:
ICE contract obligations 1 Oct 2024 to 30 Sep 2026 grouped by federal product/service code (PSC), with the largest
recipients per group, from the same USAspending.gov API (`spending_by_category/psc` and `/recipient` with a
`psc_codes` filter), read 4 Oct 2026. The overall total (12,922) is set in `build_site.py`.

- The build refuses to run if the groups do not add to the total. "OTHER" is the remainder, not a query result.
- Recipients can add to slightly more than their group: cancelled awards are negative in the group total.
- A group is a filing code, not a description of the work. S206 "guard services" is used for running detention sites.
- `funding_subagency` returned ICE for all but $2 million, so nothing here shows another agency paying.

Four more hand-saved files (pipe-delimited, millions of dollars) complete "Follow the money", all read from
USAspending.gov on 4 Oct 2026:

- `ice_budget_totals.csv`, `ice_budget_accounts.csv`: ICE's budget by fiscal year and by account
  (`/api/v2/agency/070/sub_components/`). "Available" carries unspent money forward, so years must not be added.
- `ice_recipient_parents.csv`: each contractor's parent from the recipient profile (`/api/v2/recipient/<id>/`).
  That profile lists every parent ever recorded, including former ones (Amentum still shows AECOM); the file keeps
  the one I judged current. Check it before quoting. The `kind` column marks Alaska Native corporation ownership.
- `ice_subawards.csv`: the largest reported subcontracts (`spending_by_award` with `spending_level: subawards`).
  Reporting is sparse; absence is not evidence.

The $75 billion / $45 billion sentence about the July 2025 law is from news coverage, not from these files.

"Follow the money" is its own tab (`v-money`). Its headline tiles and the "beds ICE pays for" section are computed
in the page from data already loaded (`DATA.money`, `DATA.vendors`, `DATA.contracts`); nothing new is stored.
"Guaranteed minimum" is read as beds paid for whether or not filled; ICE's file gives no price per bed.

## Political committee money (`data/reference/fec_pac_recipients.csv`)

Contributions from the political committees of GEO Group (C00382150), CoreCivic (C00366468) and Management & Training Corporation (C00208322) to other committees, 2024 and 2026 election cycles. Source: FEC API `schedules/schedule_b/by_recipient_id/`, read 4 Oct 2026. Pipe-delimited. `build_site.py` refuses to build unless rows add to 1,539,950.

Silent-error risks:
- Rows are recipient **committees**, not people. Do not roll a party committee or joint fundraiser up to an official.
- `party` is the FEC committee record; only REP and DEM are used, other codes are shown as "other or no party on record". `state` is a mailing address and is not shown.
- The 2026 cycle is still open: the figure grows, and the hard-coded total must be updated with any re-read.
- Excludes executives' and employees' personal donations, trade groups and lobbying. Amentum and NANA have committees but are left out as broad contractors.
- Negative rows are refunds.

## Members, votes, lobbying and SEC filings (read 4 Oct 2026)

- `fec_committee_candidates.csv`: recipient committee -> FEC candidate id(s). `C` = the candidate's own campaign committee, `L` = leadership fund or joint committee the FEC ties to that candidate. NRSC is deliberately absent (FEC lists a senator against it; it is a party committee).
- `pac_members_votes.csv`: made by `python pipeline/pac_votes.py` (needs network). Joins the above to congress-legislators and to the vote on H.R. 1 (House roll 190, Senate vote 372).
- `lobbying_by_year.csv`, `lobbying_firms.csv`, `lobbying_targets.csv`: lda.gov API, quarterly reports 2023 to Q2 2026, latest amendment per registrant and quarter.
- `sec_company_facts.csv`, `sec_shareholders.csv`: GEO and CoreCivic 10-K (FY2025) and March 2026 proxy statements.

Silent-error risks:
- Votes are rebuilt from party on the day plus five named exceptions, not downloaded per member. The script refuses to write unless it reproduces 218-214 and 50-50. The legislators file stores TODAY's party; `party_affiliations` is used for the day (Kiley switched in 2026).
- A committee linked to two different members, or to nobody in the legislators file, stays unlinked. Two FEC rows look mis-filed by the giver (a 2012 Virginia committee, a retired Kansas member's committee) and are left as recorded.
- Lobbying: own-report and outside-firm columns can overlap. Never present their sum as the figure. One registrant files under a personal name and is shown without the name.
- 2026 lobbying is half a year. SEC ICE dollars are percent x revenue, rounded.
- `oversight_coverage.csv`: 415 of 539 members' press pages were readable (77%), and senators are worse (63 of 99). A member with no statement may simply be unread.

## Flights: all contractor legs are now saved (4 Oct 2026)

`flights.py` writes `data/flights/all_DAY.json.gz` (every contractor leg, before the ICE rule) beside `legs_DAY.*` (kept legs). Backfill and catch-up treat a day as done only when the `all_` file exists, so days read before this change are downloaded once more. After that the keep rule can change without any download.

Silent-error risks:
- `all_` files are not ICE flights. They include Avelo scheduled services, Omni military charters and ordinary charters. Never publish them or count them as ICE.
- The page's date range lists kept legs only. Lines for a range join airport pairs (top 400 pairs); real tracks exist only for the last 14 days.

## 287(g) agreements no longer listed (`data/reference/287g_no_longer_listed.csv`)

Made by `python pipeline/agreements_history.py PATH_TO_CLONE` from the dated sheets in appelson/Tracking_287g (19 May 2025 on). 195 rows on 4 Oct 2026.

Silent-error risks:
- ICE retypes agency names and misspells states. A plain comparison gave 325 "endings"; fuzzy matching on state, model, agency type, key words and signing date leaves 195. A few renames may remain, and an over-eager match could hide a real ending.
- No end date or reason exists. `last_listed` is the last sheet a row appeared in; 22 of 211 daily sheets were unreadable.
- Nothing before 19 May 2025 is covered.

## Review of 4 Oct 2026: what was added

- `pipeline/custody_trend.py` -> `custody_by_month.csv` (people held, book-ins, deported, released, by month). Counts stays, complete months only, from October 2023. Refuses to write an implausible result. Rerun whenever the detention records are refreshed.
- `data/reference/sources.csv`: one row per data source with its date, shown in the page footer. **Update the date by hand whenever a source is re-read**; nothing checks it.
- Still not run: `pipeline/districts.py` (House member per facility). It needs the Census geocoder, reachable from the PC but not from the cloud sandbox.

`ice_subawards.csv` now holds every reported subcontract on ICE contracts (94 prime-to-sub lines, 116 records, $400,825,351; read 4 Oct 2026), not just the largest. The build refuses unless the rows add to 400.825M, so update that number on any re-read. Descriptions were shortened by hand from the contractors' own wording.

`ice_ownership.csv`: who is at the top of the chain for the 28 largest traced contractors, researched by web search on 4 Oct 2026 (one source URL per row, `sure` = high/medium/low). Organisations only: where owners are individuals the row says "private" and names nobody. Silent-error risks: ownership changes with sales (Steampunk's sale was announced, not confirmed closed); most "private" rows rest on the absence of a reported parent, not a filing; notes are English only.

## Keeping it current without hand work (4 Oct 2026)

`run_refresh.ps1` (weekly, once `register_task.ps1` has been run) now also rebuilds the custody trend, runs every test before touching the page (`pipeline/run_tests.py`), keeps `site/index.previous.html`, and restores it if the build fails.

`build_site.py` writes:
- `data/health.json`: build date and any source older than its `max_age_days` in `data/reference/sources.csv`. The same warning shows in the page footer.
- `site/layers/*.geojson`: facilities, 287(g) counties, airports used, flight routes (all days, one line per airport pair) and recent flight tracks, for loading into a globe.

Sources with a `key` in `sources.csv` take their date from the data on each build. The rest are **one-off reads** (USAspending, FEC, lobbying, SEC, contract file, death reports, sexual abuse audits, ownership research): nothing refreshes them yet, and their `read` date must be edited by hand after a re-read. They will be flagged as stale once past `max_age_days`.

## Running on GitHub (prepared 4 Oct 2026, not yet live)

- `pipeline/refresh_all.py` is the single refresh, used by `run_refresh.ps1` on a PC and by `.github/workflows/refresh.yml` on GitHub (Mondays 11:17 UTC, or by hand from the Actions tab). Required steps stop the run and leave the published page alone; optional steps may fail and are recorded in `data/refresh_status.json`.
- The workflow commits refreshed data back to the repository and publishes `site/` to GitHub Pages.
- `.gitignore` keeps the large downloads (`data/raw/`) and the unsent `outreach/` drafts out of the repository.
- Not yet proven on GitHub: whether ice.gov answers a cloud server (the `ice_site` step), and how long eight days of flight downloads take.

`287g_agency_contacts_manual.csv`: main phone numbers for the 287(g) signers that are not police, sheriffs or jails, looked up by hand on each office's own site on 5 Oct 2026 (58 of 66; source URL per row). These rows win over the automatic match. Eight are blank on purpose: no number on an official page. Nothing refreshes this file.

## Refusals, watchdog reports, court case (researched 5 Oct 2026)

- `oversight_visits.csv`: now 48 refused visits (members of Congress, state and local officials) with a `who` column. Each row has one public source. Dates marked "date approximate" in the reason were inferred from a weekday in a news report.
- `watchdog_reports.csv` (pipe-delimited): 48 reports by the DHS Inspector General, the detention ombudsman, the California Attorney General and GAO. `sure=medium` rows were seen only as a listing, not opened; their finding is left blank on purpose. The build refuses unknown facility codes.
- `access_court_events.csv`: timeline of Neguse v. ICE, English and Spanish.

Silent-error risks: all three were compiled by web research, not from a feed, so nothing refreshes them; the court docket itself could not be opened (filings were read from the plaintiffs' lawyers' copies); CRCL memos are missing; a refusal nobody published is not here.

`facility_operators.csv` (pipe-delimited): the company that runs each privately run site on ICE's list (69 sites, researched 5 Oct 2026; GEO and CoreCivic from their FY2025 annual reports, MTC from its own site, LaSalle, Akima, Paragon and Amentum from news reports = `sure=medium`). The build refuses unknown or repeated facility codes. Silent-error risks: operators change (four sites were sold to DHS in 2026 with the operator staying); Florence SPC is left out because the only source was weak; the Trends cross-tab counts events per operator but has no population per site, so it must never be read as a rate.

## Rates: allegations and deaths against days of detention (`pipeline/person_days.py`)

`person_days.py` writes `data/reference/facility_person_days.csv` (facility, month, days of detention served) from the
detention records; it runs as the `days` step of the weekly refresh. `conduct_rates()` in `build_site.py` uses it for the
"Sexual abuse allegations and deaths, by who runs the site" section of the trends tab.

What can go wrong without an error:
- **Audit period.** Each audit's count is set against the period its own report states (`period_start`, `period_end`,
  `period_basis` in `prea_audits.csv`), read from the reports on 5 October 2026. Periods run from one to three years.
  An audit with no stated period, or whose period begins before the day counts, is left out of rates. **A new audit
  added without its period is silently left out of rates** — fill the three columns when adding a row.
  One report (Karnes, January 2026) gives an end date after the audit itself; the audit's last day is used.
- **Small numbers.** A rate is shown with the number of audits or deaths behind it; one event moves a small operator's rate a lot.
- **Day counts start October 2022.** Audits whose period begins earlier are left out of rates.
- **Only sites on ICE's contract list** are grouped by operator; an unlisted site's audits and deaths are not in the rates.
- **Operator is today's operator.** A site that changed hands has all its history counted under the current one.
- Floors ("files reviewed") and audits at sites averaging under 50 people held are left out of rates.

## Population history, solitary confinement and inspection deficiencies (collected weekly)

`pipeline/detention_stats.py` (step `stats`) reads ICE's detention statistics workbooks, FY19 to now, from
https://www.ice.gov/detain/detention-management. It writes `facility_adp_by_year.csv` (average people held a day, per
facility per fiscal year), `facility_segregation.csv` (placements into segregation per facility per month, April 2024 on)
and rewrites `ice_facility_contracts.csv` from the newest year. A workbook is re-read only when its link changes.

`pipeline/inspection_findings.py` (step `findings`) reads each inspection report in `ice_inspections.csv` once and writes
`ice_inspection_findings.csv`. Most reports are scanned images, so pages are read by OCR (tesseract).

`facility_name_aliases.csv` (by hand) maps ICE's other spellings of a facility name to the code used here.

What can go wrong without an error:
- **A new spelling of a facility name.** ICE renames and misspells sites between workbooks. A name the matcher cannot place
  is left out of the rates. The build line prints how many people-a-day and placements were unmatched: if that number
  jumps, add the new spelling to `facility_name_aliases.csv`. The segregation sheet gives no state, so a name there is
  matched only when exactly one facility in the country fits.
- **Segregation months with no row.** A facility missing from a month is treated as zero placements that month. If ICE
  ever drops a facility from the sheet for another reason, its rate is understated. September 2025 was never published.
- **Yearly averages are coarse.** Audit periods that start before October 2022 use ICE's fiscal-year average for each month,
  so a site that filled or emptied mid-year is mis-weighted. Those rows are labelled on the page.
- **Inspection totals come from one sentence.** The count used is the report's own summary ("ODO found N deficiencies in
  M standards"), first occurrence only, because later sentences describe earlier inspections. If OCR misreads that
  sentence the count falls back to the citations it could read, which is usually too low. A report with nothing readable
  is "unreadable", never zero. The per-standard breakdown rests on citations only and undercounts.
- **The civil rights office memos** (`watchdog_reports.csv`, body CRCL) are hand research and do not refresh. DHS removed
  most of them from its site in 2025; POGO keeps a fuller mirror.

## Who is held, and for how long (`pipeline/held_profile.py`, step `held`)

Writes `data/reference/held_profile.json` from the detention records: people held on the newest day in the records,
nationally and per facility (30 or more held): share of women, age bands, five largest countries of citizenship, share
held more than 180 and 365 days so far, median days so far.

What can go wrong without an error:
- **"Held now" is as of the records' last day**, weeks or months before today. The page states the date.
- **Time is counted across the whole stay.** A person moved to a site last week after a year elsewhere counts as held over
  a year at that site. That is deliberate (it is how long the person has been detained) but is not time at that site.
- **A stay with no book-out is treated as still held.** A missing book-out in ICE's data would count as a long detention.
- **Small groups are hidden**, not zero: any share resting on fewer than 10 people is left out. Operator totals are
  rebuilt from rounded shares and treat a hidden share as zero, so they are approximate and slightly low.

## Collectors added 5 October 2026 (all run in the weekly refresh)

- `pipeline/money_usaspending.py` (step `spending`): contract recipients, spending by product/service group, ICE's budget and
  every reported subcontract, for the two most recently completed fiscal years. It writes `money_meta.json` with the
  source's own totals, and `build_site.py` checks the files against those instead of fixed numbers. The window rolls
  forward each October; nothing is written unless every request succeeds. `ice_recipient_parents.csv` stays hand-kept:
  a new large contractor appears without a parent until someone adds one.
- `pipeline/prea_audits.py` (step `audits`): finds newly published sexual-abuse audits and adds them as "unread" with
  their review period and the sentences that mention allegation counts. It never fills in the count: tested on 36
  audits read by hand, automatic reading was wrong about 1 time in 15. **An unread audit is on the page with its link
  but is in no total and no rate until a person fills in `allegations` and `basis`.**
- Still read once by hand, with no collector: FEC political committees (needs an API key), lobbying reports, SEC filings,
  ownership chains, facility operators, refusals of officials, court events, watchdog and civil rights reports,
  death reports, pregnancy figures, the manually found police phone numbers.

## Court results, memos, flights by aircraft, deaths timing (added 5 October 2026)

- `pipeline/court_outcomes.py` (step `court`): bond decisions and case results for detained people by hearing location, last 24
  months, from the Deportation Data Project's public-domain cleaned copy of the immigration courts' case data
  (https://github.com/deportationdata/eoir). It lags the courts' own monthly file by days to weeks; the download is skipped
  when unchanged. Writes `court_by_location.csv` and `court_meta.json`. `court_location_facility.csv` (by hand, 66 rows) ties a
  hearing location to a facility; other locations are tied only if exactly one facility fits the name.
  Silent-error risks: results are counted where the hearing was held, usually but not always where the person was held;
  each person is counted once, by the LAST bond decision and the case's final result, so an earlier denial before a grant
  does not show; "had a lawyer" means on record at any point, not at the bond hearing; courts serving many jails
  ("Chicago Detained") are national-only; a renamed or new hearing location is untied until added to the crosswalk
  (the build line prints how many decisions are tied).
- `pipeline/crcl_memos.py` (step `memos`): Homeland Security civil rights office memos from POGO's DocumentCloud mirror
  (organisation 334), dated from POGO's file names. `build_site.py` places a memo at the facility whose distinctive name
  words all appear in the title; a tie is left unplaced. A wrong placement is possible for facilities with one-word
  distinctive names. Hand-kept CRCL rows in `watchdog_reports.csv` win over a collected memo with the same date and facility.
- Flights: `fleet_extra()` in `pipeline/flights.py` adds legs by an aircraft that flew an ICE pattern on at least two days
  within a week and on at least half the days it flew. It needs the `all_DAY.json.gz` files, which exist only from
  26 September 2026, so older days still rest on the three staging airports alone.
- Deaths: `held_profile.py` also writes how long people had been held when ICE's records end a stay with "Died". Fewer than
  ICE's listed deaths (a death after hospital release is often recorded as a release). Cause of death is not collected:
  ICE's reports do not state it consistently.
- The audit collector runs weekly. Reading the counts of new audits and re-checking hand-kept files is a monthly scheduled task.
- Members' press pages: the collector tries more addresses, the site's own press link, and a real browser when refused.
  `oversight_coverage.csv` has a `why` column for pages still unreadable.

## Money collectors for lobbying, political committees and SEC filings (added 5 October 2026)

- `pipeline/money_lobbying.py` (step `lobbying`): lda.gov filings for GEO Group, CoreCivic, MTC and CSI Aviation, 2023 on. Tested
  against the hand-read 2025 figures for GEO and CoreCivic, which it reproduces exactly. A client is matched by a name
  pattern (`COMPANIES`); a firm hired through a differently named intermediary would be missed. A registrant with no
  company word in its name is treated as a person and shown without the name.
- `pipeline/money_fec.py` (step `fec`): needs the repository secret `FEC_API_KEY`; without it the step does nothing and the file
  stays as last read. It writes `fec_meta.json` with the cycles and the FEC's own total, which the build checks.
  The cycles roll forward every two years; the page's wording about cycles is still fixed text. New recipient committees
  are not linked to a member of Congress until `fec_committee_candidates.csv` is updated by hand (monthly task).
- `pipeline/sec_watch.py` (step `sec`): does not read figures. It checks the SEC index for a 10-K or proxy statement newer than
  the ones on file and records it in `sec_meta.json`; the source then shows as out of date until a person re-reads it.

## Operator history (`data/reference/facility_operator_history.csv`, by hand, added 5 October 2026)

`facility_operators.csv` says who runs a site today. This file holds the earlier operators: `facility_code|operator|from|to|url|sure`,
one row per earlier period, `to` being the last day that company ran the site (`from` blank means "since before the records here begin").
`operator_on(site)` in `build_site.py` answers "who ran this site on this date", and every dated record is counted under that company:
deaths (date of death), ICE inspections (first day), days of detention and solitary placements (by month, judged on the 15th),
audits (only if one company ran the site for the audit's whole stated period), watchdog reports and refused visits (their date).

Three changes are recorded: Port Isabel (Ahtna until 31 Jan 2023, then Akima), Farmville (Immigration Centers of America until
30 Jun 2025, then CoreCivic), Camp East Montana (Acquisition Logistics 1 Aug 2025 to 12 Mar 2026, then Amentum).

What can be silently wrong:
- **A site with no row is assumed to have had today's operator on every date.** For about 30 long-running CoreCivic, GEO, LaSalle and
  MTC sites no source was found that confirms continuity since October 2022. A missed change puts the old operator's records on the new one.
- The earliest period in the file is stretched back to cover any older record at that site.
- El Paso Service Processing Center is kept as one operator (Paragon). Its contract moved from Global Precision Systems, a sister
  company under the same parent, at a date sources disagree on (between Sep 2022 and Sep 2023; a June 2024 Senate letter still names the old one).
- A watchdog report is placed by publication date, which can fall after the period it describes.
- Court results are one total per place for the whole period, so sites that changed operator inside it go to no operator (`CHG`).
- At Camp East Montana, Amentum is reported to have worked as a subcontractor before it became the main contractor; records
  before 13 Mar 2026 are under Acquisition Logistics, the contract holder.
- Contract dates in the research came partly from a mirror of USAspending; the three dates used here rest on a DHS ombudsman
  report, a company filing and local news, not on the mirror.

## Page weight: the flights file (5 October 2026)

`build_site.py` writes two files: `site/index.html` and `site/flights-data.js`. The second holds every flight row, the day's legs and
the world map (about 1.2 MB), and the page fetches it the first time the flights tab opens. Nothing was removed from the page.
Both files carry one stamp (`FLIGHTS.more`); the page refuses a flight file with a different stamp and shows "did not load" with a
retry, so a stale cached copy can never be mixed with new totals. **Both files must be published together**; `index.html` alone
works except for the flights tab. First load fell from 2.71 MB to 1.57 MB (661 KB to 405 KB compressed).

## Guaranteed beds against people held (`bed_use()` in `build_site.py`, added 6 October 2026)

For each site with a guaranteed minimum on ICE's facility list, compares the guarantee with ICE's own average daily population for
the newest fiscal year (`facility_adp_by_year.csv`). Shown under "Guaranteed beds" in Follow the money. Silent-error risks: the
yearly average covers the whole year to date, so a site that opened or whose guarantee began mid-year looks emptier than it is now
(Diamondback: 606 average against 1,200 guaranteed, but 1,789 held on 6 Aug 2026); a site whose name is not matched to the population
file is left out, not counted as empty; a surplus at one site never offsets a shortfall at another. No dollar figure is computed:
per-bed prices are not in any file here.

## For families tab, self-hosted files, links (6 October 2026)

- **For families** (`#v-fam`, first tab, the page a visitor lands on): locator, last-known-facility search with a call card, the
  court's automated line, free help. The three national numbers (ORR call center 1-800-203-7001, EOIR automated line
  1-800-898-7180, hotline code 9233#) are written in `template.html` by hand and were confirmed on the agencies' pages on
  6 Oct 2026. **Nothing refreshes them**: re-check when re-reading the hand-kept files.
- **Nothing is fetched from another site.** Fonts (`site/vendor/fonts`, SIL Open Font License) and d3/topojson
  (`site/vendor/*.min.js`) are served with the page; a test fails if the template loads anything over http(s).
  **Publishing must include `vendor/` and `flights-data.js`** beside `index.html`, or maps, the flights tab and the fonts are lost
  (the page still works with system fonts and without maps).
- **Address**: `#tab` or `#find/CODE` (for example `#find/PIC`), so Back works and a facility can be shared. Language is kept in
  the visitor's own browser storage; nothing else is.
- **Search** (`findFacilities`): every typed word must match the name, city, state, county or address; short forms and Spanish
  words are mapped (`ALIAS`), and words of four letters or more may be off by one letter (two from eight letters). Exact matches
  are listed before loose ones. A loose match can surface a wrong facility with a similar name: the list always shows city and state.
- On touch screens the globe is turned with the arrow buttons; a swipe over it scrolls the page.

## Money build-out (6 October 2026): by year, how awarded, lobbying detail, contribution timeline

All from collectors that already ran weekly; each new part is left off the page, never shown wrong, if its file does not add up.
- `ice_spending_by_year.csv` (step `spending`): each spending group and each of the 60 largest recipients per fiscal year. Group
  years come from the same product-code search as the totals. **Recipient years come from a search by company name**, which can
  sweep in a similarly named company; a row is kept only if its years add to that recipient's own total within 2% (`checked`).
  "Paid nothing in the first year" means under $0.5 million in that search, among the 60 largest only; a renamed or acquired
  company looks new.
- `ice_competition.csv`, `ice_not_competed_top.csv`: dollars by the "extent competed" code. Competed = A, D, F, CDO; not competed =
  B, C, E, G, NDO (E, a follow-on to a competed contract, is counted as not competed). The remainder is "not recorded".
- `lobbying_by_quarter.csv`, `lobbying_issues.csv` (step `lobbying`): quarters must add to the yearly file or nothing is written;
  issue areas are the form's fixed list, counted per filing; the free-text description is never stored.
- `fec_by_quarter.csv` (step `fec`): from each committee's periodic reports (the form's line for contributions to federal
  candidates and committees), newest version per period, by the quarter the period ends in. Written only if it is within 10% of
  the by-recipient total. It starts in 2023 because the two election cycles do, and will not match the recipient list exactly.
- Trends, "Each operator": people held, empty guaranteed beds and deficiencies per inspection sit beside the existing counts.
  Empty beds use today's operator; the rest follow the dated operator history.

## Company-stated yearly revenue per site (`data/reference/facility_bed_revenue.csv`, by hand, added 6 October 2026)

No ICE contract's daily bed price is public. For sites where the operating company has told investors what it expects a site
to bring in each year, this file holds that figure, the company's own bed count, how it says it is paid (`fixed`, `mixed`, or
blank when not stated) and a link to the filing or announcement. The build divides the yearly figure by those beds and 365 and
the page shows the result labeled "Calculated by this page", next to the "Company-stated" line. Read with care:

- The yearly figure is an expectation for a normal year, not what ICE has paid and not a guaranteed payment.
- The bed count is the company's and often differs from ICE's guaranteed minimum (Dilley 2,400 against 2,000).
- No dollar total for empty beds is computed anywhere, on purpose: it would mix these two bases.
- `sold` marks a site the company has since reported selling; its yearly figure may no longer apply.

## Award-level contracts (`pipeline/money_awards.py`, step `awards`, added 7 October 2026)

`data/reference/ice_awards.csv` holds every ICE contract of $1 million or more with activity in the three-year window, one row
per award (1,162 awards to 430 recipients on the first pull). The page shows them as "Its contracts of $1 million or more" under
each company in Follow the money section 5 and in the panel under the money wheel, each linked to its USAspending record.

Unit and meaning trap: `amount_usd` is WHOLE DOLLARS over the WHOLE LIFE of the award. Every other money file is in MILLIONS
and covers the window only. The build converts to millions for display and the page never adds awards to a window total.

## Page behavior added 7 October 2026

- Dates the data carries as `2025-09-18` or `2025-09` are shown as words in the page's language by one display-only pass
  (`dateify`); the data and sorting still use the ISO form.
- Charts mark an unfinished or not-fully-reported last period with a lighter, dashed bar or line segment.
- `facility_bed_revenue.csv` gained `annual_max_musd` for a range the company stated; a row cannot be both a range and "at least".
- For Families gained step 5 (paying a bond, from ICE's "Post a Bond" page, read 7 October 2026) and step 6 (where visiting
  rules are). The bond facts are hand-entered text: re-read ICE's page when it changes.

## Added late on 7 October 2026

- `site/more-data.js`: the long 287(g) lists and the contract records, fetched when the agreements, money or trends tab first
  opens. It carries the same stamp as the page (`DATA.lazy`); a page beside a file from another build refuses it. The workflow
  copies it to `_site`, and any manual publish must include it or those tabs show a "could not be loaded" note.
- `ice_awards.csv` gained `window_usd` (WHOLE DOLLARS inside the window, can be negative, blank = not read), `competed`
  (C/N/blank), `psc`, and place of performance. The collector opens every award twice more (about 25 minutes) and checks the
  window amounts against ICE's window total before writing.
- Guard-service contracts (code S206) are placed on a facility page only when it is the one listed facility in that city
  (74 of 185 on the first run). It is a match by place, and the page says so.
- `data/headline_history.json`: the headline counts at each build, one entry per day they change. The About tab lists what
  moved since the entry before. The 5 October entry has no contract total on purpose: the window was two years then, so
  the jump to three years is a change of measure, not of money.
- Accessibility: axe-core reports no violations on any tab in light or dark at phone width; chart colors pass the colorblind
  check in both themes. Charts and the money wheel are pointer-driven; the number tables and the finder are the keyboard route.

## Contracts awarded without competition (added 7 October 2026)

`ice_awards.csv` gained `extent` (the source's own competition code), `offers` (offers received; blank = not recorded, never
zero) and `reason` (the stated reason an award was not fully competed, in the source's words). Follow the money has a section
listing every not-competed contract of $1 million or more by reason, every "competed" contract that drew one offer, and two
plain filters (not competed and $50 million or more; not competed to a company with no ICE dollars in the first fiscal year).
These are filters on the record. The page states that none is a finding of wrongdoing, and that wording should stay.

## Other agencies, states and countries (added 8 October 2026)

A tab of its own: everyone outside ICE who holds, moves, judges, pays for or shares records about people facing removal.
Every line carries its source and the kind of source: official record (agency, GAO, CRS, court, state attorney general),
one party's members of Congress, research group, or news report. Organizations and public officials only.

Collected weekly by `pipeline/other_agencies.py` (step `others`), each part written only when it reads cleanly:
- `cbp_encounters_by_month.csv` from CBP's own monthly encounters file (the newest one linked from its document page). Encounters are events, not people.
- `cbp_custody_by_month.csv` from CBP's custody and transfer tables (southwest border; CBP shows only the current fiscal year, so earlier months are kept).
- `ohss_repatriations.csv` from DHS Yearbook table 39 (newest yearbook that has it). Ends where DHS ends; nothing is estimated.
- `orr_by_month.csv`, `orr_days_by_fy.csv` from HHS's children's operational and release workbooks.
- `other_money.csv` + `other_money_meta.json` from USAspending: CBP holding (W054, M1AZ, M1JZ), CBP medical (Q-codes), CBP guards, transport, food and care; HHS grants 93.676 and contracts mentioning unaccompanied children; FEMA 97.158 (detention) and 97.141/97.149 (shelter after release); two Army detention awards read one by one. Negative amounts are money taken back.
  Private people are never written: a payee the source marks as an individual, a sole proprietorship whose name has no business word, a practice named after a person (Dr., M.D., D.D.S., Ph.D., Esq.), and REDACTED/MULTIPLE RECIPIENTS are folded into "Everyone else" and only counted.
- `cbp_notices_seen.csv`: CBP death notices on its accountability page, for review. Nothing reaches the page until added by hand to `cbp_death_notices.csv`.

`went_dark.csv` has a `tab` column: oversight that was cut goes on the inspections tab, data that stopped goes on the trends tab (with a tile counting days since ICE's last required detention file, measured from the day this page last checked ICE's site).
By hand, each row checked against the document itself (the `probe` step saved the pages, since this sandbox cannot reach .gov):
`cbp_deaths_by_year.csv`, `cbp_death_notices.csv`, `gov_facts.csv`, `state_sites.csv`, `third_country_payments.csv`, `data_sharing.csv`, `went_dark.csv`.
The build refuses an unknown kind of source, a non-https link, an unknown facility code, money that does not add up to the source's total, and any line with no Spanish in `es_text.csv`.

Monthly by hand: add new CBP notices from `cbp_notices_seen.csv`; look for a CBP deaths report after FY2023, an OHSS FY2024 enforcement yearbook, an ICE FY2025 annual report, and new GAO reports on detention.

`pipeline/probe_sources.py` (step `probe`) runs only when named. It saves what source pages return into `data/probe/`, which is for writing parsers and checking figures, not for the page. Remove `data/probe/` from the repository and its history before going live.

## Money across every payer (added 8 October 2026)

Follow the money now starts from the budget laws (`budget_laws.csv`, read from the text of P.L. 119-21 and P.L. 119-98), then shows what every agency committed (ICE, ICE money in DHS headquarters contracts, CBP, HHS, FEMA, the State Border Security Reinforcement Fund, the Army, U.S. Marshals detention contracts, and the Senate minority figures for payments to other countries), then the companies paid by more than one agency (`shared_payees()` in `build_site.py`: names matched after removing legal-form words, units joined to their parent from `ice_recipient_parents.csv`), and what federal spending data leaves out (`money_gaps.csv`; numbers in braces are filled at build time).
`other_agencies.py` also writes `ice_payees_all.csv` and `other_money_payees.csv` (every payee of $1 million or more) for that matching.
Known: payments to counties for jail beds, ICE repayments to the Bureau of Prisons, the Justice Department reimbursement fund and any 287(g) payments are not in USAspending (checked October 8, 2026).

## Trends across agencies, and how current each source is (8 October 2026)

Trends has a card, **Across the system**, that sets the other agencies next to ICE. It shows:

- CBP encounters, Border Patrol hand-offs to federal custody, and ICE book-ins, deportations and releases on one monthly timeline.
- Children in HHS care.
- DHS removals, returns and expulsions by fiscal year.
- Deaths in custody by fiscal year for ICE and for CBP.

These are counts from different agencies. Do not add them up or read one line as a share of another. A month with no data is drawn blank, not zero.

The card **What is tracked, and how current** lists every row of `sources.csv`. Each row shows the newest date it covers, or, for sources checked by hand, the day it was checked. Rows past `max_age_days` are listed first and marked overdue. Monthly series (CBP encounters, CBP custody, HHS) are dated by the last month they cover, from `other_sources_meta.json`. The OHSS yearbook is dated by its last fiscal year. ICE's detention statistics file is now dated by the file's own date, not the day it was read. So a source that stops publishing shows as overdue rather than "checked today". This is a silent-error guard: before this change, the detention file read as current while it was 80 days old.

## Clarity pass and new data (8 October 2026)

**Display.**
- Company and committee names are shown in normal case (`cn()` in the page). The data keeps the records' capitals, so lookups still match.
- Years are written out in full, and English dates use US order.
- The ICE trail now says that $16.6B = $16.1B in ICE's own contracts + $0.46B through DHS headquarters.
- The tiles now say "largest single company" (CSI Aviation) and "most to any one owner" (GEO).
- Trends tiles that have a history show the change from a year earlier and a small line chart.

**New collectors.** All of these write counts only.

| Step | Script | Source | Writes |
|---|---|---|---|
| `arrests` | `arrests_trend.py` | Deportation Data Project ICE arrest records, read only in Actions | arrests by month, method and state |
| `stats` (extended) | `detention_stats.py` | ICE detention statistics workbooks | alternatives to detention (count and daily tech cost), people held by arresting agency, removals so far this year, book-ins by arresting agency per month |
| `staff` | `staff_opm.py` | OPM Federal Workforce Data | headcount, job series, hires and separations for ICE, CBP, USCIS, EOIR and USMS |
| `accounts` | `money_object_class.py` | USAspending agency account reports | ICE and CBP obligations by object class, payroll included |

**Hand-checked.** `detention_costs.csv` holds GAO-26-108663's bed rates, purchases and waste findings.

**Checks.**
- ICE custody against TRAC's figures from ICE's biweekly data: Feb 2026 peak 68,289 vs our 69,343 on Feb 1; Apr 4 60,311 vs 58,917 on Apr 1; Jul 11 65,765 vs 63,084 on Jul 1. The June 2026 low (54,831) fits these.
- Arrests against DHS's announced totals: June about 43,000 vs our 42,588; July over 49,000 vs our 49,091.
- Book-ins against TRAC: June 43,138, which equals the ICE workbook's 39,563 + 3,575.

**Silent-error guards.**
- OPM withholds pay for law-enforcement series, so pay sums are not written. Payroll comes from the account reports instead.
- The share with no conviction means ICE's "other immigration violator" label: no conviction and no pending charge.
- The account reports and the contract records differ by design. The page explains the gap: about $2.3B in fiscal year 2025.

## Follow the money: groups, network, finer accounting (8 October 2026)

**Groups.** The tab now has four folding groups:
- Where the money comes from
- Who gets it
- Influence
- What the records do not show

The section numbers are gone. The old "What the records do not show" list was merged into one list of gaps, and its stale lines were removed.

**Network.** "The whole network: who pays whom" draws every payer against its top 18 recipients, grouped by owner (`netData()` reuses `mfTree()`).

**Accounts.** `money_object_class.py` now also writes:
- `agency_object_class_minor.csv`: finer federal spending categories. These must add up to the account total within 0.2%, or they are left out.
- `agency_award_linked.csv`: the part of each spending kind tied to a published award. The rest has no payee in public records. Fiscal 2025: $3.4B of ICE's $6.3B for contracts and services.
- `ice_spending_by_state.csv`: ICE-funded contract money by place of performance. Headquarters services land in VA and DC, and the page says so.

**287(g) payments.** These are added to the gaps from NPR (May 2026, citing DHS, FWD.us and Florida records). No payee-level data exists for them.

## Polar Star, and more from ICE's workbook (9 October 2026)

The page is now named **Polar Star** ("Navigate immigration detention and find your family. Free. Never Commercial. Not affiliated with any government agency."), with a star mark drawn in the page itself, a matching browser icon, and a polar-navy palette (light and dark). Collectors now identify themselves as `polar-star-data-refresh`. The raw-data link still points to the old repository until the new one exists.

`detention_stats.py` now also reads four more sheets from each ICE detention statistics workbook (counts only):

| File | Sheet | What |
|---|---|---|
| `ice_semiannual.csv` | Semiannual | arrests, book-ins, removals by fiscal year: parents of US-citizen children, US citizens, military members and veterans, TPS countries |
| `ice_segregation_reasons.csv` | Vulnerable & Special Population | segregation placements each quarter by reason, average days, unique people |
| `ice_bond_monthly.csv` | Monthly Bond Statistics | final book-outs each month, how many after a bond was posted, average bond, average stay |
| `ice_length_of_stay.csv` | ICLOS and Detainees | average days in custody and people held 0–180, 181–365, 366–730, 730+ days, twice a month |

ICE's newer workbooks show earlier periods as 0 (every fiscal 2025 figure in the FY26 file; bond months before October 2025). A zero in a newer file never replaces a count an older file gave; such rows keep `src` (the file used) and `zeroed_in` (the newer file). On Trends: a new card for the twice-yearly groups; length of stay joins "Who is held"; bond joins "Bond and court results"; segregation reasons join the conduct card. Tests: `test_detention_extra.py`, and browser tests for the money tab in `test_page_money.py` (skipped where Playwright is absent).

## Publisher identity in one place (9 October 2026)

`pipeline/identity.py` holds the publisher name (Polar Star Project), the page name in each language (Polar Star / Estrella Polar),
the public repository address and the project's contact email. The page and every collector read from it; no file names a person or a
personal account, and `test_identity.py` fails the build if one does. Until the new repository and email exist:
`REPO_URL` is blank, so the page leaves out its raw-data link; `CONTACT` is blank, so the SEC check (which requires a contact address)
is skipped and the page keeps the filings already read. Fill both in when the accounts are ready; nothing else needs editing.

## Legal and researcher tabs, downloads, printing (9 October 2026)

- **Legal** tab (after About): not legal advice, accuracy and sources, independence and Never Commercial, privacy, people in the records, outside content, corrections. Drafted for a lawyer's review before launch. The corrections contact comes from `identity.CONTACT`; until it is set the tab says one will be listed at launch.
- **For researchers** tab: how to cite (date built plus the exact view's address), how the numbers are made, getting the data (the raw-data link moved here and appears once `identity.REPO_URL` is set), the terms of data from other projects (Deportation Data Project CC0; adsb.lol ODbL, so the derived flight data must be shared under ODbL; Tracking 287(g) MIT; TRAC cited; public-domain sources), and known limits.
- Every "Show the numbers" table, the flights-by-country table and the 287(g) payments table have **Download these numbers (CSV)**, made in the browser.
- **Print styles**: menus and buttons hidden, each outside link printed with its full address, and a line with the build date and the page address.
- **Link previews**: title and caption for messages and posts.

## Licences (9 October 2026)

- `LICENSE`: PolyForm Noncommercial 1.0.0 for the software (official text, with the Required Notice for the Polar Star Project).
- `LICENSE-CONTENT`: CC BY-NC-SA 4.0 for the page's text, design and charts. The Polar Star names, logo and seal are excluded: all rights reserved (unaltered use to refer to the project is allowed).
- `LICENSE-DATA`: CC BY 4.0 for the data files; flight data under ODbL 1.0 (required by adsb.lol's licence); government records public domain; other projects' data keeps its own terms.
- The page footer carries the licence line in both languages, and the For researchers tab has "What you may reuse".

## Watch list

`pipeline/watch.py` runs inside the build. It works out alerts for oversight bodies from the page's own data:

- **Overdue required reports.** At present this covers ICE's detention statistics, which Congress asked for every two weeks. An alert opens once more than a full cycle plus a week has passed without a new file. It is shown on the Trends tab (first section), in the feed `site/watch.xml`, and as a one-page brief in `data/watch/briefs/` for the publisher to send by hand. Each alert lists the committees and offices that oversee it, regardless of party.
- **Facility alerts.** A facility qualifies on either measure:
  - its death rate over the last 12 months, or
  - the allegation rate in its latest ICE audit

  is at least twice the overall rate, rests on at least 3 deaths, 5 allegations or 10 people, and a count that high would come up by chance no more than 5 times in 100 (Poisson). Refusals of officials at the site are listed beside the figures as facts, never as a cause.

  These alerts are worked out at every build but stay off the page, out of the feed and out of the briefs until `data/reference/watch_rules.json` has `"facility_published": true`. Candidates go to `data/watch/candidates.json`, which is not committed.

`data/reference/watch_log.csv` keeps the day each alert opened and closed. Nothing is sent anywhere automatically.

## Politicians

`pipeline/politicians.py` (refresh step `politicians`) reads the official House Clerk and Senate roll-call records for the laws passed since 2025 that fund and expand immigration enforcement:
- the Laken Riley Act;
- the July 2025 budget law (H.R. 1);
- the Secure America Act (S. 2).

It checks each record's member votes against its own printed totals. Committee membership and official sites come from the public-domain congress-legislators files. The Politicians tab lists every member who voted, whichever way, with their oversight committees and the detention or ICE contractor committee money already shown on Follow the money. Trends compares the votes by party, split by whether a member received that money, and carries a caution: the votes split by party, so a comparison across parties shows party, not influence.

### Named donors (added 2026-10-09)

`pipeline/money_donors.py` (refresh step `donors`, needs `FEC_API_KEY`, runs in Actions) reads the FEC's itemized individual
contributions (Schedule A) whose donor reported working for GEO Group (and its subsidiaries GEO Secure Services, GEO Care,
GEO Transport, BI Incorporated), CoreCivic (and its former name, Corrections Corporation of America), Management & Training
Corporation, LaSalle Corrections, Immigration Centers of America or CSI Aviation, in the current and previous election cycles.
Amentum, Akima and Ahtna are left out: ICE work is a small share of what their staff do.

- **Decision (project, 2026-10-09):** donors in the public record are named for the historical record. Anything not public is not pursued.
- Kept per gift: name, employer and occupation as filed, state, amount, date, recipient committee, link to the filing image.
  Never a street address, city or ZIP.
- 52 U.S.C. 30111(a)(4): FEC contributor names may not be used to solicit contributions or for commercial purposes. The
  project is non-commercial and says so on the page. The FEC salts filings with fictitious names; the page says names are as filed and unchecked.
- Double counts removed: rows filed by WinRed/ActBlue (the candidate's copy is kept), memo entries (code X), exact repeats.
- Gifts to a company's own PAC are shown on their own line (`ctype` O), since that PAC's gifts on are already counted.
- A recipient is tied to a member only through the FEC's own candidate or leadership-fund sponsor link, to exactly one member.
- Shown on Follow the money › Political money and lobbying › Named donors (lazy file), and as a per-member total on Politicians.

## Page layout (changed 2026-10-09)

- **Sub-tabs.** Follow the money has four (Budget, Contracts, Beds and owners, Influence); Trends has five (Enforcement, Who is
  held, Courts and bond, Harm and conditions, By state); the Watch list has two (Facilities and reporting, Officials and money).
  The open sub-tab is in the address (`#money/infl`, `#trends/harm`, `#watch/off`). `trendsSplit()` places each Trends card and
  tile by its title or key; the money charts that used to sit on Trends go to Follow the money (`moneyCharts()`), the watch list
  to its own tab, "data that stopped" and "what is tracked" to About this data, and the agreement trends to Government bodies.
  A card with an unknown title falls back by group, so nothing disappears silently.
- **Folds.** Opening a fold closes the others at the same level, on the click itself as well as on the toggle event.
- **Find anything.** One box above every tab searches members, facilities and every section title, and jumps there.
- **Long lists** (contractors, named donors) show ten, with search and "show more".

## Member scorecards (added 2026-10-09)

Every member on Politicians, on a facility page, in the political money lists and in the donor list opens a scorecard
(`#pol/<bioguide>`). Built by `pol_cards()` in build_site.py from records already on the page: votes on the enforcement laws,
oversight committees, contractor committee money by committee (campaign or leadership fund), joint fundraisers that took
contractor money and the other members in them, named staff donors, ICE facilities in the district (state for senators) with
operator, people held, ICE death reports and watch-list status, and oversight visits, refusals and statements that name them.
Counts are shown side by side; no composite score is computed (a weighting would be our judgment, not the record's).
`pipeline/member_committees.py` (refresh step `membercom`, Actions) reads each member's own FEC committees so joint fundraisers
and committee money can be tied to them by exact FEC committee name.

## Watch list › Officials and money (added 2026-10-09)

`official_flags()`: one rule for every current member, both parties. Listed when (com) on a committee that oversees ICE and at least
`officials_min_usd` (set to 0 on 2026-10-10 by project decision: any amount counts; every itemized gift is summed) from contractor committees or named staff, or (local) a privately run facility in the district
(state for senators) is run by a company whose committee or staff gave them at least that much. Facts only; the page says these are
overlaps between public records, not findings, and names the House Committee on Ethics, the Office of Congressional Conduct and the
Senate Select Committee on Ethics. Names are shown when `officials_published` is true in `watch_rules.json` (approved 2026-10-10); the candidate
list is written to `data/watch/officials_candidates.json` (not committed).

## Review round 4 (2026-10-10)

- **Your state** tab: members for a chosen state (each with a scorecard) and the state's figures side by side (moved from Trends).
- **For families**: steps 7 (consulates; Mexico's 24-hour CIAM line 520-623-7874, from the SRE consulate site) and 8 (if the
  person may already have been deported); the EOIR case-status link is EOIR's current portal. Steps no longer close each other.
- **Facility pages** lead with visiting and legal help; the statistics follow.
- **Scorecards**: facilities and oversight visits come before money; a notice and link when the member is on the overlap list;
  money a member total counts but no committee name matched is shown as one labelled row; party on earlier votes is noted.
- **Top donors and outside spending, any cause** (`pipeline/member_top_donors.py`, refresh step `topdonors`): each current
  member's ten largest committee donors (Schedule A line 11C of the member's own committees) and ten largest outside spenders for
  and against (Schedule E by candidate), current cycle. The project chose this over listing one interest group (AIPAC) alone, so no
  cause is singled out; AIPAC's PAC and other groups appear wherever they actually rank.
- **CSV downloads** added for contracts without competition, every contractor, refusals of entry, and inspections and reports.
- **Cite this section**: any top-level fold, once opened, ends with a citation line and a copy button.
- **Long lists** (no-competition contracts, committee recipients) show ten first.
- **Layout**: desktop sidebar menu and wider content (≥1100px); tables scroll inside themselves; one-row sub-tab bar on phones;
  one fold marker; control outlines at 3:1; focus outlines; legend switches with a check; "›" marks numbers that open a chart.
- `fec_pac_recipients.csv` now keeps `recipient_id`, so committee money is tied to members by FEC id, not only by name.

## Officials, organizations and money added 2026-10-10

Each list below is checked automatically in GitHub Actions. Nothing is approved by hand, and a row that stops passing drops off the page.

- **Organizations to follow** (`social_check.py`; candidates in `data/reference/social_orgs.csv`).
  - Bluesky and Instagram accounts only.
  - Each account is shown only while:
    - the IRS record exists, or the site is a .gov site;
    - the organization's own website links that exact account;
    - for Bluesky, it has posted within 90 days.
  - Instagram activity cannot be checked without signing in.
- **News coverage:** links to Ground News topic pages only. Its search ignores search terms in a URL, so there are no per-facility links.
- **Jail heads** (`officials_check.py`, `local_officials.csv`): the official who runs each local jail holding people for ICE. A name is shown only while the official page in `source_url` still names that person.
- **Governors** (`officials_check.py`)
  - Names come from Wikidata, or from `governors_ref.csv` (kept by hand) where Wikidata does not settle it.
  - A governor is shown only when their own official site names them.
- **Signed 287(g) agreements** (`moa_links.py`)
  - Each agency on ICE's list is matched, by name and model, to the newest signed agreement archived by github.com/appelson/Tracking_287g.
  - Links are pinned to a repository commit.
  - Signers' names are not retyped from the scans; reading them automatically was too error-prone.
- **Former officials lobbying** (`money_lobbying.py` → `lobbying_former_officials.csv`): lobbyists for the detention companies who listed a past government post ("covered position") on their LDA filings, in their own words.
- **PACs focused on US policy toward a specific country** (`country_pacs.py`)
  - Rule A (name):
    - Listed: a PAC or super PAC whose registered name names a foreign country, or its people the way a foreign-policy group does.
    - Left out: "<people> American" community names, unions "of the United States and <country>", leadership PACs and joint fundraisers.
    - Never searched: ambiguous names such as Georgia, Jordan, Chad, Niger and "Turkey" on its own.
  - Rule B (affiliate): a committee a public record identifies as the affiliate of a rule-A committee, kept in `country_pacs_affiliates.csv` with its source.
  - Money is read from each committee's own reports and kept in three separate kinds, never added together:
    - **G:** own-funds contributions to current members (Schedule B).
    - **E:** donor money forwarded as a conduit (earmarked contributions, Schedule B).
    - **S/O:** independent spending supporting or opposing members (Schedule E, regular reports only).
- **Registered foreign agents** (`fara.py`)
  - Covers active FARA registrants and their foreign principals, with the Exhibit A/B filing that describes the work.
  - Countries are ordered by ICE removals.
  - Registrants' political contributions are only in scanned filings and are not read.

## Persona review fixes (2026-10-11)

Four reviews (a family member, a researcher, a congressional staffer, a legal-aid attorney with a designer's eye) led to these changes.

- **For families.** A scam warning at the top; the A-number explained at first use; a dated note that many people now get no bond hearing (with habeas as the route a lawyer may use); warnings for relatives without status about paying bond at an ICE office and about visiting; know-your-rights basics; consulate links; what to do after a deportation. Search finds these steps first, in English and Spanish ("abogado", "fianza", "deportado"...).
- **Help lines are checked.** `pipeline/hotlines_check.py` (step `hotlines`) reads `data/reference/hotlines.csv` and shows a phone number or help link only while one of its official pages still shows it (21-day grace if every page is unreachable). A number that fails is hidden, not guessed. ice.gov and state.gov block GitHub's runners, so lines published only there stay hidden until another official page carries them.
- **One clock.** `build_site.py` runs in UTC, like Actions, and stops if any `*meta*.json` date is later than the build date.
- **Dates.** ICE's statistics file is dated by the figures' as-of date, not the day it was posted. The deaths header says "since October 2022" and lists the yearly counts before that.
- **Politicians.** The overlap list moved here from the Watch list, with a $200 floor (`officials_min_usd`), no ethics-office links, and only the member's own committees counted (joint fundraisers are shown apart). All 50 governors are listed; one whose site failed the check is marked, not dropped. Oversight visits say "not checked" when the member's press page could not be read, and give the window read when it could. Country-focused PACs and FARA registrants sit under **Other political money**, with a stated reason; an affiliate counts only when the FEC's own record names its parent (so United Democracy Project drops off unless its FEC registration names AIPAC); FARA countries are alphabetical, with no removal counts beside them. Any "own funds" amount above $10,000 per member per cycle is held back and counted on the page as awaiting review.
- **Alerts from the records** (was Watch list): facility flags use a Benjamini-Hochberg cut-off across all facilities and measures; federal prisons are left out of the long-stay test; neutral titles.
- **Menu and access.** "Get help" group; Flights under Money and patterns; one H1 per view; skip link; `aria-current` on the open tab; state view has its own link (`#state/TX`).

## Other ICE contractors (added 2026-10-11)

A tab under Who works with ICE for every company in `ice_awards.csv` (ICE contracts of $1 million or more, window dollars) whose ICE money is not mostly for running detention sites (code S206; those stay on Companies). Each company is placed by the federal product/service code of most of its dollars (`build_site.vendor_cat`). `pipeline/vendor_lobbying.py` (step `vendorlobby`) reads each contractor's lobbying reports since 2023 (those with $10 million or more, and their parent unless the parent is a detention operator): reports, dollars (own plus outside, an upper figure), how many listed ICE as an agency contacted and how many listed immigration, and a link to the newest such report. Matching is by the client name on the report starting with the company's own name.

## 287(g) signers and joint fundraiser flows (added 2026-10-11)

- `pipeline/moa_signers.py` (step `signers`) downloads each agreement PDF and reads the agency side of its signature block (pdftotext -layout, left of the "For ICE:" column). A name is shown only when it is on the Name line, reads as 2–4 clean words, has a local-office title, appears a second time in the same agreement, is not an ICE signer, and is not the "signer" on more than 3 agencies' agreements. Otherwise the typed Appendix A point of contact is shown, labelled as the contact and not as the signer. Results are cached by PDF path; bump `PARSER` to re-read everything. Needs `poppler-utils` in the workflow.
- `pipeline/jfc_flows.py` (step `jfc`) reads, for each joint fundraising committee that took detention-company PAC money, its FEC totals and its Schedule B payments to other committees, with recipient party, committee type and designation. `build_site.jfc_flows` makes the "Where the joint fundraisers sent the money" fold: totals, a breakdown by committee kind and party, top recipients, recipients paid by several fundraisers, and each fundraiser. The company share for each recipient is an estimate (contractor ÷ receipts × payment) and is labelled as one. A fundraiser with no FEC total gets no estimate.
