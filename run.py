"""Qafila gross margin pipeline: raw files -> DuckDB -> dbt -> Iceberg.

    uv run python run.py --data-dir data --warehouse warehouse

Must work on an empty warehouse folder, and must be safe to run again on the same one.
The grader runs it on a dataset you haven't seen, so never hard-code file names, row counts or SKUs.
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.catalog.sql import SqlCatalog

DBT_DIR = Path(__file__).resolve().parent / "dbt"
APP_TABLES = ("orders", "order_items", "products", "stores")
OUTPUT_SCHEMAS = {
    "silver.product_cost_history": pa.schema([
        ("sku", pa.string()), ("unit_cost_sar", pa.float64()),
        ("valid_from", pa.date32()), ("valid_to", pa.date32()), ("is_current", pa.bool_()),
    ]),
    "gold.weekly_margin": pa.schema([
        ("iso_week", pa.int32()), ("city", pa.string()), ("category", pa.string()),
        ("lines", pa.int32()), ("revenue_sar", pa.float64()),
        ("costed_revenue_sar", pa.float64()), ("cost_sar", pa.float64()),
        ("margin_sar", pa.float64()), ("uncosted_lines", pa.int32()),
    ]),
    "quality.price_quarantine": pa.schema([
        ("source_file", pa.string()), ("sku", pa.string()), ("valid_from", pa.date32()),
        ("raw_cost", pa.string()), ("reason", pa.string()),
    ]),
}


def quote_identifier(name: str) -> str:
    """Quote source column names without treating them as SQL."""
    return '"' + name.replace('"', '""') + '"'


def read_supplier_files(data_dir: Path) -> pa.Table:
    """Keep CSV cells as text, including empty cells and the original cost spelling."""
    columns = {"sku", "unit_cost", "cost_sar", "valid_from"}
    records = []
    for path in sorted((data_dir / "suppliers").glob("prices_*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if (not {"sku", "valid_from"}.issubset(headers)
                    or not {"unit_cost", "cost_sar"}.intersection(headers)):
                raise ValueError(f"{path.name}: expected sku, valid_from and a cost column")
            if len(headers) != len(set(headers)) or {"source_file", "source_row"}.intersection(headers):
                raise ValueError(f"{path.name}: duplicate or reserved CSV column name")
            columns.update(headers)
            for row_number, row in enumerate(reader, start=1):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"{path.name}, row {row_number}: inconsistent CSV field count")
                records.append({**row, "source_file": path.name, "source_row": row_number})
    schema = pa.schema([(name, pa.string()) for name in sorted(columns)]
                       + [("source_file", pa.string()), ("source_row", pa.int64())])
    return pa.Table.from_pylist(records, schema=schema)


def get_catalog(warehouse: Path) -> SqlCatalog:
    """The Iceberg catalog the grader reads. Don't change the name, the URI or the warehouse."""
    warehouse.mkdir(parents=True, exist_ok=True)
    return SqlCatalog("qafila", uri=f"sqlite:///{(warehouse / 'catalog.db').as_posix()}", warehouse=warehouse.resolve().as_posix())


