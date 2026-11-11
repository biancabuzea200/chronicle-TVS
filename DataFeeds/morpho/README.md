# Morpho markets powered by Chronicle

Identifies which Morpho Blue markets (https://app.morpho.org/variable) use a
Chronicle price feed, for Component 2 (Data Feeds TVS).

## Setup

```
pip install requests
```

## Run

```
python3 morpho_markets.py
```

Every run rescans **all** currently-listed Morpho markets (~700, takes a few
minutes) and merges the results into `morpho_chronicle_history.json` (created
automatically next to this script). That file is the persistent source of
truth: each run prints what changed since the last one --

- **NEW** -- a market using Chronicle that wasn't there last time
- **RE-APPEARED** -- a market that had dropped off and is back
- **no longer listed** -- a previously-tracked market that's gone (kept in
  history with `currentlyListed: false`, not deleted, so nothing is lost)

Optional snapshot exports of the current run only:

```
python3 morpho_markets.py --json snapshot.json --csv snapshot.csv
```

## How it works

Oracle-provider decoding (Chainlink vs. Chronicle vs. Pyth, etc.) is done
server-side by Morpho and embedded directly in each market's detail page --
no browser or on-chain calls needed, just a plain HTTP GET per market. A
market counts as powered by Chronicle's oracle if any price leg reports
`provider == "chronicle"`. Each market's raw oracle leg(s) are kept in the
output (`legs`) in case you want to check the details yourself per market.

## Latest result (2026-11-10)

12 of 714 listed markets rely on Chronicle's oracle. Total market size:
~$36.1M. Full list with links in `morpho_chronicle_markets.csv` /
`morpho_chronicle_snapshot.json`.
