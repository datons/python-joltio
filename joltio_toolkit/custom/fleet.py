"""Importación local de activos sobre el endpoint transaccional de Fleet."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from joltio_toolkit import generate
from joltio_toolkit.http import CliError, emit, request


def import_assets(file: Path, dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"No se pudo leer el inventario JSON: {exc}") from exc
    rows = document.get("assets") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        raise CliError("El inventario debe ser una lista JSON o un objeto con `assets`.")
    emit(request("POST", "/api/fleet/assets/import", query={"dry_run": dry_run}, body={"assets": rows}))


def _deprecated(alias_id: str) -> None:
    old, new = generate.RETIRED_VIEW_ALIASES[alias_id]
    typer.echo(f"Aviso: `joltio {old}` está obsoleto; usa `joltio {new}`.", err=True)


def _retired(alias_id: str) -> None:
    old, new = generate.RETIRED_VIEW_ALIASES[alias_id]
    raise CliError(f"`joltio {old}` fue retirado aguas arriba (9a477e2); usa `joltio {new}`.")


def legacy_views() -> None:
    _deprecated("fleet_views")
    emit(request("GET", "/api/scopes", query={"entity": "asset"}))


def legacy_create_view(data: str | None = typer.Option(None, "--data", "-d")) -> None:
    _retired("fleet_create_view")


def legacy_update_view(view_id: str, data: str | None = typer.Option(None, "--data", "-d")) -> None:
    _retired("fleet_update_view")


def legacy_toggle_view_member(view_id: str, code: str) -> None:
    _retired("fleet_toggle_view_member")


def legacy_set_view_members(view_id: str, data: str = typer.Option(..., "--data", "-d")) -> None:
    payload = generate._parse_body(data)
    if not isinstance(payload, dict) or not isinstance(payload.get("assetCodes"), list):
        raise CliError("El cuerpo de la vista debe contener `assetCodes` como lista.")
    _deprecated("fleet_set_view_members")
    result = request("PUT", f"/api/scopes/{view_id}/members", body={"members": payload["assetCodes"]})
    emit({"id": view_id, "count": result["count"]})


def legacy_delete_view(view_id: str) -> None:
    _deprecated("fleet_delete_view")
    scopes = request("GET", "/api/scopes", query={"entity": "asset"})
    current = next((item for item in scopes if item["id"] == view_id), None)
    measures = request("GET", "/api/measures")
    measure = next((item for item in measures if item["id"] == f"m-{view_id}"), None)
    if current is None and measure is None:
        raise CliError("Esa vista ya no existe como ámbito ni como conjunto de medidas.")
    if current is not None:
        request("DELETE", f"/api/scopes/{view_id}")
    if measure is not None and (current is None or measure["name"] == current["name"]):
        request("DELETE", f"/api/measures/{measure['id']}")
    emit({"id": view_id, "deleted": True})


def attach(app: typer.Typer) -> None:
    resources: dict[str, typer.Typer] = getattr(app, "_joltio_resources", {})
    group = resources.get("assets")
    if group is None:
        group = typer.Typer(no_args_is_help=True, help="Activos de Fleet.")
        group.callback()(lambda: None)
        app.add_typer(group, name="assets")
    group.command("import")(import_assets)
    app.command("views", hidden=True)(legacy_views)
    app.command("create-view", hidden=True)(legacy_create_view)
    app.command("update-view", hidden=True)(legacy_update_view)
    app.command("toggle-view-member", hidden=True)(legacy_toggle_view_member)
    app.command("set-view-members", hidden=True)(legacy_set_view_members)
    app.command("delete-view", hidden=True)(legacy_delete_view)
