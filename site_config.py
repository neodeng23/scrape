from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SiteDefinition:
    website: str
    domains: tuple[str, ...]
    default_base_urls: tuple[str, ...]
    dynamic_search_templates: tuple[str, ...]

    @property
    def base_url(self) -> str:
        for url in self.default_base_urls:
            if url:
                return url
        for url in self.domains:
            if url:
                return url
        return ""


def load_site_definitions(path: Path) -> dict[str, SiteDefinition]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    definitions: dict[str, SiteDefinition] = {}
    for item in raw.get("crawler_sites", []):
        dynamic_templates = item.get("dynamic_templates", {})
        search_templates = tuple(dynamic_templates.get("search", []))
        definition = SiteDefinition(
            website=item["website"],
            domains=tuple(item.get("domains", [])),
            default_base_urls=tuple(item.get("default_base_urls", [])),
            dynamic_search_templates=search_templates,
        )
        definitions[definition.website] = definition
    return definitions
