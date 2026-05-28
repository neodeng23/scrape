import json
import tempfile
import unittest
from pathlib import Path

from config import Settings
from models import MediaTask, MovieMetadata
from writers.library import FailureWriter, LibraryWriter


class DummyHttpClient:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    def download(self, _url: str, destination: Path) -> None:
        if self.should_fail:
            raise RuntimeError("download failed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"stub")


def build_settings(root: Path) -> Settings:
    return Settings(
        source_dir=root / "source",
        output_dir=root / "output",
        failed_dir=root / "output" / "_failed",
        log_file=root / "output" / "_logs" / "scrape.log",
        run_report_file=root / "output" / "_logs" / "last_run_summary.json",
        success_record_file=root / "output" / "_logs" / "success_paths.txt",
        site_config_file=root / "sites.json",
        media_extensions=(".mp4",),
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
        download_images=True,
        download_trailer=False,
        extrafanart_dirname="extrafanart",
        nfo_filename="movie.nfo",
        skip_recorded_success=True,
        stop_on_error=False,
        max_items=None,
    )


def build_task(source_root: Path, relative_path: str) -> MediaTask:
    source_path = source_root / relative_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"video")
    return MediaTask(
        source_path=source_path,
        relative_path=Path(relative_path),
        stem=source_path.stem,
        extension=source_path.suffix.lower(),
        code="ABP-123",
    )


class LibraryWriterTests(unittest.TestCase):
    def test_write_success_cleans_new_directory_when_artwork_download_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = build_settings(root)
            task = build_task(settings.source_dir, "movie.mp4")
            metadata = MovieMetadata(
                code="ABP-123",
                source_name="javdb",
                title="Example Title",
            )
            metadata.artwork.thumb_url = "https://example.com/thumb.jpg"

            writer = LibraryWriter(settings, DummyHttpClient(should_fail=True))

            with self.assertRaisesRegex(RuntimeError, "download failed"):
                writer.write_success(task, metadata)

            self.assertFalse((settings.output_dir / "ABP-123 Example Title").exists())
            self.assertTrue(task.source_path.exists())

    def test_failure_writer_uses_unique_relative_path_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = build_settings(root)
            writer = FailureWriter(settings)
            settings.failed_dir.mkdir(parents=True, exist_ok=True)

            first = build_task(settings.source_dir, "disc1/movie.mp4")
            second = build_task(settings.source_dir, "disc2/movie.mp4")

            first_dir = writer.write_failure(first, "first")
            second_dir = writer.write_failure(second, "second")

            self.assertNotEqual(first_dir, second_dir)
            first_record = json.loads((first_dir / "failure.json").read_text(encoding="utf-8"))
            second_record = json.loads((second_dir / "failure.json").read_text(encoding="utf-8"))
            self.assertEqual(first_record["reason"], "first")
            self.assertEqual(second_record["reason"], "second")


if __name__ == "__main__":
    unittest.main()
