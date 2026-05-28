import tempfile
import unittest
from pathlib import Path

from config import Settings
from scanner import scan_media_files


def build_settings(root: Path) -> Settings:
    source_dir = root / "source"
    output_dir = source_dir / "_library"
    return Settings(
        source_dir=source_dir,
        output_dir=output_dir,
        failed_dir=output_dir / "_failed",
        log_file=output_dir / "_logs" / "scrape.log",
        run_report_file=output_dir / "_logs" / "last_run_summary.json",
        success_record_file=output_dir / "_logs" / "success_paths.txt",
        site_config_file=root / "sites.json",
        media_extensions=(".mp4", ".mkv"),
        media_action="copy",
        copy_failed_media=False,
        enabled_sources=("javdb",),
        http_timeout=10.0,
        http_retries=1,
        request_interval_seconds=0.0,
        follow_redirects=True,
        user_agent="test-agent",
        write_nfo=True,
        write_metadata_json=True,
        download_images=False,
        download_trailer=False,
        extrafanart_dirname="extrafanart",
        nfo_filename="movie.nfo",
        skip_recorded_success=True,
        stop_on_error=False,
        max_items=None,
    )


class ScannerTests(unittest.TestCase):
    def test_scans_nested_media_and_ignores_output_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = build_settings(root)

            (settings.source_dir / "nested").mkdir(parents=True, exist_ok=True)
            (settings.source_dir / "nested" / "ABP-123.mp4").write_bytes(b"video")
            (settings.source_dir / "nested" / "README.txt").write_text("ignore", encoding="utf-8")
            (settings.output_dir / "ABP-123 Example").mkdir(parents=True, exist_ok=True)
            (settings.output_dir / "ABP-123 Example" / "ABP-123.mp4").write_bytes(b"done")
            (settings.failed_dir / "XYZ_00000000").mkdir(parents=True, exist_ok=True)
            (settings.failed_dir / "XYZ_00000000" / "XYZ-999.mp4").write_bytes(b"failed")

            tasks = scan_media_files(settings)

            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].relative_path.as_posix(), "nested/ABP-123.mp4")
            self.assertEqual(tasks[0].code, "ABP-123")


if __name__ == "__main__":
    unittest.main()
