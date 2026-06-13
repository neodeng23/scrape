#!/usr/bin/env python3
"""JAV metadata scraper for Emby/Jellyfin/Kodi."""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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

# Multi-file part patterns (CD, Disc, Part, PT, _number, etc.)
_MULTI_FILE_PATTERNS = [
    r'_CD\d+',
    r'_DISC\d+',
    r'_PART\d+',
    r'_PT\d+',
    r'_\d+',  # _01, _02, etc.
    r'-CD\d+',
    r'-DISC\d+',
    r'-PART\d+',
    r'-PT\d+',
    r'-\d+',  # -01, -02, etc.
    r'CD\d+$',
    r'DISC\d+$',
    r'PART\d+$',
    r'PT\d+$',
]


def _group_multi_files(files: list[tuple[Path, str | None]]) -> list[tuple[Path, str | None, list[Path]]]:
    """Group multi-file videos. Returns list of (rep_file, code, all_files)."""
    import re
    from collections import defaultdict

    groups: dict[str, list[Path]] = defaultdict(list)

    for path, code in files:
        if not code:
            groups[f"__nocode__{path}"].append(path)
        else:
            # Group by code (multi-files share same code)
            groups[code].append(path)

    # For each group, select representative file (prefer the one without part suffix)
    result = []
    for code, paths in groups.items():
        paths.sort(key=lambda p: p.name)
        # Prefer files without part suffix as representative
        rep_path = paths[0]
        for p in paths:
            has_part = False
            for pattern in _MULTI_FILE_PATTERNS:
                if re.search(pattern + r'\.', p.name.upper()):
                    has_part = True
                    break
            if not has_part:
                rep_path = p
                break

        is_noc = code.startswith("__nocode__")
        result.append((rep_path, None if is_noc else code, paths))

    return result


def scan_files(cfg: dict) -> list[tuple[Path, str | None, list[Path]]]:
    """Scan source directory for media files. Returns list of (rep_file, code, all_files)."""
    src = cfg["source_dir"]
    exts = set(e.lower() for e in cfg.get("media_extensions", []))
    out = cfg["output_dir"]

    raw_results: list[tuple[Path, str | None]] = []
    try:
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
            raw_results.append((p, code))
    except (OSError, PermissionError):
        # Skip broken symlinks/junctions during rglob
        pass

    raw_results.sort(key=lambda x: x[0].name.lower())

    # Group multi-file videos, then cap by number of groups so that a
    # multi-part title (CD1/CD2/...) is never split across the limit.
    grouped = _group_multi_files(raw_results)
    if cfg.get("max_items"):
        grouped = grouped[:cfg["max_items"]]
    return grouped


# ---------------------------------------------------------------------------
# Symlink detection
# ---------------------------------------------------------------------------

def _build_symlink_target_set(final_dir: Path) -> set[str]:
    """Scan final_dir once and collect the resolved targets of every symlink.

    Returns a set of resolved target paths (as strings) so that membership
    checks during the main loop are O(1) instead of re-scanning the whole
    output tree for each source file.
    """
    targets: set[str] = set()
    try:
        for subdir in final_dir.iterdir():
            if not subdir.is_dir():
                continue
            try:
                for entry in subdir.iterdir():
                    # Use is_symlink() instead of exists() to avoid TOCTOU race
                    if not entry.is_symlink():
                        continue
                    try:
                        targets.add(str(entry.resolve()))
                    except (OSError, RuntimeError):
                        # Broken symlink or resolution error, skip
                        pass
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        # Output dir not accessible
        pass
    return targets


