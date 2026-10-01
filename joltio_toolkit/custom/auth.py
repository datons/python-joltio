"""API keys compartidas con la librería y alias de joltio 0.1.0."""

import typer

from joltio.config import read_api_key, remove_api_key, write_api_key

auth_app = typer.Typer(no_args_is_help=True, help="Gestiona la clave API local.")


@auth_app.command("set")
def set_key(key: str) -> None:
    """Guarda una clave API para la librería y la CLI."""
    typer.echo("Aviso: `joltio auth set` es un alias de compatibilidad.", err=True)
    write_api_key(key)
    typer.echo("Clave API guardada.")


@auth_app.command("show")
def show_key() -> None:
    """Muestra una clave local enmascarada."""
    typer.echo("Aviso: `joltio auth show` es un alias de compatibilidad.", err=True)
    key = read_api_key()
    if not key:
        raise typer.Exit(1)
    typer.echo(f"Clave API: {key[:8]}…{key[-4:]}")


@auth_app.command("remove")
def remove_key() -> None:
    """Elimina la clave API local."""
    typer.echo("Aviso: `joltio auth remove` es un alias de compatibilidad.", err=True)
    typer.echo("Clave API eliminada." if remove_api_key() else "No había una clave API local.")
