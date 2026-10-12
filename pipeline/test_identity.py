"""The page and the collectors carry the project's identity from pipeline/identity.py, and never a personal account."""
import pathlib, re
import identity

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_page_names_match_identity_and_no_personal_account_is_left():
    tpl = (ROOT / "site" / "template.html").read_text(encoding="utf-8")
    for lang, name in identity.NAME.items(): assert f'{lang}:{{brand:"{name}"' in tpl, (lang, name)
    files = [*ROOT.glob("pipeline/*.py"), ROOT / "site" / "template.html", ROOT / "site" / "flights_template.html", *ROOT.glob(".github/workflows/*.yml")]
    hits = [f.name for f in files if f.name != "test_identity.py" and re.search(r"psdon|icebreaker|rompehielos", f.read_text(encoding="utf-8"), re.I)]
    assert not hits, f"personal handle or old name in {hits}"


def test_raw_data_line_follows_the_repository_setting():
    import build_site
    tpl = (ROOT / "site" / "template.html").read_text(encoding="utf-8")
    old = identity.REPO_URL
    try:
        identity.REPO_URL = ""; assert "raw-line" not in build_site.page_identity(tpl)
        identity.REPO_URL = "https://github.com/example/polar-star"; out = build_site.page_identity(tpl)
        assert "https://github.com/example/polar-star/tree/main/data/reference" in out and "{{REPO_DATA}}" not in out
    finally: identity.REPO_URL = old
