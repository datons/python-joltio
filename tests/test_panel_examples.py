import json
import sys
import types
from pathlib import Path

import httpx
import polars as pl
import pytest

import joltio.client

# Fixture generado desde frontend/src/lib/data/code-examples.ts (python-examples.test.ts lo mantiene al día): son los fragmentos que el panel y el cuaderno de arranque enseñan a los clientes.
EXAMPLES = json.loads((Path(__file__).parent / "fixtures" / "panel_python_examples.json").read_text(encoding="utf-8"))
QUERY_RESPONSE = {
    "columns": [{"name": "day", "type": "Date"}, {"name": "avg_price", "type": "Float64"}],
    "rows": [["2026-09-30", 104.7]],
    "row_count": 1,
    "query_type": "aggregated",
    "max_rows_applied": 50,
    "truncated": False,
}


@pytest.mark.parametrize("example", EXAMPLES, ids=[example["id"] for example in EXAMPLES])
def test_panel_example_runs_against_current_library(example, monkeypatch, tmp_path):
    # Sin sesión ni clave reales de la máquina: el ejemplo solo puede usar la clave del entorno, como en el panel.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("JOLTIO_API_KEY", "jol_live_example")
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=QUERY_RESPONSE)

    real_client = httpx.Client
    monkeypatch.setattr(joltio.client.httpx, "Client", lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(respond), **kwargs))
    # El cuaderno carga .env con python-dotenv, que no es dependencia de `joltio`.
    monkeypatch.setitem(sys.modules, "dotenv", types.SimpleNamespace(find_dotenv=lambda **_: "", load_dotenv=lambda *_, **__: False))

    namespace: dict[str, object] = {"__name__": "__main__"}
    exec(compile(example["code"], example["id"], "exec"), namespace)

    assert requests, "el ejemplo no llegó a consultar la API"
    assert all(request.url.path == "/data/query" for request in requests)
    if "df" in namespace:
        assert isinstance(namespace["df"], pl.DataFrame)
