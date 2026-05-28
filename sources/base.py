from __future__ import annotations

from abc import ABC, abstractmethod

from models import MovieMetadata


class ScrapeSource(ABC):
    name: str

    @abstractmethod
    def scrape(self, code: str) -> MovieMetadata | None:
        raise NotImplementedError
