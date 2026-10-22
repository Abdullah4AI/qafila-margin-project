"""Hand-sized source files with deliberately visible boundary cases."""

from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from pathlib import Path


def write_prices(path: Path, rows: list[tuple[str, str, str]], *, modern: bool = False, bom: bool = False) -> None:
    with path.open("w", newline="", encoding="utf-8-sig" if bom else "utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sku", "valid_from", "cost_sar" if modern else "unit_cost"])
        writer.writerows(rows)


def make_edge_data(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    suppliers = directory / "suppliers"
    suppliers.mkdir()
    with closing(sqlite3.connect(directory / "qafila_oltp.sqlite")) as db:
        db.executescript("""
            CREATE TABLE products (product_id INTEGER PRIMARY KEY, sku TEXT, category TEXT, unit_price REAL);
            CREATE TABLE stores (store_id TEXT PRIMARY KEY, city TEXT);
            CREATE TABLE orders (order_id INTEGER PRIMARY KEY, store_id TEXT, status TEXT, created_at TEXT);
            CREATE TABLE order_items (order_id INTEGER, line_no INTEGER, product_id INTEGER,
                                      quantity INTEGER, unit_price REAL, discount REAL);
        """)
        db.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", [
            (1, " A ", "Pantry", 10.0), (2, "B", "Dairy", 20.0),
            (3, "C", "Pantry", 30.0), (4, "D", "Dairy", 1.0),
        ])
        db.execute("INSERT INTO stores VALUES ('S1', 'Riyadh')")
        cases = [
            ("2026-08-30 20:59:59", "delivered", 1, 1, 10.0, 0.0),
            ("2026-08-30 21:00:00", "delivered", 1, 2, 10.0, 1.0),
            ("2026-09-06 20:59:59", "delivered", 1, 1, 10.0, 0.0),
            ("2026-09-06 21:00:00", "delivered", 1, 1, 10.0, 0.0),
            ("2026-09-13 21:00:00", "delivered", 1, 1, 10.0, 0.0),
            ("2026-09-20 21:00:00", "delivered", 1, 1, 10.0, 0.0),
            ("2026-09-06 21:00:00", "delivered", 2, 1, 20.0, 0.0),
            ("2026-09-13 21:00:00", "delivered", 2, 1, 20.0, 0.0),
            ("2026-09-27 21:00:00", "delivered", 3, 1, 30.0, 0.0),
            ("2026-09-20 21:00:00", "cancelled", 1, 1, 10.0, 0.0),
            ("2026-09-20 21:00:00", "delivered", 1, 0, 10.0, 0.0),
            ("2026-09-20 21:00:00", "delivered", 1, -1, 10.0, 0.0),
            ("2026-09-13 21:00:00", "delivered", 4, 1, 1.0, 0.0),
        ]
        for order_id, (created, status, product, quantity, price, discount) in enumerate(cases, 1):
            db.execute("INSERT INTO orders VALUES (?, 'S1', ?, ?)", (order_id, status, created))
            db.execute("INSERT INTO order_items VALUES (?, 1, ?, ?, ?, ?)", (order_id, product, quantity, price, discount))
        db.commit()
    write_prices(suppliers / "prices_alpha.csv", [
        ("A ", "2026-08-31", " 2,50 "), ("A", "2026-09-07", "2.500"),
        ("A", "2026-09-21", "4.00"), ("B ", "2026-09-14", "٩٫٤٩"),
        ("D", "2026-09-14", "0.004"),
    ], bom=True)
    write_prices(suppliers / "prices_beta.csv", [
        ("A", "2026-09-21", "4.00"), ("A", "2026-09-07", "-1"),
        (" UNKNOWN ", "2026-09-07", "-1"), ("C", "2026-09-07", "NaN"),
        ("C", "2026-09-07", "Infinity"), ("C", "2026-09-07", ""),
        ("C", "2026-09-07", "broken"), ("C", "2026-09-07", "0"),
        ("C", "2026-09-07", ""),
    ], modern=True)


def add_edge_correction(directory: Path) -> None:
    # Both files revise the same key: zzz sorts last even when it is written first.
    write_prices(directory / "suppliers" / "prices_zzz_fix.csv", [("A", "2026-09-21", "3.25")], modern=True)
    write_prices(directory / "suppliers" / "prices_zz_fix.csv", [("A", "2026-09-21", "3.50")], modern=True)
