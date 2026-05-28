from dataclasses import dataclass
from pathlib import Path

from path_utils import safe_absolute_path


# Core runtime constants. Edit these paths for your machine.
SOURCE_DIR = Path(r"W:\P\new")
OUTPUT_DIR = Path(r"F:\P\link")
RUNTIME_DIR = Path(__file__).with_name("runtime")

# Optional output/runtime constants.
FAILED_DIR = RUNTIME_DIR / "failed"
LOG_FILE = RUNTIME_DIR / "logs" / "scrape.log"
RUN_REPORT_FILE = RUNTIME_DIR / "logs" / "last_run_summary.json"
SUCCESS_RECORD_FILE = RUNTIME_DIR / "logs" / "success_paths.txt"
SITE_CONFIG_FILE = Path(__file__).with_name("mdcx_scrape_sites.json")

# Media handling.
MEDIA_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".ts",
    ".m4v",
    ".iso",
)
MEDIA_ACTION = "copy"  # supported: "copy", "move"
COPY_FAILED_MEDIA = False

# Scraping.
ENABLED_SOURCES = ("javdb",)
HTTP_TIMEOUT = 20.0
HTTP_RETRIES = 2
REQUEST_INTERVAL_SECONDS = 0.0
FOLLOW_REDIRECTS = True
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

# Output files.
WRITE_NFO = True
WRITE_METADATA_JSON = True
DOWNLOAD_IMAGES = True
DOWNLOAD_TRAILER = False
EXTRAFANART_DIRNAME = "extrafanart"
NFO_FILENAME = "movie.nfo"

# Execution.
SKIP_RECORDED_SUCCESS = True
STOP_ON_ERROR = False
MAX_ITEMS = None  # set to an int for small-batch testing


@dataclass(frozen=True)
class Settings:
    source_dir: Path
    output_dir: Path
    failed_dir: Path
    log_file: Path
    run_report_file: Path
    success_record_file: Path
    site_config_file: Path
    media_extensions: tuple[str, ...]
    media_action: str
    copy_failed_media: bool
    enabled_sources: tuple[str, ...]
    http_timeout: float
    http_retries: int
    request_interval_seconds: float
    follow_redirects: bool
    user_agent: str
    write_nfo: bool
    write_metadata_json: bool
    download_images: bool
    download_trailer: bool
    extrafanart_dirname: str
    nfo_filename: str
    skip_recorded_success: bool
    stop_on_error: bool
    max_items: int | None


def get_settings() -> Settings:
    return Settings(
        source_dir=safe_absolute_path(SOURCE_DIR),
        output_dir=safe_absolute_path(OUTPUT_DIR),
        failed_dir=safe_absolute_path(FAILED_DIR),
        log_file=safe_absolute_path(LOG_FILE),
        run_report_file=safe_absolute_path(RUN_REPORT_FILE),
        success_record_file=safe_absolute_path(SUCCESS_RECORD_FILE),
        site_config_file=safe_absolute_path(SITE_CONFIG_FILE),
        media_extensions=tuple(ext.lower() for ext in MEDIA_EXTENSIONS),
        media_action=MEDIA_ACTION,
        copy_failed_media=COPY_FAILED_MEDIA,
        enabled_sources=tuple(ENABLED_SOURCES),
        http_timeout=HTTP_TIMEOUT,
        http_retries=HTTP_RETRIES,
        request_interval_seconds=REQUEST_INTERVAL_SECONDS,
        follow_redirects=FOLLOW_REDIRECTS,
        user_agent=USER_AGENT,
        write_nfo=WRITE_NFO,
        write_metadata_json=WRITE_METADATA_JSON,
        download_images=DOWNLOAD_IMAGES,
        download_trailer=DOWNLOAD_TRAILER,
        extrafanart_dirname=EXTRAFANART_DIRNAME,
        nfo_filename=NFO_FILENAME,
        skip_recorded_success=SKIP_RECORDED_SUCCESS,
        stop_on_error=STOP_ON_ERROR,
        max_items=MAX_ITEMS,
    )
