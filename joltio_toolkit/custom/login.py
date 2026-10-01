"""Comando `joltio login`: flujo PKCE por loopback, idéntico al de la CLI TypeScript.

Comparte contrato y fichero de sesión con `cli/` (misma pareja `/cli/authorize` → `/api/cli/token`, mismo `~/.config/joltio/session.json`), así que autenticarse aquí sirve para ambas CLIs. No reimplementa la identidad: reutiliza Better Auth del backend.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import threading
import urllib.parse
import webbrowser

import httpx
import typer

from joltio_toolkit import config
from joltio_toolkit.http import CliError

CALLBACK_TIMEOUT_SECONDS = 120.0


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _code_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    expected_state: str = ""
    received_code: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        code = (query.get("code") or [None])[0]
        state = (query.get("state") or [None])[0]
        if parsed.path != "/callback" or state != type(self).expected_state or not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("Solicitud de autorización no válida.".encode())
            return
        type(self).received_code = code
        self.send_response(200)
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Joltio CLI autenticado. Ya puedes cerrar esta pestaña.".encode())

    def log_message(self, format: str, *args: object) -> None:  # silencia el log de acceso del servidor
        return


def login(
    open_browser: bool = typer.Option(True, "--open-browser/--no-open-browser", help="Abrir el navegador automáticamente."),
) -> None:
    """Autentica la sesión de la CLI contra el workspace de Joltio."""
    session = config.load_session()
    state = _b64url(secrets.token_bytes(24))
    verifier = _b64url(secrets.token_bytes(48))

    handler = type("_Handler", (_CallbackHandler,), {"expected_state": state, "received_code": None})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    authorize = httpx.URL(f"{session.base_url}/cli/authorize").copy_merge_params(
        {"redirect_uri": redirect_uri, "state": state, "code_challenge": _code_challenge(verifier)}
    )
    typer.echo(f"Abriendo {authorize} …")
    if open_browser:
        webbrowser.open(str(authorize))
    else:
        typer.echo("Abre esa URL en tu navegador para continuar.")

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(CALLBACK_TIMEOUT_SECONDS)
    server.server_close()

    code = handler.received_code
    if not code:
        raise CliError("La autenticación no se completó (tiempo agotado o respuesta inválida).")

    try:
        response = httpx.post(
            f"{session.base_url}/api/cli/token",
            json={"code": code, "codeVerifier": verifier},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise CliError(f"No se pudo canjear el código: {exc}") from exc
    if response.status_code >= 400:
        raise CliError(f"Joltio rechazó el canje del código ({response.status_code}).")
    token = response.json().get("token")
    refresh_token = response.json().get("refreshToken")
    if not token:
        raise CliError("Joltio no devolvió un token de terminal.")

    path = config.store_session(token=token, refresh_token=refresh_token, base_url=session.base_url, api_url=session.api_url)
    typer.echo(f"Sesión de Joltio guardada en {path}.")


def logout() -> None:
    """Elimina la sesión guardada."""
    session = config.load_session()
    if session.refresh_token:
        try:
            response = httpx.post(f"{session.base_url}/api/cli/logout", json={"refreshToken": session.refresh_token}, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CliError(f"No se pudo revocar la sesión: {exc}") from exc
    typer.echo("Sesión eliminada." if config.clear_session() else "No había ninguna sesión guardada.")
