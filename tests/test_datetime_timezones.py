from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from joltio.esios.manager import EsiosDataManager, _time_zone
from joltio.esios.models import QueryColumn, QueryResult

MADRID = ZoneInfo("Europe/Madrid")

# Formatos tal como los devuelve la Data API (comprobados contra producción el 2026-10-02): con zona en el tipo y desfase en el valor, con zona UTC sin desfase, sin zona y fecha.
RESULT = QueryResult(
    columns=[
        QueryColumn(name="madrid", type="DateTime('Europe/Madrid')"),
        QueryColumn(name="dt64", type="DateTime64(3, 'Europe/Madrid')"),
        QueryColumn(name="utc", type="DateTime('UTC')"),
        QueryColumn(name="sin_zona", type="DateTime"),
        QueryColumn(name="fecha", type="Date"),
    ],
    rows=[
        ["2026-10-01T23:45:00+02:00", "2026-10-25T02:30:00.123000+02:00", "2026-10-25T02:30:00", "2026-10-25T02:30:00", "2026-10-25"],
        # Cambio de hora: las 02:00 se repiten, ahora con +01:00.
        ["2026-10-25T02:00:00+01:00", "2026-10-25T02:30:00.123000+01:00", "2026-10-25T03:30:00", "2026-10-25T03:30:00", "2026-10-26"],
    ],
    row_count=2,
    query_type="raw",
    max_rows_applied=100,
    truncated=False,
)


@pytest.mark.parametrize(
    ("column_type", "zone"),
    [("DateTime('Europe/Madrid')", "Europe/Madrid"), ("DateTime64(3, 'Europe/Madrid')", "Europe/Madrid"), ("DateTime('UTC')", "UTC"), ("DateTime", None), ("Nullable(DateTime('Europe/Madrid'))", "Europe/Madrid")],
)
def test_time_zone_comes_from_the_column_type(column_type, zone):
    assert _time_zone(column_type) == zone


def test_polars_keeps_the_column_time_zone_and_the_wall_clock_hour():
    df = EsiosDataManager._to_polars(RESULT)
    assert df.schema["madrid"] == pl.Datetime("ms", "Europe/Madrid")
    assert df.schema["utc"] == pl.Datetime("ms", "UTC")
    assert df.schema["sin_zona"] == pl.Datetime("ms")
    assert df.schema["fecha"] == pl.Date
    # 23:45 en Madrid, no las 21:45 UTC sin zona de antes.
    assert df["madrid"][0] == datetime(2026, 10, 1, 23, 45, tzinfo=MADRID)
    assert df["madrid"][0].hour == 23
    assert df["utc"][0] == datetime(2026, 10, 25, 2, 30, tzinfo=timezone.utc)
    assert df["fecha"][0] == date(2026, 10, 25)


def test_polars_tells_apart_the_repeated_hour_when_clocks_go_back():
    df = EsiosDataManager._to_polars(RESULT)
    first, second = df["dt64"].to_list()
    assert (first.hour, second.hour) == (2, 2)
    # Mismo reloj de pared, una hora real de diferencia (Python compara por reloj de pared dentro de una zona, por eso el instante).
    assert second.timestamp() - first.timestamp() == 3600
    assert df["dt64"].n_unique() == 2 and df["dt64"].is_sorted()


def test_pandas_keeps_the_column_time_zone_even_across_the_clock_change():
    pd = pytest.importorskip("pandas")
    df = EsiosDataManager._to_pandas(RESULT)
    assert str(df["madrid"].dt.tz) == "Europe/Madrid"
    assert df["madrid"][0] == pd.Timestamp("2026-10-01 23:45", tz="Europe/Madrid")
    # Con desfases distintos (+02:00 y +01:00) pandas dejaba texto; ahora es una columna de fechas con zona.
    assert str(df["dt64"].dtype).startswith("datetime64") and df["dt64"].nunique() == 2
    assert str(df["utc"].dt.tz) == "UTC"
    assert df["sin_zona"].dt.tz is None


def test_empty_result_keeps_the_typed_columns():
    empty = QueryResult(columns=RESULT.columns, rows=[], row_count=0, query_type="raw", max_rows_applied=100, truncated=False)
    df = EsiosDataManager._to_polars(empty)
    assert df.schema["madrid"] == pl.Datetime("ms", "Europe/Madrid") and df.height == 0
