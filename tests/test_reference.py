from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from tests.fixtures import add_edge_correction, make_edge_data
from tests.reference import compute, local_date, parse_cost


class ReferenceTests(unittest.TestCase):
    def test_decimal_parsing_and_rounding(self):
        for text, expected in [("9,49", "9.49"), ("٩٫٤٩", "9.49"), (" 1.005 ", "1.01"), ("0.004", "0.00")]:
            with self.subTest(text=text):
                self.assertEqual(parse_cost(text), Decimal(expected))

    def test_invalid_and_nonfinite_costs(self):
        for text in ("", "no cost", "0", "-1", "NaN", "Infinity", "-Infinity"):
            with self.subTest(text=text):
                self.assertIsNone(parse_cost(text))

    def test_riyadh_cutoff(self):
        self.assertEqual(local_date("2026-08-30 20:59:59"), date(2026, 8, 30))
        self.assertEqual(local_date("2026-08-30T21:00:00Z"), date(2026, 8, 31))
        self.assertEqual(local_date("2026-08-31T00:00:00+03:00"), date(2026, 8, 31))

    def test_hand_calculated_history_and_margin(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "input"
            make_edge_data(data)
            result = compute(data)
            history = result["silver.product_cost_history"]
            a = [r for r in history if r["sku"] == "A"]
            self.assertEqual(len(a), 2)
            self.assertEqual(a[0]["valid_to"], date(2026, 9, 21))
            self.assertEqual([r["unit_cost_sar"] for r in a], [2.5, 4.0])
            margin = {(r["iso_week"], r["category"]): r for r in result["gold.weekly_margin"]}
            self.assertEqual(margin[36, "Pantry"]["lines"], 2)
            self.assertEqual(margin[36, "Pantry"]["revenue_sar"], 29.0)
            self.assertEqual(margin[36, "Pantry"]["cost_sar"], 7.5)
            self.assertEqual(margin[36, "Pantry"]["margin_sar"], 21.5)
            self.assertEqual(margin[37, "Dairy"]["uncosted_lines"], 1)
            self.assertEqual(margin[37, "Dairy"]["costed_revenue_sar"], 0.0)
            self.assertEqual(margin[38, "Dairy"]["cost_sar"], 9.49)
            self.assertEqual(margin[38, "Dairy"]["uncosted_lines"], 0)
            quarantine = result["quality.price_quarantine"]
            self.assertEqual(len(quarantine), 8)
            self.assertEqual(next(r for r in quarantine if r["sku"] == "UNKNOWN")["reason"], "unknown_sku")
            add_edge_correction(data)
            corrected = compute(data)
            a = [r for r in corrected["silver.product_cost_history"] if r["sku"] == "A"]
            self.assertEqual(a[-1]["unit_cost_sar"], 3.25)
            week39 = next(r for r in corrected["gold.weekly_margin"] if r["iso_week"] == 39)
            self.assertEqual(week39["margin_sar"], 6.75)


if __name__ == "__main__":
    unittest.main()
