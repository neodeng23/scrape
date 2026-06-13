"""JavDB metadata scraper."""
from __future__ import annotations

import re
import sys
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

import providers
from models import Movie


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _unique(values) -> list[str]:
    return list(dict.fromkeys(v for v in (_clean(item) for item in values) if v))


# ---------------------------------------------------------------------------
# Public provider interface: search(code, session, config) -> Movie | None
# ---------------------------------------------------------------------------

def search(code: str, session, config: dict) -> Movie | None:
    site = providers.get_site("javdb")
    base_url = site.get("base_url", "https://javdb.com")
    locale = site.get("locale", "en")

    detail_url = _find_detail_url(code, session, config, base_url, locale)
    if not detail_url:
        return None
    return _parse_detail(code, detail_url, session, config)


# ---------------------------------------------------------------------------
# Internal: search -> find detail URL
# ---------------------------------------------------------------------------

def _find_detail_url(code: str, session, config: dict, base_url: str, locale: str) -> str | None:
    site = providers.get_site("javdb")
    tpl = site.get("search_url", "/search?q={code}&locale=en")
    search_url = base_url + tpl.replace("{code}", quote_plus(code)).replace("{locale}", locale)

    html = providers.fetch(session, search_url, config)

    if "ray-id" in html or "Due to copyright restrictions" in html:
        raise RuntimeError("JavDB blocked the request")

    soup = BeautifulSoup(html, "html.parser")
    matches: list[tuple[str, str, str]] = []
    for box in soup.select("a.box[href]"):
        href = box.get("href", "").strip()
        title_node = box.select_one("div.video-title")
        meta_node = box.select_one("div.meta")
        title = _clean(title_node.get_text(" ")) if title_node else ""
        meta = _clean(meta_node.get_text(" ")) if meta_node else ""
        if href:
            matches.append((href, title, meta))

    if not matches:
        return None

    normalized_target = re.sub(r"[-_. ]", "", code).upper()

    # Pass 1: exact code boundary match in title
    code_pattern = re.compile(
        r"(?<![A-Z0-9])" + re.escape(code.upper()) + r"(?![A-Z0-9])"
    )
    for href, title, _ in matches:
        if code_pattern.search(title.upper()):
            return _detail_url(href, base_url, locale)

    # Pass 2: normalized boundary match in title + meta
    target_boundary = r"(?<![A-Z0-9])" + re.escape(normalized_target) + r"(?![A-Z0-9])"
    for href, title, meta in matches:
        normalized = re.sub(r"[-_. ]", "", f"{title} {meta}").upper()
        if re.search(target_boundary, normalized):
            return _detail_url(href, base_url, locale)

    return None


def _detail_url(href: str, base_url: str, locale: str) -> str:
    url = urljoin(base_url, href)
    if "locale=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}locale={locale}"


# ---------------------------------------------------------------------------
# Internal: parse detail page -> Movie
# ---------------------------------------------------------------------------

def _parse_detail(code: str, detail_url: str, session, config: dict) -> Movie:
    html = providers.fetch(session, detail_url, config)
    soup = BeautifulSoup(html, "html.parser")

    title = _clean(_select_text(soup, "h2.title.is-4 strong.current-title"))
    original_title = _clean(_select_text(soup, "h2.title.is-4 span.origin-title"))
    plot = _clean(_meta_content(soup, "og:description"))
    if plot.startswith(title):
        plot = ""

    # Cover image: img.video-cover src is the LARGE cover
    cover_url = _select_attr(soup, "img.video-cover", "src")
    # Derive small thumbnail by replacing path segment
    thumb_url = cover_url.replace("/covers/", "/thumbs/") if cover_url else ""
    # Poster should be the large cover (shown in Emby library grid)
    poster_url = cover_url

    extrafanart_urls = _unique(
        a.get("href", "")
        for a in soup.select("div.tile-images.preview-images a.tile-item[href]")
    )
    trailer_url = _select_attr(soup, "video#preview-video source", "src")
    if trailer_url.startswith("//"):
        trailer_url = f"https:{trailer_url}"

    number = _extract_number(soup) or code
    release_date = _field_value(soup, "Released Date:")
    runtime = _digits_only(_field_value(soup, "Duration:"))

    return Movie(
        code=number,
        title=title or code,
        originaltitle=original_title or title or code,
        plot=plot,
        released=release_date,
        year=release_date[:4] if len(release_date) >= 4 else "",
        runtime=runtime,
        studio=_field_value(soup, "Maker:"),
        series=_field_value(soup, "Series:"),
        actors=_extract_people(soup),
        genres=_unique(_field_values(soup, "Tags:")),
        poster_url=poster_url,
        fanart_url=cover_url,
        thumb_url=thumb_url,
        extrafanart_urls=extrafanart_urls,
        trailer_url=trailer_url,
        detail_url=detail_url,
    )


# ---------------------------------------------------------------------------
# Internal: HTML parsing helpers
# ---------------------------------------------------------------------------

def _select_text(soup, selector: str) -> str:
    node = soup.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def _select_attr(soup, selector: str, attr: str) -> str:
    node = soup.select_one(selector)
    return _clean(node.get(attr, "")) if node else ""


def _meta_content(soup, prop: str) -> str:
    node = soup.find("meta", attrs={"property": prop})
    if not isinstance(node, Tag):
        return ""
    return _clean(node.get("content", ""))


def _extract_number(soup) -> str:
    node = soup.select_one("a.button.is-white.copy-to-clipboard")
    return _clean(node.get("data-clipboard-text", "")) if node else ""


def _extract_people(soup) -> list[str]:
    people: list[str] = []
    for sel in ("span:has(strong.female) a", "span:has(strong.male) a"):
        people.extend(node.get_text(" ", strip=True) for node in soup.select(sel))
    return _unique(people)


def _field_values(soup, *labels: str) -> list[str]:
    normalized_labels = tuple(_clean(l) for l in labels)
    for strong in soup.find_all("strong"):
        label = _clean(strong.get_text(" ", strip=True))
        if not any(t in label for t in normalized_labels):
            continue
        container = strong.parent if isinstance(strong.parent, Tag) else None
        if not container:
            continue
        linked = [a.get_text(" ", strip=True) for a in container.find_all("a")]
        if linked:
            return _unique(linked)
        span = container.find("span")
        if isinstance(span, Tag):
            return _unique([span.get_text(" ", strip=True)])
        text = container.get_text(" ", strip=True).replace(label, "", 1)
        cleaned = _clean(text)
        if cleaned:
            return [cleaned]
    return []


def _field_value(soup, *labels: str) -> str:
    vals = _field_values(soup, *labels)
    return vals[0] if vals else ""


def _digits_only(value: str) -> str:
    m = re.search(r"\d+", value)
    return m.group(0) if m else ""


def scrape_url(url: str, session, config: dict) -> Movie | None:
    """Scrape metadata directly from a JavDB detail URL (bypass search)."""
    return _parse_detail("", url, session, config)


# Self-register
providers.register("javdb", sys.modules[__name__])
