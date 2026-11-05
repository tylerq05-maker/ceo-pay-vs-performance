"""Disk-cached, rate-limited HTTP client.

* Every successful response body is written under ``data/raw`` and served from
  disk on subsequent calls, so nothing is ever downloaded twice.
* A process-wide token bucket keeps SEC traffic under the 10 req/s fair-access
  limit even when several worker threads fetch concurrently.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config


class RateLimiter:
    """Simple thread-safe minimum-interval limiter."""

    def __init__(self, max_per_sec: float):
        self.min_interval = 1.0 / max_per_sec
        self._lock = threading.Lock()
        self._next_ok = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_ok:
                time.sleep(self._next_ok - now)
                now = time.monotonic()
            self._next_ok = now + self.min_interval


_SEC_LIMITER = RateLimiter(config.SEC_MAX_REQUESTS_PER_SEC)
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": config.SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
})


def _cache_path(url: str, cache_dir: Path) -> Path:
    """Map a URL to a stable, human-readable file path inside ``cache_dir``."""
    parsed = urlparse(url)
    tail = parsed.path.strip("/").replace("/", "__")
    if parsed.query:
        tail += "__" + hashlib.md5(parsed.query.encode()).hexdigest()[:10]
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", tail)[-180:]
    return cache_dir / parsed.netloc / tail


def get(url: str, cache_dir: Path | None = None, *, binary: bool = False,
        retries: int = 4, timeout: int = 60) -> str | bytes | None:
    """GET ``url`` with on-disk caching. Returns None on a permanent 404."""
    cache_dir = cache_dir or config.RAW_EDGAR
    path = _cache_path(url, cache_dir)
    if path.exists():
        return path.read_bytes() if binary else path.read_text(encoding="utf-8", errors="replace")
    miss_marker = path.with_suffix(path.suffix + ".404")
    if miss_marker.exists():
        return None

    is_sec = "sec.gov" in urlparse(url).netloc
    last_err: Exception | None = None
    for attempt in range(retries):
        if is_sec:
            _SEC_LIMITER.wait()
        try:
            resp = _SESSION.get(url, timeout=timeout)
        except requests.RequestException as exc:  # network blip
            last_err = exc
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404:
            miss_marker.parent.mkdir(parents=True, exist_ok=True)
            miss_marker.touch()
            return None
        if resp.status_code in (429, 500, 502, 503, 504):
            last_err = RuntimeError(f"HTTP {resp.status_code} for {url}")
            time.sleep(2 ** (attempt + 1))
            continue
        resp.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        return resp.content if binary else resp.content.decode("utf-8", errors="replace")
    raise RuntimeError(f"Failed to GET {url}: {last_err}")
