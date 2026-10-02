from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer
from typer.testing import CliRunner

from joltio import config as library_config
from joltio_toolkit import app as app_module
from joltio_toolkit import config, generate, spec
from joltio_toolkit.app import build_app

runner = CliRunner()

# Spec mínima que ejercita ruta, query, cuerpo y los alias declarados por OpenAPI.
FIXTURE_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Fixture", "version": "9.9.9"},
    "paths": {
        "/api/data/coverage": {
            "get": {"tags": ["data"], "operationId": "data_coverage", "summary": "Cobertura", "responses": {}}
        },
        "/api/fleet/portfolio": {
            "get": {"tags": ["fleet"], "operationId": "fleet_portfolio", "summary": "Cartera", "responses": {}}
        },
        "/api/ledger/overview": {
            "get": {"tags": ["ledger"], "operationId": "ledger_overview", "summary": "Resumen", "responses": {}}
        },
        "/api/ledger/units/{unit_id}/periods/{period}/latest": {
            "get": {
                "tags": ["ledger"],
                "operationId": "ledger_latest",
                "parameters": [
                    {"name": "unit_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "period", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "stage", "in": "query", "required": False, "schema": {"type": "string"}},
                ],
                "responses": {},
            }
        },
        "/api/ledger/assets": {
            "post": {
                "tags": ["ledger"],
                "operationId": "ledger_asset_create",
                "x-legacy-operation-id": "ledger_create_asset",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {}}}},
                "responses": {},
            }
        },
    },
}


class _Capture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json={"ok": True}, request=httpx.Request(method, url))


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> tuple[typer.Typer, _Capture]:
    monkeypatch.delenv("JOLTIO_API_KEY", raising=False)
    monkeypatch.delenv("JOLTIO_TOKEN", raising=False)
    monkeypatch.setattr(library_config, "read_api_key", lambda: None)
    monkeypatch.setattr(spec, "load_spec", lambda: FIXTURE_SPEC)
    monkeypatch.setattr(app_module, "load_spec", lambda: FIXTURE_SPEC)
    monkeypatch.setattr(generate.http, "load_session", lambda: config.Session("tok", "https://x", "https://api.x"))
    monkeypatch.setattr(generate.http, "effective_workspace", lambda: None)
    capture = _Capture()
    monkeypatch.setattr(httpx.Client, "request", lambda client, method, url, **kwargs: capture(method, str(client.base_url).rstrip("/") + url, **kwargs))
    return build_app(), capture


def test_tree_groups_by_module_and_names_actions(cli: tuple[typer.Typer, _Capture]) -> None:
    app, _ = cli
    result = runner.invoke(app, ["ledger", "--help"])
    assert result.exit_code == 0
    assert "overview" in result.stdout and "latest" in result.stdout and "asset" in result.stdout
    assert "create-asset" not in result.stdout


def test_get_sends_path_and_query(cli: tuple[typer.Typer, _Capture]) -> None:
    app, capture = cli
    result = runner.invoke(app, ["ledger", "latest", "U1", "2025-01", "--stage", "final"])
    assert result.exit_code == 0, result.stdout
    call = capture.calls[-1]
    assert call["method"] == "GET"
    assert call["url"] == "https://api.x/api/ledger/units/U1/periods/2025-01/latest"
    assert call["params"] == {"stage": "final"}
    assert call["headers"]["Authorization"] == "Bearer tok"


def test_optional_query_omitted_when_absent(cli: tuple[typer.Typer, _Capture]) -> None:
    app, capture = cli
    result = runner.invoke(app, ["ledger", "latest", "U1", "2025-01"])
    assert result.exit_code == 0, result.stdout
    assert capture.calls[-1]["params"] is None  # None se filtra en http.request


def test_post_parses_json_body(cli: tuple[typer.Typer, _Capture]) -> None:
    app, capture = cli
    result = runner.invoke(app, ["ledger", "asset", "create", "--data", '{"name": "La Palma"}'])
    assert result.exit_code == 0, result.stdout
    assert capture.calls[-1]["json"] == {"name": "La Palma"}


def test_legacy_alias_preserves_response_and_warns(cli: tuple[typer.Typer, _Capture]) -> None:
    app, capture = cli
    modern = runner.invoke(app, ["ledger", "asset", "create", "--data", '{"name":"La Palma"}'])
    legacy = runner.invoke(app, ["ledger", "create-asset", "--data", '{"name":"La Palma"}'])
    assert modern.exit_code == legacy.exit_code == 0
    assert modern.stdout == legacy.stdout
    assert capture.calls[-1]["json"] == capture.calls[-2]["json"]
    assert "joltio ledger asset create" in legacy.stderr


