from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Movie:
    code: str = ""
    title: str = ""
    originaltitle: str = ""
    plot: str = ""
    released: str = ""  # YYYY-MM-DD
    year: str = ""
    runtime: str = ""  # minutes as string
    studio: str = ""
    director: str = ""
    series: str = ""
    actors: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    poster_url: str = ""
    fanart_url: str = ""
    thumb_url: str = ""
    extrafanart_urls: list[str] = field(default_factory=list)
    trailer_url: str = ""
    source: str = ""  # which provider filled this
    detail_url: str = ""
