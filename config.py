"""Load configuration from config.yaml with sensible defaults."""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULTS = {
    "provider_order": ["javdb", "javbus"],
    "timeout": 20,
    "retries": 2,
    "delay": 0.5,
    "proxy_url": None,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "media_action": "symlink",  # symlink, copy, or move
    "download_images": True,
    "download_trailer": False,
    "write_metadata_json": True,
    "skip_processed": True,
    "max_items": None,
    "stop_on_error": False,
    "media_extensions": [
        ".mp4", ".mkv", ".avi", ".mov",
        ".wmv", ".flv", ".ts", ".m4v", ".iso",
    ],
}

REQUIRED_KEYS = ("source_dir", "output_dir")
OPTIONAL_PATH_KEYS = ("final_dir",)


def load_config(path: str | Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).with_name("config.yaml")
    path = Path(path)
    cfg = dict(DEFAULTS)
    if path.exists():
        try:
            # Use utf-8-sig to handle BOM if present (Windows Notepad issue)
            with open(path, encoding="utf-8-sig") as f:
                user = yaml.safe_load(f) or {}
            cfg.update(user)
        except (yaml.YAMLError, OSError) as e:
            raise SystemExit(f"Failed to load config.yaml: {e}")

    for key in REQUIRED_KEYS:
        if key not in cfg or not cfg[key]:
            raise SystemExit(f"config.yaml missing required field: {key}")

    cfg["source_dir"] = Path(cfg["source_dir"]).absolute()
    cfg["output_dir"] = Path(cfg["output_dir"]).absolute()
    if cfg.get("final_dir"):
        cfg["final_dir"] = Path(cfg["final_dir"]).absolute()
    return cfg
