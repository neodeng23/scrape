from __future__ import annotations

import time
from pathlib import Path


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float,
        retries: int,
        follow_redirects: bool,
        user_agent: str,
        request_interval_seconds: float = 0.0,
    ):
        import httpx

        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=follow_redirects,
            headers={"User-Agent": user_agent},
        )
        self._retries = max(retries, 1)
        self._request_interval_seconds = max(request_interval_seconds, 0.0)
        self._last_request_at = 0.0

    def close(self) -> None:
        self._client.close()

    def _sleep_if_needed(self) -> None:
        if self._request_interval_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get_text(self, url: str) -> str:
        last_error: Exception | None = None
        for _ in range(self._retries):
            try:
                self._sleep_if_needed()
                response = self._client.get(url)
                self._last_request_at = time.monotonic()
                response.raise_for_status()
                return response.text
            except Exception as exc:
                last_error = exc
        if last_error is None:
            raise RuntimeError(f"Failed to fetch URL: {url}")
        raise last_error

    def download(self, url: str, destination: Path) -> Path:
        last_error: Exception | None = None
        destination.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(self._retries):
            try:
                self._sleep_if_needed()
                with self._client.stream("GET", url) as response:
                    self._last_request_at = time.monotonic()
                    response.raise_for_status()
                    with destination.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
                return destination
            except Exception as exc:
                last_error = exc
        if last_error is None:
            raise RuntimeError(f"Failed to download URL: {url}")
        raise last_error
