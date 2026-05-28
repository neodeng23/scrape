from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

from models import Artwork, MovieMetadata
from site_config import SiteDefinition
from .base import ScrapeSource


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(v for v in (_clean_text(item) for item in values) if v))


class JavDbSource(ScrapeSource):
    name = "javdb"

    def __init__(self, *, http_client, site_definitions: dict[str, SiteDefinition | object]):
        self.http_client = http_client
        definition = site_definitions.get("javdb")
        if isinstance(definition, SiteDefinition) and definition.base_url:
            self.base_url = definition.base_url.rstrip("/")
        else:
            self.base_url = "https://javdb.com"

    def scrape(self, code: str) -> MovieMetadata | None:
        detail_url = self._search_detail_url(code)
        if not detail_url:
            return None
        return self._fetch_detail(code, detail_url)

    def _search_detail_url(self, code: str) -> str | None:
        search_url = f"{self.base_url}/search?q={quote_plus(code)}&locale=en"
        html = self.http_client.get_text(search_url)
        if "ray-id" in html or "Due to copyright restrictions" in html:
            raise RuntimeError("JavDB blocked the current request.")

        soup = BeautifulSoup(html, "html.parser")
        matches: list[tuple[str, str, str]] = []
        for box in soup.select("a.box[href]"):
            href = box.get("href", "").strip()
            title_node = box.select_one("div.video-title")
            meta_node = box.select_one("div.meta")
            title = _clean_text(title_node.get_text(" ")) if title_node else ""
            meta = _clean_text(meta_node.get_text(" ")) if meta_node else ""
            if href:
                matches.append((href, title, meta))

        if not matches:
            return None

        normalized_target = re.sub(r"[-_. ]", "", code).upper()
        for href, title, _meta in matches:
            if code.upper() in title.upper():
                return self._detail_url(href)
        for href, title, meta in matches:
            normalized = re.sub(r"[-_. ]", "", f"{title} {meta}").upper()
            if normalized_target in normalized:
                return self._detail_url(href)
        return None

    def _fetch_detail(self, code: str, detail_url: str) -> MovieMetadata:
        html = self.http_client.get_text(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        title = _clean_text(self._select_text(soup, "h2.title.is-4 strong.current-title"))
        original_title = _clean_text(self._select_text(soup, "h2.title.is-4 span.origin-title"))
        plot = _clean_text(self._meta_content(soup, "og:description"))
        if plot.startswith(title):
            plot = ""

        thumb_url = self._select_attr(soup, "img.video-cover", "src")
        poster_url = thumb_url.replace("/covers/", "/thumbs/") if thumb_url else ""
        extrafanart_urls = _unique(a.get("href", "") for a in soup.select("div.tile-images.preview-images a.tile-item[href]"))
        trailer_url = self._select_attr(soup, "video#preview-video source", "src")
        if trailer_url.startswith("//"):
            trailer_url = f"https:{trailer_url}"

        metadata = MovieMetadata(
            code=self._extract_number(soup) or code,
            source_name=self.name,
            detail_url=detail_url,
            title=title or code,
            original_title=original_title or title or code,
            plot=plot,
            release_date=self._field_value(soup, "Released Date:"),
            runtime_minutes=self._digits_only(self._field_value(soup, "Duration:")),
            studio=self._field_value(soup, "Maker:"),
            publisher=self._field_value(soup, "Publisher:"),
            series=self._field_value(soup, "Series:"),
            actors=self._extract_people(soup),
            tags=_unique(self._field_values(soup, "Tags:")),
            artwork=Artwork(
                thumb_url=thumb_url,
                poster_url=poster_url,
                fanart_url=thumb_url,
                extrafanart_urls=extrafanart_urls,
                trailer_url=trailer_url,
            ),
        )
        metadata.year = metadata.release_date[:4] if len(metadata.release_date) >= 4 else ""
        return metadata

    def _select_text(self, soup: BeautifulSoup, selector: str) -> str:
        node = soup.select_one(selector)
        return node.get_text(" ", strip=True) if node else ""

    def _select_attr(self, soup: BeautifulSoup, selector: str, attr: str) -> str:
        node = soup.select_one(selector)
        if not node:
            return ""
        return _clean_text(node.get(attr, ""))

    def _meta_content(self, soup: BeautifulSoup, property_name: str) -> str:
        node = soup.find("meta", attrs={"property": property_name})
        if not isinstance(node, Tag):
            return ""
        return _clean_text(node.get("content", ""))

    def _detail_url(self, href: str) -> str:
        absolute_url = urljoin(self.base_url, href)
        if "locale=" in absolute_url:
            return absolute_url
        separator = "&" if "?" in absolute_url else "?"
        return f"{absolute_url}{separator}locale=en"

    def _extract_number(self, soup: BeautifulSoup) -> str:
        node = soup.select_one("a.button.is-white.copy-to-clipboard")
        if not node:
            return ""
        return _clean_text(node.get("data-clipboard-text", ""))

    def _extract_people(self, soup: BeautifulSoup) -> list[str]:
        selectors = (
            "span:has(strong.female) a",
            "span:has(strong.male) a",
        )
        people: list[str] = []
        for selector in selectors:
            people.extend(node.get_text(" ", strip=True) for node in soup.select(selector))
        return _unique(people)

    def _field_values(self, soup: BeautifulSoup, *labels: str) -> list[str]:
        normalized_labels = tuple(_clean_text(label) for label in labels)
        for strong in soup.find_all("strong"):
            label = _clean_text(strong.get_text(" ", strip=True))
            if not any(target in label for target in normalized_labels):
                continue
            container = strong.parent if isinstance(strong.parent, Tag) else None
            if container is None:
                continue
            linked_values = [a.get_text(" ", strip=True) for a in container.find_all("a")]
            if linked_values:
                return _unique(linked_values)
            span = container.find("span")
            if isinstance(span, Tag):
                return _unique([span.get_text(" ", strip=True)])
            text = container.get_text(" ", strip=True).replace(label, "", 1)
            cleaned = _clean_text(text)
            if cleaned:
                return [cleaned]
        return []

    def _field_value(self, soup: BeautifulSoup, *labels: str) -> str:
        values = self._field_values(soup, *labels)
        return values[0] if values else ""

    def _digits_only(self, value: str) -> str:
        match = re.search(r"\d+", value)
        return match.group(0) if match else ""
