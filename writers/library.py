from __future__ import annotations

import json
import shutil
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlparse

from config import Settings
from models import FailureRecord, MediaTask, MovieMetadata
from .nfo import write_nfo


INVALID_FS_CHARS = '<>:"/\\|?*'


def sanitize_filename(value: str) -> str:
    cleaned = "".join("_" if ch in INVALID_FS_CHARS else ch for ch in value)
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned.strip(". ") or "untitled"


def _guess_extension(url: str, fallback: str = ".jpg") -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix or fallback


class LibraryWriter:
    def __init__(self, settings: Settings, http_client):
        self.settings = settings
        self.http_client = http_client

    def write_success(self, task: MediaTask, metadata: MovieMetadata) -> Path:
        folder_name = sanitize_filename(f"{metadata.code} {metadata.title}".strip())
        target_dir = self.settings.output_dir / folder_name
        target_dir_existed = target_dir.exists()
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            if self.settings.write_nfo:
                write_nfo(target_dir / self.settings.nfo_filename, metadata)
            if self.settings.write_metadata_json:
                (target_dir / "metadata.json").write_text(
                    json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if self.settings.download_images:
                self._download_artwork(target_dir, metadata)
            if self.settings.download_trailer and metadata.artwork.trailer_url:
                self.http_client.download(metadata.artwork.trailer_url, target_dir / "trailer.mp4")

            self._place_media(task, target_dir)
            return target_dir
        except Exception:
            if not target_dir_existed and target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise

    def _place_media(self, task: MediaTask, target_dir: Path) -> Path:
        target_path = target_dir / task.source_path.name
        if self.settings.media_action == "move":
            shutil.move(str(task.source_path), str(target_path))
        else:
            shutil.copy2(task.source_path, target_path)
        return target_path

    def _download_artwork(self, target_dir: Path, metadata: MovieMetadata) -> None:
        artwork = metadata.artwork
        if artwork.thumb_url:
            self.http_client.download(artwork.thumb_url, target_dir / f"thumb{_guess_extension(artwork.thumb_url)}")
        if artwork.poster_url:
            self.http_client.download(artwork.poster_url, target_dir / f"poster{_guess_extension(artwork.poster_url)}")
        if artwork.fanart_url:
            self.http_client.download(artwork.fanart_url, target_dir / f"fanart{_guess_extension(artwork.fanart_url)}")
        if artwork.extrafanart_urls:
            extrafanart_dir = target_dir / self.settings.extrafanart_dirname
            extrafanart_dir.mkdir(parents=True, exist_ok=True)
            for index, url in enumerate(artwork.extrafanart_urls, start=1):
                self.http_client.download(url, extrafanart_dir / f"{index:02d}{_guess_extension(url)}")


class FailureWriter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def write_failure(self, task: MediaTask, reason: str) -> Path:
        unique_suffix = sha1(task.relative_path.as_posix().encode("utf-8")).hexdigest()[:8]
        folder_name = sanitize_filename(f"{task.stem or task.source_path.stem}_{unique_suffix}")
        target_dir = self.settings.failed_dir / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        record = FailureRecord(source_path=str(task.source_path), code=task.code, reason=reason)
        (target_dir / "failure.json").write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if self.settings.copy_failed_media:
            shutil.copy2(task.source_path, target_dir / task.source_path.name)

        return target_dir
