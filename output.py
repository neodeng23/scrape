"""Output folder creation, image download, and media file placement."""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

import providers
from models import Movie
from nfo import write_nfo

INVALID_FS_CHARS = '<>:"/\\|?*'


def sanitize_filename(value: str) -> str:
    cleaned = "".join("_" if ch in INVALID_FS_CHARS else ch for ch in value)
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned.strip(". ") or "untitled"


def _guess_ext(url: str, fallback: str = ".jpg") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix or fallback


def build_output(
    output_dir: Path,
    movie: Movie,
    source_path: Path,
    session,
    config: dict,
) -> Path:
    """Create output folder with NFO, images, and media file. Returns target dir."""
    folder_name = sanitize_filename(f"{movie.code} {movie.title}".strip())
    target_dir = output_dir / folder_name
    existed = target_dir.exists()
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        video_stem = source_path.stem
        write_nfo(target_dir / f"{video_stem}.nfo", movie)

        if config.get("write_metadata_json", True):
            (target_dir / "metadata.json").write_text(
                json.dumps(asdict(movie), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if config.get("download_images", True):
            _download_artwork(target_dir, movie, session)

        if config.get("download_trailer", False) and movie.trailer_url:
            providers.download(session, movie.trailer_url, target_dir / "trailer.mp4")

        # Place media file
        target_media = target_dir / source_path.name
        if config.get("media_action", "copy") == "move":
            shutil.move(str(source_path), str(target_media))
        else:
            shutil.copy2(source_path, target_media)

        return target_dir
    except Exception:
        # Clean up partially created directory on failure
        if not existed and target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise


def _download_artwork(target_dir: Path, movie: Movie, session) -> None:
    if movie.thumb_url:
        providers.download(
            session, movie.thumb_url,
            target_dir / f"thumb{_guess_ext(movie.thumb_url)}",
        )
    if movie.poster_url:
        providers.download(
            session, movie.poster_url,
            target_dir / f"poster{_guess_ext(movie.poster_url)}",
        )
    if movie.fanart_url:
        providers.download(
            session, movie.fanart_url,
            target_dir / f"fanart{_guess_ext(movie.fanart_url)}",
        )
    if movie.extrafanart_urls:
        extra_dir = target_dir / "extrafanart"
        extra_dir.mkdir(parents=True, exist_ok=True)
        for i, url in enumerate(movie.extrafanart_urls, 1):
            providers.download(session, url, extra_dir / f"fanart{i}{_guess_ext(url)}")
