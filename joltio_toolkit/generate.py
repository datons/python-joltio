"""OpenAPI → árbol Typer: operationId determina módulo, recurso y verbo."""

from __future__ import annotations

import inspect
import json
import keyword
import sys
from collections.abc import Callable
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from joltio_toolkit import http

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_TYPE_MAP: dict[str, type] = {"integer": int, "number": float, "boolean": bool, "string": str}
FUTURE_MODULES = frozenset({"alerts"})
NEW_MODULES = frozenset({"measures", "scopes"})
FUTURE_OPERATION_IDS = frozenset({"fleet_measure_catalog_get", "fleet_portfolio_units_get"})
EXCLUDED_MODULES = frozenset({"core", "leads", "pulse-internal", "workspaces"}) | FUTURE_MODULES
EXCLUDED_PATH_FRAGMENTS = ("/public/", "/internal/")
MODULE_ALIASES = {"entitlements": "workspace"}
NEW_OPERATION_IDS = frozenset({"fleet_assets_import", "workspace_invitation_create"}) | FUTURE_OPERATION_IDS
RETIRED_VIEW_ALIASES = {
    "fleet_create_view": ("fleet create-view", "scopes create / joltio measures create"),
    "fleet_delete_view": ("fleet delete-view", "scopes delete / joltio measures delete"),
    "fleet_set_view_members": ("fleet set-view-members", "scopes members set"),
    "fleet_toggle_view_member": ("fleet toggle-view-member", "scopes members add / joltio scopes members remove"),
    "fleet_update_view": ("fleet update-view", "scopes update / joltio measures update"),
    "fleet_views": ("fleet views", "scopes list"),
}


def _py_type(schema: dict[str, Any] | None) -> type:
    return _TYPE_MAP.get((schema or {}).get("type", "string"), str)


def _sanitize(name: str) -> str:
    clean = "".join(ch if ch.isalnum() else "_" for ch in name)
    if clean and clean[0].isdigit():
        clean = f"_{clean}"
    if keyword.iskeyword(clean):
        clean = f"{clean}_"
    return clean or "arg"


def module_of(operation: dict[str, Any]) -> str:
    tags = operation.get("tags")
    return tags[0] if tags else "core"


def action_name(operation_id: str, module: str) -> str:
    prefix = f"{module}_"
    core = operation_id.removeprefix(prefix)
    return core.replace("_", "-")


def command_parts(operation_id: str, module: str) -> tuple[str, ...]:
    core = operation_id.removeprefix(f"{module}_")
    parts = core.split("_")
    if len(parts) < 2:
        return (core.replace("_", "-"),)
    return ("-".join(parts[:-1]), parts[-1])


def included_operation(module: str, path: str, operation: dict[str, Any]) -> bool:
    return module not in EXCLUDED_MODULES and operation.get("operationId") not in FUTURE_OPERATION_IDS and not any(fragment in path for fragment in EXCLUDED_PATH_FRAGMENTS) and not operation.get("x-cli-hidden", False)


