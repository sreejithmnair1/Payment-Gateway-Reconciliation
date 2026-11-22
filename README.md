# Payment gateway reconciliation

A System Analyst case study using Python and SQL to reconcile payment gateway and processor records for collections and payouts. Includes a sequence diagram, decision rules, and automated tests for timeouts, duplicate transactions, and mismatched amounts.

A customer pays €79.00. The gateway times out, but the processor records a successful collection. Should the merchant retry?

This runnable System Analyst case study follows that transaction from a business question to a decision rule, a SQL implementation and acceptance tests. It compares two synthetic payment snapshots and produces a review queue for collections and payouts. It never initiates a payment or changes a ledger.

## Run the example

From this directory, using Python 3.9 or later:

```sh
python3 reconcile.py
python3 reconcile.py --json
python3 -m unittest -v
```

Python's standard library supplies SQLite. The default run reads the two included CSV files. Expect **8 references, 2 matched and 6 for review**. A match means both sources agree on a final state. A declined payment can match, too.

## Three transactions worth opening

| Merchant reference | Evidence from the two snapshots | Decision |
| --- | --- | --- |
| `atlas-demo / C-102` | The gateway shows the €79.00 collection as pending. The processor shows success. | Flag `FINAL_AT_PROCESSOR`. Verify the transaction by its existing reference before updating the merchant's order. A second collection could charge the customer twice. |
| `atlas-demo / C-103` | The gateway shows €25.00. The processor shows €24.00. Both report success. | Flag `AMOUNT_MISMATCH`. Check the original amount and the processor record before posting an adjustment. |
| `atlas-demo / P-201` | One €35.00 payout appears at the gateway. Two processor rows share its reference. | Flag `DUPLICATE` once. Inspect both processor rows before deciding whether the export repeated a line or two transfers were sent. |

## Explore the case

- [System specification and QA evidence](SYSTEM_SPEC.md) covers the timeout sequence, input contract, decision priorities and acceptance tests.
- [Reconciliation query](reconcile.sql) contains the full comparison logic. [Python runner](reconcile.py) validates the inputs and executes it in memory.
- [Gateway snapshot](gateway.csv) and [processor snapshot](processor.csv) reproduce the worked cases. [Tests](test_reconcile.py) cover one-sided records, conflicting outcomes, duplicates, merchant isolation and malformed inputs.

To try another snapshot, copy the CSV files, edit one field and pass the new paths:

```sh
python3 reconcile.py --gateway my-gateway.csv --processor my-processor.csv --json
```

The JSON output includes the raw values and row counts from both sides. A missing or ambiguous side has null values. Source extracts represent the same cutoff and use one agreed status vocabulary. See the specification for the assumptions behind the comparison.

Independent portfolio exercise prepared with AI assistance. All merchants and transactions are fictional.
