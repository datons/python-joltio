"""ESIOS Data manager — preprocessed I90 market data from ClickHouse.

Endpoints:
    /data/metadata  — schema, programs, global stats
    /data/query     — read-only SQL queries
    /data/search    — fuzzy search across dimensions
    /data/dimensions — unit/company/technology lookups
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from joltio.esios.models import (
    DimensionResult,
    MetadataResult,
    QueryResult,
    SearchResult,
)

if TYPE_CHECKING:
    from joltio.client import Client

API_PREFIX = "/data"

Backend = Literal["polars", "pandas"]



_TIME_ZONE = re.compile(r"DateTime(?:64)?\((?:\s*\d+\s*,)?\s*'([^']+)'\s*\)")
_WRAPPER = re.compile(r"^(?:Nullable|LowCardinality)\((.*)\)$")
_INTEGER = re.compile(r"^U?Int(8|16|32|64|128|256)$")
_TEXT = re.compile(r"^(?:String|FixedString\(\d+\)|UUID|IPv[46]|Enum(?:8|16)?\(.*\))$")

ColumnKind = Literal["datetime", "date", "integer", "wide_integer", "float", "bool", "text", "other"]


def _column_kind(column_type: str) -> ColumnKind:
    """Clase de una columna a partir de su tipo de ClickHouse, sin envoltorios Nullable(...) ni LowCardinality(...)."""
    base = column_type.strip()
    while match := _WRAPPER.match(base):
        base = match.group(1).strip()
    if base.startswith("DateTime"):
        return "datetime"
    if base.startswith("Date"):
        return "date"
    integer = _INTEGER.match(base)
    if integer:
        return "integer" if int(integer.group(1)) <= 64 else "wide_integer"
    if base.startswith(("Float", "Decimal")):
        return "float"
    if base == "Bool":
        return "bool"
    if _TEXT.match(base):
        return "text"
    return "other"


def _polars_column(name: str, column_type: str, values: list[Any]) -> pl.Series:
    kind = _column_kind(column_type)
    if kind in ("integer", "wide_integer", "float"):
        # El JSON de ClickHouse envía Int64, UInt64, (U)Int128 y (U)Int256 como texto («96») y el resto como número: se leen como texto y se convierten, y un valor fuera de rango falla en vez de quedar nulo.
        text = pl.Series(name, [None if v is None else str(v) for v in values], dtype=pl.Utf8)
        if kind == "float":
            return text.cast(pl.Float64)
        if kind == "wide_integer" and hasattr(pl, "Int128"):
            return text.cast(pl.Int128)
        return text.cast(pl.Int64)
    if kind == "datetime":
        # Se lee como texto y se convierte con la zona del tipo: con pl.Datetime sin zona, «23:45+02:00» acababa en 21:45 UTC sin zona.
        return pl.Series(name, values, dtype=pl.Utf8).str.to_datetime(time_unit="ms", time_zone=_time_zone(column_type))
    if kind == "date":
        return pl.Series(name, values, dtype=pl.Utf8).str.to_date()
    if kind == "bool":
        return pl.Series(name, values, dtype=pl.Boolean)
    if kind == "text":
        return pl.Series(name, values, dtype=pl.Utf8)
    return pl.Series(name, values)


def _time_zone(column_type: str) -> str | None:
    """Zona declarada en el tipo de ClickHouse: DateTime('Europe/Madrid') o DateTime64(3, 'Europe/Madrid'). Sin zona en el tipo, la columna se deja sin zona."""
    match = _TIME_ZONE.search(column_type)
    return match.group(1) if match else None

class EsiosDataManager:
    """Manager for ESIOS preprocessed data.

    Usage::

        from joltio import Client

        client = Client(token="esd_live_...")

        # SQL query → Polars DataFrame (default)
        df = client.esios.query(
            "SELECT unit, datetime, energy FROM esios.archives_i90 "
            "WHERE program='PDBF' LIMIT 100"
        )

        # SQL query → pandas DataFrame
        df = client.esios.query("SELECT ...", backend="pandas")

        # Metadata (schema, programs, stats)
        meta = client.esios.metadata()

        # Search for dimension values
        results = client.esios.search("iberdrola")

        # Dimension lookup
        techs = client.esios.dimensions("technology")
    """

    def __init__(self, client: Client):
        self._client = client

    def download(
        self,
        table: str,
        start: str | None = None,
        end: str | None = None,
        *,
        path: str,
        since: str | None = None,
        revise_days: int = 0,
        max_wait: float = 3600,
    ) -> list:
        """Write resumable monthly Parquet partitions from the governed Data API."""
        from joltio.data.download import download

        return download(self._client, table, start, end, path=path, since=since, revise_days=revise_days, max_wait=max_wait)

    def query(
        self,
        sql: str,
        *,
        limit: int | None = None,
        backend: Backend = "polars",
    ) -> Any:
        """Execute a read-only SQL query and return a DataFrame.

        Args:
            sql: SQL SELECT query against ``esios.archives_i90`` (per-program
                I90 dispatch) or ``esios.indicators`` (time series).
            limit: Max rows to return. Server enforces 50 for raw queries,
                10000 for aggregated queries.
            backend: DataFrame backend — ``"polars"`` (default) or ``"pandas"``.
                Pandas requires ``pip install joltio[pandas]``.

        Returns:
            Polars or pandas DataFrame with the query results.

        Raises:
            QueryError: On invalid SQL, timeout, or write attempt.
        """
        body: dict = {"sql": sql}
        if limit is not None:
            body["limit"] = limit

        data = self._client.post(f"{API_PREFIX}/query", json=body)
        result = QueryResult.model_validate(data)

        if backend == "pandas":
            return self._to_pandas(result)
        return self._to_polars(result)

    def query_raw(self, sql: str, *, limit: int | None = None) -> QueryResult:
        """Execute a query and return the raw API response (no DataFrame conversion).

        Useful when you need metadata (query_type, truncated, max_rows_applied)
        or want to handle the data yourself.
        """
        body: dict = {"sql": sql}
        if limit is not None:
            body["limit"] = limit

        data = self._client.post(f"{API_PREFIX}/query", json=body)
        return QueryResult.model_validate(data)

    def metadata(
        self,
        *,
        lang: Literal["en", "es"] = "en",
        detail: Literal["summary", "full"] = "summary",
    ) -> MetadataResult:
        """Get dataset metadata: schema, programs, and global statistics.

        Args:
            lang: Language for column descriptions ('en' or 'es').
            detail: 'summary' for lightweight overview (~2.7K tokens),
                'full' for complete stats + categorical values (~5.7K tokens).
        """
        data = self._client.get(
            f"{API_PREFIX}/metadata",
            params={"lang": lang, "detail": detail},
        )
        return MetadataResult.model_validate(data)

    def search(
        self,
        q: str,
        *,
        column: str | None = None,
    ) -> SearchResult:
        """Fuzzy search across all metadata dimensions.

        Searches unit codes, unit names, company names, technologies,
        and other categorical values.

        Args:
            q: Search query (case-insensitive substring match).
            column: Optional column to limit search to.

        Examples::

            client.esios.search("iber")      # → Iberdrola units/companies
            client.esios.search("ciclo")      # → Ciclo Combinado technology
            client.esios.search("CTGN")       # → unit codes CTGN1, CTGN2...
        """
        params: dict = {"q": q}
        if column:
            params["column"] = column

        data = self._client.get(f"{API_PREFIX}/search", params=params)
        return SearchResult.model_validate(data)

    def dimensions(
        self,
        dim: Literal["unit", "company", "technology"] = "unit",
        *,
        detail: Literal["summary", "full"] = "summary",
        q: str | None = None,
    ) -> DimensionResult:
        """Get dimension values (unit registry, companies, technologies).

        Args:
            dim: Dimension to query.
            detail: 'summary' for flat list, 'full' for enriched records.
            q: Optional fuzzy filter.
        """
        params: dict = {"dim": dim, "detail": detail}
        if q:
            params["q"] = q

        data = self._client.get(f"{API_PREFIX}/dimensions", params=params)
        return DimensionResult.model_validate(data)

    def health(self) -> bool:
        """Check if the ESIOS Data API is reachable."""
        try:
            data = self._client.get(f"{API_PREFIX}/health")
            return data.get("status") == "ok"
        except Exception:  # noqa: BLE001
            return False

    def coverage(self, table: str | None = None) -> list[dict]:
        return self._client.get(f"{API_PREFIX}/coverage", params={"table": table} if table else None)

    # -- Internal helpers ------------------------------------------------------

    @staticmethod
    def _to_polars(result: QueryResult) -> pl.DataFrame:
        """Convert a QueryResult to a Polars DataFrame."""
        return pl.DataFrame([_polars_column(col.name, col.type, [row[i] for row in result.rows]) for i, col in enumerate(result.columns)])

    @staticmethod
    def _to_pandas(result: QueryResult) -> Any:
        """Convert a QueryResult to a pandas DataFrame."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for backend='pandas'. "
                "Install it with: pip install joltio[pandas]"
            ) from None

        col_names = [c.name for c in result.columns]
        df = pd.DataFrame(result.rows, columns=col_names)

        for col in result.columns:
            kind = _column_kind(col.type)
            if kind in ("integer", "wide_integer"):
                # Int64/UInt64 y mayores llegan como texto en el JSON de ClickHouse; con nulos se usa el entero anulable de pandas para no pasar a float.
                values = pd.to_numeric(df[col.name])
                df[col.name] = values.astype("Int64") if kind == "integer" and values.isna().any() else values
            elif kind == "float":
                df[col.name] = pd.to_numeric(df[col.name]).astype("float64")
            elif kind == "datetime":
                zone = _time_zone(col.type)
                values = df[col.name]
                if zone is None:
                    df[col.name] = pd.to_datetime(values)
                elif values.astype(str).str.contains(r"[+-]\d{2}:\d{2}$|Z$", regex=True).any():
                    # Con desfase (p. ej. Europe/Madrid, que cambia de +02:00 a +01:00): se pasa por UTC y se lleva a la zona del tipo; sin utc=True, pandas dejaba texto en los días de cambio de hora.
                    df[col.name] = pd.to_datetime(values, utc=True).dt.tz_convert(zone)
                else:
                    df[col.name] = pd.to_datetime(values).dt.tz_localize(zone)
            elif kind == "date":
                df[col.name] = pd.to_datetime(df[col.name])

        return df

    def __repr__(self) -> str:
        return f"EsiosDataManager(base_url='{self._client.base_url}{API_PREFIX}')"
