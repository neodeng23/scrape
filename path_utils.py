from __future__ import annotations

import os
from pathlib import Path


def safe_absolute_path(path: Path | str) -> Path:
    expanded = Path(path).expanduser()
    return Path(os.path.abspath(str(expanded)))


def safe_display_path(path: Path | str) -> str:
    return str(safe_absolute_path(path))


def normalize_path_key(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(safe_display_path(path)))
