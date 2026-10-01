"""Ensamblado del árbol `joltio`: módulos REST autogenerados + comandos custom (no-REST)."""

from __future__ import annotations

import typer

from joltio_toolkit import config, generate
from joltio_toolkit.custom import admin as admin_cmd
from joltio_toolkit.custom import artifacts as artifacts_cmd
from joltio_toolkit.custom import auth as auth_cmd
from joltio_toolkit.custom import data as data_cmd
from joltio_toolkit.custom import fleet as fleet_cmd
from joltio_toolkit.custom import login as login_cmd
from joltio_toolkit.custom import mcp as mcp_cmd
from joltio_toolkit.custom import system as system_cmd
from joltio_toolkit.custom import workspace as workspace_cmd
from joltio_toolkit.spec import load_spec

HELP = "Joltio · CLI. Los grupos por módulo se autogeneran del OpenAPI canónico; los comandos transversales viven en custom/."


def build_app() -> typer.Typer:
    root = typer.Typer(no_args_is_help=True, help=HELP, add_completion=True)

    @root.callback()
    def options(ctx: typer.Context, workspace: str | None = typer.Option(None, "--workspace", help="Workspace para este comando (id o slug)."), json_output: bool = typer.Option(False, "--json", help="Emite una respuesta JSON.")) -> None:
        if workspace is not None and not workspace.strip():
            raise typer.BadParameter("Indica un id o slug de workspace.")
        config.set_workspace_override(ctx, workspace)
        config.set_json_output(ctx, json_output)

    module_apps = generate.build_module_apps(load_spec(), skip_operation_ids=frozenset({"admin_workspace_provision", "fleet_assets_import"}))
    # La autoría de artefactos (dev/build/init/validate, delegada a Bun) se cuelga del grupo `artifacts` generado.
    if "artifacts" in module_apps:
        artifacts_cmd.attach(module_apps["artifacts"])
    if "fleet" in module_apps:
        fleet_cmd.attach(module_apps["fleet"])
    if "data" in module_apps:
        data_cmd.attach(module_apps["data"])
    admin_app = module_apps.setdefault("admin", typer.Typer(no_args_is_help=True, help="Administración de Joltio."))
    admin_cmd.attach(admin_app)
    workspace_app = module_apps.setdefault("workspace", typer.Typer(no_args_is_help=True, help="Workspaces de Joltio."))
    workspace_cmd.attach(workspace_app)
    for name, sub in module_apps.items():
        root.add_typer(sub, name=name, hidden=name in generate.EXCLUDED_MODULES or name == "entitlements")

    # custom/ — todo lo que no es una operación REST del backend.
    root.command("login")(login_cmd.login)
    root.command("logout")(login_cmd.logout)
    root.command("whoami")(system_cmd.whoami)
    root.command("mcp")(mcp_cmd.mcp)
    root.add_typer(auth_cmd.auth_app, name="auth")
    root.add_typer(system_cmd.self_app, name="self")
    artifacts_cmd.attach_legacy_root(root)
    workspace_cmd.attach_legacy_root(root)
    return root