def test_self_update_explains_python_upgrade(cli: tuple[typer.Typer, _Capture], monkeypatch: pytest.MonkeyPatch) -> None:
    from joltio_toolkit.custom import system

    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    app, _ = cli
    result = runner.invoke(app, ["self", "update"])
    assert result.exit_code == 0
    assert "pip install --upgrade joltio" in result.stdout


def test_data_query_uses_session_and_data_api_spec(cli: tuple[typer.Typer, _Capture], monkeypatch: pytest.MonkeyPatch) -> None:

    app, _ = cli
    monkeypatch.setattr(config, "load_session", lambda: config.Session("tok", "https://x", "https://api.x"))
    monkeypatch.setattr(config, "data_api_url", lambda: "https://data.x/data")
    calls: list[dict[str, Any]] = []

    @contextmanager
    def stream(client, method, url, **kwargs):
        full_url = str(client.base_url).rstrip("/") + url
        calls.append({"method": method, "url": full_url, **kwargs})
        yield httpx.Response(200, json={"rows": [{"value": 1}]}, request=httpx.Request(method, full_url))

    monkeypatch.setattr(httpx.Client, "stream", stream)
    result = runner.invoke(app, ["data", "query", "select 1"])
    assert result.exit_code == 0, result.stdout
    assert '"value": 1' in result.stdout
    assert calls[0]["url"] == "https://data.x/data/query"
    assert calls[0]["json"] == {"sql": "select 1"}
    assert calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_post_body_from_file(cli: tuple[typer.Typer, _Capture], tmp_path: Any) -> None:
    app, capture = cli
    payload = tmp_path / "body.json"
    payload.write_text('{"tech": "eólica"}', encoding="utf-8")
    result = runner.invoke(app, ["ledger", "asset", "create", "--data", f"@{payload}"])
    assert result.exit_code == 0, result.stdout
    assert capture.calls[-1]["json"] == {"tech": "eólica"}


def test_invalid_json_body_fails_cleanly(cli: tuple[typer.Typer, _Capture]) -> None:
    app, _ = cli
    with pytest.raises(generate.http.CliError):
        runner.invoke(app, ["ledger", "asset", "create", "--data", "no-json"], catch_exceptions=False)


def test_bundled_spec_builds_full_tree() -> None:
    # El árbol real debe montarse desde el esquema empaquetado sin errores y con los verticales esperados.
    modules = generate.build_module_apps(spec.bundled_spec())
    assert {"ledger", "pulse", "fleet", "artifacts", "entitlements", "workspace", "scopes", "measures"} <= set(modules)
    help_text = runner.invoke(build_app(), ["--help"]).stdout
    assert "leads" not in help_text
    assert "pulse-internal" not in help_text
    assert "core" not in help_text


def test_every_renamed_openapi_command_keeps_a_compatible_hidden_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    bundled = spec.bundled_spec()
    monkeypatch.setattr(app_module, "load_spec", lambda: bundled)
    monkeypatch.setattr(generate.http, "request", lambda *args, **kwargs: {"ok": True})
    app = build_app()
    operations = {operation.get("x-legacy-operation-id", operation["operationId"]): operation for methods in bundled["paths"].values() for method, operation in methods.items() if method in generate.HTTP_METHODS}
    for legacy_id, old_path, new_path in generate.command_mapping(bundled):
        if old_path == new_path or legacy_id == "admin_provision" or legacy_id in generate.RETIRED_VIEW_ALIASES:
            continue
        operation = operations[legacy_id]
        args = []
        for parameter in operation.get("parameters", []):
            if parameter.get("in") == "path":
                args.append("1" if parameter.get("schema", {}).get("type") in {"integer", "number"} else "00000000-0000-0000-0000-000000000001")
            elif parameter.get("in") == "query" and parameter.get("required"):
                args.extend(["--" + parameter["name"].replace("_", "-"), "1"])
        if operation.get("requestBody"):
            args.extend(["--data", "{}"])
        modern = runner.invoke(app, [*new_path.split(), *args])
        legacy = runner.invoke(app, [*old_path.split(), *args])
        assert modern.exit_code == legacy.exit_code == 0, (old_path, new_path, modern.stdout, legacy.stdout, modern.exception, legacy.exception)
        assert modern.stdout == legacy.stdout, (old_path, new_path)
        assert f"joltio {new_path}" in legacy.stderr, (old_path, new_path)


