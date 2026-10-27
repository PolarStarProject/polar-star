"""Every tab opens in both languages with every fold open and no script error (skipped where Playwright is not installed).
A Spanish-only date bug once stopped the pregnancies and deaths tab from drawing at all."""
import pathlib

PAGE = pathlib.Path(__file__).resolve().parent.parent / "site" / "index.html"
VIEWS = ["fam", "find", "flights", "orgs", "agree", "co", "ven", "opm", "gov", "pol", "life", "over", "news", "disp", "money", "trends", "about", "legal", "research", "watch", "state"]


def test_every_tab_draws_in_english_and_spanish_without_errors():
    try: from playwright.sync_api import sync_playwright
    except ImportError: return
    if not PAGE.exists(): return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(PAGE.as_uri()); pg.wait_for_timeout(1000)
        for lang in ("en", "es"):
            pg.evaluate(f"setLang('{lang}')")
            for v in VIEWS:
                pg.evaluate(f"showView('{v}')"); pg.wait_for_timeout(250)
                pg.evaluate(f"document.querySelectorAll('#v-{v} details').forEach(d => d.open = true)"); pg.wait_for_timeout(150)
                assert not errs, f"{lang}/{v}: {errs[:2]}"
                assert pg.evaluate(f"document.getElementById('v-{v}').innerText.trim().length") > 200 or v == "flights", f"{lang}/{v} is nearly empty"
        b.close()


def test_every_menu_button_opens_its_tab():
    """A tab that only opens through showView() but not by tapping its button is broken for readers."""
    try: from playwright.sync_api import sync_playwright
    except ImportError: return
    if not PAGE.exists(): return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844})
        pg.goto(PAGE.as_uri()); pg.wait_for_timeout(1000)
        bad = []
        for tid in pg.evaluate("[...document.querySelectorAll('#views button[id^=tab-]')].filter(x => !x.hidden).map(x => x.id)"):
            pg.evaluate("document.getElementById('menu').open = true")
            if pg.evaluate(f"document.getElementById('{tid}').closest('.vg').classList.contains('shut')"): pg.click(f"#{tid} >> xpath=ancestor::div[contains(@class,'vg')]/button[contains(@class,'vgl')]")
            pg.click("#" + tid); pg.wait_for_timeout(200)
            if pg.evaluate(f"document.getElementById('v-{tid[4:]}').hidden"): bad.append(tid)
            if pg.evaluate("document.querySelectorAll('#views .vg:not(.shut)').length") != 1: bad.append(tid + " (more than one topic open)")
        b.close()
        assert not bad, bad


def test_site_search_finds_family_words_places_and_points_names_to_the_locator():
    try: from playwright.sync_api import sync_playwright
    except ImportError: return
    if not PAGE.exists(): return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(PAGE.as_uri()); pg.wait_for_timeout(1000)
        got = {}
        for q in ["niño", "92301", "adelanto ca", "fraud", "juan perez", "A123456789"]:
            pg.fill("#fa-q", ""); pg.focus("#fa-q"); pg.fill("#fa-q", q); pg.wait_for_timeout(700)
            got[q] = pg.evaluate("document.getElementById('fa-list').innerText")
        b.close()
        assert not errs, errs
        assert "1." in got["niño"] and "Adelanto" in got["92301"] and "Adelanto" in got["adelanto ca"] and "4." in got["fraud"], got
        assert "locator" in got["juan perez"].lower() and "locator" in got["A123456789"].lower(), got


def test_a_facility_page_draws_in_both_languages_with_the_steps_before_the_alert():
    try: from playwright.sync_api import sync_playwright
    except ImportError: return
    if not PAGE.exists(): return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(PAGE.as_uri() + "#find/ADLNTCA"); pg.wait_for_timeout(1500)
        deaths = pg.evaluate("document.getElementById('f-deaths').textContent")
        order = pg.evaluate("(()=>{const w=document.getElementById('f-watch'), n=document.querySelector('#detail h2[data-t=next]'); return !w || w.hidden || !!(n.compareDocumentPosition(w) & Node.DOCUMENT_POSITION_FOLLOWING)})()")
        pg.evaluate("setLang('es')"); pg.wait_for_timeout(500)
        es = pg.evaluate("document.getElementById('detail').textContent")
        b.close()
        assert not errs, errs
        assert order and deaths and "Field Office" not in es


def test_share_offers_ways_to_send_the_public_link_and_loads_nothing_until_tapped():
    try: from playwright.sync_api import sync_playwright
    except ImportError: return
    if not PAGE.exists(): return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}); errs, reqs = [], []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("request", lambda r: reqs.append(r.url))
        pg.goto(PAGE.as_uri() + "#find/ADLNTCA"); pg.wait_for_timeout(1200); n0 = len(reqs)
        pg.evaluate("navigator.share = undefined"); pg.click("#f-share"); pg.wait_for_timeout(300)
        links = pg.evaluate("[...document.querySelectorAll('#snap .shlist a')].map(a => a.href)")
        b.close()
        assert not errs, errs
        assert any(u.startswith("mailto:") for u in links) and any(u.startswith("sms:") for u in links)
        assert all("polarstarproject.org" in u and "find%2FADLNTCA" in u for u in links), links
        assert all(u.startswith("file:") for u in reqs[n0:]), reqs[n0:]       # nothing fetched from another site


def test_other_political_money_has_tiles_that_open_charts():
    try: from playwright.sync_api import sync_playwright
    except ImportError: return
    if not PAGE.exists(): return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(PAGE.as_uri()); pg.wait_for_timeout(1000); pg.evaluate("showView('opm')"); pg.wait_for_timeout(400)
        n = pg.evaluate("document.querySelectorAll('#opm-tiles button').length")
        if n: pg.click("#opm-tiles button"); pg.wait_for_timeout(300)
        bars = pg.evaluate("document.querySelectorAll('#snap .mgl li').length")
        b.close()
        assert not errs, errs
        assert n == 0 or bars > 0, (n, bars)


def test_a_lobbying_firm_opens_its_card_from_money_and_foreign_agents_in_both_languages():
    try: from playwright.sync_api import sync_playwright
    except ImportError: return
    if not PAGE.exists(): return
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(PAGE.as_uri()); pg.wait_for_timeout(1000)
        names = pg.evaluate("Object.keys((DATA.firms || {}).cards || {})")
        if not names: b.close(); return
        out = []
        for lg in ("en", "es"):
            pg.evaluate(f"setLang && setLang('{lg}')") if pg.evaluate("typeof setLang === 'function'") else None
            for n in names:
                pg.evaluate("n => firmCard(n)", n); pg.wait_for_timeout(50)
                out.append(pg.evaluate("[document.querySelector('#snap h2').textContent, document.querySelectorAll('#snap .fcard .tiles button').length, document.querySelectorAll('#snap .fcard details').length]"))
        both = pg.evaluate("((DATA.pol || {}).fara || {}).both || []")
        fm = pg.evaluate("((DATA.pol || {}).fara || {}).fmap || {}")
        b.close()
        assert not errs, errs
        assert all(h and t >= 1 and d >= 1 for h, t, d in out), out
        assert all(fm.get(x) in names for x in both), (both, fm)
