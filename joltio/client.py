"""Joltio API client.

Central entry point that lazily initializes product-specific managers.
"""

from __future__ import annotations

from importlib.metadata import version
from typing import Any

import httpx

from joltio.config import credential_headers
from joltio.exceptions import AuthenticationError, DatonsError, QueryError, RateLimitError

DEFAULT_BASE_URL = "https://api.joltio.app"
DEFAULT_TIMEOUT = 30.0


def user_agent() -> str:
    """User-Agent de todo lo que `joltio` pide por HTTP. Cloudflare rechaza el de urllib (error 1010), así que ninguna descarga debe usar el suyo por defecto."""
    return f"python-joltio/{version('joltio')}"


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
        _allow_anonymous: bool = False,
        _session_token: str | None = None,
    ):
        self._explicit_credential = api_key is not None or token is not None
        self._session_token = _session_token
        headers = credential_headers(api_key=api_key, token=token, session_token=_session_token)
        self.token = headers.get("X-API-Key") or headers.get("Authorization", "").removeprefix("Bearer ")
        if not self.token and not _allow_anonymous:
            raise DatonsError(
                "Credentials required. Run joltio login, pass api_key=, or set JOLTIO_API_KEY."
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                **headers,
                "User-Agent": user_agent(),
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
            response = self.request_response(method, path, params=params, json=json)
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
            except ValueError:
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

    def _request_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        if not self._explicit_credential:
            self._http.headers.pop("X-API-Key", None)
            self._http.headers.pop("Authorization", None)
            self._http.headers.update(credential_headers(session_token=self._session_token))
        return {**dict(self._http.headers), **(extra or {})}

    def request_response(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None, headers: dict[str, str] | None = None) -> httpx.Response:
        """Petición HTTP cruda compartida con la CLI generada."""
        return self._http.request(method, path, params=params, json=json, headers=self._request_headers(headers))

    def stream_response(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None, headers: dict[str, str] | None = None):
        """Respuesta en streaming para exportaciones tabulares de la CLI."""
        return self._http.stream(method, path, params=params, json=json, headers=self._request_headers(headers))

    # -- Lifecycle -------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        masked = self.token[:8] + "..." if self.token else "None"
        return f"Client(token='{masked}', base_url='{self.base_url}')"
