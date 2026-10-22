# Qafila gross margin

Submitted by: Abdullah AlRashoudi — academy: @SDAIAAcademy

A supplier correction should change the margin for the affected orders, without erasing what finance saw before it arrived. This pipeline keeps that cost history and publishes a weekly margin table with uncosted lines visible.

The assignment and output contract are in [BRIEF.md](BRIEF.md). The implementation checklist is in [REQUIREMENTS.md](REQUIREMENTS.md).

```bash
uv sync --frozen
uv run python tools/make_data.py
uv run python run.py
uv run python tools/check.py
```

Custom locations work with `run.py --data-dir <folder> --warehouse <folder>` and the same flags on `tools/check.py`. Generate the input first: `tools/make_data.py` replaces its chosen output directory, so do not point it at files you want to keep.

## Design

SQLite + CSV → Python `sqlite3`/`csv` + Arrow → DuckDB `raw` → dbt staging → dbt silver/quality/gold → PyIceberg's local SQL catalog.

| Model | Layer | Grain: one row per… | Materialization |
|---|---|---|---|
| `stg_orders` | staging | order, with its Riyadh order date | view |
| `stg_order_items` | staging | order ID and line number | view |
| `stg_products` | staging | product, with a trimmed SKU | view |
| `stg_stores` | staging | store | view |
| `stg_supplier_prices` | staging | source file and data-row number | view |
| `product_cost_history` | silver | SKU and actual cost change | table; Iceberg |
| `order_line_margin` | silver | eligible order line, costed at its order date | view |
| `weekly_margin` | gold | ISO week × city × category with eligible lines | table; Iceberg |
| `price_quarantine` | quality | rejected supplier row | table; Iceberg |

The four raw app tables retain their source columns and filename. Supplier cells stay as text; `source_file` and `source_row` preserve lineage even when two rejected rows look identical. A read-only SQLite transaction gives a consistent source snapshot, and one DuckDB transaction replaces the raw layer. The loader does not need a downloaded SQLite extension.

**Cost history.** Staging trims both sets of SKUs and normalizes Arabic-Indic digits and decimal separators. Unknown SKUs are rejected first; otherwise a nonnumeric, nonfinite or nonpositive cost is rejected. Usable costs are rounded to cents. For each SKU/date, the last filename wins among usable quotes; a tie inside one file uses its last row. Missing quotes leave the previous cost in force. Consecutive equal costs collapse into one interval, ending exclusively at the next actual change. A correction rebuilds those intervals from the landed observations, including later intervals that it may affect.

**Line costing.** Only delivered orders, positive quantities and Riyadh order dates from 2026-08-31 count. Each line joins the interval containing that date. Revenue is rounded per line using decimal arithmetic before aggregation. An unmatched line remains in `lines` and `revenue_sar`; its revenue is excluded from `costed_revenue_sar`, and it contributes no cost. `margin_sar` therefore measures the margin on costed sales. Money becomes double only at the output boundary.

## Data problems I found

Counts below are from the uncorrected course dataset, seed 2026. They describe overlapping issues, so they should not be added together.

| Problem | Where | Rows affected | Treatment |
|---|---|---:|---|
| Decimal comma | W38 supplier costs | 126 | Normalize to a decimal point |
| Arabic-Indic digits | W38 supplier costs | 34 | Translate digits and Arabic decimal mark |
| UTF-8 BOM | W38 file | 160 in one file | Decode the header with `utf-8-sig` |
| `unit_cost` renamed to `cost_sar` | W39 | 160 | Union both fields without losing raw text |
| Zero or negative cost | W39 | 4 | Quarantine as `invalid_cost` |
| Unknown SKU | W39 | 3 | Quarantine as `unknown_sku` |
| Trailing spaces in SKU | App products | 2 | Trim before matching |
| Nonpositive quantity | App order items | 142 | Exclude from eligible lines |
| No quote valid on the order date | Eligible lines | 20,626 | Keep the sale visible and mark it uncosted |

The baseline contains 82,404 eligible lines and SAR 3,504,002.19 revenue. The seven rejected original quotes remain in quarantine after the correction; a later good quote does not erase the audit record. Customer, payment and delivery feeds are outside this margin calculation and are not loaded.

## Tests

