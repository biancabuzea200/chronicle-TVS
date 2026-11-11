# Sky (formerly MakerDAO) — Chronicle-powered Data Feeds TVS

Tracks how much of Sky's value counts toward Component 2 (Data Feeds TVS).
All values are sourced directly from Sky's own on-chain contracts — no
DefiLlama, no CoinGecko.

## What's tracked

Just **Sky Lending** (the core CDP/vault engine) and **Sky RWA** (which is
just the RWA-type ilks already inside Sky Lending's own registry, not a
separate product) — every ilk scanned and priced on-chain by
[sky_ilks.py](sky_ilks.py). Output: [sky_ilks.csv](sky_ilks.csv) /
[sky_ilks.json](sky_ilks.json) (full raw detail) and
[sky_chronicle_overview.csv](sky_chronicle_overview.csv) (the per-ilk
totals that actually count, with a `TOTAL` row).

Sky Money and Spark are **not** counted here — out of scope.

## Total

Not stated here — numbers written in prose go stale the moment the script
is rerun. See [chronicle_total.json](chronicle_total.json) (regenerated on
every `python3 sky_ilks.py` run) or [sky_chronicle_overview.csv](sky_chronicle_overview.csv)'s
`TOTAL` row for the current figure. `chronicle_total.json` follows a
standard shape so [../chronicle_total_tvs.py](../chronicle_total_tvs.py)
can sum it together with every other protocol's total (Morpho, etc.) into
one combined Data Feeds TVS figure.

## What's left out of the calculation

- The 8 `ALLOCATOR-*` ilks — Sky-minted DAI/USDS deployed into other
  systems (Spark, Grove, etc.), tracked in their own right elsewhere, not
  counted here as Sky Lending collateral.
- `TELEPORT-FW-A` and `LSEV2-SKY-A` — not yet resolvable with the current
  script (flagged with a `note` in the overview CSV, not guessed).
