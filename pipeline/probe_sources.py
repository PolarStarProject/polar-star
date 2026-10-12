"""One-off look at sources this sandbox cannot reach: saves what each page or file returns, so parsers are written against
the real thing. Runs only when asked by name (refresh_all.py --only probe). Writes data/probe/ (index.json + one file per URL).

Nothing here feeds the page. Files over 40 MB are cut; CSVs are gzipped.
"""
import gzip, hashlib, json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
import icefetch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "probe_inbox"      # committed by the workflow, read here, then removed; data/probe/ (local only) keeps earlier rounds

PAGES = {
    "https://www.cbp.gov/": [
        "https://www.cbp.gov/document/stats/nationwide-encounters",
        "https://www.cbp.gov/newsroom/stats/nationwide-encounters",
        "https://www.cbp.gov/newsroom/stats/cbp-public-data-portal",
        "https://www.cbp.gov/newsroom/stats/custody-and-transfer-statistics",
        "https://www.cbp.gov/newsroom/stats/border-rescues-and-mortality-data",
        "https://www.cbp.gov/newsroom/accountability-and-transparency",
        "https://www.cbp.gov/document/foia-record/death-custody",
        "https://www.cbp.gov/document/report/fiscal-year-2023-office-professional-responsibility-cbp-related-deaths-report",
        "https://www.cbp.gov/sites/default/files/2025-04/fy20232-cbp-opr-related-deaths-report.pdf",
        "https://www.cbp.gov/sites/default/files/assets/documents/2024-Mar/fy2022-cbp-opr-related-deaths-report.pdf",
        "https://www.cbp.gov/sites/default/files/assets/documents/2023-Jan/Death%20in%20Custody%20Statistics%202017-2022.pdf",
        "https://www.cbp.gov/newsroom/media-releases/all?title=summary+of+incident",
        "https://www.cbp.gov/newsroom/media-releases/all?title=summary+of+incident&page=1",
        "https://www.cbp.gov/newsroom/media-releases/all?title=summary+of+incident&page=2",
        "https://www.cbp.gov/newsroom/media-releases/all?title=dies",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-woman-china-dies-us-border-patrol-facility-yuma",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-subject-dies-custody-blaine-peace-arch-poe",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-cbp-detainee-terminal-illness-dies-hospital",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-illegal-alien-dies-custody-unreported-pre-existing",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-agents-encounter-illegal-alien-having-heart-attack",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-woman-dies-pre-existing-cancer-after-illegally",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-man-mexico-heart-disease-dies-while-illegally",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-man-mexico-dies-pneumonia-and-heart-disease-after",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-migrant-medical-distress-dies-after-calling-911",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-border-patrol-agents-unable-save-illegal-alien",
        "https://www.cbp.gov/newsroom/national-media-release/summary-incident-migrant-found-dimmit-county-dies-environmental",
    ],
    "https://ohss.dhs.gov/": [
        "https://ohss.dhs.gov/topics/immigration/immigration-enforcement/monthly-tables",
        "https://ohss.dhs.gov/topics/immigration/immigration-enforcement/annual-flow-report",
        "https://ohss.dhs.gov/topics/immigration/yearbook/2023",
        "https://ohss.dhs.gov/topics/immigration/yearbook/2023/table39",
        "https://ohss.dhs.gov/topics/immigration/yearbook/2024",
        "https://ohss.dhs.gov/khsm/ice-detentions",
        "https://ohss.dhs.gov/khsm/cbp-encounters",
        "https://ohss.dhs.gov/khsm/dhs-repatriations",
        "https://ohss.dhs.gov/topics/immigration/immigration-enforcement",
    ],
    "https://www.gao.gov/": [
        "https://www.gao.gov/products/gao-26-108663",
        "https://www.gao.gov/products/gao-26-108886",
        "https://www.gao.gov/products/gao-25-107346",
        "https://www.gao.gov/products/gao-20-536",
        "https://www.gao.gov/assets/gao-26-108663.pdf",
        "https://www.gao.gov/assets/gao-26-108886.pdf",
        "https://www.gao.gov/assets/gao-25-107346.pdf",
        "https://www.gao.gov/assets/d20536.pdf",
    ],
    "https://acf.gov/": ["https://acf.gov/orr/about/ucs/facts-and-data"],
    "https://www.justice.gov/": ["https://www.justice.gov/eoir/workload-and-adjudication-statistics"],
    "https://www.uscis.gov/": ["https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data",
                               "https://www.uscis.gov/sites/default/files/document/data/CredibleFearandReasonableFearWorkload.pdf"],
    "https://www.foreign.senate.gov/": ["https://www.foreign.senate.gov/imo/media/doc/(FINAL%20-%20web)%20At%20What%20Cost%20-%20Inside%20the%20Trump%20Administration%27s%20Secret%20Deportation%20Deals_2.17.26.pdf"],
    "https://bjs.ojp.gov/": ["https://bjs.ojp.gov/document/fdcda23st.pdf", "https://bjs.ojp.gov/document/fdcda22st.pdf"],
    "https://www.ice.gov/": ["https://www.ice.gov/statistics", "https://www.ice.gov/detain/detention-management"],
    "https://www.everycrsreport.com/": ["https://www.everycrsreport.com/files/2026-09-17_LSB11413_644f0635f41eb8607df238ee9e4f37cfa35d590a.pdf"],
    "https://files.gao.gov/": ["https://files.gao.gov/assets/gao-26-108437.pdf", "https://www.gao.gov/assets/gao-26-108437-highlights.pdf",
                               "https://www.gao.gov/products/b-337366", "https://www.gao.gov/products/gao-26-108437"],
    "https://www.warren.senate.gov/": ["https://www.warren.senate.gov/imo/media/doc/cost_report_on_diverting_military_resources_for_immigration_enforcement.pdf"],
    "https://oag.ca.gov/": ["https://oag.ca.gov/system/files/attachments/press-docs/Multistate%20Letter%20on%20ICE%20Change%20in%20Detainee%20Death%20Policy.FINAL_.pdf"],
    "https://www.ajc.com/": ["https://www.ajc.com/news/2026/06/ice-will-no-longer-report-deaths-of-detainees-who-have-recently-been-released-from-custody/"],
    "https://www.wwno.org/": ["https://www.wwno.org/npr-news/2026-05-07/dhs-blames-funding-lapse-for-shutdown-of-internal-detention-oversight"],
    "https://ctmirror.org/": ["https://ctmirror.org/2026/01/06/judge-hhs-authorized-to-resume-sharing-some-medicaid-data-with-ice/"],
    "https://www.courthousenews.com/": ["https://www.courthousenews.com/wp-content/uploads/2026/02/community-v-bessent-mass-ruling.pdf"],
    "https://immpolicytracking.org/": ["https://immpolicytracking.org/policies/reported-social-security-administration-shares-immigrants-addresses-with-dhs/",
                                       "https://immpolicytracking.org/policies/dhs-partners-with-the-state-of-nebraska-to-build-the-cornhusker-clink-for-ice-detention/",
                                       "https://immpolicytracking.org/policies/reported-dhs-immigration-data-no-longer-publicly-available/"],
    "https://kmph.com/": ["https://kmph.com/news/nation-world/ice-opens-new-louisiana-lockup-immigrant-detention-center-at-notorious-prison-angola-louisiana-state-penitentiary-dhs-deportations-immigration"],
    "https://www.wndu.com/": ["https://www.wndu.com/2025/08/06/dhs-open-new-speedway-slammer-ice-detention-facility-north-central-indiana"],
    "https://www.pogo.org/": ["https://www.pogo.org/investigates/ice-inspections-plummeted-as-detentions-soared-in-2025"],
    "https://www.themarshallproject.org/": ["https://www.themarshallproject.org/2026/07/15/ice-data-immigration-detention-transparency"],
    "https://www.bostonglobe.com/": ["https://www.bostonglobe.com/2026/03/15/nation/trump-pushes-deportations-immigration-data-becomes-harder-find"],
    "https://acf.gov/ ": ["https://acf.gov/orr/data/uac-operational", "https://acf.gov/orr/data/uac-monthly-release-sponsor"],
    "https://ohss.dhs.gov/ ": ["https://ohss.dhs.gov/sites/default/files/2025-01/KHSM%20Detentions%20%28Book-ins%29%20fy25m11.xlsx",
                               "https://ohss.dhs.gov/sites/default/files/2025-01/KHSM%20Repatriations%20fy25m11.xlsx",
                               "https://ohss.dhs.gov/system/files/2026-08/2026_0806_ohss_yearbook_enforcement_fy2023.xlsx"],
    "https://acf.gov/  ": ["https://acf.gov/sites/default/files/documents/orr/UAC-Operational-Data_Sep2026.xlsx", "https://acf.gov/sites/default/files/documents/orr/UAC-Monthly-Released-to-Sponsor-Data_Sep2026.xlsx"],
    "https://www.cbp.gov/ ": ["https://www.cbp.gov/newsroom/national-media-release/summary-incident-border-patrol-agent-defends-himself-deadly", "https://www.cbp.gov/newsroom/national-media-release/summary-incident-multiple-illegal-aliens-killed-during-vehicle"],
    "https://www.congress.gov/": ["https://www.congress.gov/119/plaws/publ21/PLAW-119publ21.htm", "https://www.congress.gov/119/plaws/publ98/PLAW-119publ98.htm"],
    "https://www.govinfo.gov/": ["https://www.govinfo.gov/content/pkg/PLAW-119publ21/html/PLAW-119publ21.htm"],
    "https://www.oig.dhs.gov/": ["https://www.oig.dhs.gov/reports/audits-inspections-and-evaluations"],
    "https://www.ice.gov/ ": ["https://www.ice.gov/doclib/foia/policy/11003.7.pdf"],
    "https://www.ice.gov/  ": [
        "https://www.ice.gov/doclib/detention/FY26_detentionStats07202026.xlsx",
        "https://www.ice.gov/doclib/detention/FY25_detentionStats.xlsx",
        "https://www.ice.gov/doclib/detention/FY24_detentionStats.xlsx",
        "https://www.ice.gov/statistics",
        "https://www.ice.gov/detain/detention-management",
    ],
    "https://data.opm.gov/": [
        "https://data.opm.gov/FWD%20Data%20Dictionary.xlsx",
        "https://data.opm.gov/api/v1/files/employment?current=true",
        "https://data.opm.gov/api/v1/files/employment?year=2025&current=true",
    ],
    "https://www.dhs.gov/": [
        "https://www.dhs.gov/dhs-budget",
        "https://www.dhs.gov/cj",
        "https://www.dhs.gov/publication/congressional-budget-justification-fiscal-year-fy-2026",
        "https://www.dhs.gov/publication/fy-2026-budget-brief",
    ],
    "https://www.justice.gov/ ": ["https://www.justice.gov/eoir/media/1344791/dl?inline", "https://www.justice.gov/jmd/media/1434716/dl"],
}

