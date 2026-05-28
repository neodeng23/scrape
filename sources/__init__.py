from .base import ScrapeSource
from .javdb import JavDbSource


def build_sources(enabled_sources: tuple[str, ...], site_definitions: dict[str, object], http_client) -> list[ScrapeSource]:
    sources: list[ScrapeSource] = []
    for name in enabled_sources:
        if name == "javdb":
            sources.append(JavDbSource(http_client=http_client, site_definitions=site_definitions))
    return sources


__all__ = ["ScrapeSource", "JavDbSource", "build_sources"]
