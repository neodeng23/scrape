from __future__ import annotations

import os
from pathlib import Path

from path_utils import normalize_path_key, safe_display_path


HEADER = (
    "# One absolute source media path per line.\n"
    "# Delete a line to force that file to be scraped again.\n"
    "# Lines starting with # are treated as comments.\n"
)


class SuccessRecordStore:
    def __init__(self, path: Path):
        self.path = path
        self._records: set[str] | None = None

    def contains(self, media_path: Path) -> bool:
        return self._normalize(media_path) in self._load()

    def mark_success(self, media_path: Path) -> bool:
        normalized = self._normalize(media_path)
        records = self._load()
        if normalized in records:
            return False

        display_path = self._display_path(media_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(HEADER, encoding="utf-8", newline="\n")

        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            if self.path.stat().st_size > 0 and not self._ends_with_newline():
                handle.write("\n")
            handle.write(f"{display_path}\n")

        records.add(normalized)
        return True

    def _load(self) -> set[str]:
        if self._records is not None:
            return self._records

        records: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                value = line.strip()
                if not value or value.startswith("#"):
                    continue
                records.add(self._normalize(Path(value)))
        self._records = records
        return records

    def _display_path(self, media_path: Path) -> str:
        return safe_display_path(media_path)

    def _normalize(self, media_path: Path) -> str:
        return normalize_path_key(media_path)

    def _ends_with_newline(self) -> bool:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return False
        with self.path.open("rb") as handle:
            handle.seek(-1, os.SEEK_END)
            return handle.read(1) in {b"\n", b"\r"}