def test_documented_command_mapping_matches_bundled_openapi() -> None:
    documentation = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    rows = generate.command_mapping(spec.bundled_spec())
    assert len(rows) == 137
    for legacy_id, old_path, new_path in rows:
        if legacy_id in generate.RETIRED_VIEW_ALIASES:
            assert f"#### joltio {old_path}\n- Retirado aguas arriba (9a477e2): `joltio {new_path}`." in documentation
        else:
            assert f"#### joltio {old_path}\n- Nuevo: `joltio {new_path}`." in documentation


def test_removed_fleet_view_aliases_name_the_new_commands(cli: tuple[typer.Typer, _Capture]) -> None:
    app, _ = cli
    for command, arguments, hint in (
        ("create-view", [], "scopes create / joltio measures create"),
        ("update-view", ["view-1"], "scopes update / joltio measures update"),
        ("toggle-view-member", ["view-1", "SAGV"], "scopes members add / joltio scopes members remove"),
    ):
        result = runner.invoke(app, ["fleet", command, *arguments])
        assert result.exit_code != 0
        assert f"joltio {hint}" in str(result.exception)


def test_surviving_fleet_view_aliases_use_scopes_and_measures(cli: tuple[typer.Typer, _Capture], monkeypatch: pytest.MonkeyPatch) -> None:
    from joltio_toolkit.custom import fleet

    app, _ = cli
    calls: list[tuple[str, str, Any]] = []

    def fake_request(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path, kwargs.get("body")))
        if method == "GET" and path == "/api/scopes":
            return [{"id": "view-1", "name": "Vista", "kind": "manual"}]
        if method == "GET" and path == "/api/measures":
            return [{"id": "m-view-1", "name": "Vista"}]
        if method == "PUT":
            return {"count": 2}
        return None

    monkeypatch.setattr(fleet, "request", fake_request)
    assert runner.invoke(app, ["fleet", "views"]).exit_code == 0
    assert runner.invoke(app, ["fleet", "set-view-members", "view-1", "--data", '{"assetCodes":["A","B"]}']).exit_code == 0
    assert runner.invoke(app, ["fleet", "delete-view", "view-1"]).exit_code == 0
    assert ("PUT", "/api/scopes/view-1/members", {"members": ["A", "B"]}) in calls
    assert ("DELETE", "/api/scopes/view-1", None) in calls
    assert ("DELETE", "/api/measures/m-view-1", None) in calls


def test_action_name_strips_module_prefix() -> None:
    assert generate.action_name("ledger_get_overview", "ledger") == "get-overview"
    assert generate.action_name("pulse_data_catalog", "pulse") == "data-catalog"


