"""Comandos de administración con flags de producto sobre el API canónico."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from joltio_toolkit import generate
from joltio_toolkit.http import emit, request

workspace_app = typer.Typer(no_args_is_help=True, help="Provisión de workspaces de cliente.")
plan_app = typer.Typer(no_args_is_help=True, help="Planes versionados de Joltio Data.")


@plan_app.command("create")
def plan_create(key: str, definition: Path = typer.Option(..., help="JSON con la definición o las diferencias respecto al plan base."), visibility: str = typer.Option("private"), base_key: str | None = typer.Option(None), default_duration_days: int | None = typer.Option(None)) -> None:
    emit(request("POST", "/api/admin/plans", body={"key": key, "definition": json.loads(definition.read_text()), "visibility": visibility, "base_key": base_key, "default_duration_days": default_duration_days}, workspace_header=False))


@plan_app.command("publish")
def plan_publish(key: str) -> None:
    emit(request("POST", f"/api/admin/plans/{key}/publish", workspace_header=False))


@plan_app.command("show")
def plan_show(key: str) -> None:
    emit(request("GET", f"/api/admin/plans/{key}", workspace_header=False))


@plan_app.command("list")
def plan_list() -> None:
    emit(request("GET", "/api/admin/plans", workspace_header=False))


@plan_app.command("archive")
def plan_archive(key: str) -> None:
    emit(request("POST", f"/api/admin/plans/{key}/archive", workspace_header=False))


@workspace_app.command("provision")
def provision(
    domain: Annotated[list[str], typer.Option(help="Dominio permitido; repite el flag para varios.")],
    name: str = typer.Option(..., help="Nombre del workspace."),
    owner: str = typer.Option(..., help="Correo de un usuario registrado."),
    data: str | None = typer.Option(None, help="Plan de Data."),
    data_seats: int | None = typer.Option(None, "--data-seats"),
    data_plan_version: int | None = typer.Option(None, "--data-plan-version"),
    pulse: str | None = typer.Option(None, help="Plan de Pulse."),
    pulse_seats: int | None = typer.Option(None, "--pulse-seats"),
    fleet: str | None = typer.Option(None, help="Plan de Fleet."),
    fleet_seats: int | None = typer.Option(None, "--fleet-seats"),
    ledger: str | None = typer.Option(None, help="Plan de Ledger."),
    ledger_seats: int | None = typer.Option(None, "--ledger-seats"),
    until: str | None = typer.Option(None, help="Fecha final YYYY-MM-DD."),
    domain_join: str | None = typer.Option(None, "--domain-join"),
    seat_overflow: bool | None = typer.Option(None, "--seat-overflow/--no-seat-overflow", help="Asientos sin límite: las altas reciben asiento aunque se superen los contratados."),
    lifecycle: str | None = typer.Option(None, "--lifecycle", help="Estado comercial del workspace: fija la política de acceso de soporte y el domain_join por defecto. La API indica los valores válidos."),
    owner_seats: bool = typer.Option(False, "--owner-seats"),
    release_owner: bool = typer.Option(False, "--release-owner", help="Retira al --owner como miembro del workspace; exige que ya haya otro owner."),
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
            entry = {"product": product, "plan": plan, "seats": seats}
            if product == "data" and data_plan_version is not None:
                entry["plan_version"] = data_plan_version
            products.append(entry)
    result = request("POST", "/api/admin/workspaces/provision", body={"name": name, "domains": domain, "owner_email": owner, "products": products, "until": until, "domain_join": domain_join, "seat_overflow": seat_overflow, "lifecycle": lifecycle, "owner_seats": True if owner_seats else None, "release_owner": release_owner, "dry_run": dry_run}, workspace_header=False)
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    typer.echo(f"{'Crear' if result['created'] else 'Actualizar'} workspace: {result['name']} ({result['slug'] or 'previsualización'})")
    for change in result["changes"]:
        typer.echo(f"- {change}")
    if not result["changes"]:
        typer.echo("Sin cambios.")


def attach(admin_app: typer.Typer) -> None:
    plan = next((group.typer_instance for group in admin_app.registered_groups if group.name == "plan"), None)
    if plan is None:
        admin_app.add_typer(plan_app, name="plan")
    else:
        for command in plan_app.registered_commands:
            plan.registered_commands.append(command)
    workspace = next((group.typer_instance for group in admin_app.registered_groups if group.name == "workspace"), None)
    if workspace is None:
        admin_app.add_typer(workspace_app, name="workspace")
    else:
        workspace.command("provision")(provision)

    @admin_app.command("provision", hidden=True)
    def legacy_provision(data: str = typer.Option(..., "--data", "-d")) -> None:
        typer.echo("Aviso: `joltio admin provision` está obsoleto; usa `joltio admin workspace provision`.", err=True)
        emit(request("POST", "/api/admin/workspaces/provision", body=generate._parse_body(data), workspace_header=False))
