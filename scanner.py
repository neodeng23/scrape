from __future__ import annotations

from pathlib import Path

from config import Settings
from models import MediaTask
from parsers import extract_media_code
from path_utils import normalize_path_key


def _should_skip(path: Path, ignored_dirs: tuple[Path, ...]) -> bool:
    normalized_path = normalize_path_key(path)
    for ignored in ignored_dirs:
        normalized_ignored = normalize_path_key(ignored)
        if normalized_path == normalized_ignored or normalized_path.startswith(f"{normalized_ignored}\\"):
            return True
    return False


def scan_media_files(settings: Settings) -> list[MediaTask]:
    ignored_dirs = tuple({settings.output_dir, settings.failed_dir})
    tasks: list[MediaTask] = []

    for path in settings.source_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in settings.media_extensions:
            continue
        if _should_skip(path, ignored_dirs):
            continue
        tasks.append(
            MediaTask(
                source_path=path,
                relative_path=path.relative_to(settings.source_dir),
                stem=path.stem,
                extension=path.suffix.lower(),
                code=extract_media_code(path.name),
            )
        )

    tasks.sort(key=lambda item: item.relative_path.as_posix().lower())
    if settings.max_items is not None:
        return tasks[: settings.max_items]
    return tasks
