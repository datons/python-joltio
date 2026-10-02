"""Comando `joltio mcp`: servidor MCP fino que proxya al backend remoto del workspace.

Misma fuente (el OpenAPI canónico) y mismos nombres de tool que el MCP del servidor, pero pensado para el portátil del usuario: no necesita el backend instalado, solo la sesión. Un host de agente (Claude Desktop, Cursor…) lo lanza por stdio y habla con `api_url` usando el bearer de la sesión.
"""

from __future__ import annotations

from importlib.metadata import version

import typer

from joltio.config import credential_headers
from joltio_toolkit.config import data_api_url, effective_workspace, load_session
from joltio_toolkit.custom.data import data_api_operations
from joltio_toolkit.http import CliError
from joltio_toolkit.spec import load_data_spec, load_spec

# Mismas exclusiones que el MCP del servidor: nada público ni de infraestructura como tool de agente.
_EXCLUDE_PATTERNS = (r"^/api/[^/]+/public/.*", r"^/health$", r"^/openapi\.json$")


def mcp() -> None:
    """Arranca un servidor MCP (stdio) que expone la API de Joltio como tools."""
    try:
        import httpx2
        from fastmcp import FastMCP
        from fastmcp.server.providers.openapi import MCPType, RouteMap
    except ImportError as exc:
        raise CliError('Instala MCP con `uv tool install "joltio[mcp]"` o `pip install "joltio[mcp]"`.') from exc

    session = load_session()
    headers = credential_headers(session_token=session.token)
    if not headers:
        raise CliError("No hay sesión activa. Ejecuta `joltio login` antes de arrancar el MCP.")

    # fastmcp genera el cliente OpenAPI sobre httpx2 (httpx.AsyncClient está deprecado ahí).
    workspace = effective_workspace()
    if workspace:
        headers["X-Joltio-Workspace"] = workspace
    client = httpx2.AsyncClient(
        base_url=session.api_url,
        headers=headers,
        timeout=30.0,
    )
    backend_spec = load_spec()
    server = FastMCP.from_openapi(
        openapi_spec=backend_spec,
        client=client,
        name="joltio",
        version=version("joltio"),
        route_maps=[RouteMap(pattern=pattern, mcp_type=MCPType.EXCLUDE) for pattern in _EXCLUDE_PATTERNS],
    )
    # La Data API (consultas SQL, cobertura, indicadores…) es otro servicio con su propio OpenAPI: se monta con los mismos nombres que la CLI (`data_query`, `data_coverage_list`…) y la misma credencial y workspace.
    data_spec = load_data_spec()
    data_names = data_api_operations(data_spec, backend_spec)
    data_server = FastMCP.from_openapi(
        openapi_spec=data_spec,
        client=httpx2.AsyncClient(base_url=data_api_url(), headers=headers, timeout=60.0),
        name="joltio-data",
        route_map_fn=lambda route, mcp_type: None if route.operation_id in data_names else MCPType.EXCLUDE,
        mcp_names=data_names,
    )
    server.mount(data_server)
    typer.echo(f"Servidor MCP de Joltio (stdio) contra {session.api_url}", err=True)
    server.run()
