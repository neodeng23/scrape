#!/usr/bin/env python3
from config import get_settings
from logging_utils import build_logger


def main() -> int:
    settings = get_settings()
    logger = build_logger(settings.log_file)

    try:
        from pipeline import ScrapePipeline
    except ModuleNotFoundError as exc:
        raise SystemExit(
            f"Missing dependency: {exc.name}. Install packages from requirements-headless.txt first."
        ) from exc

    logger.info("Starting independent headless scraper.")
    logger.info("Source directory: %s", settings.source_dir)
    logger.info("Output directory: %s", settings.output_dir)
    logger.info("Failed directory: %s", settings.failed_dir)
    logger.info("Enabled sources: %s", ", ".join(settings.enabled_sources))
    logger.info("Success record file: %s", settings.success_record_file)
    logger.info("Skip recorded success: %s", settings.skip_recorded_success)

    pipeline = ScrapePipeline(settings, logger)
    return pipeline.run()


if __name__ == "__main__":
    raise SystemExit(main())