```bash
uv run python -m unittest discover -s tests -v
uv run python -m tests.integration
```

The integration command uses a new `warehouse/verification` directory and writes its logs and `report.json` there. Choose a different `--work-dir` for another run. It checks the complete pipeline on seeds 2026, 11 and 73, then a small boundary fixture and empty inputs. All generated inputs, warehouses and logs remain ignored by Git.

| Check | What it protects |
|---|---|
| 40 dbt tests, including 10 business checks | Keys, foreign keys, required values, unique history versions, one current version, interval continuity, unchanged-cost collapse, winning quote coverage, eligible-line preservation, point-in-time costs, quarantine multiplicity and weekly reconciliation |
| 10 Python unit tests | Hand-calculated answers, decimal parsing/rounding, UTC+3 cutoff, raw text and lineage, repeat ingestion, malformed CSV rejection and rollback |
| Independent Python/Decimal reference | Every history, margin and quarantine row, before and after correction; no dbt calculation is used as the expected answer |
| Integration reruns and time travel | Identical rows, table UUIDs and snapshot IDs on a no-op; old snapshots still readable after changed output |
| Boundary fixture | Unchanged and missing quotes, competing correction names, duplicate rejected rows, nonfinite costs, tiny positive costs rounded to zero, uncosted sales and week/date boundaries |
| Empty inputs | All three empty tables retain the contract's types and can be rerun |
| Supplied checker | 22/22 contract checks on each generated dataset |

The full integration run passed all 18 pipeline builds. A fresh tracked checkout also passed `uv sync --frozen`, data generation, the pipeline and all 22 contract checks. Python compilation, `tabnanny` and whitespace checks pass. An additional check with the Mac's existing mypy installation passed for `run.py` and `tests/` using `--follow-imports=skip --ignore-missing-imports`; it is not a new project dependency or a substitute for runtime checks.

## Re-runs and the correction

```bash
uv run python run.py
uv run python tools/make_data.py --add-correction
uv run python run.py
uv run python tools/check.py
```

Publication compares complete row multisets with the current Iceberg contents. An identical run does not write a new snapshot. Changed tables use `overwrite()` on the existing table, retaining their UUID and earlier snapshots; tables are never dropped. Quarantine stayed unchanged in the generated correction cases.

The integration run on 2026-10-22 (`--work-dir warehouse/verification-final`) matched every output row for all three seeds:

| Seed | Baseline margin, SAR | Corrected margin, SAR | History rows, before → after |
|---|---:|---:|---:|
| 2026 | 801,016.88 | 803,515.80 | 633 → 637 |
| 11 | 748,231.25 | 748,714.99 | 632 → 636 |
| 73 | 1,046,485.02 | 1,046,994.23 | 633 → 637 |

Each had 165 weekly groups and seven quarantined rows. For the course seed:

| State | Current `gold.weekly_margin` snapshot | Total cost, SAR | Total margin, SAR |
|---|---:|---:|---:|
| Before correction | `9092709110982502752` | 1,654,199.98 | 801,016.88 |
| After correction | `716958128391080228` | 1,651,701.06 | 803,515.80 |

After the correction, reading snapshot `9092709110982502752` still returned SAR 801,016.88 margin and matched every original row. Baseline and corrected reruns preserved all three tables' contents and snapshot lists. Snapshot IDs are specific to this local run; a fresh warehouse gets different IDs.

## What I'd do next

At 100× the data, full dbt rebuilds and reading every published row for comparison would become the first bottlenecks. SQLite loading is batched, but supplier parsing and publication still materialize tables in memory. I would partition the fact data by order date, retain file fingerprints, and recalculate only the SKU/date ranges affected by a changed quote. Daily files need the same correction semantics, with explicit handling of multiple quotes within a day.

The three Iceberg updates commit separately. If publication stops midway, a rerun repairs the remaining tables, but readers could briefly see different refreshes. A release manifest would let readers select a consistent set of snapshots. A retention policy would also be needed before allowing snapshots and data files to grow indefinitely. The current SQLite loader deliberately targets the supplied source schema.

## AI assistance

I used OpenAI Codex to help implement the Python pipeline and dbt models, build independent tests, review edge cases, and draft this README. The numerical examples above come from actual local runs.