def test_workspace_use_persists_and_generated_requests_switch(monkeypatch, tmp_path):

    monkeypatch.setattr(spec, "load_spec", lambda: FIXTURE_SPEC)
    monkeypatch.setenv("JOLTIO_SESSION", str(tmp_path / "session.json"))
    config.store_session(token="tok", base_url="https://x", api_url="https://api.x")
    capture = _Capture()

    def fake_request(method, url, **kwargs):
        capture.calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/api/workspaces"):
            return httpx.Response(200, json=[{"id": "A", "slug": "alpha", "name": "Alpha", "role": "owner"}, {"id": "B", "slug": "beta", "name": "Beta", "role": "viewer"}], request=httpx.Request(method, url))
        return httpx.Response(200, json={"portfolio": "B"}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", lambda client, method, url, **kwargs: fake_request(method, str(client.base_url).rstrip("/") + url, **kwargs))
    app = build_app()
    assert runner.invoke(app, ["workspace", "use", "beta"]).exit_code == 0
    assert config.load_session().workspace == "beta"
    result = runner.invoke(app, ["fleet", "portfolio"])
    assert result.exit_code == 0, result.stdout
    assert capture.calls[-1]["headers"]["X-Joltio-Workspace"] == "beta"
    monkeypatch.setenv("JOLTIO_WORKSPACE", "beta")
    result = runner.invoke(app, ["--workspace", "alpha", "fleet", "portfolio"])
    assert result.exit_code == 0, result.stdout
    assert capture.calls[-1]["headers"]["X-Joltio-Workspace"] == "alpha"
    result = runner.invoke(app, ["workspace", "list"])
    assert result.exit_code == 0
    assert "* beta" in result.stdout
    assert "X-Joltio-Workspace" not in capture.calls[-1]["headers"]


def test_workspace_env_and_non_member_rejection(monkeypatch, tmp_path):
    from joltio_toolkit import http

    monkeypatch.setattr(spec, "load_spec", lambda: FIXTURE_SPEC)
    monkeypatch.setenv("JOLTIO_SESSION", str(tmp_path / "session.json"))
    monkeypatch.setenv("JOLTIO_WORKSPACE", "beta")
    config.store_session(token="tok", base_url="https://x", api_url="https://api.x")
    capture = _Capture()

    def fake_request(method, url, **kwargs):
        capture.calls.append(kwargs)
        return httpx.Response(403, json={"detail": "No perteneces al workspace solicitado."}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", lambda client, method, url, **kwargs: fake_request(method, str(client.base_url).rstrip("/") + url, **kwargs))
    with pytest.raises(http.CliError, match="No perteneces"):
        runner.invoke(build_app(), ["fleet", "portfolio"], catch_exceptions=False)
    assert capture.calls[-1]["headers"]["X-Joltio-Workspace"] == "beta"


def test_whoami_shows_effective_workspace(monkeypatch, tmp_path):

    monkeypatch.setattr(spec, "load_spec", lambda: FIXTURE_SPEC)
    monkeypatch.setenv("JOLTIO_SESSION", str(tmp_path / "session.json"))
    config.store_session(token="tok", base_url="https://x", api_url="https://api.x")

    def fake_request(method, url, **kwargs):
        return httpx.Response(200, json=[{"id": "A", "slug": "alpha", "name": "Alpha", "role": "owner", "current": True}], request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", lambda client, method, url, **kwargs: fake_request(method, str(client.base_url).rstrip("/") + url, **kwargs))
    result = runner.invoke(build_app(), ["whoami"])
    assert result.exit_code == 0, result.stdout
    assert '"slug": "alpha"' in result.stdout


def test_mcp_uses_effective_workspace(monkeypatch, tmp_path):
    import fastmcp
    import httpx2

    from joltio_toolkit.custom import mcp

    monkeypatch.setenv("JOLTIO_SESSION", str(tmp_path / "session.json"))
    config.store_session(token="tok", base_url="https://x", api_url="https://api.x")
    config.store_workspace("beta")
    monkeypatch.setattr(mcp, "load_spec", lambda: FIXTURE_SPEC)
    monkeypatch.setattr(mcp, "load_data_spec", lambda: {"paths": {"/query": {"post": {"operationId": "run_query_query_post"}}}})
    clients = []
    mounted = []

    def fake_client(**kwargs):
        clients.append(kwargs)
        return object()

    class Server:
        def mount(self, server):
            mounted.append(server)

        def run(self):
            return None

    monkeypatch.setattr(httpx2, "AsyncClient", fake_client)
    monkeypatch.setattr(fastmcp.FastMCP, "from_openapi", lambda **kwargs: Server())
    mcp.mcp()
    # Backend y Data API: las dos con la misma credencial y el workspace efectivo.
    assert [client["headers"] for client in clients] == [{"Authorization": "Bearer tok", "X-Joltio-Workspace": "beta"}] * 2
    assert clients[1]["base_url"] == config.data_api_url()
    assert len(mounted) == 1


def test_admin_workspace_provision_flags_and_json(cli: tuple[typer.Typer, _Capture]) -> None:
    app, capture = cli
    result = runner.invoke(app, ["admin", "workspace", "provision", "--name", "Energía Ejemplo", "--domain", "ejemplo.es", "--owner", "owner@datons.com", "--data", "pilot", "--data-seats", "5", "--pulse", "starter", "--pulse-seats", "5", "--fleet", "starter", "--fleet-seats", "5", "--until", "2026-12-31", "--domain-join", "auto", "--dry-run", "--json"])
    assert result.exit_code == 0, result.stdout
    assert capture.calls[-1]["url"] == "https://api.x/api/admin/workspaces/provision"
    assert capture.calls[-1]["json"] == {"name": "Energía Ejemplo", "domains": ["ejemplo.es"], "owner_email": "owner@datons.com", "products": [{"product": "data", "plan": "pilot", "seats": 5}, {"product": "pulse", "plan": "starter", "seats": 5}, {"product": "fleet", "plan": "starter", "seats": 5}], "until": "2026-12-31", "domain_join": "auto", "owner_seats": False, "dry_run": True}