def ingest(data_dir: Path, db: Path) -> None:
    """Step 1: land the sources in DuckDB, schema `raw`, exactly as they arrive.

    - From data_dir/qafila_oltp.sqlite: orders, order_items, products, stores.
    - Every data_dir/suppliers/prices_*.csv, keeping the file name of each row.

    Running this twice must not duplicate anything.
    """
    source = (data_dir / "qafila_oltp.sqlite").resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Missing app database: {source}")
    supplier_rows = read_supplier_files(data_dir)
    db.parent.mkdir(parents=True, exist_ok=True)
    # sqlite3 reads locally without DuckDB downloading an extension. Read-only mode
    # also prevents a mistyped source path from creating a new SQLite database.
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as app:
        app.execute("BEGIN")  # All four app tables come from the same source snapshot.
        with duckdb.connect(str(db)) as con:
            con.execute("BEGIN TRANSACTION")
            try:
                con.execute("CREATE SCHEMA IF NOT EXISTS raw")
                for name in APP_TABLES:
                    info = app.execute(f"PRAGMA table_info({quote_identifier(name)})").fetchall()
                    if not info:
                        raise ValueError(f"Missing required app table: {name}")
                    arrow_types = {"INTEGER": pa.int64(), "REAL": pa.float64(),
                                   "TEXT": pa.string(), "BLOB": pa.binary()}
                    fields = [(col[1], arrow_types[col[2].upper()]) for col in info]
                    schema = pa.schema(fields + [("source_file", pa.string())])
                    empty_rows = pa.Table.from_pylist([], schema=schema)
                    con.register("app_batch", empty_rows)
                    con.execute(f"CREATE OR REPLACE TABLE raw.{name} AS SELECT * FROM app_batch")
                    con.unregister("app_batch")
                    cursor = app.execute(f"SELECT * FROM {quote_identifier(name)}")
                    while batch := cursor.fetchmany(10_000):
                        arrays = [pa.array(values, type=field.type)
                                  for values, field in zip(zip(*batch), schema)]
                        arrays.append(pa.array([source.name] * len(batch), type=pa.string()))
                        con.register("app_batch", pa.Table.from_arrays(arrays, schema=schema))
                        con.execute(f"INSERT INTO raw.{name} SELECT * FROM app_batch")
                        con.unregister("app_batch")
                con.register("supplier_rows", supplier_rows)
                con.execute("CREATE OR REPLACE TABLE raw.supplier_prices AS SELECT * FROM supplier_rows")
                con.unregister("supplier_rows")
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
    print(f"landed four app tables and {supplier_rows.num_rows} supplier rows", flush=True)


def transform(db: Path) -> None:
    """Steps 2-4: build and test the dbt project in dbt/ against the DuckDB file.

    dbt runs in its own process: in this one it would keep the DuckDB file open and block publish().
    """
    env = {**os.environ, "QAFILA_DUCKDB": str(db.resolve()),
           "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    cmd = [sys.executable, "-c", "from dbt.cli.main import cli; cli()",
           "build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    if subprocess.run(cmd, env=env).returncode != 0:
        raise SystemExit("dbt build failed")


def publish(db: Path, warehouse: Path) -> None:
    """Step 5: publish three dbt models to Iceberg (see the brief for the exact columns).

        silver.product_cost_history   gold.weekly_margin   quality.price_quarantine

    Update existing tables in place, never drop and recreate them: the table's snapshots are
    how we see what a number was before the supplier's correction arrived.
    """
    # Check all three Arrow schemas before making any catalog writes. Decimal
    # arithmetic stays inside dbt; the publication boundary uses contract types.
    outputs = {}
    with duckdb.connect(str(db), read_only=True) as con:
        for name, schema in OUTPUT_SCHEMAS.items():
            columns = ", ".join(quote_identifier(field.name) for field in schema)
            outputs[name] = con.execute(f"SELECT {columns} FROM {name}").to_arrow_table().cast(schema)
    catalog = get_catalog(warehouse)
    for name, rows in outputs.items():
        catalog.create_namespace_if_not_exists(name.split(".")[0])
        if catalog.table_exists(name):
            table = catalog.load_table(name)
            previous = table.scan().to_arrow().cast(OUTPUT_SCHEMAS[name])
            if canonical_rows(previous).equals(canonical_rows(rows)):
                print(f"unchanged: {name} ({rows.num_rows} rows)", flush=True)
                continue
            table.overwrite(rows)
        else:
            table = catalog.create_table(name, schema=OUTPUT_SCHEMAS[name])
            table.append(rows)
        snapshot = table.current_snapshot()
        print(f"published: {name} ({rows.num_rows} rows), snapshot "
              f"{snapshot.snapshot_id if snapshot else 'empty'}", flush=True)


def canonical_rows(table: pa.Table) -> pa.Table:
    """Compare row multisets, without depending on scan order or chunk layout."""
    indices = pc.sort_indices(table, sort_keys=[(name, "ascending") for name in table.column_names])
    return table.take(indices).combine_chunks()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--warehouse", type=Path, default=Path("warehouse"))
    args = ap.parse_args()

    args.warehouse.mkdir(parents=True, exist_ok=True)
    db = args.warehouse / "qafila.duckdb"
    ingest(args.data_dir, db)
    transform(db)
    publish(db, args.warehouse)
    print(f"done: {args.warehouse.resolve()}")


if __name__ == "__main__":
    main()