def _has_valid_symlink(symlink_targets: set[str], source_path: Path) -> bool:
    """Check if source_path is the target of a known symlink (see _build_symlink_target_set)."""
    try:
        return str(source_path.resolve()) in symlink_targets
    except (OSError, RuntimeError):
        return False


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
    # Build JSON data first to avoid FD leak if json.dumps fails
    data = json.dumps({
        "path": str(file),
        "code": code,
        "reason": reason,
    }, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(data + "\n")


# ---------------------------------------------------------------------------
# Symlink privilege (Windows): one-time check at startup + UAC relaunch
# ---------------------------------------------------------------------------

def _relaunch_as_admin() -> None:
    """Relaunch this script with admin privileges via UAC. Exits current process.

    Uses ShellExecuteW("runas", ...) which pops the Windows UAC dialog. If the
    user approves, a new elevated process runs (this one exits). Mirrors the
    approach in the Media-handling tools.
    """
    import ctypes
    import os
    import subprocess
    # Make the script path absolute and pass the current working directory so
    # the elevated process resolves relative paths (e.g. --config) the same way.
    argv = list(sys.argv)
    argv[0] = os.path.abspath(argv[0])
    params = subprocess.list2cmdline(argv)
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, os.getcwd(), 1
    )
    # ShellExecuteW returns > 32 on success
    if rc <= 32:
        raise RuntimeError(f"UAC elevation declined or failed (code {rc})")
    sys.exit(0)


