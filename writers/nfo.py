from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from models import MovieMetadata


def _add_text(parent: ET.Element, tag: str, value: str) -> None:
    if value:
        ET.SubElement(parent, tag).text = value


def write_nfo(destination: Path, metadata: MovieMetadata) -> None:
    movie = ET.Element("movie")
    _add_text(movie, "title", metadata.title)
    _add_text(movie, "originaltitle", metadata.original_title)
    _add_text(movie, "sorttitle", metadata.code)
    _add_text(movie, "plot", metadata.plot)
    _add_text(movie, "outline", metadata.plot)
    _add_text(movie, "id", metadata.code)
    _add_text(movie, "premiered", metadata.release_date)
    _add_text(movie, "year", metadata.year)
    _add_text(movie, "runtime", metadata.runtime_minutes)
    _add_text(movie, "studio", metadata.studio)
    _add_text(movie, "set", metadata.series)
    _add_text(movie, "source", metadata.source_name)
    _add_text(movie, "website", metadata.detail_url)

    for tag in metadata.tags:
        _add_text(movie, "tag", tag)
        _add_text(movie, "genre", tag)

    for actor_name in metadata.actors:
        actor = ET.SubElement(movie, "actor")
        _add_text(actor, "name", actor_name)

    tree = ET.ElementTree(movie)
    ET.indent(tree, space="  ")
    tree.write(destination, encoding="utf-8", xml_declaration=True)
