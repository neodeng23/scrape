"""JavBus metadata scraper.

NOTE: JavBus requires passing an age verification quiz in the browser.
After passing it, export your cookies and paste them in sites.yaml
under the 'cookies' field for javbus.
"""
from __future__ import annotations

import logging
import re
import sys
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag

import providers
from models import Movie

logger = logging.getLogger("scrape")


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.replace("\xa0", " ").split()).strip()


# ---------------------------------------------------------------------------
# Cookie injection
# ---------------------------------------------------------------------------

_cookies_injected = False


def _inject_cookies(session, site: dict) -> None:
    """Inject browser cookies from sites.yaml into the session."""
    global _cookies_injected
    if _cookies_injected:
        return
    cookie_str = site.get("cookies", "")
    if not cookie_str:
        logger.warning(
            "JavBus requires age verification cookies. "
            "Export cookies from your browser and set them in sites.yaml."
        )
        _cookies_injected = True  # don't spam the warning
        return
    base_url = site.get("base_url", "https://www.javbus.com")
    domain = base_url.replace("https://", "").replace("http://", "").split("/")[0]
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            session.cookies.set(name.strip(), value.strip(), domain=domain)
    logger.info("Injected %d cookies for JavBus", len(session.cookies))
    _cookies_injected = True


# ---------------------------------------------------------------------------
# Public provider interface: search(code, session, config) -> Movie | None
# ---------------------------------------------------------------------------

def search(code: str, session, config: dict) -> Movie | None:
    site = providers.get_site("javbus")
    base_url = site.get("base_url", "https://www.javbus.com")

    _inject_cookies(session, site)

    # Try direct URL first (JavBus supports /CODE)
    direct_tpl = site.get("direct_url", "/{code}")
    detail_url = base_url + direct_tpl.replace("{code}", quote(code.upper()))
    try:
        html = providers.fetch(session, detail_url, config)
        if "driver-verify" not in html and "找不到" not in html:
            return _parse_detail(code, html, detail_url)
        if "driver-verify" in html:
            logger.warning(
                "JavBus returned age verification page. "
                "Set your browser cookies in sites.yaml."
            )
    except Exception as e:
        logger.debug("JavBus direct URL failed for %s: %s", code, e)

    # Fallback to search
    search_tpl = site.get("search_url", "/search/{code}?type=1")
    search_url = base_url + search_tpl.replace("{code}", quote(code))
    url = _find_by_search(code, search_url, session, config)
    if not url:
        return None
    html = providers.fetch(session, url, config)
    if "driver-verify" in html:
        logger.warning("JavBus age verification required. Set cookies in sites.yaml.")
        return None
    return _parse_detail(code, html, url)


# ---------------------------------------------------------------------------
# Internal: search page
# ---------------------------------------------------------------------------

def _find_by_search(code: str, search_url: str, session, config: dict) -> str | None:
    html = providers.fetch(session, search_url, config)
    if "driver-verify" in html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # Find exact match
    for a in soup.select("a.movie-box"):
        href = a.get("href", "").strip()
        img = a.select_one("img")
        title = img.get("title", "") or img.get("alt", "") if img else ""
        if href and code.upper() in title.upper():
            return href

    # Single result → use it
    results = soup.select("a.movie-box[href]")
    if len(results) == 1:
        return results[0].get("href", "").strip()

    return None


# ---------------------------------------------------------------------------
# Internal: parse detail page -> Movie
# ---------------------------------------------------------------------------

def _parse_detail(code: str, html: str, detail_url: str) -> Movie:
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_node = soup.select_one("h3")
    title = _clean(title_node.get_text()) if title_node else code
    originaltitle = title  # JavBus title is the original Japanese

    # Cover image
    big_img = soup.select_one("a.bigImage")
    cover_url = ""
    thumb_url = ""
    if big_img:
        cover_url = big_img.get("href", "").strip()
        img = big_img.find("img")
        if isinstance(img, Tag):
            thumb_url = img.get("src", "").strip()

    # Sample images (extrafanart)
    extrafanart_urls: list[str] = []
    for a in soup.select("#sample-waterfall a.sample-box"):
        href = a.get("href", "").strip()
        if href:
            extrafanart_urls.append(href)

    # Info fields (JavBus uses traditional + simplified Chinese labels)
    release_date = (
        _info_field(soup, "發行日期") or _info_field(soup, "发行日期")
    )
    runtime = _digits_only(
        _info_field(soup, "長度") or _info_field(soup, "长度")
    )
    studio = (
        _info_field(soup, "製作商") or _info_field(soup, "制作商")
    )
    series = _info_field(soup, "系列")
    director = (
        _info_field(soup, "導演") or _info_field(soup, "导演")
    )

    # Genres
    genres: list[str] = []
    for p in soup.select(".info p"):
        header = p.select_one("span.header")
        if header and ("類別" in header.get_text() or "类别" in header.get_text()):
            for a in p.select("a[href]"):
                g = _clean(a.get_text())
                if g:
                    genres.append(g)
    if not genres:
        for a in soup.select("span.genre a, li.genre a"):
            g = _clean(a.get_text())
            if g:
                genres.append(g)
    genres = list(dict.fromkeys(genres))

    # Actors — avatar section is the standard actor list on JavBus
    actors: list[str] = []
    for a in soup.select("a.avatar-box"):
        img = a.find("img")
        if isinstance(img, Tag):
            name = _clean(img.get("title", "") or img.get("alt", ""))
        else:
            name = _clean(a.get_text())
        if name:
            actors.append(name)
    actors = list(dict.fromkeys(actors))

    return Movie(
        code=code.upper(),
        title=title,
        originaltitle=originaltitle,
        released=release_date,
        year=release_date[:4] if len(release_date) >= 4 else "",
        runtime=runtime,
        studio=studio,
        director=director,
        series=series,
        actors=actors,
        genres=genres,
        poster_url=cover_url,
        fanart_url=cover_url,
        thumb_url=thumb_url,
        extrafanart_urls=extrafanart_urls,
        detail_url=detail_url,
    )


# ---------------------------------------------------------------------------
# Internal: HTML parsing helpers
# ---------------------------------------------------------------------------

def _info_field(soup, label: str) -> str:
    """Extract a field value from the info section by its label."""
    for p in soup.select(".info p"):
        header = p.select_one("span.header")
        if not header or label not in header.get_text():
            continue
        # Prefer link values (e.g. studio with URL)
        links = p.find_all("a")
        if links:
            return _clean(links[0].get_text())
        # Extract text after header
        full = _clean(p.get_text())
        hdr = _clean(header.get_text())
        value = full.replace(hdr, "", 1).strip(": ").strip()
        return value
    return ""


def _digits_only(value: str) -> str:
    m = re.search(r"\d+", value)
    return m.group(0) if m else ""


# Self-register
providers.register("javbus", sys.modules[__name__])
