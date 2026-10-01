"""Cliente HTTP con la identidad de la sesión y presentación de respuestas.

Una sola ruta de red para todos los comandos REST autogenerados: adjunta el bearer de la sesión, resuelve la URL contra `api_url` y traduce los fallos a mensajes accionables (401 → `joltio login`).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import typer

from joltio import Client
from joltio.config import credential_headers
from joltio_toolkit.config import effective_workspace, load_session


class CliError(RuntimeError):
    """Fallo esperado y presentable; el punto de entrada lo imprime y sale con código ≠ 0."""


def request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: Any | None = None,
    workspace_header: bool = True,
) -> Any:
    # No se bloquea del lado cliente por falta de token: se adjunta si existe y se deja que el backend decida (endpoints públicos como leads no lo requieren). Un 401 se traduce a un mensaje que invita a `joltio login`.
    session = load_session()
    headers = credential_headers(session_token=session.token)
    workspace = effective_workspace()
    if workspace and workspace_header:
        headers["X-Joltio-Workspace"] = workspace
    url = f"{session.api_url}{path}"
    params = {k: v for k, v in (query or {}).items() if v is not None}
    try:
        with Client(base_url=session.api_url, _allow_anonymous=True, _session_token=session.token) as client:
            response = client.request_response(method.upper(), path, params=params or None, json=body if body is not None else None, headers=headers)
    except httpx.HTTPError as exc:
        raise CliError(f"No se pudo contactar con {url}: {exc}") from exc

    if response.status_code == 401:
        raise CliError("Sesión inválida o caducada. Ejecuta `joltio login` de nuevo.")
    if response.status_code == 403:
        raise CliError(_error_detail(response) or "El workspace no tiene acceso a este recurso.")
    if response.status_code >= 400:
        raise CliError(_error_detail(response) or f"La API respondió {response.status_code}.")

    if not response.content:
        return None
    try:
        return response.json()
    except json.JSONDecodeError:
        return response.text


def _error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text or None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, list):  # errores de validación de FastAPI
        return "; ".join(str(item.get("msg", item)) for item in detail)
    return str(detail) if detail is not None else json.dumps(payload, ensure_ascii=False)


def emit(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        typer.echo(value)
    else:
        typer.echo(json.dumps(value, indent=2, ensure_ascii=False))
