from __future__ import annotations

from datetime import datetime, timezone

from config import Settings
from http_client import HttpClient
from models import MediaTask, MovieMetadata, RunSummary, TaskResult
from scanner import scan_media_files
from site_config import load_site_definitions
from sources import build_sources
from writers import FailureWriter, LibraryWriter, SuccessRecordStore, write_run_summary


class ScrapePipeline:
    def __init__(self, settings: Settings, logger):
        self.settings = settings
        self.logger = logger

    def run(self) -> int:
        self._validate_settings()
        site_definitions = load_site_definitions(self.settings.site_config_file)
        http_client = HttpClient(
            timeout=self.settings.http_timeout,
            retries=self.settings.http_retries,
            follow_redirects=self.settings.follow_redirects,
            user_agent=self.settings.user_agent,
            request_interval_seconds=self.settings.request_interval_seconds,
        )
        summary = RunSummary(
            source_dir=str(self.settings.source_dir),
            output_dir=str(self.settings.output_dir),
            failed_dir=str(self.settings.failed_dir),
            started_at=self._utc_now(),
        )

        try:
            sources = build_sources(self.settings.enabled_sources, site_definitions, http_client)
            library_writer = LibraryWriter(self.settings, http_client)
            failure_writer = FailureWriter(self.settings)
            success_record_store = SuccessRecordStore(self.settings.success_record_file)
            tasks = scan_media_files(self.settings)
            summary.total = len(tasks)
            self.logger.info("Discovered %s media file(s).", len(tasks))

            for index, task in enumerate(tasks, start=1):
                self.logger.info("[%s/%s] Processing %s", index, len(tasks), task.relative_path.as_posix())
                if self.settings.skip_recorded_success and success_record_store.contains(task.source_path):
                    summary.skipped += 1
                    summary.items.append(
                        TaskResult(
                            source_path=str(task.source_path),
                            relative_path=task.relative_path.as_posix(),
                            code=task.code,
                            status="skipped",
                            reason="Already recorded as successful.",
                        )
                    )
                    self.logger.info("Skipping already recorded success: %s", task.source_path)
                    continue
                try:
                    metadata = self._scrape_task(task, sources)
                    if metadata is None:
                        summary.failure += 1
                        if not task.code:
                            reason = "Could not extract a media code from the filename."
                        else:
                            reason = "No enabled source returned metadata."
                        failure_writer.write_failure(task, reason)
                        summary.items.append(
                            TaskResult(
                                source_path=str(task.source_path),
                                relative_path=task.relative_path.as_posix(),
                                code=task.code,
                                status="failure",
                                reason=reason,
                            )
                        )
                        self.logger.warning("Scrape failed for %s: %s", task.source_path, reason)
                        continue

                    target_dir = library_writer.write_success(task, metadata)
                    success_record_store.mark_success(task.source_path)
                    summary.success += 1
                    summary.items.append(
                        TaskResult(
                            source_path=str(task.source_path),
                            relative_path=task.relative_path.as_posix(),
                            code=metadata.code,
                            status="success",
                            source_name=metadata.source_name,
                            detail_url=metadata.detail_url,
                            output_dir=str(target_dir),
                        )
                    )
                    self.logger.info("Scrape succeeded for %s -> %s", task.source_path, target_dir)
                except Exception as exc:
                    summary.failure += 1
                    failure_writer.write_failure(task, str(exc))
                    summary.items.append(
                        TaskResult(
                            source_path=str(task.source_path),
                            relative_path=task.relative_path.as_posix(),
                            code=task.code,
                            status="failure",
                            reason=str(exc),
                        )
                    )
                    self.logger.exception("Task failed for %s", task.source_path)
                    if self.settings.stop_on_error:
                        raise

            self.logger.info(
                "Completed. success=%s failed=%s skipped=%s total=%s",
                summary.success,
                summary.failure,
                summary.skipped,
                summary.total,
            )
            return 0 if summary.failure == 0 else 1
        finally:
            summary.finished_at = self._utc_now()
            report_path = write_run_summary(self.settings.run_report_file, summary)
            self.logger.info("Wrote run summary to %s", report_path)
            http_client.close()

    def _validate_settings(self) -> None:
        if not self.settings.source_dir.exists():
            raise FileNotFoundError(f"SOURCE_DIR does not exist: {self.settings.source_dir}")
        if not self.settings.source_dir.is_dir():
            raise NotADirectoryError(f"SOURCE_DIR is not a directory: {self.settings.source_dir}")
        if self.settings.source_dir == self.settings.output_dir:
            raise ValueError("SOURCE_DIR and OUTPUT_DIR must be different directories.")
        if self.settings.media_action not in {"copy", "move"}:
            raise ValueError("MEDIA_ACTION must be either 'copy' or 'move'.")
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings.failed_dir.mkdir(parents=True, exist_ok=True)

    def _scrape_task(self, task: MediaTask, sources) -> MovieMetadata | None:
        if not task.code:
            self.logger.info("No media code found in filename, skipping: %s", task.source_path)
            return None
        for source in sources:
            self.logger.info("Trying source=%s code=%s", source.name, task.code)
            result = source.scrape(task.code)
            if result is not None:
                return result
        return None

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
