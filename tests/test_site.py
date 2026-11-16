"""The Pages site must stay self-contained, and every link must resolve.

`site/` is deployed by copying it into `_site/` and adding the generated dbt
docs. The one local path the workflow creates is `dbt-docs/`; everything else
must exist in git, so a broken link fails here rather than on the live site.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
CANONICAL = "https://willowvibe.github.io/plm-bom-pipeline/"
BUILD_GENERATED = "dbt-docs/"
GIF = ROOT / "docs" / "assets" / "demo.gif"
GIF_MAX_BYTES = 2 * 1024 * 1024


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def test_landing_page_has_metadata():
    html = _html()
    assert "<title>PLM / BOM Intelligence — plm-bom-pipeline</title>" in html
    assert f'<link rel="canonical" href="{CANONICAL}">' in html
    assert '<meta name="description"' in html
    assert 'name="viewport"' in html


def test_landing_page_is_self_contained():
    html = _html()
    assert "<script src=" not in html
    assert '<link rel="stylesheet"' not in html
    assert "@import" not in html
    assert "<iframe" not in html
    # The canonical URL is the only absolute <link>; everything else is inline.
    external_links = re.findall(r"""<link[^>]+href="https?://[^"]+""", html)
    assert external_links == [f'<link rel="canonical" href="{CANONICAL}'], external_links


def test_autoplay_contract():
    video = re.search(r"<video[^>]*>", _html())
    assert video, "landing page has no video element"
    attrs = video.group(0)
    for attribute in ("controls", "muted", "autoplay", "playsinline"):
        assert attribute in attrs
    assert 'preload="auto"' in attrs
    assert 'id="unmute-demo"' in _html()


def test_video_and_poster_exist():
    html = _html()
    assert '<source src="plm-bom-pipeline-demo.mp4" type="video/mp4">' in html
    assert 'poster="plm-bom-pipeline-demo-poster.jpg"' in html
    for asset in ("plm-bom-pipeline-demo.mp4", "plm-bom-pipeline-demo-poster.jpg"):
        path = SITE / asset
        assert path.is_file(), f"missing {path}"


def test_local_links_resolve():
    html = _html()
    hrefs = re.findall(r'href="([^"]+)"', html)
    assert hrefs
    checked = set()
    for href in hrefs:
        parsed = urlparse(href)
        if parsed.scheme or href.startswith("#"):
            continue
        if href == BUILD_GENERATED:
            continue  # copied in by .github/workflows/pages.yml
        target = SITE / parsed.path
        if parsed.path.endswith("/"):
            target = target / "index.html"
        assert target.is_file(), f"{href} does not resolve to {target}"
        checked.add(href)
    assert "report/" in checked
    assert "plm-bom-pipeline-demo.mp4" in checked


def test_workflow_builds_the_generated_links():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "cp -R site/. _site/" in workflow
    assert "_site/dbt-docs/index.html" in workflow
    assert "_site/plm-bom-pipeline-demo.mp4" in workflow


def test_readme_gif_exists_and_links_to_the_demo():
    assert GIF.is_file(), f"missing {GIF}"
    assert GIF.stat().st_size < GIF_MAX_BYTES, (
        f"{GIF.name} is {GIF.stat().st_size} bytes; keep it under 2 MB"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/assets/demo.gif" in readme
    assert f"]({CANONICAL}#demo)" in readme