def _ensure_symlink_privilege(media_action: str) -> None:
    """If symlinks are needed but we lack privilege, UAC-elevate and restart.

    Only acts on Windows when media_action == "symlink". Checks once; if the
    test symlink fails, relaunches elevated. If the user declines UAC, aborts
    with guidance to run as admin or switch to copy mode.
    """
    if sys.platform != "win32":
        return
    if media_action != "symlink":
        return
    from output import can_create_symlinks
    if can_create_symlinks():
        return
    print("创建软链接需要管理员权限（或开启开发者模式），正在请求 UAC 提权...")
    try:
        _relaunch_as_admin()
    except Exception as e:
        print(f"\n无法获取管理员权限: {e}")
        print("请以管理员身份运行此程序，或在 config.yaml 中将 media_action 改为 copy")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="JAV metadata scraper for Emby")
    ap.add_argument("--config", help="Path to config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    ap.add_argument("--scan-only", action="store_true", help="Only scan files and output results")
    ap.add_argument("--scan-output", help="Output scan results to file (JSON)")
    ap.add_argument("--init", action="store_true", help="Initialize: scan final_dir symlinks and record to success.txt")
    ap.add_argument("--retry-unmatched", action="store_true", help="Retry unmatched files with manually added URLs from unmatched.txt")
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
        for rep_file, code, all_files in files:
            # Show if this is a multi-file group
            file_count = len(all_files)
            if file_count > 1:
                print(f"  [{file_count} files] {code or '-'}: {rep_file.name}")
                for f in all_files:
                    print(f"             -> {f.name}")
            else:
                tag = "skip" if str(rep_file) in processed else ("process" if code else "no-code")
                print(f"  [{tag:>8}] {rep_file.name} -> {code or '-'}")
        total_groups = len(files)
        total_files = sum(len(all_files) for _, _, all_files in files)
        with_code = sum(1 for _, c, _ in files if c)
        print(f"\nTotal: {total_groups} groups ({total_files} files) ({with_code} with codes)")
        return 0

    if args.scan_only:
        # Output scan results
        scan_results = []
        final_dir = cfg.get("final_dir")
        symlink_targets = _build_symlink_target_set(final_dir) if final_dir else set()
        for rep_file, code, all_files in files:
            # Check if any file in the group is processed
            group_processed = any(str(f) in processed for f in all_files)
            status = "skipped" if group_processed else ("no-code" if not code else "ready")
            has_symlink = False
            if final_dir and status == "skipped":
                has_symlink = _has_valid_symlink(symlink_targets, rep_file)

            scan_results.append({
                "path": str(rep_file),
                "filename": rep_file.name,
                "code": code,
                "status": status,
                "has_symlink": has_symlink,
                "file_count": len(all_files),
                "all_files": [str(f) for f in all_files],
            })

        # Filter out skipped entries
        active_results = [r for r in scan_results if r["status"] != "skipped"]

        output_path = Path(args.scan_output) if args.scan_output else None
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(scan_results, f, ensure_ascii=False, indent=2)
            logger.info("Scan results saved to: %s", output_path)
            print(f"\n✓ Scan results saved to: {output_path}")
        else:
            # Print to stdout (skip already-processed entries)
            if active_results:
                print(f"\n{'='*80}")
                print(f"{'Filename':<40} {'Code':<12} {'Files':<6} {'Status':<10}")
                print(f"{'='*80}")
                for r in active_results:
                    file_info = f"({r['file_count']})" if r['file_count'] > 1 else ""
                    print(f"{r['filename']:<40} {r['code'] or '-':<12} {file_info:<6} {r['status']:<10}")

            total = len(scan_results)
            total_files = sum(r["file_count"] for r in scan_results)
            ready = sum(1 for r in scan_results if r["status"] == "ready")
            no_code = sum(1 for r in scan_results if r["status"] == "no-code")
            skipped = sum(1 for r in scan_results if r["status"] == "skipped")
            print(f"{'='*80}")
            print(f"Total: {total} groups ({total_files} files) | Ready: {ready} | No-code: {no_code} | Skipped: {skipped}")

            # List ready + no-code files with full paths
            pending = [r for r in scan_results if r["status"] in ("ready", "no-code")]
            if pending:
                print(f"\n{'='*80}")
                print(f"Files pending ({len(pending)}):")
                print(f"{'='*80}")
                for r in pending:
                    label = r["code"] or "no-code"
                    for fpath in r["all_files"]:
                        print(f"  [{label}] {fpath}")

        session.close()
        return 0

    # Initialize mode: scan final_dir symlinks and record to success.txt
    if args.init:
        final_dir = cfg.get("final_dir")
        if not final_dir:
            logger.error("--init requires final_dir to be set in config.yaml")
            return 1

        if not final_dir.exists():
            logger.error("Final dir does not exist: %s", final_dir)
            return 1

        logger.info("Scanning %s for existing symlinks...", final_dir)
        source_dir = cfg["source_dir"]

        found_count = 0
        not_in_source_count = 0
        broken_link_count = 0

        try:
            for item in final_dir.rglob("*"):
                if not item.is_symlink():
                    continue
                try:
                    # Read raw symlink target (handles NT namespace \\?\ prefix)
                    import os
                    raw_target = os.readlink(item)

                    # Remove NT namespace prefix if present
                    prefix = "\\\\?\\"
                    if raw_target.startswith(prefix):
                        link_target = Path(raw_target[4:])
                    else:
                        link_target = Path(raw_target)

                    # Check if the target exists and is within source_dir
                    if not link_target.exists():
                        broken_link_count += 1
                        logger.debug("Broken symlink: %s -> %s", item, raw_target)
                        continue

                    # Check if target is within source_dir
                    try:
                        link_target.relative_to(source_dir)
                        # Found a symlink pointing to a file in source_dir
                        source_path = str(link_target)
                        with open(success_file, "a", encoding="utf-8") as f:
                            f.write(source_path + "\n")
                        processed.add(source_path)
                        found_count += 1
                        logger.info("Recorded: %s -> %s", item.name, link_target)
                    except ValueError:
                        # Symlink target is not in source_dir
                        not_in_source_count += 1
                        logger.debug("Skipping: %s (not in source_dir: %s)", item, link_target)
                except (OSError, RuntimeError) as e:
                    # Error reading symlink
                    broken_link_count += 1
                    logger.debug("Error reading symlink %s: %s", item, e)
        except (OSError, PermissionError):
            logger.error("Error scanning final_dir")

        logger.info(
            "Init complete: %d recorded, %d not in source_dir, %d broken",
            found_count, not_in_source_count, broken_link_count
        )

        session.close()
        return 0

    # Modes below this point create symlinks — ensure privilege once.
    _ensure_symlink_privilege(cfg.get("media_action", "symlink"))

    # --retry-unmatched mode: read unmatched.txt, scrape files with URLs
    if args.retry_unmatched:
        import provider_javdb

        unmatched_file = scrape_dir / "unmatched.txt"
        if not unmatched_file.exists():
            logger.error("unmatched.txt not found: %s", unmatched_file)
            session.close()
            return 1

        # Parse unmatched.txt
        pending: list[tuple[str, str]] = []  # (path, url)
        with open(unmatched_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if " # " in line:
                    path_part, url = line.split(" # ", 1)
                    pending.append((path_part.strip(), url.strip()))

        if not pending:
            print("No URLs found in unmatched.txt (add ' # <URL>' after file paths)")
            session.close()
            return 0

        print(f"Found {len(pending)} files with URLs in unmatched.txt\n")

        failed_file = scrape_dir / "failed.jsonl"
        retry_stats = {"success": 0, "failed": 0, "skipped": 0}
        retry_success: list[str] = []
        retry_failed: list[tuple[str, str]] = []  # (path, reason)

        for i, (file_path, url) in enumerate(pending, 1):
            source = Path(file_path)
            if not source.exists():
                logger.warning("[%d/%d] File not found, skipping: %s", i, len(pending), file_path)
                retry_stats["skipped"] += 1
                continue

            if str(source) in processed:
                logger.info("[%d/%d] Already processed, skipping: %s", i, len(pending), source.name)
                retry_stats["skipped"] += 1
                continue

            logger.info("[%d/%d] Scraping URL: %s <- %s", i, len(pending), source.name, url)
            try:
                movie = provider_javdb.scrape_url(url, session, cfg)
                if not movie:
                    retry_stats["failed"] += 1
                    logger.warning("No metadata from URL for %s", source.name)
                    reason = f"No metadata from URL: {url}"
                    _record_failure(failed_file, source, None, reason)
                    retry_failed.append((str(source), reason))
                    continue

                build_output(cfg["output_dir"], movie, source, session, cfg)

                with open(success_file, "a", encoding="utf-8") as fp:
                    fp.write(str(source) + "\n")
                processed.add(str(source))

                retry_stats["success"] += 1
                retry_success.append(str(source))
                logger.info("Done: %s -> %s", source.name, movie.code)
            except Exception as e:
                retry_stats["failed"] += 1
                logger.exception("Error: %s - %s", source.name, e)
                reason = str(e) or type(e).__name__
                _record_failure(failed_file, source, None, reason)
                retry_failed.append((str(source), reason))

        session.close()

        # Terminal summary
        print(f"\n{'='*80}")
        print(f"RETRY SUMMARY")
        print(f"{'='*80}")
        if retry_success:
            print(f"\n✓ Success ({len(retry_success)}):")
            for p in retry_success:
                print(f"  {p}")
        if retry_failed:
            print(f"\n✗ Failed ({len(retry_failed)}):")
            for path, reason in retry_failed:
                print(f"  [{reason}] {path}")
        print(f"\n{'='*80}")
        print(f"Total: {retry_stats['success']} success, {retry_stats['failed']} failed, {retry_stats['skipped']} skipped")
        return 0 if retry_stats["failed"] == 0 else 1

    # Normal scraping mode
    failed_file = scrape_dir / "failed.jsonl"
    unmatched_file = scrape_dir / "unmatched.txt"
    stats = {"success": 0, "failed": 0, "skipped": 0}
    failed_items: list[tuple[str, str]] = []  # (path, reason) for unmatched.txt + summary
    success_paths: list[str] = []  # successful rep file paths for summary

    final_dir = cfg.get("final_dir")
    symlink_targets = _build_symlink_target_set(final_dir) if final_dir else set()

    try:
        for i, (rep_file, code, all_files) in enumerate(files, 1):
            file_count = len(all_files)
            if file_count > 1:
                logger.info("[%d/%d] Group %s: %d files", i, len(files), code, file_count)

            # Check if already processed via success.txt (check all files in group)
            group_processed = any(str(f) in processed for f in all_files)
            if group_processed:
                stats["skipped"] += 1
                logger.info("[%d/%d] Skip: %s", i, len(files), rep_file.name)
                continue

            # Check if symlink already exists in final dir (where Emby reads)
            if final_dir and _has_valid_symlink(symlink_targets, rep_file):
                stats["skipped"] += 1
                logger.info("[%d/%d] Skip (symlink exists in final dir): %s", i, len(files), rep_file.name)
                # Also record to success.txt to avoid re-checking next time
                for f in all_files:
                    with open(success_file, "a", encoding="utf-8") as file:
                        file.write(str(f) + "\n")
                    processed.add(str(f))
                continue

            if not code:
                stats["failed"] += 1
                logger.warning("[%d/%d] No code: %s", i, len(files), rep_file.name)
                for f in all_files:
                    _record_failure(failed_file, f, None, "No code extracted from filename")
                    failed_items.append((str(f), "No code extracted from filename"))
                continue

            logger.info("[%d/%d] Processing: %s (%s)", i, len(files), rep_file.name, code)
            try:
                movie = providers.search_all(code, cfg, session)
                if not movie:
                    stats["failed"] += 1
                    logger.warning("No metadata for %s (%s)", rep_file.name, code)
                    for f in all_files:
                        _record_failure(failed_file, f, code, "No metadata found from any provider")
                        failed_items.append((str(f), "No metadata found from any provider"))
                    continue

                # Process all files in the group
                for source_file in all_files:
                    build_output(cfg["output_dir"], movie, source_file, session, cfg)

                # Record success for all files in group
                for f in all_files:
                    with open(success_file, "a", encoding="utf-8") as file:
                        file.write(str(f) + "\n")
                    processed.add(str(f))

                stats["success"] += 1
                success_paths.append(str(rep_file))
                logger.info("Done: %s -> %s (%d files)", rep_file.name, code, file_count)
            except Exception as e:
                stats["failed"] += 1
                logger.exception("Error: %s - %s", rep_file.name, e)
                reason = str(e) or type(e).__name__
                for f in all_files:
                    _record_failure(failed_file, f, code, reason)
                    failed_items.append((str(f), reason))
                if cfg.get("stop_on_error"):
                    return 1
    finally:
        session.close()

    # Terminal summary: list successful and failed files with full paths
    print(f"\n{'='*80}")
    print(f"SCRAPE SUMMARY")
    print(f"{'='*80}")
    if success_paths:
        print(f"\n✓ Success ({len(success_paths)}):")
        for p in success_paths:
            print(f"  {p}")
    if failed_items:
        print(f"\n✗ Failed ({len(failed_items)}):")
        # Group by reason to keep output compact when many share a cause
        for path, reason in failed_items:
            print(f"  [{reason}] {path}")
    print(f"\n{'='*80}")
    print(f"Total: {stats['success']} success, {stats['failed']} failed, {stats['skipped']} skipped")

    # Write unmatched.txt with all failed file paths
    if failed_items:
        failed_paths = [p for p, _ in failed_items]
        with open(unmatched_file, "w", encoding="utf-8") as f:
            f.write("# 未匹配文件 — 添加 \" # \" 和 JavDB URL 后运行 --retry-unmatched\n")
            f.write("# 示例: W:\\P\\J\\file.mp4 # https://javdb.com/v/abcde?locale=en\n")
            for p in failed_paths:
                f.write(p + "\n")
        logger.info("Wrote %d unmatched files to %s", len(failed_paths), unmatched_file)
        print(f"\n未匹配文件已写入: {unmatched_file}")
        print(f"请编辑该文件，在路径后添加 \" # <JavDB URL>\"，然后运行:")
        print(f"  python scrape.py --retry-unmatched")

    logger.info(
        "Summary: %d success, %d failed, %d skipped",
        stats["success"], stats["failed"], stats["skipped"],
    )
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
