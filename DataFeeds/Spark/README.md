# Spark — Chronicle-powered Data Feeds TVS

Tracks how much of SparkLend's value counts toward Component 2 (Data Feeds
TVS). All values are sourced directly from SparkLend's own on-chain
contracts — no DefiLlama, no CoinGecko.

## What's tracked

**SparkLend** (Spark's Aave V3 fork lending market): every reserve, scanned
and priced on-chain by [spark_reserves.py](spark_reserves.py), counted in
full. Output: [spark_reserves.csv](spark_reserves.csv) / [spark_reserves.json](spark_reserves.json)
(full raw detail) and [spark_chronicle_overview.csv](spark_chronicle_overview.csv)
(per-reserve totals, with a `TOTAL` row).

Spark Liquidity Layer and Spark Savings are **not** tracked here.

## Total

Not stated here — see [chronicle_total.json](chronicle_total.json)
(regenerated on every `python3 spark_reserves.py` run). It follows the same
standard shape as every other protocol folder, so
[../chronicle_total_tvs.py](../chronicle_total_tvs.py) sums it together
with Sky, Morpho, etc. into one combined Data Feeds TVS figure.
