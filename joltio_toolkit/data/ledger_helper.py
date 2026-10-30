#!/usr/bin/env python3
"""Convierte el XLSX nativo del representante en la plantilla CSV limpia de Joltio Ledger.

Este helper se ejecuta en el entorno del propietario. Joltio no recibe ni interpreta el formato nativo salvo que el propietario adjunte el crudo opcionalmente para auditoría.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
from datetime import datetime, timedelta
from pathlib import Path

SHEETS = ("DETALLES", "Detalle liquidación C2")
ENERGY_COLUMNS = (
    "Energía MD",
    "Energía S1",
    "Energía S2",
    "Energía S3",
    "Energía bajar continuo",
    "Energía subir continuo",
    "PHF",
    "P48",
    "Cantidad Subir mFRR",
    "Cantidad Bajar mFRR",
    "Cantidad Bajar RT1",
    "Cantidad Bajar RT2",
    "Cantidad Bajar RT5",
    # Continuo (MIC), con el nombre de cada versión del fichero: subir/bajar (C2 antiguo) o vendida/comprada (V2). Las columnas ya traen el signo, así que el MIC neto es su suma.
    "Energía vendida continuo",
    "Energía comprada continuo",
)
TU_COLUMNS = ("MD", "RT", "S1", "S2", "S3", "Balance", "final")
RT_COLUMNS = ("RT1", "RT2", "RT5")


def number(value) -> float:
    try:
        parsed = float(value)
        return 0.0 if math.isnan(parsed) else parsed
    except (TypeError, ValueError):
        return 0.0


def period(fecha, hora: int, quarter: int) -> str:
    day = (
        fecha.date() if isinstance(fecha, datetime) else datetime.strptime(str(fecha)[:10], "%Y-%m-%d").date()
    )
    value = datetime(day.year, day.month, day.day) + timedelta(minutes=(hora - 1) * 60 + (quarter - 1) * 15)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def parse_representante(source: bytes) -> dict[str, dict[str, float | None]]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(source), read_only=True, data_only=True)
    sheet = next((name for name in SHEETS if name in workbook.sheetnames), workbook.sheetnames[0])
    values = list(workbook[sheet].iter_rows(min_row=2, values_only=True))
    header = values[0]
    indexes = {name: index for index, name in enumerate(header) if name}
    resolved = {
        wanted: indexes[actual]
        for wanted in ENERGY_COLUMNS
        for actual in indexes
        if str(actual).strip().startswith(wanted)
    }
    rt_present = any(
        name in resolved for name in ("Cantidad Bajar RT1", "Cantidad Bajar RT2", "Cantidad Bajar RT5")
    )
    result = {}
    for row in values[1:]:
        if row[indexes["Fecha"]] is None:
            continue
        data = {name: number(row[index]) for name, index in resolved.items()}
        rt = {
            "RT1": data.get("Cantidad Bajar RT1", 0.0),
            "RT2": data.get("Cantidad Bajar RT2", 0.0),
            "RT5": data.get("Cantidad Bajar RT5", 0.0),
        }
        result[period(row[indexes["Fecha"]], int(row[indexes["Hora"]]), int(row[indexes["Periodo"]]))] = {
            "MD": data.get("Energía MD", 0.0),
            "RT": sum(rt.values()),
            "S1": data.get("Energía S1", 0.0),
            "S2": data.get("Energía S2", 0.0),
            "S3": data.get("Energía S3", 0.0),
            "Balance": data.get("Cantidad Subir mFRR", 0.0) + data.get("Cantidad Bajar mFRR", 0.0),
            "final": data.get("P48", data.get("PHF", 0.0)),
            "MIC": (
                data.get("Energía subir continuo", 0.0)
                + data.get("Energía bajar continuo", 0.0)
                + data.get("Energía vendida continuo", 0.0)
                + data.get("Energía comprada continuo", 0.0)
            ),
            **(
                {name: value for name, value in rt.items()}
                if rt_present
                else {name: None for name in RT_COLUMNS}
            ),
        }
    return result


def fill(raw: Path, template: Path, output: Path) -> None:
    parsed = parse_representante(raw.read_bytes())
    with template.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
        fields = source.seek(0) or next(csv.reader(source))
    for row in rows:
        values = parsed.get(row["periodo"])
        if values is None:
            continue
        for concept in TU_COLUMNS:
            row[f"tu {concept}"] = f"{float(values[concept] or 0):.4f}"
        if "tu MIC" in row:
            row["tu MIC"] = f"{float(values['MIC']):.4f}"
        for concept in RT_COLUMNS:
            if values[concept] is not None and f"tu {concept}" in row:
                row[f"tu {concept}"] = f"{float(values[concept]):.4f}"
    with output.open("w", encoding="utf-8", newline="") as target:
        target.write("\ufeff")
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rellena una plantilla Joltio Ledger desde el XLSX del representante.")
    parser.add_argument("raw", type=Path)
    parser.add_argument("template", type=Path)
    parser.add_argument("--output", type=Path, default=Path("template_filled.csv"))
    args = parser.parse_args()
    fill(args.raw, args.template, args.output)


if __name__ == "__main__":
    main()
