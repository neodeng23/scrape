"""Generate Emby/Jellyfin/Kodi-compatible NFO XML."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from models import Movie


def _add(parent: ET.Element, tag: str, value: str) -> None:
    if value:
        ET.SubElement(parent, tag).text = value


def write_nfo(path: Path, movie: Movie) -> None:
    root = ET.Element("movie")

    # Identity
    _add(root, "title", movie.title)
    _add(root, "originaltitle", movie.originaltitle)
    _add(root, "sorttitle", movie.code)

    uid = ET.SubElement(root, "uniqueid", type="num", default="true")
    uid.text = movie.code

    # Description
    _add(root, "plot", movie.plot)
    _add(root, "outline", movie.plot)

    # Dates & runtime
    _add(root, "premiered", movie.released)
    _add(root, "year", movie.year)
    _add(root, "runtime", movie.runtime)

    # Classification
    _add(root, "mpaa", "NC-17")
    _add(root, "studio", movie.studio)
    _add(root, "director", movie.director)

    # Series → <set>
    if movie.series:
        set_el = ET.SubElement(root, "set")
        _add(set_el, "name", movie.series)

    # Genres and tags
    for g in movie.genres:
        _add(root, "genre", g)
    for t in movie.tags:
        _add(root, "tag", t)

    # Actors
    for name in movie.actors:
        actor = ET.SubElement(root, "actor")
        _add(actor, "name", name)

    # Artwork URLs (Emby reads these for online image detection)
    if movie.poster_url:
        ET.SubElement(root, "thumb", aspect="poster").text = movie.poster_url

    if movie.fanart_url or movie.extrafanart_urls:
        fanart = ET.SubElement(root, "fanart")
        if movie.fanart_url:
            ET.SubElement(fanart, "thumb").text = movie.fanart_url
        for url in movie.extrafanart_urls:
            ET.SubElement(fanart, "thumb").text = url

    # Trailer
    if movie.trailer_url:
        _add(root, "trailer", movie.trailer_url)

    # Source URL (non-standard but harmless)
    _add(root, "website", movie.detail_url)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
