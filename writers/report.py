from __future__ import annotations

import json
from pathlib import Path

from models import RunSummary


def write_run_summary(path: Path, summary: RunSummary) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
