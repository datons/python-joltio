"""Selección del workspace de la CLI."""

from __future__ import annotations

from typing import Annotated, Literal

import typer

from joltio_toolkit import config
from joltio_toolkit.http import CliError, emit, request

workspace_app = typer.Typer(no_args_is_help=True, help="Lista y selecciona tus workspaces.")


def memberships() -> list[dict[str, str]]:
    return request("GET", "/api/workspaces", workspace_header=False)


@workspace_app.command("list")
def list_workspaces() -> None:
    """Lista los workspaces a los que perteneces."""
    current = config.effective_workspace()
    items = memberships()
    if config.json_output():
        emit(items)
        return
    for item in items:
        marker = "*" if current in (item["id"], item["slug"]) or (current is None and item.get("current")) else " "
        typer.echo(f"{marker} {item['slug']:<24} {item['name']:<32} {item['role']}")


@workspace_app.command("use")
def use(workspace: str) -> None:
    """Guarda el workspace predeterminado por id o slug."""
    selected = next((item for item in memberships() if workspace in (item["id"], item["slug"])), None)
    if selected is None:
        raise CliError("No perteneces al workspace solicitado.")
    try:
        config.store_workspace(selected["slug"])
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    typer.echo(f"Workspace activo: {selected['name']} ({selected['slug']}).")


def show() -> None:
    """Muestra el workspace efectivo."""
    current = config.effective_workspace()
    selected = next((item for item in memberships() if current in (item["id"], item["slug"]) or (current is None and item.get("current"))), None)
    if selected is None:
        raise CliError("No hay un workspace activo. Ejecuta `joltio workspace use <slug>`. ")
    emit(selected)


def invite(email: str, role: Literal["member", "admin"] = "member", product: Annotated[list[str] | None, typer.Option("--product")] = None, type: Literal["join", "create"] = "join") -> None:
    """Invita a una persona al workspace activo."""
    result = request("POST", "/api/workspaces/invitations", body={"email": email, "role": role, "type": type, "products": product or []})
    if config.json_output():
        emit(result)
    else:
        typer.echo(f"Invitación enviada a {email} ({'nuevo workspace' if type == 'create' else 'unirse al workspace'}{'; productos: ' + ', '.join(product) if product else ''}).")


def attach(app: typer.Typer) -> None:
    app.command("list")(list_workspaces)
    app.command("use")(use)
    app.command("show")(show)
    app.command("invite")(invite)


def attach_legacy_root(root: typer.Typer) -> None:
    @root.command("invite", hidden=True)
    def legacy_invite(ctx: typer.Context, email: str, type: Literal["create", "join"] = "create", role: Literal["member", "admin"] = "member", product: Annotated[list[str] | None, typer.Option("--product")] = None, workspace: str | None = None) -> None:
        typer.echo("Aviso: `joltio invite` está obsoleto; usa `joltio workspace invite`.", err=True)
        if workspace:
            config.set_workspace_override(ctx, workspace)
        invite(email=email, role=role, product=product, type=type)
