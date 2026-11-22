-- Aggregate before joining: a repeated processor row must never multiply an amount.
WITH gateway_counts AS (
    SELECT merchant, reference, COUNT(*) AS copies
    FROM gateway
    GROUP BY merchant, reference
),
processor_counts AS (
    SELECT merchant, reference, COUNT(*) AS copies
    FROM processor
    GROUP BY merchant, reference
),
all_keys AS (
    SELECT merchant, reference FROM gateway_counts
    UNION
    SELECT merchant, reference FROM processor_counts
),
observations AS (
    SELECT k.merchant, k.reference,
           COALESCE(gc.copies, 0) AS gateway_rows,
           COALESCE(pc.copies, 0) AS processor_rows,
           g.status AS gateway_status, p.status AS processor_status,
           g.direction AS gateway_direction, p.direction AS processor_direction,
           g.currency AS gateway_currency, p.currency AS processor_currency,
           g.amount_minor AS gateway_amount, p.amount_minor AS processor_amount
    FROM all_keys AS k
    LEFT JOIN gateway_counts AS gc USING (merchant, reference)
    LEFT JOIN processor_counts AS pc USING (merchant, reference)
    LEFT JOIN gateway AS g ON g.merchant = k.merchant
        AND g.reference = k.reference AND gc.copies = 1
    LEFT JOIN processor AS p ON p.merchant = k.merchant
        AND p.reference = k.reference AND pc.copies = 1
)
SELECT *,
       CASE
           WHEN gateway_rows > 1 OR processor_rows > 1 THEN 'DUPLICATE'
           WHEN gateway_rows = 0 THEN 'PROCESSOR_ONLY'
           WHEN processor_rows = 0 THEN 'GATEWAY_ONLY'
           WHEN gateway_direction <> processor_direction THEN 'DIRECTION_MISMATCH'
           WHEN gateway_currency <> processor_currency THEN 'CURRENCY_MISMATCH'
           WHEN gateway_amount <> processor_amount THEN 'AMOUNT_MISMATCH'
           WHEN gateway_status = 'PENDING' AND processor_status <> 'PENDING'
               THEN 'FINAL_AT_PROCESSOR'
           WHEN gateway_status <> processor_status THEN 'STATUS_MISMATCH'
           WHEN gateway_status = 'PENDING' THEN 'BOTH_PENDING'
           ELSE 'MATCHED'
       END AS finding
FROM observations
ORDER BY merchant, reference;