API = "https://api.usaspending.gov"
W = [{"start_date": "2022-10-01", "end_date": "2025-09-30"}]
W26 = [{"start_date": "2022-10-01", "end_date": "2026-09-30"}]
CONTRACTS, GRANTS = ["A", "B", "C", "D"], ["02", "03", "04", "05"]
CBP = {"type": "awarding", "tier": "subtier", "name": "U.S. Customs and Border Protection", "toptier_name": "Department of Homeland Security"}
ICE_FUND = {"type": "funding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}
ACF = {"type": "awarding", "tier": "subtier", "name": "Administration for Children and Families", "toptier_name": "Department of Health and Human Services"}
FEMA = {"type": "awarding", "tier": "subtier", "name": "Federal Emergency Management Agency", "toptier_name": "Department of Homeland Security"}
AWARD_FIELDS = ["Award ID", "Recipient Name", "Award Amount", "Description", "Awarding Agency", "Awarding Sub Agency", "Funding Sub Agency",
                "Start Date", "End Date", "recipient_id", "generated_internal_id"]

def cat(kind, filters): return ("POST", f"/api/v2/search/spending_by_category/{kind}/", {"filters": filters, "limit": 100, "page": 1})
def awards(filters): return ("POST", "/api/v2/search/spending_by_award/", {"filters": filters, "fields": AWARD_FIELDS, "limit": 100, "page": 1, "sort": "Award Amount", "order": "desc"})

QUERIES = {
    "cbp_recipients_contracts": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [CBP], "time_period": W}),
    "cbp_psc_contracts": cat("psc", {"award_type_codes": CONTRACTS, "agencies": [CBP], "time_period": W}),
    "cbp_naics_contracts": cat("naics", {"award_type_codes": CONTRACTS, "agencies": [CBP], "time_period": W}),
    "cbp_recipients_individuals": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [CBP], "time_period": W, "recipient_type_names": ["individuals"]}),
    "cbp_recipients_soleprop": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [CBP], "time_period": W, "recipient_type_names": ["sole_proprietorship"]}),
    "acf_93676_recipients": cat("recipient", {"award_type_codes": GRANTS, "program_numbers": ["93.676"], "agencies": [ACF], "time_period": W26}),
    "acf_contracts_recipients": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [ACF], "time_period": W26}),
    "acf_contracts_psc": cat("psc", {"award_type_codes": CONTRACTS, "agencies": [ACF], "time_period": W26}),
    "fema_97158_recipients": cat("recipient", {"award_type_codes": GRANTS, "program_numbers": ["97.158"], "time_period": W26}),
    "fema_97158_awards": awards({"award_type_codes": GRANTS, "program_numbers": ["97.158"], "time_period": W26}),
    "ice_funded_awarding_agencies": cat("awarding_subagency", {"award_type_codes": CONTRACTS, "agencies": [ICE_FUND], "time_period": W26}),
    "ice_funded_other_awarders": awards({"award_type_codes": CONTRACTS, "agencies": [ICE_FUND, {"type": "awarding", "tier": "toptier", "name": "Department of Defense"}], "time_period": W26}),
    "dod_migrant_awards": awards({"award_type_codes": CONTRACTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Defense"}], "description": "migrant", "time_period": W26}),
    "dod_detention_awards": awards({"award_type_codes": CONTRACTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Defense"}], "description": "detention", "time_period": W26}),
    "state_iom_awards": awards({"award_type_codes": GRANTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "recipient_search_text": ["INTERNATIONAL ORGANIZATION FOR MIGRATION"], "time_period": W26}),
    "cfda_detention": ("POST", "/api/v2/autocomplete/cfda/", {"search_text": "detention", "limit": 20}),
    "cfda_shelter": ("POST", "/api/v2/autocomplete/cfda/", {"search_text": "shelter and services", "limit": 20}),
    "cfda_unaccompanied": ("POST", "/api/v2/autocomplete/cfda/", {"search_text": "unaccompanied", "limit": 20}),
    "award_fort_bliss_army": ("GET", "/api/v2/awards/CONT_AWD_W9124J25FA075_9700_N0002325D0004_9700/", None),
    "award_fort_bliss_ice": ("GET", "/api/v2/awards/CONT_AWD_70CDCR26FR0000001_7012_N0002325D0004_9700/", None),
    "award_wexmac_idv": ("GET", "/api/v2/awards/CONT_IDV_N0002325D0004_9700/", None),
    "award_gtmo_idv": ("GET", "/api/v2/awards/CONT_IDV_70CDCR24D00000008_7012/", None),
    "toptier_agencies": ("GET", "/api/v2/references/toptier_agencies/", None),
    "ice_gov_recipients": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": W26, "recipient_type_names": ["government"]}),
    "ice_local_gov_recipients": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": W26, "recipient_type_names": ["local_government"]}),
    "ice_assistance_by_type": ("POST", "/api/v2/search/spending_by_category/cfda/", {"filters": {"award_type_codes": ["02", "03", "04", "05", "06", "07", "08", "09", "10", "11"], "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": W26}, "limit": 50, "page": 1}),
    "ice_assistance_recipients": cat("recipient", {"award_type_codes": ["02", "03", "04", "05", "06", "07", "08", "09", "10", "11"], "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": W26}),
    "ice_idv_recipients": cat("recipient", {"award_type_codes": ["IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E"], "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": W26}),
    "state_foreign_gov": awards({"award_type_codes": GRANTS + ["09", "11"], "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "recipient_search_text": ["GOVERNMENT OF"], "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "state_return_awards": awards({"award_type_codes": GRANTS + ["09", "11"], "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "description": "return", "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "state_reintegration_awards": awards({"award_type_codes": GRANTS + ["09", "11"], "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "description": "reintegration", "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "state_eqg": awards({"award_type_codes": GRANTS + ["09", "11"], "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "recipient_search_text": ["EQUATORIAL GUINEA"], "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "doj_eoir_contracts": awards({"award_type_codes": CONTRACTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Justice"}], "description": "immigration review", "time_period": W26}),
    "doj_eoir_cat": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Justice"}], "description": "immigration", "time_period": W26}),
    "usms_ice_funded": cat("awarding_subagency", {"award_type_codes": CONTRACTS + GRANTS, "agencies": [{"type": "funding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": W26}),
    "recipient_types_ref": ("GET", "/api/v2/references/filter_tree/psc/", None),
    "state_grants_foreign_gov": awards({"award_type_codes": GRANTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "recipient_search_text": ["GOVERNMENT OF"], "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "state_grants_return": awards({"award_type_codes": GRANTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "description": "return", "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "state_grants_reception": awards({"award_type_codes": GRANTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "description": "third country", "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "state_other_foreign_gov": awards({"award_type_codes": ["09", "11"], "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of State"}], "recipient_search_text": ["GOVERNMENT"], "time_period": [{"start_date": "2025-01-20", "end_date": "2026-09-30"}]}),
    "ice_funded_opo": cat("recipient", {"award_type_codes": CONTRACTS, "agencies": [ICE_FUND, {"type": "awarding", "tier": "subtier", "name": "Office of Procurement Operations", "toptier_name": "Department of Homeland Security"}], "time_period": W26}),
    "ice_funded_opo_awards": awards({"award_type_codes": CONTRACTS, "agencies": [ICE_FUND, {"type": "awarding", "tier": "subtier", "name": "Office of Procurement Operations", "toptier_name": "Department of Homeland Security"}], "time_period": W26}),
    "doj_corecivic": awards({"award_type_codes": CONTRACTS, "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Justice"}], "description": "immigration", "recipient_search_text": ["CORECIVIC"], "time_period": W26}),
    "cfda_bridging": ("POST", "/api/v2/autocomplete/cfda/", {"search_text": "reimbursement fund", "limit": 20}),
    "cfda_border_fund": ("POST", "/api/v2/autocomplete/cfda/", {"search_text": "border security", "limit": 20}),
    "cfda_287g": ("POST", "/api/v2/autocomplete/cfda/", {"search_text": "287", "limit": 20}),
    "fa_ice_os": ("GET", "/api/v2/federal_accounts/070-0540/", None),
    "fa_ice_os_oc": ("GET", "/api/v2/federal_accounts/070-0540/available_object_classes/", None),
    "fa_ice_os_snap25": ("GET", "/api/v2/federal_accounts/070-0540/fiscal_year_snapshot/2025/", None),
    "agency_070_oc25": ("GET", "/api/v2/agency/070/object_class/?fiscal_year=2025", None),
    "agency_070_fa25": ("GET", "/api/v2/agency/070/federal_account/?fiscal_year=2025&limit=100", None),
    "spend_dhs_fa25": ("POST", "/api/v2/spending/", {"type": "federal_account", "filters": {"fy": "2025", "period": "12", "agency": 766}}),
    "spend_dhs_oc25": ("POST", "/api/v2/spending/", {"type": "object_class", "filters": {"fy": "2025", "period": "12", "agency": 766}}),
    "fa_ice_oc_total25": ("POST", "/api/v2/federal_accounts/070-0540/object_classes/total/", {"filters": {"time_period": [{"start_date": "2024-10-01", "end_date": "2025-09-30"}]}, "limit": 100}),
    "fa_ice_pa_total25": ("POST", "/api/v2/federal_accounts/070-0540/program_activities/total/", {"filters": {"time_period": [{"start_date": "2024-10-01", "end_date": "2025-09-30"}]}, "limit": 100}),
    "spend_ice_oc_drill": ("POST", "/api/v2/spending/", {"type": "object_class", "filters": {"fy": "2025", "period": "12", "agency": 766, "federal_account": 5205, "object_class": "20"}}),
    "spend_ice_recipient25": ("POST", "/api/v2/spending/", {"type": "recipient", "filters": {"fy": "2025", "period": "12", "agency": 766, "federal_account": 5205, "object_class": "20"}}),
    "spend_ice_pa25": ("POST", "/api/v2/spending/", {"type": "program_activity", "filters": {"fy": "2025", "period": "12", "agency": 766, "federal_account": 5205}}),
    "ice_geo_state26": ("POST", "/api/v2/search/spending_by_geography/", {"scope": "place_of_performance", "geo_layer": "state", "filters": {"award_type_codes": ["A", "B", "C", "D"], "agencies": [{"type": "funding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": [{"start_date": "2023-10-01", "end_date": "2026-09-30"}]}}),
    "ice_geo_state_aw26": ("POST", "/api/v2/search/spending_by_geography/", {"scope": "place_of_performance", "geo_layer": "state", "filters": {"award_type_codes": ["A", "B", "C", "D"], "agencies": [{"type": "awarding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "time_period": [{"start_date": "2023-10-01", "end_date": "2026-09-30"}]}}),
    "ice_iaa_awards": ("POST", "/api/v2/search/spending_by_award/", {"filters": {"award_type_codes": ["IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E"], "agencies": [{"type": "funding", "tier": "subtier", "name": "U.S. Immigration and Customs Enforcement", "toptier_name": "Department of Homeland Security"}], "recipient_search_text": ["MARSHALS"], "time_period": [{"start_date": "2023-10-01", "end_date": "2026-09-30"}]}, "fields": ["Award ID", "Recipient Name", "Award Amount", "Description"], "limit": 50, "page": 1}),
}


# This round only: what is listed here is fetched; earlier rounds' results are kept locally in data/probe/.
NOW_PAGES = set()
NOW_QUERIES = set()


def slug(u):
    s = re.sub(r"[^A-Za-z0-9]+", "-", u.split("://", 1)[-1])[:90].strip("-")
    return f"{s}-{hashlib.sha1(u.encode()).hexdigest()[:6]}"


def links(html, base):
    found = set(re.findall(r'href="([^"#]+)"', html))
    keep = [urljoin(base, h) for h in found if re.search(r"\.(csv|xlsx?|pdf|zip)(\?|$)|summary-incident|death|custody|encounter|table|yearbook", h, re.I)]
    return sorted(set(keep))[:400]


def save(name, data, ext):
    OUT.mkdir(parents=True, exist_ok=True)
    if len(data) > 40e6: data = data[:int(40e6)]
    if ext == "csv": p = OUT / f"{name}.csv.gz"; p.write_bytes(gzip.compress(data))
    else: p = OUT / f"{name}.{ext}"; p.write_bytes(data)
    return p.name


def main():
    import requests
    OUT.mkdir(parents=True, exist_ok=True)
    old = OUT / "index.json"
    index = json.loads(old.read_text(encoding="utf-8")) if old.exists() else {"pages": {}, "api": {}}
    for origin, urls in PAGES.items():
        if origin not in NOW_PAGES: continue
        origin = origin.strip()
        for u in urls:
            if "file" in index["pages"].get(u, {}): continue
            got = {}
            try: got = icefetch.fetch_bytes([u], origin=origin, pause=1.0)
            except Exception as e: index["pages"][u] = {"error": str(e)[:200]}; continue
            b = got.get(u)
            if not b: index["pages"][u] = {"error": "not read"}; continue
            low = u.lower().split("?")[0]
            ext = "pdf" if low.endswith(".pdf") or b[:4] == b"%PDF" else "csv" if low.endswith(".csv") else "xlsx" if low.endswith((".xlsx", ".xls")) or b[:2] == b"PK" else "html"
            entry = {"bytes": len(b), "file": save(slug(u), b, ext)}
            if ext == "html":
                h = b.decode("utf-8", "replace"); entry["title"] = (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1].strip()[:200]
                entry["links"] = links(h, u)
            index["pages"][u] = entry
            print(f"{u}: {entry.get('bytes')} bytes", flush=True)
    s = requests.Session()
    for name, (method, path, body) in QUERIES.items():
        if name not in NOW_QUERIES or index["api"].get(name, {}).get("status") == 200: continue
        for attempt in range(3):
            try:
                r = s.request(method, API + path, json=body, timeout=120)
                index["api"][name] = {"status": r.status_code, "body": body}
                (OUT / f"api-{name}.json").write_text(r.text[:5_000_000], encoding="utf-8")
                break
            except Exception as e:
                index["api"][name] = {"error": str(e)[:200], "body": body}; time.sleep(20)
        print(f"api {name}: {index['api'][name].get('status')}", flush=True); time.sleep(1.5)
    # encounters CSVs linked from the CBP document page, newest first
    enc = []
    for u in sorted(set(enc), reverse=True)[:3]:
        try:
            b = icefetch.fetch_bytes([u], origin="https://www.cbp.gov/", pause=1.0).get(u)
            index["pages"][u] = {"bytes": len(b), "file": save(slug(u), b, "csv")} if b else {"error": "not read"}
        except Exception as e: index["pages"][u] = {"error": str(e)[:200]}
    (OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    ok = sum(1 for p in index["pages"].values() if "file" in p)
    print(f"probe: {ok}/{len(index['pages'])} pages read, {sum(1 for a in index['api'].values() if a.get('status') == 200)}/{len(QUERIES)} API calls ok")


if __name__ == "__main__":
    main()
