"""Comandos transversales: `whoami` y el grupo `self` (introspección y refresco del esquema)."""

from __future__ import annotations

import base64
import binascii
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import typer

from joltio_toolkit import config, spec
from joltio_toolkit.http import CliError, emit, request


def _decode_claims(token: str) -> dict[str, Any]:
    # Solo para mostrar: se lee el payload del JWT sin verificar firma (la validación real la hace el backend por JWKS).
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, binascii.Error, json.JSONDecodeError):
        return {}


def whoami() -> None:
    """Muestra la identidad y los endpoints de la sesión activa."""
    session = config.load_session()
    if not session.token:
        raise CliError("No hay sesión activa. Ejecuta `joltio login`.")
    claims = _decode_claims(session.token)
    workspace = config.effective_workspace()
    memberships = request("GET", "/api/workspaces")
    active = next((item for item in memberships if item["id"] == workspace or item["slug"] == workspace), None) if workspace else next((item for item in memberships if item.get("current")), None)
    emit(
        {
            "email": claims.get("email"),
            "user_id": claims.get("sub"),
            "organization_id": claims.get("organization_id"),
            "workspace": active,
            "expires_at": claims.get("exp"),
            "base_url": session.base_url,
            "api_url": session.api_url,
        }
    )


self_app = typer.Typer(no_args_is_help=True, help="Introspección y mantenimiento de la propia CLI.")


@self_app.command("update")
def update() -> None:
    """Actualiza la instalación de uv tool o indica el comando del gestor utilizado."""
    environment = Path(sys.prefix)
    zm = shutil.which("zm")
    if zm:
        status = subprocess.run([zm, "package", "status", "--json"], check=False, capture_output=True, text=True)
        if status.returncode == 0:
            try:
                installed = next((item for item in json.loads(status.stdout) if item.get("name") == "joltio" and item.get("present")), None)
            except (ValueError, TypeError):
                installed = None
            if installed:
                completed = subprocess.run([zm, "package", "sync", "joltio"], check=False)
                if completed.returncode:
                    raise typer.Exit(completed.returncode)
                return
    uv = shutil.which("uv")
    if "/uv/tools/joltio" in str(environment) and uv:
        completed = subprocess.run([uv, "tool", "upgrade", "joltio"], check=False)
        if completed.returncode:
            raise typer.Exit(completed.returncode)
        return
    typer.echo("Instalación Python: ejecuta `python -m pip install --upgrade joltio` o `uv add --upgrade-package joltio joltio` en tu proyecto.")


@self_app.command("info")
def info() -> None:
    """Muestra sesión, endpoints y origen del esquema OpenAPI."""
    session = config.load_session()
    loaded = spec.load_spec()
    cached = spec.cached_spec_path()
    emit(
        {
            "session_file": str(config.session_path()),
            "authenticated": bool(session.token),
            "base_url": session.base_url,
            "api_url": session.api_url,
            "spec_source": "cache" if cached.exists() else "bundled",
            "spec_cache_path": str(cached),
            "api_title": loaded.get("info", {}).get("title"),
            "api_version": loaded.get("info", {}).get("version"),
            "paths": len(loaded.get("paths", {})),
        }
    )


@self_app.command("sync-spec", hidden=True)
def sync_spec() -> None:
    """Refresca el esquema OpenAPI desde el backend del workspace (`/openapi.json`)."""
    session = config.load_session()
    url = f"{session.api_url}/openapi.json"
    headers = {"Authorization": f"Bearer {session.token}"} if session.token else {}
    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        fetched = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise CliError(f"No se pudo obtener el esquema desde {url}: {exc}") from exc
    data_url = f"{config.data_api_url()}/openapi.json"
    try:
        data_response = httpx.get(data_url, headers=headers, timeout=30.0)
        data_response.raise_for_status()
        data_spec = data_response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise CliError(f"No se pudo obtener el esquema de Data desde {data_url}: {exc}") from exc
    path = spec.store_cached_spec(fetched)
    data_path = config.config_dir() / spec.DATA_SPEC
    data_path.write_text(json.dumps(data_spec, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"Esquemas actualizados en {path} y {data_path}. Reabre la CLI para ver los comandos nuevos.")
