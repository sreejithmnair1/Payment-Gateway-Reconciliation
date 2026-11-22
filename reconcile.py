"""Compare two synthetic payment snapshots using Python and SQLite."""
import argparse
import csv
import json
from pathlib import Path
import re
import sqlite3
import sys
from contextlib import closing

ROOT = Path(__file__).resolve().parent
COLUMNS = ["merchant", "reference", "direction", "currency", "amount_minor", "status"]
DIRECTIONS = {"COLLECTION", "PAYOUT"}
STATUSES = {"PENDING", "SUCCEEDED", "FAILED"}
TABLE = """(merchant TEXT, reference TEXT, direction TEXT, currency TEXT,
            amount_minor INTEGER, status TEXT)"""


def read_snapshot(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != COLUMNS:
            raise ValueError(f"{path}: expected CSV header {','.join(COLUMNS)}")
        for row in reader:
            location = f"{path}:{reader.line_num}"
            if len(row) != len(COLUMNS):
                raise ValueError(f"{location}: expected six fields")
            merchant, reference, direction, currency, raw_amount, status = row
            if not merchant.strip() or not reference.strip() or any(v != v.strip() for v in row):
                raise ValueError(f"{location}: missing key or surrounding whitespace")
            if direction not in DIRECTIONS or status not in STATUSES:
                raise ValueError(f"{location}: unrecognised direction or status")
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError(f"{location}: expected a three-letter currency code")
            if not re.fullmatch(r"[0-9]{1,19}", raw_amount):
                raise ValueError(f"{location}: expected an integer amount in minor units")
            amount = int(raw_amount)
            if not 0 < amount <= 2**63 - 1:
                raise ValueError(f"{location}: amount outside the supported positive range")
            yield merchant, reference, direction, currency, amount, status


def reconcile(gateway_path, processor_path):
    with closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = sqlite3.Row
        for table, path in (("gateway", gateway_path), ("processor", processor_path)):
            db.execute(f"CREATE TABLE {table} {TABLE}")
            db.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)", read_snapshot(path))
            db.execute(f"CREATE INDEX {table}_key ON {table}(merchant, reference)")
        query = (ROOT / "reconcile.sql").read_text(encoding="utf-8")
        return [dict(row) for row in db.execute(query)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, default=ROOT / "gateway.csv")
    parser.add_argument("--processor", type=Path, default=ROOT / "processor.csv")
    parser.add_argument("--json", action="store_true", help="Include both sides of each comparison")
    args = parser.parse_args()
    try:
        records = reconcile(args.gateway, args.processor)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(2, f"Input error: {error}\n")
    if args.json:
        print(json.dumps(records, indent=2))
        return
    print("MERCHANT          REFERENCE       GATEWAY      PROCESSOR    FINDING")
    for row in records:
        print(f"{row['merchant']:<17} {row['reference']:<15} "
              f"{(row['gateway_status'] or '-'):12} {(row['processor_status'] or '-'):12} "
              f"{row['finding']}")
    matched = sum(row["finding"] == "MATCHED" for row in records)
    print(f"\n{len(records)} references | {matched} matched | {len(records) - matched} for review")


if __name__ == "__main__":
    main()
