"""HTTP / REST API collector with retry and rate-limiting."""
import time
import os
import httpx
from typing import Any
from ..utils.logger import logger


class HttpCollector:
    """General-purpose HTTP collector with automatic retries and configurable delay."""

    def __init__(self):
        self.delay = float(os.getenv("REQUEST_DELAY", 1.0))
        self.max_retries = int(os.getenv("MAX_RETRIES", 3))
        self.timeout = int(os.getenv("TIMEOUT", 30))
        self.headers = {"User-Agent": os.getenv("USER_AGENT", "data-collector/1.0")}

    def get(self, url: str, params: dict = None, **kwargs) -> Any:
        """Send a GET request, retrying on failure."""
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"GET {url} (attempt {attempt})")
                with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                    resp = client.get(url, params=params, **kwargs)
                    resp.raise_for_status()
                    time.sleep(self.delay)
                    return resp
            except httpx.HTTPError as e:
                logger.warning(f"Request failed: {e}")
                if attempt == self.max_retries:
                    raise
                time.sleep(self.delay * attempt)
        return None

    def get_json(self, url: str, params: dict = None, **kwargs) -> dict:
        """Fetch and return parsed JSON."""
        resp = self.get(url, params=params, **kwargs)
        return resp.json() if resp else {}
