"""Checks on the built page in a real browser (skipped where Playwright is not installed, e.g. the weekly refresh).

The Follow the money tab fills four sub-tabs (budget, contracts, beds and owners, influence) from hosts inside them; anything that falls back to the hidden containers would vanish
from the page without an error. The network chart must draw every dollar exactly once: each company's ribbons add to its box.
"""
import pathlib

PAGE = pathlib.Path(__file__).resolve().parent.parent / "site" / "index.html"


def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


def _money_page(p, lang):
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 844}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(PAGE.as_uri()); pg.wait_for_timeout(1000)
    if lang == "es": pg.evaluate("setLang('es')")
    pg.evaluate("showView('money')"); pg.wait_for_timeout(700)
    return b, pg, errs


def test_money_groups_are_filled_and_nothing_lands_in_the_hidden_fallback():
    sp = _browser()
    if not sp or not PAGE.exists(): return
    with sp() as p:
        for lang in ("en", "es"):
            b, pg, errs = _money_page(p, lang)
            counts = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#v-money .stp')].map(g => [g.dataset.p, g.querySelectorAll('details, li, .trend').length]))")
            assert set(counts) == {"budget", "contracts", "beds", "infl"} and all(n > 0 for n in counts.values()), (lang, counts)
            assert pg.evaluate("document.querySelector('#v-money .mgd[data-g=gaps]').querySelectorAll('li, details').length") > 0
            assert pg.evaluate("[...document.querySelectorAll('#v-money .stp')].filter(x => !x.hidden).length") == 1        # one sub-tab at a time
            moved = pg.evaluate("[...document.querySelectorAll('#mtp-budget .trend, #mtp-infl .trend')].length")
            assert moved >= 3, f"{lang}: the money charts from Trends did not arrive ({moved})"
            fallback = pg.evaluate("[...document.querySelectorAll('#mw-body,#mf-src,#mf-after,#mf-more')].reduce((a, e) => a + e.children.length, 0)")
            assert fallback == 0, f"{lang}: {fallback} sections went to the hidden fallback"
            pg.evaluate(f"setLang('{'en' if lang == 'es' else 'es'}')"); pg.wait_for_timeout(300)        # a second render must not double the sections
            again = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#v-money .stp')].map(g => [g.dataset.p, g.querySelectorAll('details, li, .trend').length]))")
            assert again == counts, (lang, counts, again)
            assert not errs, errs; b.close()


def test_network_draws_every_dollar_once_and_a_tap_lists_who_pays():
    sp = _browser()
    if not sp or not PAGE.exists(): return
    with sp() as p:
        b, pg, errs = _money_page(p, "en")
        d = pg.evaluate("""(() => { const {payers, ents} = netData();
            const tp = payers.reduce((a, p) => a + p.m, 0), te = ents.reduce((a, e) => a + e.m, 0);
            const byOk = ents.every(e => Math.abs([...e.by.values()].reduce((a, v) => a + v, 0) - e.m) < 1e-6 * Math.max(1, e.m));
            return {np: payers.length, ne: ents.length, tp, te, byOk, rest: ents.filter(e => e.rest).length}; })()""")
        assert d["np"] >= 2 and 2 <= d["ne"] <= 19 and d["rest"] <= 1, d
        assert d["byOk"], "a company's links do not add to its total"
        assert abs(d["tp"] - d["te"]) < 0.001 * d["tp"], f"payers send {d['tp']}, companies receive {d['te']}"
        pg.evaluate("stShow('money', 'contracts'); document.querySelector('#mf-net-host details').open = true"); pg.wait_for_timeout(300)
        n = pg.evaluate("document.querySelectorAll('#mf-net-host path.nrib').length")
        assert n >= d["ne"] - 1, n
        pg.evaluate("document.querySelectorAll('#mf-net-host g.mfk')[" + str(d["np"]) + "].dispatchEvent(new MouseEvent('click', {bubbles:true}))"); pg.wait_for_timeout(200)
        info = pg.evaluate("document.querySelector('#mf-net-host .note').textContent")
        assert "$" in info and pg.evaluate("document.querySelectorAll('#mf-net-host path.nrib.dim').length") > 0, info[:200]
        assert not errs, errs; b.close()
