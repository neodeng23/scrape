#!/usr/bin/env python3
"""JAV metadata scraper for Emby/Jellyfin/Kodi."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from config import load_config
from output import build_output
from parser import extract_media_code
import providers

# Import providers to trigger self-registration
import provider_javdb  # noqa: F401
import provider_javbus  # noqa: F401

logger = logging.getLogger("scrape")


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    _logger = logging.getLogger("scrape")
    _logger.setLevel(logging.INFO)
    _logger.handlers.clear()
    _logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    _logger.addHandler(sh)

    try:
        fh = logging.FileHandler(log_dir / "scrape.log", encoding="utf-8")
        fh.setFormatter(fmt)
        _logger.addHandler(fh)
    except OSError:
        pass

    return _logger


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------

def scan_files(cfg: dict) -> list[tuple[Path, str | None]]:
    src = cfg["source_dir"]
    exts = set(e.lower() for e in cfg.get("media_extensions", []))
    out = cfg["output_dir"]

    results: list[tuple[Path, str | None]] = []
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        try:
            p.relative_to(out)
            continue  # skip files inside output dir
        except ValueError:
            pass
        code = extract_media_code(p.name)
        results.append((p, code))

    results.sort(key=lambda x: x[0].name.lower())
    if cfg.get("max_items"):
        results = results[:cfg["max_items"]]
    return results


# ---------------------------------------------------------------------------
# Incremental success tracking
# ---------------------------------------------------------------------------

def _load_success(path: Path) -> set[str]:
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


# ---------------------------------------------------------------------------
# Failure recording
# ---------------------------------------------------------------------------

def _record_failure(path: Path, file: Path, code: str | None, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "path": str(file),
            "code": code,
            "reason": reason,
        }, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="JAV metadata scraper for Emby")
    ap.add_argument("--config", help="Path to config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    args = ap.parse_args()

    cfg = load_config(args.config)
    scrape_dir = cfg["output_dir"] / ".scrape"
    _setup_logging(scrape_dir)

    # Validate
    if not cfg["source_dir"].exists():
        logger.error("Source dir does not exist: %s", cfg["source_dir"])
        return 1
    if cfg["source_dir"] == cfg["output_dir"]:
        logger.error("Source and output must be different directories")
        return 1

    cfg["output_dir"].mkdir(parents=True, exist_ok=True)

    session = providers.create_session(cfg)

    success_file = scrape_dir / "success.txt"
    processed = _load_success(success_file) if cfg.get("skip_processed", True) else set()

    files = scan_files(cfg)
    logger.info("Found %d media files in %s", len(files), cfg["source_dir"])

    if args.dry_run:
        for path, code in files:
            if str(path) in processed:
                tag = "skip"
            elif code:
                tag = "process"
            else:
                tag = "no-code"
            print(f"  [{tag:>8}] {path.name} -> {code or '-'}")
        total = len(files)
        with_code = sum(1 for _, c in files if c)
        print(f"\nTotal: {total} files ({with_code} with codes)")
        return 0

    failed_file = scrape_dir / "failed.jsonl"
    stats = {"success": 0, "failed": 0, "skipped": 0}

    for i, (path, code) in enumerate(files, 1):
        if str(path) in processed:
            stats["skipped"] += 1
            logger.info("[%d/%d] Skip: %s", i, len(files), path.name)
            continue

        if not code:
            stats["failed"] += 1
            logger.warning("[%d/%d] No code: %s", i, len(files), path.name)
            _record_failure(failed_file, path, None, "No code extracted from filename")
            continue

        logger.info("[%d/%d] Processing: %s (%s)", i, len(files), path.name, code)
        try:
            movie = providers.search_all(code, cfg, session)
            if not movie:
                stats["failed"] += 1
                logger.warning("No metadata for %s (%s)", path.name, code)
                _record_failure(failed_file, path, code, "No metadata found from any provider")
                continue

            target = build_output(cfg["output_dir"], movie, path, session, cfg)

            # Record success
            with open(success_file, "a", encoding="utf-8") as f:
                f.write(str(path) + "\n")
            processed.add(str(path))

            stats["success"] += 1
            logger.info("Done: %s -> %s", path.name, target.name)
        except Exception as e:
            stats["failed"] += 1
            logger.exception("Error: %s - %s", path.name, e)
            _record_failure(failed_file, path, code, str(e))
            if cfg.get("stop_on_error"):
                session.close()
                return 1

    logger.info(
        "Summary: %d success, %d failed, %d skipped",
        stats["success"], stats["failed"], stats["skipped"],
    )
    session.close()
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
