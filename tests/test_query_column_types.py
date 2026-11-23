import polars as pl
import pytest

from joltio.esios.manager import EsiosDataManager
from joltio.esios.models import QueryColumn, QueryResult

# Valores tal como los devuelve la Data API (comprobados contra producción el 2026-11-23): el JSON de ClickHouse envía UInt64, Int64 y los enteros de 128/256 bits como texto, y Decimal, Bool y los enteros pequeños como valores JSON.
RESULT = QueryResult(
    columns=[
        QueryColumn(name="day", type="Date"),
        QueryColumn(name="n", type="UInt64"),
        QueryColumn(name="n32", type="UInt32"),
        QueryColumn(name="nullable", type="Nullable(UInt64)"),
        QueryColumn(name="wide", type="Int128"),
        QueryColumn(name="price", type="Decimal(18, 4)"),
        QueryColumn(name="flag", type="Bool"),
        QueryColumn(name="label", type="LowCardinality(String)"),
    ],
    rows=[
        ["2026-11-10", "96", 96, "96", "96", 171.384, True, "96"],
        ["2026-11-11", "92", 92, None, "92", 150.5, False, "92"],
    ],
    row_count=2,
    query_type="raw",
    max_rows_applied=100,
    truncated=False,
)


def test_polars_reads_integers_sent_as_text_as_integer_columns():
    df = EsiosDataManager._to_polars(RESULT)
    assert df.schema["n"] == pl.Int64
    assert df.schema["n32"] == pl.Int64
    assert df.schema["nullable"] == pl.Int64
    assert df.schema["wide"].is_integer()
    assert df.schema["price"] == pl.Float64
    assert df.schema["flag"] == pl.Boolean
    assert df.schema["label"] == pl.Utf8
    assert df["n"].to_list() == [96, 92]
    assert df["nullable"].to_list() == [96, None]
    assert df["price"].to_list() == [171.384, 150.5]


def test_pandas_reads_integers_sent_as_text_as_integer_columns():
    pd = pytest.importorskip("pandas")
    df = EsiosDataManager._to_pandas(RESULT)
    assert pd.api.types.is_integer_dtype(df["n"]) and df["n"].tolist() == [96, 92]
    assert pd.api.types.is_integer_dtype(df["nullable"]) and df["nullable"].isna().tolist() == [False, True]
    assert pd.api.types.is_float_dtype(df["price"])
