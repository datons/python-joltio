"""ESIOS Data — preprocessed Spanish electricity market data from ClickHouse."""

from joltio.esios.manager import EsiosDataManager
from joltio.esios.models import (
    ColumnInfo,
    DimensionResult,
    MetadataResult,
    ProgramInfo,
    QueryResult,
    SearchResult,
)

__all__ = [
    "ColumnInfo",
    "DimensionResult",
    "EsiosDataManager",
    "MetadataResult",
    "ProgramInfo",
    "QueryResult",
    "SearchResult",
]
