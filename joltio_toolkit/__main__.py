"""Punto de entrada de la consola `joltio`.

Envuelve la app Typer para presentar los `CliError` (fallos esperados: sin sesión, 4xx, cuerpo inválido) como un mensaje limpio con salida ≠ 0, en vez de un traceback.
"""

from __future__ import annotations

import sys

import typer

from joltio.config import CredentialError
from joltio_toolkit.app import build_app
from joltio_toolkit.http import CliError


def app() -> None:
    cli = build_app()
    try:
        cli()
    except (CliError, CredentialError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        sys.exit(1)


if __name__ == "__main__":
    app()
