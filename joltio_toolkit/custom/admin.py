"""Comandos de administración con flags de producto sobre el API canónico."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from joltio_toolkit import generate
from joltio_toolkit.http import emit, request

workspace_app = typer.Typer(no_args_is_help=True, help="Provisión de workspaces de cliente.")


@workspace_app.command("provision")
def provision(
    domain: Annotated[list[str], typer.Option(help="Dominio permitido; repite el flag para varios.")],
    name: str = typer.Option(..., help="Nombre del workspace."),
    owner: str = typer.Option(..., help="Correo de un usuario registrado."),
    data: str | None = typer.Option(None, help="Plan de Data."),
    data_seats: int | None = typer.Option(None, "--data-seats"),
    pulse: str | None = typer.Option(None, help="Plan de Pulse."),
    pulse_seats: int | None = typer.Option(None, "--pulse-seats"),
    fleet: str | None = typer.Option(None, help="Plan de Fleet."),
    fleet_seats: int | None = typer.Option(None, "--fleet-seats"),
    ledger: str | None = typer.Option(None, help="Plan de Ledger."),
    ledger_seats: int | None = typer.Option(None, "--ledger-seats"),
    until: str | None = typer.Option(None, help="Fecha final YYYY-MM-DD."),
    domain_join: str | None = typer.Option(None, "--domain-join"),
    owner_seats: bool = typer.Option(False, "--owner-seats"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Crea o actualiza un workspace sin enviar invitaciones."""
    products = []
    for product, plan, seats in (("data", data, data_seats), ("pulse", pulse, pulse_seats), ("fleet", fleet, fleet_seats), ("ledger", ledger, ledger_seats)):
        if plan is None and seats is not None:
            raise typer.BadParameter(f"--{product}-seats requiere --{product} <plan>.")
        if plan is not None and seats is None:
            raise typer.BadParameter(f"--{product}-seats es obligatorio con --{product}.")
        if plan is not None:
            products.append({"product": product, "plan": plan, "seats": seats})
    result = request("POST", "/api/admin/workspaces/provision", body={"name": name, "domains": domain, "owner_email": owner, "products": products, "until": until, "domain_join": domain_join, "owner_seats": owner_seats, "dry_run": dry_run}, workspace_header=False)
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    typer.echo(f"{'Crear' if result['created'] else 'Actualizar'} workspace: {result['name']} ({result['slug'] or 'previsualización'})")
    for change in result["changes"]:
        typer.echo(f"- {change}")
    if not result["changes"]:
        typer.echo("Sin cambios.")


def attach(admin_app: typer.Typer) -> None:
    admin_app.add_typer(workspace_app, name="workspace")

    @admin_app.command("provision", hidden=True)
    def legacy_provision(data: str = typer.Option(..., "--data", "-d")) -> None:
        typer.echo("Aviso: `joltio admin provision` está obsoleto; usa `joltio admin workspace provision`.", err=True)
        emit(request("POST", "/api/admin/workspaces/provision", body=generate._parse_body(data), workspace_header=False))
