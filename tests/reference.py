"""Small Python oracle: deliberately does not import pipeline transformation code.

The implementation uses Decimal arithmetic and walks quotes in date order instead
of reproducing the SQL window functions. It reads only the four required tables.
"""

from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")
ZERO = Decimal(0)
START = date(2026, 8, 31)
RIYADH = timezone(timedelta(hours=3))
COLUMNS = {
    "silver.product_cost_history": (
        "sku", "unit_cost_sar", "valid_from", "valid_to", "is_current",
    ),
    "gold.weekly_margin": (
        "iso_week", "city", "category", "lines", "revenue_sar",
        "costed_revenue_sar", "cost_sar", "margin_sar", "uncosted_lines",
    ),
    "quality.price_quarantine": (
        "source_file", "sku", "valid_from", "raw_cost", "reason",
    ),
}


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_cost(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value.strip().replace(",", ".").replace("٫", "."))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return money(parsed)


def local_date(value: str) -> date:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(RIYADH).date()


def compute(data_dir: Path) -> dict[str, list[dict]]:
    data_dir = data_dir.resolve()
    with closing(sqlite3.connect(f"{(data_dir / 'qafila_oltp.sqlite').as_uri()}?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        products = {r["product_id"]: dict(r) for r in db.execute("SELECT * FROM products")}
        stores = {r["store_id"]: dict(r) for r in db.execute("SELECT * FROM stores")}
        orders = {r["order_id"]: dict(r) for r in db.execute("SELECT * FROM orders")}
        items = [dict(r) for r in db.execute("SELECT * FROM order_items")]

    known_skus = {p["sku"].strip() for p in products.values()}
    quotes: dict[tuple[str, date], Decimal] = {}
    quarantine = []
    # Sorted files overwrite earlier valid observations at exactly the same key.
    for path in sorted((data_dir / "suppliers").glob("prices_*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                sku = row["sku"].strip()
                valid_from = date.fromisoformat(row["valid_from"])
                raw_cost = row["cost_sar"] if "cost_sar" in row else row["unit_cost"]
                cost = parse_cost(raw_cost)
                reason = "unknown_sku" if sku not in known_skus else "invalid_cost" if cost is None else None
                if reason:
                    quarantine.append({
                        "source_file": path.name, "sku": sku, "valid_from": valid_from,
                        "raw_cost": raw_cost, "reason": reason,
                    })
                else:
                    assert cost is not None
                    quotes[sku, valid_from] = cost

    versions: dict[str, list[dict]] = defaultdict(list)
    for (sku, valid_from), cost in sorted(quotes.items()):
        previous = versions[sku][-1] if versions[sku] else None
        if previous and previous["unit_cost_sar"] == cost:
            continue
        if previous:
            previous["valid_to"] = valid_from
            previous["is_current"] = False
        versions[sku].append({
            "sku": sku, "unit_cost_sar": cost, "valid_from": valid_from,
            "valid_to": None, "is_current": True,
        })

    groups = {}
    for item in items:
        order = orders[item["order_id"]]
        ordered_on = local_date(order["created_at"])
        quantity = item["quantity"]
        if order["status"] != "delivered" or quantity <= 0 or ordered_on < START:
            continue
        product = products[item["product_id"]]
        city = stores[order["store_id"]]["city"]
        key = ordered_on.isocalendar().week, city, product["category"]
        if key not in groups:
            groups[key] = dict(zip(COLUMNS["gold.weekly_margin"], (*key, 0, ZERO, ZERO, ZERO, ZERO, 0)))
        group = groups[key]
        revenue = money(Decimal(quantity) * Decimal(str(item["unit_price"])) - Decimal(str(item["discount"])))
        group["lines"] += 1
        group["revenue_sar"] += revenue
        cost = None
        for version in versions[product["sku"].strip()]:
            if version["valid_from"] <= ordered_on:
                cost = version["unit_cost_sar"]
            else:
                break
        if cost is None:
            group["uncosted_lines"] += 1
        else:
            group["costed_revenue_sar"] += revenue
            group["cost_sar"] += quantity * cost

    for group in groups.values():
        group["margin_sar"] = group["costed_revenue_sar"] - group["cost_sar"]
    outputs = {
        "silver.product_cost_history": [row for sku in sorted(versions) for row in versions[sku]],
        "gold.weekly_margin": [groups[key] for key in sorted(groups)],
        "quality.price_quarantine": quarantine,
    }
    return {
        name: [{key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()} for row in rows]
        for name, rows in outputs.items()
    }


def comparable(name: str, rows: list[dict]) -> list[tuple]:
    """Compare full row multisets, including duplicate quarantine rows."""
    result = [tuple(row[column] for column in COLUMNS[name]) for row in rows]
    return sorted(result, key=repr)


def assert_matches(name: str, actual: list[dict], expected: list[dict]) -> None:
    left, right = comparable(name, actual), comparable(name, expected)
    if len(left) != len(right):
        raise AssertionError(f"{name}: {len(left)} actual rows, {len(right)} expected")
    for index, (got, want) in enumerate(zip(left, right)):
        for column, a, b in zip(COLUMNS[name], got, want):
            # Decimal cents are converted to double only at the contract boundary.
            equal = abs(a - b) <= 0.000001 if isinstance(b, float) else a == b
            if not equal:
                raise AssertionError(f"{name} row {index}, {column}: got {a!r}, expected {b!r}; key {want[:3]!r}")
