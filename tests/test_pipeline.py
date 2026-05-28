import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Settings
from models import MediaTask, MovieMetadata
from path_utils import safe_display_path
from pipeline import ScrapePipeline


class DummyLogger:
    def info(self, *_args, **_kwargs) -> None:
        pass

    def warning(self, *_args, **_kwargs) -> None:
        pass

    def exception(self, *_args, **_kwargs) -> None:
        pass


class DummyHttpClient:
    def close(self) -> None:
        pass


class StubSource:
    name = "stub"

    def scrape(self, code: str) -> MovieMetadata:
        return MovieMetadata(
            code=code,
            source_name=self.name,
            detail_url=f"https://example.com/{code}",
            title="Example Title",
        )


class ExplodingSource:
    name = "explode"

    def scrape(self, _code: str) -> MovieMetadata:
        raise AssertionError("skip logic failed; source should not be called")


def build_settings(root: Path) -> Settings:
    source_dir = root / "source"
    output_dir = root / "output"
    return Settings(
        source_dir=source_dir,
        output_dir=output_dir,
        failed_dir=output_dir / "_failed",
        log_file=output_dir / "_logs" / "scrape.log",
        run_report_file=output_dir / "_logs" / "last_run_summary.json",
        success_record_file=output_dir / "_logs" / "success_paths.txt",
        site_config_file=root / "sites.json",
        media_extensions=(".mp4",),
        media_action="copy",
        copy_failed_media=False,
        enabled_sources=("stub",),
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


def build_task(source_dir: Path, relative_path: str = "ABP-123.mp4") -> MediaTask:
    media_path = source_dir / relative_path
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"video")
    return MediaTask(
        source_path=media_path,
        relative_path=Path(relative_path),
        stem=media_path.stem,
        extension=media_path.suffix.lower(),
        code="ABP-123",
    )


class PipelineTests(unittest.TestCase):
    def test_pipeline_writes_run_summary_and_success_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = build_settings(root)
            task = build_task(settings.source_dir)
            pipeline = ScrapePipeline(settings, DummyLogger())

            with patch("pipeline.load_site_definitions", return_value={}), patch(
                "pipeline.HttpClient",
                return_value=DummyHttpClient(),
            ), patch("pipeline.build_sources", return_value=[StubSource()]), patch(
                "pipeline.scan_media_files",
                return_value=[task],
            ):
                exit_code = pipeline.run()

            self.assertEqual(exit_code, 0)
            report = json.loads(settings.run_report_file.read_text(encoding="utf-8"))
            self.assertEqual(report["success"], 1)
            self.assertEqual(report["failure"], 0)
            self.assertEqual(report["skipped"], 0)
            self.assertEqual(report["total"], 1)
            self.assertEqual(report["items"][0]["status"], "success")
            self.assertEqual(report["items"][0]["code"], "ABP-123")
            self.assertEqual(report["items"][0]["source_name"], "stub")

            record_lines = [
                line.strip()
                for line in settings.success_record_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            self.assertEqual(record_lines, [safe_display_path(task.source_path)])

    def test_pipeline_skips_recorded_success_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = build_settings(root)
            task = build_task(settings.source_dir)
            settings.success_record_file.parent.mkdir(parents=True, exist_ok=True)
            settings.success_record_file.write_text(
                "# One absolute source media path per line.\n"
                f"{safe_display_path(task.source_path)}\n",
                encoding="utf-8",
            )
            pipeline = ScrapePipeline(settings, DummyLogger())

            with patch("pipeline.load_site_definitions", return_value={}), patch(
                "pipeline.HttpClient",
                return_value=DummyHttpClient(),
            ), patch("pipeline.build_sources", return_value=[ExplodingSource()]), patch(
                "pipeline.scan_media_files",
                return_value=[task],
            ):
                exit_code = pipeline.run()

            self.assertEqual(exit_code, 0)
            report = json.loads(settings.run_report_file.read_text(encoding="utf-8"))
            self.assertEqual(report["success"], 0)
            self.assertEqual(report["failure"], 0)
            self.assertEqual(report["skipped"], 1)
            self.assertEqual(report["items"][0]["status"], "skipped")
            self.assertEqual(report["items"][0]["reason"], "Already recorded as successful.")


if __name__ == "__main__":
    unittest.main()
