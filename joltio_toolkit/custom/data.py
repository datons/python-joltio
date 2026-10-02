"""Consulta de Data con la identidad existente de la CLI y exportación tabular."""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from io import BytesIO
from pathlib import Path
from typing import Literal

import httpx
import typer

from joltio import Client
from joltio.config import credential_headers
from joltio_toolkit import config, generate, spec
from joltio_toolkit.http import CliError, emit

METADATA_PREFIX = b"# row_count="


def _data_without_metadata(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Deja en stdout solo la tabla: la línea `# row_count=…` que Data antepone al CSV va a stderr.

    Así `joltio data query … --format csv > fichero.csv` produce un CSV válido y Parquet no toma esa línea por la cabecera. El servidor la mantiene para quien lee con `comment='#'`. Solo se aparta esa línea de metadatos, nunca una cabecera que empiece por «#».
    """
    stream = iter(chunks)
    head = b""
    for chunk in stream:
        head += chunk
        if b"\n" in head or len(head) >= len(METADATA_PREFIX):
            break
    if head.startswith(METADATA_PREFIX):
        while b"\n" not in head:
            chunk = next(stream, None)
            if chunk is None:
                break
            head += chunk
        line, _, head = head.partition(b"\n")
        sys.stderr.write(line.decode(errors="replace") + "\n")
    if head:
        yield head
    yield from stream


def query(sql: str, format: Literal["json", "csv", "parquet"] = typer.Option("json", "--format")) -> None:
    session = config.load_session()
    headers = _headers(session.token)
    response_format = "csv" if format == "parquet" else format
    url = f"{config.data_api_url()}/query"
    try:
        with Client(base_url=config.data_api_url(), _allow_anonymous=True, _session_token=session.token) as client, client.stream_response("POST", "/query", params={"format": response_format}, json={"sql": sql}, headers=headers) as response:
            if response.status_code >= 400:
                raise CliError(f"Data respondió {response.status_code}: {response.read().decode(errors='replace')}")
            if format == "json":
                emit(json.loads(response.read()))
            elif format == "csv":
                for chunk in _data_without_metadata(response.iter_bytes()):
                    sys.stdout.buffer.write(chunk)
            else:
                try:
                    import pyarrow.csv as arrow_csv
                    from pyarrow import parquet
                except ImportError as exc:
                    raise CliError('Para Parquet instala `joltio[parquet]`.') from exc

                with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as source:
                    for chunk in _data_without_metadata(response.iter_bytes()):
                        source.write(chunk)
                    source.seek(0)
                    reader = arrow_csv.open_csv(source)
                    with parquet.ParquetWriter(sys.stdout.buffer, reader.schema) as writer:
                        for batch in reader:
                            writer.write_batch(batch)
    except httpx.HTTPError as exc:
        raise CliError(f"No se pudo contactar con Data en {url}: {exc}") from exc


def quickstart(directory: Path = typer.Argument(Path("joltio-quickstart"))) -> None:  # noqa: B008
    """Descarga el mismo cuaderno de inicio que ofrece el panel."""
    url = f"{config.load_session().base_url}/data/docs/quickstart.zip"
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            entries = {Path(item.filename).name: item for item in archive.infolist() if not item.is_dir()}
            expected = {"joltio-quickstart.ipynb", ".env", ".env.example", "README.md"}
            if set(entries) != expected:
                raise CliError("El archivo de inicio no tiene el contenido esperado.")
            directory.mkdir(parents=True, exist_ok=True)
            if any((directory / name).exists() for name in expected):
                raise CliError(f"El directorio {directory} ya contiene ficheros del quickstart.")
            for name, item in entries.items():
                (directory / name).write_bytes(archive.read(item))
    except (httpx.HTTPError, OSError, zipfile.BadZipFile) as exc:
        raise CliError(f"No se pudo descargar el quickstart: {exc}") from exc
    typer.echo(f"Quickstart guardado en {directory}.")


def legacy_search(query: str) -> None:
    from joltio import Client

    with Client() as client:
        emit(client.data.search(query).model_dump())


def legacy_coverage(table: str | None = typer.Option(None, "--table")) -> None:
    from joltio import Client

    with Client() as client:
        emit(client.data.coverage(table))


def legacy_metadata() -> None:
    from joltio import Client

    with Client() as client:
        emit(client.data.metadata().model_dump())


def _headers(token: str | None) -> dict[str, str]:
    headers = credential_headers(session_token=token)
    if not headers:
        raise CliError("No hay sesión de Data. Ejecuta `joltio login` o define JOLTIO_API_KEY.")
    if workspace := config.effective_workspace():
        headers["X-Joltio-Workspace"] = workspace
    return headers


def _request(method: str, path: str, *, query: dict | None = None, body: object | None = None) -> object:
    url = f"{config.data_api_url()}{path}"
    try:
        session = config.load_session()
        with Client(base_url=config.data_api_url(), _allow_anonymous=True, _session_token=session.token) as client:
            response = client.request_response(method.upper(), path, params={key: value for key, value in (query or {}).items() if value is not None}, json=body, headers=_headers(session.token))
        response.raise_for_status()
        return response.json() if response.content else None
    except httpx.HTTPStatusError as exc:
        raise CliError(f"Data respondió {exc.response.status_code}: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise CliError(f"No se pudo contactar con Data en {url}: {exc}") from exc


def _command_parts(path: str, method: str) -> tuple[str, str]:
    parts = [part for part in path.split("/") if part and part != "manage"]
    resource = parts[0]
    trailing = [part for part in parts[1:] if not part.startswith("{")]
    has_id = any(part.startswith("{") for part in parts)
    if trailing:
        verb = trailing[-1]
    elif method == "get":
        verb = "get" if has_id else "list"
    elif method == "post":
        verb = "create"
    elif method == "delete":
        verb = "revoke" if resource == "keys" else "delete"
    else:
        verb = method
    return resource, verb


# Rutas de Data que se exponen como comandos y como tools MCP; el resto (health, guía, GraphQL…) no.
PUBLIC_DATA_PREFIXES = ("/coverage", "/indicators", "/manage/", "/recipes", "/revisions", "/search/", "/tier-info")


def data_api_operations(data_spec: dict, backend_spec: dict | None = None) -> dict[str, str]:
    """operationId de la Data API → nombre público `data_<recurso>_<verbo>`, el mismo para la CLI y para el MCP.

    Las rutas de `/api/data/*` del backend son proxies finos de la Data API para el panel: si el backend ya ofrece una operación (mismo método y ruta, sin `/manage`) o el mismo nombre, se usa la del backend y aquí se omite, para que un agente no vea la misma acción dos veces.
    """
    backend_paths = frozenset()
    taken: frozenset[str] = frozenset()
    if backend_spec is not None:
        backend_paths = frozenset((method, path.removeprefix("/api/data")) for path, methods in backend_spec.get("paths", {}).items() if path.startswith("/api/data/") for method in methods)
        taken = frozenset(operation.get("operationId", "") for methods in backend_spec.get("paths", {}).values() for operation in methods.values() if isinstance(operation, dict))
    names: dict[str, str] = {}
    for path, methods in data_spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method not in generate.HTTP_METHODS or not operation.get("operationId"):
                continue
            if path == "/query" and method == "post":
                name = "data_query"
            elif path.startswith(PUBLIC_DATA_PREFIXES):
                resource, verb = _command_parts(path, method)
                name = f"data_{resource}_{verb}".replace("-", "_")
            else:
                continue
            if (method, path.removeprefix("/manage")) in backend_paths:
                continue
            if name not in taken and name not in names.values():
                names[operation["operationId"]] = name
    return names


def attach(app: typer.Typer) -> None:
    data_spec = spec.load_data_spec()
    if "post" not in data_spec.get("paths", {}).get("/query", {}):
        raise RuntimeError("El esquema de Data no declara POST /query.")
    app.command("query")(query)
    app.command("quickstart")(quickstart)
    app.command("legacy-search", hidden=True)(legacy_search)
    app.command("legacy-coverage", hidden=True)(legacy_coverage)
    app.command("legacy-metadata", hidden=True)(legacy_metadata)
    resources: dict[str, typer.Typer] = getattr(app, "_joltio_resources", {})
    for path, methods in data_spec.get("paths", {}).items():
        if not path.startswith(PUBLIC_DATA_PREFIXES):
            continue
        for method, operation in methods.items():
            if method not in generate.HTTP_METHODS:
                continue
            resource, verb = _command_parts(path, method)
            group = resources.get(resource)
            if group is not None and any(command.name == verb for command in group.registered_commands):
                continue
            if group is None:
                group = typer.Typer(no_args_is_help=True, help=f"Operaciones de {resource} en Data.")
                group.callback()(lambda: None)
                resources[resource] = group
                app.add_typer(group, name=resource)
            operation = {**operation, "operationId": f"data_{resource}_{verb.replace('-', '_')}"}
            group.command(verb, help=operation.get("summary"))(generate.build_command(method, path, operation, "data", request_fn=_request))
