# Data Feeds TVS (Component 2) — Sources

Fill in below: where should the script look to get Data Feeds values?
(dashboard URLs, APIs, docs pages, anything relevant)

## Sources

- Protocols (from DefiLlama-style table, names only so far — source URL TBD):
  - Sky
  - SparkLend
  - M0
  - Steakhouse Financial
  - KEEP Network
  - Hyperithm
  - Beraborrow
  - Gauntlet
  - Dolomite
  - Jigsaw
  - Re7 Labs
  - MEV Capital

- **Morpho markets** — https://app.morpho.org/variable
  Script: [morpho/morpho_markets.py](morpho/morpho_markets.py). Scans all listed
  Morpho Blue markets and flags the ones with a Chronicle oracle feed. See
  [morpho/morpho_chronicle_snapshot.json](morpho/morpho_chronicle_snapshot.json)
  for the latest run's output.

- **Sky** (Sky Lending + Sky RWA ilks) — on-chain only, no DefiLlama/CoinGecko.
  Script: [Sky/sky_ilks.py](Sky/sky_ilks.py). See [Sky/README.md](Sky/README.md).

- **Spark** (SparkLend reserves) — on-chain only, no DefiLlama/CoinGecko.
  Script: [Spark/spark_reserves.py](Spark/spark_reserves.py). See [Spark/README.md](Spark/README.md).

## Combined total

Each protocol's script writes a standard `chronicle_total.json` in its own
folder. [chronicle_total_tvs.py](chronicle_total_tvs.py) sums every one of
them (`DataFeeds/*/chronicle_total.json`) into a single Data Feeds TVS
figure — rerun the per-protocol scripts first, then this, for an
up-to-date combined total. Never hand-edit any of these files; everything
is regenerated from source.

## Notes

- Morpho markets: any live market that integrates a Chronicle oracle feed is
  counted (see methodology.md Component 2, "Primary or backup, both count").
