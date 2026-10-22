from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import duckdb

from run import ingest, read_supplier_files
from tests.fixtures import make_edge_data, write_prices


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / "input"
        self.db = Path(self.temporary.name) / "warehouse" / "qafila.duckdb"
        make_edge_data(self.data)

    def test_union_preserves_spelling_and_lineage(self):
        rows = read_supplier_files(self.data).to_pylist()
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[0]["unit_cost"], " 2,50 ")
        self.assertEqual(rows[0]["source_row"], 1)
        self.assertEqual(rows[0]["source_file"], "prices_alpha.csv")
        self.assertIsNone(rows[0]["cost_sar"])
        self.assertEqual(rows[5]["cost_sar"], "4.00")

    def test_reingest_replaces_rows_without_duplicates(self):
        ingest(self.data, self.db)
        ingest(self.data, self.db)
        with duckdb.connect(str(self.db), read_only=True) as con:
            self.assertEqual(con.sql("SELECT count(*) FROM raw.supplier_prices").fetchone()[0], 14)
            self.assertEqual(con.sql("SELECT count(*) FROM raw.orders").fetchone()[0], 13)
            self.assertEqual(con.sql("SELECT DISTINCT source_file FROM raw.products").fetchall(), [("qafila_oltp.sqlite",)])
            self.assertEqual(con.sql("SELECT sku FROM raw.products WHERE product_id = 1").fetchone()[0], " A ")

    def test_header_only_file_and_no_files_have_typed_empty_schema(self):
        for path in (self.data / "suppliers").glob("*.csv"):
            path.unlink()
        without_files = read_supplier_files(self.data)
        write_prices(self.data / "suppliers" / "prices_empty.csv", [])
        with_header = read_supplier_files(self.data)
        self.assertEqual(without_files.num_rows, 0)
        self.assertEqual(with_header.schema, without_files.schema)

    def test_malformed_csv_does_not_change_previous_landing(self):
        ingest(self.data, self.db)
        (self.data / "suppliers" / "prices_broken.csv").write_text("sku,valid_from,unit_cost\nA,2026-09-07,2,extra\n")
        with self.assertRaises(ValueError):
            ingest(self.data, self.db)
        with duckdb.connect(str(self.db), read_only=True) as con:
            self.assertEqual(con.sql("SELECT count(*) FROM raw.supplier_prices").fetchone()[0], 14)

    def test_missing_app_table_rolls_back_raw_refresh(self):
        ingest(self.data, self.db)
        with closing(sqlite3.connect(self.data / "qafila_oltp.sqlite")) as app:
            app.execute("DELETE FROM orders")
            app.execute("DROP TABLE stores")
            app.commit()
        with self.assertRaisesRegex(ValueError, "Missing required app table: stores"):
            ingest(self.data, self.db)
        with duckdb.connect(str(self.db), read_only=True) as con:
            self.assertEqual(con.sql("SELECT count(*) FROM raw.orders").fetchone()[0], 13)

    def test_missing_database_is_not_created(self):
        (self.data / "qafila_oltp.sqlite").unlink()
        with self.assertRaises(FileNotFoundError):
            ingest(self.data, self.db)
        self.assertFalse((self.data / "qafila_oltp.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
