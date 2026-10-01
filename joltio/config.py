"""Resolución de sesión y endpoints de la CLI.

La sesión se comparte con la CLI TypeScript de `cli/`: ambas leen y escriben el mismo `~/.config/joltio/session.json` (`{token, baseUrl, apiUrl}`), así que un `joltio login` desde cualquiera de las dos autentica a la otra. Todo es sobreescribible por entorno para CI y despliegues.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: tomllib llega en 3.11 y 0.1 ya soportaba 3.10.
    import tomli as tomllib
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

import typer

DEFAULT_BASE_URL = "https://joltio.app"
DEFAULT_DATA_API_URL = "https://api.joltio.app/data"


class CredentialError(RuntimeError):
    """La credencial guardada no se puede utilizar ni renovar."""
_workspace_override: ContextVar[str | None] = ContextVar("workspace_override", default=None)
_json_output: ContextVar[bool] = ContextVar("json_output", default=False)


def config_dir() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / "joltio"


def _api_key_path() -> Path:
    return config_dir() / "config.toml"


def read_api_key() -> str | None:
    try:
        data = tomllib.loads(_api_key_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("auth", {}).get("api_key")
    return value if isinstance(value, str) and value else None


def write_api_key(api_key: str) -> None:
    if '"' in api_key or "\n" in api_key:
        raise ValueError("La clave contiene caracteres no válidos.")
    path = _api_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        old = path.read_text(encoding="utf-8")
    except OSError:
        old = ""
    section = re.search(r"(?m)^\[auth\]\s*$", old)
    if section:
        end = re.search(r"(?m)^\[[^]]+\]\s*$", old[section.end():])
        stop = section.end() + end.start() if end else len(old)
        body = old[section.end():stop]
        line = f'api_key = "{api_key}"'
        body, count = re.subn(r"(?m)^api_key\s*=.*$", line, body, count=1)
        if not count:
            body = body.rstrip("\n") + "\n" + line + "\n"
        updated = old[:section.end()] + body + old[stop:]
    else:
        updated = old.rstrip("\n") + ("\n\n" if old else "") + f'[auth]\napi_key = "{api_key}"\n'
    path.write_text(updated, encoding="utf-8")
    path.chmod(0o600)


def remove_api_key() -> bool:
    path = _api_key_path()
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    section = re.search(r"(?m)^\[auth\]\s*$", text)
    if section is None:
        return False
    end = re.search(r"(?m)^\[[^]]+\]\s*$", text[section.end():])
    stop = section.end() + end.start() if end else len(text)
    body, count = re.subn(r"(?m)^api_key\s*=.*\n?", "", text[section.end():stop], count=1)
    if not count:
        return False
    path.write_text(text[:section.end()] + body + text[stop:], encoding="utf-8")
    path.chmod(0o600)
    return True


def session_path() -> Path:
    override = os.environ.get("JOLTIO_SESSION")
    return Path(override) if override else config_dir() / "session.json"


@dataclass(frozen=True, slots=True)
class Session:
    token: str | None
    base_url: str
    api_url: str
    workspace: str | None = None
    refresh_token: str | None = None


def _strip(url: str) -> str:
    return url.rstrip("/")


def load_session() -> Session:
    # Precedencia: variables de entorno > fichero de sesión > defaults. JOLTIO_TOKEN gana siempre para escenarios headless (CI, MCP) sin fichero.
    stored: dict[str, str] = {}
    path = session_path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stored = {}
    base_url = _strip(os.environ.get("JOLTIO_URL") or stored.get("baseUrl") or DEFAULT_BASE_URL)
    api_url = _strip(os.environ.get("JOLTIO_API_URL") or stored.get("apiUrl") or base_url)
    token = os.environ.get("JOLTIO_TOKEN") or stored.get("token")
    return Session(token=token, base_url=base_url, api_url=api_url, workspace=stored.get("workspace"), refresh_token=stored.get("refreshToken"))


def credential_headers(*, api_key: str | None = None, token: str | None = None, session_token: str | None = None) -> dict[str, str]:
    key = api_key or token or os.environ.get("JOLTIO_API_KEY")
    if key:
        return {"X-API-Key": key}
    if bearer := os.environ.get("JOLTIO_TOKEN"):
        return {"Authorization": f"Bearer {bearer}"}
    key = os.environ.get("JOLTIO_DATA_API_KEY") or os.environ.get("DATONS_API_KEY") or read_api_key()
    if key:
        return {"X-API-Key": key}
    bearer = current_session_token(session_token)
    return {"Authorization": f"Bearer {bearer}"} if bearer else {}


def current_session_token(fallback: str | None = None) -> str | None:
    session = load_session()
    token = fallback or session.token
    if not token or not session.refresh_token or os.environ.get("JOLTIO_TOKEN"):
        return token
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if float(claims["exp"]) > time.time() + 60:
            return token
    except (IndexError, ValueError, KeyError, TypeError):
        return token
    import httpx

    try:
        response = httpx.post(f"{session.base_url}/api/cli/refresh", json={"refreshToken": session.refresh_token}, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        store_session(token=result["token"], refresh_token=result["refreshToken"], base_url=session.base_url, api_url=session.api_url)
        return result["token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise CredentialError("La sesión no se pudo renovar. Ejecuta `joltio login` de nuevo.") from exc


def effective_workspace() -> str | None:
    return _workspace_override.get() or os.environ.get("JOLTIO_WORKSPACE") or load_session().workspace


def data_api_url() -> str:
    return _strip(os.environ.get("JOLTIO_DATA_API_URL") or DEFAULT_DATA_API_URL)


def set_workspace_override(context: typer.Context, workspace: str | None) -> None:
    token = _workspace_override.set(workspace)
    context.call_on_close(lambda: _workspace_override.reset(token))


def set_json_output(context: typer.Context, enabled: bool) -> None:
    token = _json_output.set(enabled)
    context.call_on_close(lambda: _json_output.reset(token))


def json_output() -> bool:
    return _json_output.get()


def store_workspace(workspace: str) -> Path:
    path = session_path()
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("No hay una sesión guardada. Ejecuta `joltio login`.") from exc
    stored["workspace"] = workspace
    path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)
    return path


def store_session(*, token: str, base_url: str, api_url: str, refresh_token: str | None = None) -> Path:
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous = {}
    path.write_text(
        json.dumps({"token": token, "baseUrl": _strip(base_url), "apiUrl": _strip(api_url), "refreshToken": refresh_token, "workspace": previous.get("workspace")}),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def clear_session() -> bool:
    path = session_path()
    if path.exists():
        path.unlink()
        return True
    return False
