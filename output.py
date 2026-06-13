"""Output folder creation, image download, and media file placement."""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse
import logging

import providers
from models import Movie
from nfo import write_nfo

logger = logging.getLogger("scrape")

INVALID_FS_CHARS = '<>:"/\\|?*'


def can_create_symlinks() -> bool:
    """Test whether the current process can create symlinks.

    True on non-Windows. On Windows, requires admin or Developer Mode.
    Used for a one-time check at startup (see scrape._ensure_symlink_privilege).
    """
    if sys.platform != "win32":
        return True
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            link = Path(tmpdir) / "test_link"
            target = Path(tmpdir) / "test_target"
            target.touch()
            link.symlink_to(target)
            link.unlink()
            return True
    except (OSError, PermissionError):
        return False


def sanitize_filename(value: str) -> str:
    cleaned = "".join("_" if ch in INVALID_FS_CHARS else ch for ch in value)
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned.strip(". ") or "untitled"


def _is_within(path: Path, parent: Path) -> bool:
    """Return True if `path` is inside `parent`, via string comparison.

    Uses normcase/normpath instead of resolve() so it works on volumes Windows
    can't resolve (e.g. WinError 1005).
    """
    try:
        path_s = os.path.normcase(os.path.normpath(str(path)))
        parent_s = os.path.normcase(os.path.normpath(str(parent)))
        return path_s == parent_s or path_s.startswith(parent_s + os.sep)
    except Exception:
        return False


def _symlink_or_copy(target: Path, source: Path) -> None:
    """Create symlink target -> source, falling back to copy on failure.

    Links the raw source path (never resolve()) so it works on volumes Windows
    can't resolve. Symlink privilege is verified once at startup (see
    scrape._ensure_symlink_privilege), so a failure here just falls back to copy.
    """
    try:
        target.symlink_to(source)
    except OSError as e:
        logger.warning("Symlink creation failed, using copy: %s", e)
        shutil.copy2(source, target)


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
        action = config.get("media_action", "symlink")
        if action == "move":
            shutil.move(str(source_path), str(target_media))
        elif action == "symlink":
            # Create symlink to source file.
            # IMPORTANT: link to the RAW source path, never resolve() it.
            # A symlink only stores the target path string and never reads the
            # source volume, so this works on volumes Windows can't resolve
            # (e.g. W: drives raising WinError 1005 on resolve()). Mirrors the
            # proven approach in the Media-handling tools (os.symlink raw path).
            if target_media.exists() or target_media.is_symlink():
                target_media.unlink()

            if _is_within(source_path, output_dir):
                logger.warning("Source file is within output directory, using copy instead of symlink")
                shutil.copy2(source_path, target_media)
            else:
                _symlink_or_copy(target_media, source_path)
        else:  # copy
            shutil.copy2(source_path, target_media)

        return target_dir
    except Exception:
        # Clean up partially created directory on failure
        if not existed and target_dir.exists():
            try:
                shutil.rmtree(target_dir)
            except OSError as cleanup_error:
                logger.error("Failed to clean up partial directory: %s", cleanup_error)
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
