"""Run full source-to-Iceberg checks, serially, without additional packages.

    uv run python -m tests.integration
    uv run python -m tests.integration --seeds 11 --work-dir warehouse/check-11

The work directory must be new. It contains generated inputs, run logs and a JSON
report; use an ignored path (the default is below warehouse/). No SQL model or
pipeline calculation is used to produce the expected answers.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.types import BooleanType, DateType, DoubleType, IntegerType, StringType

from tests.fixtures import add_edge_correction, make_edge_data
from tests.reference import COLUMNS, assert_matches, comparable, compute

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TYPES = {
    "silver.product_cost_history": [pa.string(), pa.float64(), pa.date32(), pa.date32(), pa.bool_()],
    "gold.weekly_margin": [pa.int32(), pa.string(), pa.string(), pa.int32(), *([pa.float64()] * 4), pa.int32()],
    "quality.price_quarantine": [pa.string(), pa.string(), pa.date32(), pa.string(), pa.string()],
}
ICEBERG_TYPES = {
    pa.string(): StringType(), pa.float64(): DoubleType(), pa.date32(): DateType(),
    pa.bool_(): BooleanType(), pa.int32(): IntegerType(),
}


def command(arguments: list[str], log: Path) -> None:
    environment = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", "PYTHONHASHSEED": "0"}
    with log.open("w") as stream:
        result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=environment,
                                stdout=stream, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        tail = "\n".join(log.read_text().splitlines()[-45:])
        raise AssertionError(f"Command failed ({result.returncode}); log: {log}\n{tail}")


def pipeline(data: Path, warehouse: Path, log: Path) -> None:
    command(["run.py", "--data-dir", str(data), "--warehouse", str(warehouse)], log)
    results = json.loads((ROOT / "dbt" / "target" / "run_results.json").read_text())
    tests = [row for row in results["results"] if row["unique_id"].startswith("test.")]
    if len(tests) < 6 or any(row["status"] != "pass" for row in tests):
        raise AssertionError("Expected at least six dbt tests, all passing")


def catalog_for(warehouse: Path) -> SqlCatalog:
    return SqlCatalog("qafila", uri=f"sqlite:///{warehouse / 'catalog.db'}", warehouse=str(warehouse))


def capture(catalog: SqlCatalog) -> dict:
    result = {}
    for name, columns in COLUMNS.items():
        table = catalog.load_table(name)
        arrow = table.scan().to_arrow()
        for column, expected_type in zip(columns, EXPECTED_TYPES[name]):
            logical_type = table.schema().find_field(column).field_type
            if logical_type != ICEBERG_TYPES[expected_type]:
                raise AssertionError(f"{name}.{column}: unexpected Iceberg type {logical_type}")
            arrow_type = arrow.schema.field(column).type
            # PyIceberg creates empty scans with large_string; populated Parquet
            # scans can use string. Both represent the same Iceberg string type.
            valid_arrow = (
                arrow_type in (pa.string(), pa.large_string())
                if expected_type == pa.string() else arrow_type == expected_type
            )
            if not valid_arrow:
                raise AssertionError(f"{name}.{column}: expected {expected_type}, got {arrow_type}")
        snapshot = table.current_snapshot()
        result[name] = {
            "rows": arrow.to_pylist(),
            "snapshot": snapshot.snapshot_id if snapshot else None,
            "all_snapshots": [s.snapshot_id for s in table.snapshots()],
            "table_uuid": str(table.metadata.table_uuid),
        }
    return result


def verify_reference(state: dict, data: Path) -> None:
    expected = compute(data)
    for name in COLUMNS:
        assert_matches(name, state[name]["rows"], expected[name])


def verify_noop(before: dict, after: dict) -> None:
    for name in COLUMNS:
        assert_matches(name, after[name]["rows"], before[name]["rows"])
        for key in ("snapshot", "all_snapshots", "table_uuid"):
            if before[name][key] != after[name][key]:
                raise AssertionError(f"Identical rerun changed {name} {key}")


def summarize(state: dict) -> dict:
    result = {}
    for name, table in state.items():
        result[name] = {key: table[key] for key in ("snapshot", "all_snapshots", "table_uuid")}
        result[name]["row_count"] = len(table["rows"])
    margin = state["gold.weekly_margin"]["rows"]
    result["gold.weekly_margin"]["totals"] = {
        key: round(sum(row[key] for row in margin), 2)
        for key in ("lines", "revenue_sar", "costed_revenue_sar", "cost_sar", "margin_sar", "uncosted_lines")
    }
    result["quality.price_quarantine"]["reasons"] = dict(Counter(row["reason"] for row in state["quality.price_quarantine"]["rows"]))
    return result


def issue_counts(data: Path) -> dict:
    counts: Counter[str] = Counter()
    for path in (data / "suppliers").glob("prices_*.csv"):
        counts["supplier_files"] += 1
        with path.open("rb") as stream:
            counts["bom_files"] += int(stream.read(3) == b"\xef\xbb\xbf")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                raw = row.get("cost_sar", row.get("unit_cost", ""))
                counts["supplier_rows"] += 1
                counts["decimal_comma_rows"] += int("," in raw)
                counts["arabic_digit_rows"] += int(any(c in "٠١٢٣٤٥٦٧٨٩" for c in raw))
                counts["renamed_cost_column_rows"] += int("cost_sar" in row)
                counts["padded_supplier_skus"] += int(row["sku"] != row["sku"].strip())
    with closing(sqlite3.connect((data / "qafila_oltp.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
        counts["padded_product_skus"] = db.execute("SELECT count(*) FROM products WHERE sku != trim(sku)").fetchone()[0]
        counts["nonpositive_item_quantities"] = db.execute("SELECT count(*) FROM order_items WHERE quantity <= 0").fetchone()[0]
    return dict(counts)


def run_cycle(directory: Path, seed: int | None) -> dict:
    directory.mkdir()
    data, warehouse = directory / "input", directory / "lake"
    if seed is None:
        make_edge_data(data)
    else:
        command(["tools/make_data.py", "--seed", str(seed), "--out", str(data)], directory / "generate.log")
    sources = issue_counts(data)
    pipeline(data, warehouse, directory / "baseline.log")
    catalog = catalog_for(warehouse)
    baseline = capture(catalog)
    verify_reference(baseline, data)
    pipeline(data, warehouse, directory / "rerun.log")
    verify_noop(baseline, capture(catalog))

    if seed is None:
        add_edge_correction(data)
    else:
        command(["tools/make_data.py", "--out", str(data), "--add-correction"], directory / "correction.log")
    pipeline(data, warehouse, directory / "corrected.log")
    corrected = capture(catalog)
    verify_reference(corrected, data)
    for name in COLUMNS:
        if baseline[name]["table_uuid"] != corrected[name]["table_uuid"]:
            raise AssertionError(f"Correction recreated {name}")
        old_snapshot = baseline[name]["snapshot"]
        if old_snapshot is not None:
            old_rows = catalog.load_table(name).scan(snapshot_id=old_snapshot).to_arrow().to_pylist()
            assert_matches(name, old_rows, baseline[name]["rows"])
    gold = "gold.weekly_margin"
    if baseline[gold]["snapshot"] == corrected[gold]["snapshot"]:
        raise AssertionError("Expected a new gold snapshot after the correction")
    if comparable(gold, baseline[gold]["rows"]) == comparable(gold, corrected[gold]["rows"]):
        raise AssertionError("Correction must change margins in this fixture")
    pipeline(data, warehouse, directory / "corrected-rerun.log")
    verify_noop(corrected, capture(catalog))
    if seed is not None:
        command(["tools/check.py", "--data-dir", str(data), "--warehouse", str(warehouse)], directory / "contract.log")
    return {
        "seed": seed, "source_issues_before_correction": sources,
        "baseline": summarize(baseline), "corrected": summarize(corrected),
        "reference_match": True, "baseline_rerun_unchanged": True,
        "corrected_rerun_unchanged": True, "old_snapshots_match_baseline": True,
    }


def run_empty(directory: Path) -> dict:
    directory.mkdir()
    data, warehouse = directory / "input", directory / "lake"
    make_edge_data(data)
    for path in (data / "suppliers").glob("*.csv"):
        path.unlink()
    with closing(sqlite3.connect(data / "qafila_oltp.sqlite")) as db:
        db.execute("DELETE FROM orders")
        db.execute("DELETE FROM order_items")
        db.commit()
    pipeline(data, warehouse, directory / "empty.log")
    catalog = catalog_for(warehouse)
    baseline = capture(catalog)
    verify_reference(baseline, data)
    if any(state["rows"] for state in baseline.values()):
        raise AssertionError("Empty sources must publish three correctly typed empty tables")
    pipeline(data, warehouse, directory / "empty-rerun.log")
    verify_noop(baseline, capture(catalog))
    return {"tables": summarize(baseline), "rerun_unchanged": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="*", default=[2026, 11, 73])
    parser.add_argument("--work-dir", type=Path, default=ROOT / "warehouse" / "verification")
    parser.add_argument("--skip-edges", action="store_true", help="only run the requested generated datasets")
    args = parser.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    report: dict = {"started_at": datetime.now(timezone.utc).isoformat(), "seeds": {}}

    def save() -> None:
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    for seed in args.seeds:
        print(f"Checking seed {seed}: baseline, rerun, correction, time travel, corrected rerun", flush=True)
        report["seeds"][str(seed)] = run_cycle(work / f"seed-{seed}", seed)
        save()
        print(f"PASS seed {seed}", flush=True)
    if not args.skip_edges:
        print("Checking boundary fixture and empty outputs", flush=True)
        report["edge_cases"] = run_cycle(work / "edges", None)
        save()
        report["empty_inputs"] = run_empty(work / "empty")
        save()
        print("PASS boundary fixture and empty outputs", flush=True)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["passed"] = True
    save()
    print(f"All integration checks passed. Evidence: {work / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
