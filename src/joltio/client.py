"""Joltio API client.

Central entry point that lazily initializes product-specific managers.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from joltio.exceptions import AuthenticationError, DatonsError, QueryError, RateLimitError

DEFAULT_BASE_URL = "https://api.joltio.app"
DEFAULT_TIMEOUT = 30.0


class Client:
    """Client for Joltio Data APIs.

    Usage::

        from joltio import Client

        client = Client(api_key="jol_live_...")
        df = client.data.query("SELECT unit, energy FROM esios.archives_i90 WHERE program='PDBF' LIMIT 10")

    Or with context manager::

        with Client(api_key="jol_live_...") as client:
            df = client.data.query("SELECT ...")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.token = api_key or token or os.getenv("JOLTIO_API_KEY") or os.getenv("DATONS_API_KEY")
        if not self.token:
            from joltio.config import read_api_key

            self.token = read_api_key()
        if not self.token:
            raise DatonsError(
                "API key required. Pass api_key=, set JOLTIO_API_KEY, or run: joltio auth set <KEY>"
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "X-API-Key": self.token,
                "User-Agent": "python-joltio/0.1.0",
            },
            timeout=self.timeout,
        )

        # Lazy-initialized managers
        self._esios: Any = None

    @property
    def data(self):
        return self.esios

    @property
    def esios(self):
        """Access ESIOS preprocessed data (I90, market programs)."""
        if self._esios is None:
            from joltio.esios.manager import EsiosDataManager

            self._esios = EsiosDataManager(self)
        return self._esios

    # -- HTTP primitives (used by managers) ------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """Issue a GET request."""
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """Issue a POST request."""
        return self._request("POST", path, json=json)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict:
        """Execute an HTTP request with error handling."""
        try:
            response = self._http.request(method, path, params=params, json=json)
        except httpx.ConnectError as exc:
            raise DatonsError(f"Connection failed: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise DatonsError(f"Request timed out: {exc}") from exc

        if response.status_code == 401:
            raise AuthenticationError()
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            # Parse structured error body from server
            try:
                body = response.json()
                detail = body.get("detail", body)
            except Exception:
                detail = None
            tier = detail.get("tier") if isinstance(detail, dict) else None
            raise RateLimitError(
                int(retry_after) if retry_after else None,
                tier=tier,
                detail=detail,
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise QueryError(response.status_code, detail)

        return response.json()

    # -- Lifecycle -------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        masked = self.token[:8] + "..." if self.token else "None"
        return f"Client(token='{masked}', base_url='{self.base_url}')"
