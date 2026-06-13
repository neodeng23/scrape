"""Provider registry, HTTP utilities, and multi-source merge."""
from __future__ import annotations

import logging
import time
import types
from pathlib import Path

# Check if curl_cffi is available for Cloudflare bypass
_USE_CURL_CFFI = False
try:
    from curl_cffi import requests
    _USE_CURL_CFFI = True
except ImportError:
    import httpx

import yaml

from models import Movie

logger = logging.getLogger("scrape")

if _USE_CURL_CFFI:
    logger.info("Using curl_cffi for Cloudflare bypass")
else:
    logger.info("Using httpx (install curl-cffi for Cloudflare bypass)")

# ---------------------------------------------------------------------------
# Sites configuration (sites.yaml)
# ---------------------------------------------------------------------------

_sites_cache: dict | None = None


def load_sites() -> dict:
    global _sites_cache
    if _sites_cache is not None:
        return _sites_cache
    path = Path(__file__).with_name("sites.yaml")
    if path.exists():
        try:
            # Use utf-8-sig to handle BOM if present (Windows Notepad issue)
            with open(path, encoding="utf-8-sig") as f:
                _sites_cache = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as e:
            logger.warning("Failed to load sites.yaml: %s", e)
            _sites_cache = {}
    else:
        _sites_cache = {}
    return _sites_cache


def get_site(name: str) -> dict:
    """Get a site's configuration from sites.yaml."""
    return load_sites().get(name, {})


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, types.ModuleType] = {}


def register(name: str, module: types.ModuleType) -> None:
    _REGISTRY[name] = module


def get_enabled(config: dict) -> list[tuple[str, types.ModuleType]]:
    order = config.get("provider_order", ["javdb"])
    result = []
    for name in order:
        if name in _REGISTRY:
            result.append((name, _REGISTRY[name]))
        else:
            logger.warning("Unknown provider skipped: %s", name)
    return result


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_last_request_time: float = 0.0


def create_session(config: dict):
    """Create HTTP session. Returns curl_cffi Session if available, else httpx Client."""
    if _USE_CURL_CFFI:
        kwargs: dict = {
            "impersonate": "chrome",
            "timeout": config.get("timeout", 20),
            "headers": {"User-Agent": config.get("user_agent", "")},
        }
        proxy = config.get("proxy_url")
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        return requests.Session(**kwargs)
    else:
        kwargs: dict = {
            "timeout": config.get("timeout", 20),
            "follow_redirects": True,
            "headers": {"User-Agent": config.get("user_agent", "")},
        }
        proxy = config.get("proxy_url")
        if proxy:
            kwargs["proxy"] = proxy
        return httpx.Client(**kwargs)


def fetch(session: httpx.Client, url: str, config: dict) -> str:
    """GET with rate-limiting and retries. Returns response text."""
    global _last_request_time
    delay = config.get("delay", 0.5)
    # retries=N means N retries after the first attempt → N+1 total attempts
    max_attempts = max(config.get("retries", 2), 0) + 1

    last_error: Exception | None = None
    for attempt in range(max_attempts):
        # Rate limiting (skip on very first request ever)
        if delay > 0 and _last_request_time > 0:
            elapsed = time.monotonic() - _last_request_time
            if elapsed < delay:
                time.sleep(delay - elapsed)
        try:
            resp = session.get(url)
            _last_request_time = time.monotonic()
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            last_error = e
            _last_request_time = time.monotonic()
            logger.debug("Attempt %d/%d failed for %s: %s", attempt + 1, max_attempts, url, e)

    raise last_error or RuntimeError(f"All retries exhausted for: {url}")


def download(session, url: str, dest: Path, timeout: int = 60) -> Path:
    """Stream-download a file. Works with both curl_cffi and httpx."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Clean up any partial file from previous attempt
    if dest.exists():
        dest.unlink()

    try:
        if _USE_CURL_CFFI:
            # curl_cffi doesn't have stream(), use iterate=True
            # Set longer timeout for downloads (default 60s)
            resp = session.get(url, stream=True, timeout=timeout)
            resp.raise_for_status()
            with dest.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        else:
            # httpx style
            with session.stream("GET", url, timeout=timeout) as resp:
                resp.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
        return dest
    except Exception:
        # Clean up partial file on failure
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Multi-source merge (first-wins for scalars, dedup-concat for lists)
# ---------------------------------------------------------------------------

MOVIE_FIELDS = [
    "code", "title", "originaltitle", "plot", "released", "year",
    "runtime", "studio", "director", "series",
    "poster_url", "fanart_url", "thumb_url", "trailer_url", "detail_url",
]


def merge(movies: list[Movie]) -> Movie:
    result = Movie()
    for field_name in MOVIE_FIELDS:
        for m in movies:
            val = getattr(m, field_name)
            if val:
                setattr(result, field_name, val)
                break
    for list_field in ("actors", "genres", "tags", "extrafanart_urls"):
        seen: set[str] = set()
        merged: list[str] = []
        for m in movies:
            for item in getattr(m, list_field):
                if item not in seen:
                    seen.add(item)
                    merged.append(item)
        setattr(result, list_field, merged)
    return result


def search_all(code: str, config: dict, session: httpx.Client) -> Movie | None:
    enabled = get_enabled(config)
    if not enabled:
        logger.error("No providers enabled")
        return None

    results: list[Movie] = []
    for name, mod in enabled:
        try:
            logger.info("Searching %s for %s", name, code)
            movie = mod.search(code, session, config)
            if movie:
                movie.source = name
                results.append(movie)
                logger.info("Found %s from %s", code, name)
        except Exception as e:
            logger.warning("Provider %s error for %s: %s", name, code, e)

    if not results:
        return None
    if len(results) == 1:
        return results[0]
    return merge(results)