def command_mapping(spec: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for module, operations in group_operations(spec).items():
        if module in FUTURE_MODULES | NEW_MODULES:
            continue
        for _, path, operation in operations:
            operation_id = operation["operationId"]
            if operation_id in NEW_OPERATION_IDS:
                continue
            legacy_id = operation.get("x-legacy-operation-id", operation_id)
            old_module = module_of(operation)
            old_action = action_name(legacy_id, old_module)
            public_module = MODULE_ALIASES.get(module, module)
            new_path = " ".join((public_module, *command_parts(operation_id, public_module)))
            rows.append((legacy_id, f"{old_module} {old_action}", new_path))
    rows.extend((legacy_id, *paths) for legacy_id, paths in RETIRED_VIEW_ALIASES.items())
    return sorted(rows)


def group_operations(spec: dict[str, Any]) -> dict[str, list[tuple[str, str, dict[str, Any]]]]:
    modules: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            modules.setdefault(module_of(operation), []).append((method.lower(), path, operation))
    for ops in modules.values():
        ops.sort(key=lambda item: item[2].get("operationId", item[1]))
    return modules


def _parse_body(raw: str | None) -> Any | None:
    if raw is None:
        return None
    if raw == "-":
        raw = sys.stdin.read()
    elif raw.startswith("@"):
        try:
            with open(raw[1:], encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as exc:
            raise http.CliError(f"No se pudo leer el cuerpo desde {raw[1:]}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise http.CliError(f"El cuerpo --data no es JSON válido: {exc}") from exc


def build_command(method: str, path: str, operation: dict[str, Any], module: str, *, request_fn: Callable[..., Any] | None = None):
    # Reúne parámetros de ruta y query del esquema; el mapa cli→api traduce nombres saneados de vuelta a los reales al construir la petición.
    params: list[inspect.Parameter] = []
    binding: dict[str, tuple[str, str]] = {}

    for spec_param in operation.get("parameters", []):
        location = spec_param.get("in")
        if location not in ("path", "query"):
            continue
        api_name = spec_param["name"]
        py_name = _sanitize(api_name)
        py_type = _py_type(spec_param.get("schema"))
        help_text = spec_param.get("description") or f"{api_name} ({location})"
        if location == "path":
            annotation = Annotated[py_type, typer.Argument(help=help_text)]
            params.append(inspect.Parameter(py_name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation))
        elif spec_param.get("required"):
            annotation = Annotated[py_type, typer.Option(help=help_text)]
            params.append(inspect.Parameter(py_name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation))
        else:
            annotation = Annotated[py_type | None, typer.Option(help=help_text)]
            params.append(inspect.Parameter(py_name, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=annotation))
        binding[py_name] = (location, api_name)

    request_body = operation.get("requestBody")
    body_required = bool(request_body and request_body.get("required"))
    if request_body:
        help_body = "Cuerpo JSON: texto literal, @fichero.json o - para stdin"
        if body_required:
            annotation = Annotated[str, typer.Option("--data", "-d", help=help_body)]
            params.append(inspect.Parameter("data", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation))
        else:
            annotation = Annotated[str | None, typer.Option("--data", "-d", help=f"{help_body} (opcional)")]
            params.append(inspect.Parameter("data", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=annotation))

    def callback(**kwargs: Any) -> None:
        query: dict[str, Any] = {}
        real_path = path
        for py_name, (location, api_name) in binding.items():
            value = kwargs.get(py_name)
            if location == "path":
                real_path = real_path.replace("{" + api_name + "}", str(value))
            else:
                query[api_name] = value
        body = _parse_body(kwargs.get("data")) if request_body else None
        http.emit((request_fn or http.request)(method, real_path, query=query, body=body))

    params.sort(key=lambda parameter: parameter.default is not inspect.Parameter.empty)
    callback.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    callback.__annotations__ = {p.name: p.annotation for p in params}
    callback.__name__ = _sanitize(action_name(operation["operationId"], module))
    callback.__doc__ = operation.get("summary") or operation.get("description") or None
    return callback


def build_module_apps(spec: dict[str, Any], *, skip: frozenset[str] = frozenset(), skip_operation_ids: frozenset[str] = frozenset()) -> dict[str, typer.Typer]:
    apps: dict[str, typer.Typer] = {}
    seen: set[tuple[str, ...]] = set()
    callbacks: dict[str, Any] = {}
    for module, operations in sorted(group_operations(spec).items()):
        if module in skip:
            continue
        public_module = MODULE_ALIASES.get(module, module)
        sub = apps.setdefault(public_module, typer.Typer(no_args_is_help=True, help=f"Operaciones REST de {public_module}."))
        # Un callback vacío fuerza semántica de grupo aunque el módulo tenga una sola operación (Typer, si no, colapsaría el subcomando).
        if not sub.registered_callback:
            sub.callback()(lambda: None)
        resources: dict[str, typer.Typer] = getattr(sub, "_joltio_resources", {})
        sub._joltio_resources = resources
        for method, path, operation in operations:
            if operation.get("operationId") in skip_operation_ids:
                continue
            hidden = not included_operation(module, path, operation)
            operation_id = operation["operationId"]
            parts = command_parts(operation_id, public_module)
            key = (public_module, *parts)
            if key in seen:
                raise ValueError(f"Comando OpenAPI duplicado: {' '.join(key)}")
            seen.add(key)
            callback = build_command(method, path, operation, public_module)
            callbacks[" ".join(key)] = callback
            if len(parts) == 1:
                sub.command(parts[0], help=operation.get("summary"), hidden=hidden)(callback)
            else:
                resource, verb = parts
                group = resources.get(resource)
                if group is None:
                    group = typer.Typer(no_args_is_help=True, help=f"Operaciones de {resource}.")
                    group.callback()(lambda: None)
                    resources[resource] = group
                    sub.add_typer(group, name=resource, hidden=hidden)
                group.command(verb, help=operation.get("summary"), hidden=hidden)(callback)
    for _, old_path, new_path in command_mapping(spec):
        if old_path in {paths[0] for paths in RETIRED_VIEW_ALIASES.values()}:
            continue
        callback = callbacks.get(new_path)
        if callback is None or old_path == new_path:
            continue
        old_module, old_name = old_path.split(" ", 1)
        if (old_module, old_name) in seen:
            continue
        sub = apps.setdefault(old_module, typer.Typer(no_args_is_help=True, help=f"Alias antiguos de {old_module}."))
        if not sub.registered_callback:
            sub.callback()(lambda: None)

        def make_alias(target, old, new):
            def deprecated(**kwargs: Any) -> None:
                typer.echo(f"Aviso: `joltio {old}` está obsoleto; usa `joltio {new}`.", err=True)
                target(**kwargs)
            deprecated.__signature__ = target.__signature__
            deprecated.__annotations__ = target.__annotations__
            deprecated.__name__ = f"legacy_{_sanitize(old)}"
            return deprecated

        resources = getattr(sub, "_joltio_resources", {})
        if old_name in resources:
            group = resources[old_name]
            verb = new_path.split()[-1]

            def make_group_alias_class(old: str, new: str, action: str):
                class LegacyGroup(TyperGroup):
                    def parse_args(self, ctx, args):
                        if not args or (args[0] not in self.commands and args[0] != "--help"):
                            typer.echo(f"Aviso: `joltio {old}` está obsoleto; usa `joltio {new}`.", err=True)
                            args = [action, *args]
                        return super().parse_args(ctx, args)
                return LegacyGroup

            group.info.cls = make_group_alias_class(old_path, new_path, verb)
        else:
            sub.command(old_name, hidden=True)(make_alias(callback, old_path, new_path))
        seen.add((old_module, old_name))
    return apps
