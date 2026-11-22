import csv
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from reconcile import COLUMNS, ROOT, reconcile

BASE = ("atlas-demo", "C-101", "COLLECTION", "EUR", "4900", "SUCCEEDED")


def changed(**fields):
    values = dict(zip(COLUMNS, BASE))
    values.update(fields)
    return [values[column] for column in COLUMNS]


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def snapshot(self, filename, rows):
        path = self.root / filename
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
        return path

    def compare(self, gateway, processor):
        return reconcile(self.snapshot("gateway.csv", gateway), self.snapshot("processor.csv", processor))

    def finding(self, gateway, processor):
        rows = self.compare(gateway, processor)
        self.assertEqual(len(rows), 1)
        return rows[0]["finding"]

    def test_final_agreement(self):
        for state in ("SUCCEEDED", "FAILED"):
            with self.subTest(state=state):
                row = changed(status=state)
                self.assertEqual(self.finding([row], [row]), "MATCHED")

    def test_uncertain_or_conflicting_outcomes(self):
        cases = [("PENDING", "SUCCEEDED", "FINAL_AT_PROCESSOR"),
                 ("PENDING", "FAILED", "FINAL_AT_PROCESSOR"),
                 ("PENDING", "PENDING", "BOTH_PENDING"),
                 ("SUCCEEDED", "PENDING", "STATUS_MISMATCH"),
                 ("SUCCEEDED", "FAILED", "STATUS_MISMATCH")]
        for gateway, processor, expected in cases:
            with self.subTest(gateway=gateway, processor=processor):
                self.assertEqual(self.finding([changed(status=gateway)], [changed(status=processor)]), expected)

    def test_material_differences_and_precedence(self):
        for other, expected in [(changed(direction="PAYOUT", currency="USD"), "DIRECTION_MISMATCH"),
                                (changed(currency="USD", amount_minor="4800"), "CURRENCY_MISMATCH"),
                                (changed(amount_minor="4800", status="FAILED"), "AMOUNT_MISMATCH")]:
            with self.subTest(expected=expected):
                self.assertEqual(self.finding([BASE], [other]), expected)

    def test_duplicates_are_not_collapsed_or_summed(self):
        for left, right in [([BASE], [BASE, BASE]), ([BASE, changed(amount_minor="3500")], [BASE]),
                            ([BASE, BASE], []), ([BASE, BASE], [BASE, BASE])]:
            with self.subTest(gateway=len(left), processor=len(right)):
                rows = self.compare(left, right)
                self.assertEqual(len(rows), 1)
                item = rows[0]
                self.assertEqual(item["finding"], "DUPLICATE")
                self.assertEqual((item["gateway_rows"], item["processor_rows"]), (len(left), len(right)))
                if len(right) != 1:
                    self.assertIsNone(item["processor_amount"])

    def test_one_sided_and_empty(self):
        self.assertEqual(self.finding([BASE], []), "GATEWAY_ONLY")
        self.assertEqual(self.finding([], [BASE]), "PROCESSOR_ONLY")
        self.assertEqual(self.compare([], []), [])

    def test_reference_is_scoped_to_merchant(self):
        rows = self.compare([BASE], [changed(merchant="birch-demo")])
        self.assertEqual([r["finding"] for r in rows], ["GATEWAY_ONLY", "PROCESSOR_ONLY"])

    def test_invalid_input_reports_source_line(self):
        for bad in [changed(amount_minor="0"), changed(amount_minor="12.34"),
                    changed(amount_minor=str(2**63)), changed(status="TIMEOUT"),
                    changed(direction="REFUND"), changed(merchant=" "), changed(currency="EuR")]:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, r"gateway\.csv:2:"):
                    self.compare([bad], [])

    def test_cli_rejects_bad_header(self):
        path = self.root / "bad.csv"
        path.write_text("amount,reference\n", encoding="utf-8")
        result = subprocess.run([sys.executable, str(ROOT / "reconcile.py"), "--gateway", str(path)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected CSV header", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_example_snapshot_and_rerun(self):
        args = [sys.executable, str(ROOT / "reconcile.py"), "--json"]
        first = subprocess.check_output(args, cwd=self.root)
        self.assertEqual(first, subprocess.check_output(args, cwd=self.root))
        result = json.loads(first)
        expected = ["MATCHED", "FINAL_AT_PROCESSOR", "AMOUNT_MISMATCH", "MATCHED",
                    "DUPLICATE", "GATEWAY_ONLY", "PROCESSOR_ONLY", "BOTH_PENDING"]
        self.assertEqual([r["finding"] for r in result], expected)


if __name__ == "__main__":
    unittest.main()
