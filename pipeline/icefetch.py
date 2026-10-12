"""Download files from ice.gov. Plain requests first; if the site refuses, fetch from inside a real browser page.

fetch_bytes(urls) -> {url: bytes}. A url that could not be read is simply absent, so callers must check.
"""
import base64, time

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
JS = """async u => { const r = await fetch(u); if (!r.ok) return null; const b = new Uint8Array(await r.arrayBuffer());
  let s = ''; for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode.apply(null, b.subarray(i, i + 32768)); return btoa(s); }"""


def _plain(urls, pause):
    import requests
    s, out = requests.Session(), {}
    for u in urls:
        r = s.get(u, headers=UA, timeout=60)
        if r.status_code != 200: raise RuntimeError(f"{u} returned {r.status_code}")
        if r.content[:15].lstrip().lower().startswith((b"<!doctype", b"<html")) and not u.lower().endswith((".html", "/")) and "." in u.rsplit("/", 1)[-1]:
            raise RuntimeError(f"{u} returned a web page instead of the file")
        out[u] = r.content; time.sleep(pause)
    return out


def _browser(urls, origin, pause):
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False); page = b.new_page()
        page.goto(origin, wait_until="domcontentloaded")
        for u in urls:
            try:
                if u.lower().endswith((".pdf", ".xlsx", ".xls", ".csv")):
                    d = page.evaluate(JS, u)
                    if d: out[u] = base64.b64decode(d)
                else:
                    pg = b.new_page(); pg.goto(u, wait_until="domcontentloaded"); out[u] = pg.content().encode("utf-8"); pg.close()
            except Exception as e: print(f"  could not read {u}: {str(e)[:120]}")
            time.sleep(pause)
        b.close()
    return out


def fetch_bytes(urls, origin="https://www.ice.gov/", pause=0.3):
    urls = list(urls)
    if not urls: return {}
    try: return _plain(urls, pause)
    except Exception as e:
        print(f"plain download refused ({str(e)[:120]}); retrying in a browser", flush=True)
        return _browser(urls, origin, pause)
