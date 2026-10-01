"""Delegación de la autoría local al motor Svelte/esbuild de Joltio."""

from __future__ import annotations

import hashlib
import os
import platform
import shlex
import shutil
import subprocess
import tempfile
import urllib.request
import webbrowser
from importlib.metadata import version
from pathlib import Path

import typer

from joltio.config import credential_headers
from joltio_toolkit import config
from joltio_toolkit.http import CliError, emit, request

# dev/build/init/validate compilan localmente (no-REST). El resto de la superficie de artefactos ya vive como REST en `joltio artifacts <acción>`.
DELEGATED_SUBCOMMANDS = ("init", "dev", "build", "validate", "preview", "publish", "pull", "versions")

_PASSTHROUGH = {"context_settings": {"allow_extra_args": True, "ignore_unknown_options": True}}


def _download_engine() -> Path:
    system = {"Darwin": "macos", "Linux": "linux"}.get(platform.system())
    machine = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(platform.machine())
    if not system or not machine:
        raise CliError("No hay motor de Joltio para esta plataforma. Define JOLTIO_APP_ENGINE.")
    release = version("joltio")
    name = f"joltio-app-engine-{system}-{machine}"
    base = f"https://cdn.joltio.app/cli/engine/{release}"
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    target = data_home / "joltio" / "engine" / release / name
    saved_checksum = target.parent / f"{name}.sha256"
    try:
        if target.exists() and saved_checksum.exists():
            expected = saved_checksum.read_text(encoding="ascii").strip()
            if hashlib.sha256(target.read_bytes()).hexdigest() == expected:
                return target
            raise CliError("El checksum del motor instalado no coincide con el publicado; no se ejecutará.")
        with urllib.request.urlopen(f"{base}/SHA256SUMS", timeout=30) as response:
            sums = response.read().decode("ascii")
        expected = next(line.split()[0] for line in sums.splitlines() if line.split()[1:] == [name])
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() == expected:
                return target
            raise CliError("El checksum del motor instalado no coincide con el publicado; no se ejecutará.")
        with urllib.request.urlopen(f"{base}/{name}", timeout=60) as response:
            binary = response.read()
        if hashlib.sha256(binary).hexdigest() != expected:
            raise CliError("El checksum del motor descargado no coincide; no se ejecutará.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as pending:
            pending.write(binary)
            pending_path = Path(pending.name)
        pending_path.chmod(0o755)
        pending_path.replace(target)
        saved_checksum.write_text(expected, encoding="ascii")
        saved_checksum.chmod(0o600)
        return target
    except (OSError, UnicodeError, StopIteration, IndexError) as exc:
        raise CliError(f"No se pudo descargar o verificar el motor de Joltio: {exc}") from exc


def _dev_source() -> Path | None:
    override = os.environ.get("JOLTIO_CLI_SRC")
    candidate = Path(override) if override else Path(__file__).resolve().parents[3] / "cli" / "src" / "index.ts"
    return candidate if candidate.exists() else None


def resolve_engine() -> list[str]:
    override = os.environ.get("JOLTIO_APP_ENGINE") or os.environ.get("JOLTIO_ARTIFACT_CLI")
    if override:
        return shlex.split(override)

    source = _dev_source()
    if source is not None:
        bun = shutil.which("bun")
        if bun is None:
            raise CliError("La autoría de apps requiere `joltio-app-engine`. Instala el paquete Joltio o define JOLTIO_APP_ENGINE; en desarrollo instala Bun.")
        return [bun, "run", str(source)]

    return [str(_download_engine())]


def _delegate(subcommand: str, extra: list[str]) -> None:
    engine = resolve_engine()
    session = config.load_session()
    env = os.environ.copy()
    env.update({"JOLTIO_URL": session.base_url, "JOLTIO_API_URL": session.api_url})
    headers = credential_headers(session_token=session.token)
    if "X-API-Key" in headers:
        env["JOLTIO_TOKEN"] = headers["X-API-Key"]
    if workspace := config.effective_workspace():
        env["JOLTIO_WORKSPACE"] = workspace
    completed = subprocess.run([*engine, subcommand, *extra], check=False, env=env)
    if completed.returncode != 0:
        raise typer.Exit(completed.returncode)


def attach(sub: typer.Typer) -> None:
    # Se cuelgan del grupo `artifacts` generado desde OpenAPI: mismo árbol, sin colisión con las acciones REST (create-project, list-functions, publish-project…).
    def _make(subcommand: str):
        def command(ctx: typer.Context) -> None:
            _delegate(subcommand, ctx.args)

        command.__name__ = subcommand
        command.__doc__ = f"`{subcommand}` del toolchain de artefactos (delegado al motor Bun)."
        return command

    for subcommand in DELEGATED_SUBCOMMANDS:
        sub.command(subcommand, **_PASSTHROUGH)(_make(subcommand))
    sub.command("list")(list_artifacts)
    sub.command("open")(open_artifact)
    sub.command("share")(share_artifact)


def list_artifacts() -> None:
    """Lista los artefactos visibles en el workspace."""
    emit(request("GET", "/api/artifacts/catalog")["artifacts"])


def open_artifact(artifact_id: str) -> None:
    """Abre un artefacto en el navegador."""
    webbrowser.open(f"{config.load_session().base_url}/panel/artefactos/{artifact_id}")


def share_artifact(artifact_id: str, visibility: str = "common", group_id: str | None = None) -> None:
    """Cambia la visibilidad de un artefacto."""
    emit(request("PATCH", f"/api/artifacts/{artifact_id}/visibility", body={"visibility": visibility, "group_id": group_id}))


def attach_legacy_root(root: typer.Typer) -> None:
    """Conserva las órdenes de la antigua CLI TypeScript sin mostrarlas en la ayuda."""
    for subcommand in DELEGATED_SUBCOMMANDS:
        def make_command(action: str):
            def command(ctx: typer.Context) -> None:
                typer.echo(f"Aviso: `joltio {action}` está obsoleto; usa `joltio artifacts {action}`.", err=True)
                _delegate(action, ctx.args)
            command.__name__ = f"legacy_{action}"
            return command
        root.command(subcommand, hidden=True, **_PASSTHROUGH)(make_command(subcommand))

    @root.command("functions", hidden=True)
    def legacy_functions() -> None:
        typer.echo("Aviso: `joltio functions` está obsoleto; usa `joltio artifacts functions list`.", err=True)
        emit(request("GET", "/api/artifacts/functions")["functions"])

    @root.command("ls", hidden=True)
    def legacy_list() -> None:
        typer.echo("Aviso: `joltio ls` está obsoleto; usa `joltio artifacts catalog list`.", err=True)
        list_artifacts()

    @root.command("open", hidden=True)
    def legacy_open(artifact_id: str) -> None:
        typer.echo("Aviso: `joltio open` está obsoleto; usa `joltio artifacts open`.", err=True)
        open_artifact(artifact_id)

    @root.command("share", hidden=True)
    def legacy_share(artifact_id: str, visibility: str = "common", group_id: str | None = None) -> None:
        typer.echo("Aviso: `joltio share` está obsoleto; usa `joltio artifacts share`.", err=True)
        share_artifact(artifact_id, visibility, group_id)
