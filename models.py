from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class MediaTask:
    source_path: Path
    relative_path: Path
    stem: str
    extension: str
    code: str | None


@dataclass(slots=True)
class Artwork:
    thumb_url: str = ""
    poster_url: str = ""
    fanart_url: str = ""
    extrafanart_urls: list[str] = field(default_factory=list)
    trailer_url: str = ""


@dataclass(slots=True)
class MovieMetadata:
    code: str
    source_name: str = ""
    detail_url: str = ""
    title: str = ""
    original_title: str = ""
    plot: str = ""
    release_date: str = ""
    year: str = ""
    runtime_minutes: str = ""
    studio: str = ""
    publisher: str = ""
    series: str = ""
    actors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    artwork: Artwork = field(default_factory=Artwork)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class FailureRecord:
    source_path: str
    code: str | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TaskResult:
    source_path: str
    relative_path: str
    code: str | None
    status: str
    reason: str = ""
    source_name: str = ""
    detail_url: str = ""
    output_dir: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class RunSummary:
    source_dir: str
    output_dir: str
    failed_dir: str
    started_at: str
    finished_at: str = ""
    total: int = 0
    success: int = 0
    failure: int = 0
    skipped: int = 0
    items: list[TaskResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        return data
