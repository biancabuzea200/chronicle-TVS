#!/usr/bin/env python3
"""
Scans Morpho Blue markets (https://app.morpho.org/variable) and identifies which
ones are powered by a Chronicle price feed, for Component 2 (Data Feeds TVS).

Approach:
  1. Pull every "listed" market from Morpho's public GraphQL API
     (https://blue-api.morpho.org/graphql) -- pair, chain, and market size
     (total supplied, in USD).
  2. For each market, fetch its detail page on app.morpho.org. Oracle
     decoding (which provider -- Chainlink, Chronicle, Pyth, etc. -- backs
     each price leg) is done server-side by Morpho and embedded directly in
     the page's React Server Components payload as a `decoding.facts` array;
     no on-chain calls or browser rendering are needed, just a plain HTTP GET.
  3. A market is "powered by Chronicle" if any of its oracle facts report
     `provider == "chronicle"` -- i.e. markets that rely on Chronicle's
     oracle.

Every run is a full rescan of all currently-listed markets (cheap: ~5 min for
~700 markets). To track changes over time -- e.g. to notice when a NEW
Chronicle market appears, or an old one stops being listed -- results are
merged into a persistent history file (default: morpho_chronicle_history.json,
next to this script). Each market in that file keeps a firstSeenAt/lastSeenAt
timestamp and a currentlyListed flag, so nothing is ever silently dropped;
re-running the script just updates it in place and prints what changed.

Every run writes morpho_chronicle_snapshot.json and
morpho_chronicle_markets.csv (next to this script, overwritten each run) in
addition to morpho_chronicle_history.json, so there's always an up-to-date
file on disk -- pass --json/--csv for different paths, or --no-output to
skip writing them.

Usage:
    pip install requests
    python3 morpho_markets.py
    python3 morpho_markets.py --json snapshot.json --csv snapshot.csv
    python3 morpho_markets.py --history /path/to/morpho_chronicle_history.json
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

DEFAULT_HISTORY_PATH = Path(__file__).parent / "morpho_chronicle_history.json"
DEFAULT_JSON_PATH = Path(__file__).parent / "morpho_chronicle_snapshot.json"
DEFAULT_CSV_PATH = Path(__file__).parent / "morpho_chronicle_markets.csv"

GRAPHQL_URL = "https://blue-api.morpho.org/graphql"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# chainId -> Morpho's URL slug (morphoChainSlug), pulled from app.morpho.org's
# own frontend bundle. Only chains that actually have listed markets today.
CHAIN_SLUGS = {
    1: "ethereum",
    10: "opmainnet",
    130: "unichain",
    137: "polygon",
    143: "monad",
    988: "stable",
    999: "hyperevm",
    4217: "tempo",
    4663: "robinhood-chain",
    5042: "arc",
    8453: "base",
    42161: "arbitrum",
    747474: "katana",
}

PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)\s*</script>", re.DOTALL)


def gql(query: str) -> dict:
    resp = requests.post(GRAPHQL_URL, json={"query": query}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data


def fetch_all_listed_markets():
    markets = []
    skip, page_size = 0, 100
    while True:
        q = f"""{{
          markets(first:{page_size}, skip:{skip}, where:{{listed:true}},
                  orderBy: SupplyAssetsUsd, orderDirection: Desc) {{
            pageInfo {{ countTotal }}
            items {{
              marketId
              loanAsset {{ symbol }}
              collateralAsset {{ symbol }}
              morphoBlue {{ chain {{ id network }} }}
              state {{ supplyAssetsUsd }}
            }}
          }}
        }}"""
        data = gql(q)["data"]["markets"]
        markets.extend(data["items"])
        skip += page_size
        if skip >= data["pageInfo"]["countTotal"]:
            break
    return markets


def extract_flight_buffer(html: str) -> str:
    chunks = []
    for m in PUSH_RE.finditer(html):
        try:
            arr = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if len(arr) >= 2 and isinstance(arr[1], str):
            chunks.append(arr[1])
    return "".join(chunks)


def fetch_oracle_facts(session: requests.Session, market: dict):
    chain_id = market["morphoBlue"]["chain"]["id"]
    slug = CHAIN_SLUGS.get(chain_id)
    if slug is None:
        return None, f"unknown chain slug for chainId={chain_id}"

    url = f"https://app.morpho.org/{slug}/variable/{market['marketId']}/x"
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        return None, str(e)

    buf = extract_flight_buffer(resp.text)
    try:
        idx = buf.index('{"decoding":{"facts":')
    except ValueError:
        return [], None  # page loaded fine but no oracle decoding present

    dec = json.JSONDecoder()
    obj, _ = dec.raw_decode(buf, idx)
    return obj["decoding"]["facts"], None


def pair_name(market: dict) -> str:
    return f"{market['loanAsset']['symbol']}/{market['collateralAsset']['symbol']}"


def load_history(path: Path) -> dict:
    if not path.exists():
        return {"markets": {}, "lastRunAt": None}
    with open(path) as fh:
        return json.load(fh)


def merge_history(history: dict, current_results: list, run_at: str) -> dict:
    """Update history in place: new markets are added, previously-seen ones
    get their lastSeenAt/value refreshed, and ones no longer found are kept
    but marked currentlyListed=False. Returns (new, reappeared, dropped)."""
    markets = history.setdefault("markets", {})
    seen_ids = set()
    new, reappeared = [], []

    for r in current_results:
        mid = r["marketId"]
        seen_ids.add(mid)
        existing = markets.get(mid)
        if existing is None:
            new.append(r)
            markets[mid] = {**r, "firstSeenAt": run_at, "lastSeenAt": run_at, "currentlyListed": True}
        else:
            if not existing.get("currentlyListed", True):
                reappeared.append(r)
            markets[mid] = {
                **r,
                "firstSeenAt": existing.get("firstSeenAt", run_at),
                "lastSeenAt": run_at,
                "currentlyListed": True,
            }

    dropped = []
    for mid, entry in markets.items():
        if mid not in seen_ids and entry.get("currentlyListed", True):
            entry["currentlyListed"] = False
            dropped.append(entry)

    history["lastRunAt"] = run_at
    return new, reappeared, dropped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", default=str(DEFAULT_JSON_PATH), help=f"write full results to this JSON file (default: {DEFAULT_JSON_PATH})"
    )
    parser.add_argument(
        "--csv", default=str(DEFAULT_CSV_PATH), help=f"write the Chronicle-market table to this CSV file (default: {DEFAULT_CSV_PATH})"
    )
    parser.add_argument(
        "--workers", type=int, default=12, help="concurrent requests (default: 12)"
    )
    parser.add_argument(
        "--history",
        default=str(DEFAULT_HISTORY_PATH),
        help=f"persistent history file to merge results into (default: {DEFAULT_HISTORY_PATH})",
    )
    parser.add_argument(
        "--no-history", action="store_true", help="skip reading/writing the history file"
    )
    parser.add_argument("--no-output", action="store_true", help="skip writing --json/--csv files")
    args = parser.parse_args()
    if args.no_output:
        args.json = None
        args.csv = None

    print("Fetching listed markets from Morpho's GraphQL API...", file=sys.stderr)
    markets = fetch_all_listed_markets()
    print(f"{len(markets)} listed markets found. Checking oracle providers...", file=sys.stderr)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_oracle_facts, session, m): m for m in markets}
        done = 0
        for fut in as_completed(futs):
            m = futs[fut]
            facts, err = fut.result()
            done += 1
            if done % 100 == 0:
                print(f"  checked {done}/{len(markets)}", file=sys.stderr)
            if err:
                errors.append({"market": pair_name(m), "chain": m["morphoBlue"]["chain"]["network"], "error": err})
                continue
            chronicle_facts = [f for f in facts if f.get("provider") == "chronicle"]
            if chronicle_facts:
                results.append(
                    {
                        "pair": pair_name(m),
                        "chain": m["morphoBlue"]["chain"]["network"],
                        "marketId": m["marketId"],
                        "valueUsd": m["state"]["supplyAssetsUsd"],
                        "legs": [
                            {"path": f["path"], "pair": f"{f.get('base')}/{f.get('quote')}"}
                            for f in chronicle_facts
                        ],
                        "url": f"https://app.morpho.org/{CHAIN_SLUGS[m['morphoBlue']['chain']['id']]}/variable/{m['marketId']}/x",
                    }
                )

    results.sort(key=lambda r: r["valueUsd"], reverse=True)

    print(f"\n{'Market':24s} {'Chain':18s} {'Value (USD)':>16s}  URL")
    print("-" * 100)
    for r in results:
        print(f"{r['pair']:24s} {r['chain']:18s} {r['valueUsd']:>16,.2f}  {r['url']}")

    total = sum(r["valueUsd"] for r in results)

    print(f"\n{'Markets powered by Chronicle:':34s} {len(results)} / {len(markets)} listed markets")
    print(f"{'Total value:':34s} ${total:,.2f}")

    if errors:
        print(f"\n{len(errors)} market(s) could not be checked:", file=sys.stderr)
        for e in errors[:10]:
            print(f"  - {e['pair'] if 'pair' in e else e['market']} ({e['chain']}): {e['error']}", file=sys.stderr)

    if not args.no_history:
        history_path = Path(args.history)
        history = load_history(history_path)
        run_at = datetime.now(timezone.utc).isoformat()
        new, reappeared, dropped = merge_history(history, results, run_at)

        if new:
            print(f"\nNEW Chronicle market(s) since last run ({len(new)}):")
            for r in new:
                print(f"  + {r['pair']} on {r['chain']} -- ${r['valueUsd']:,.2f} -- {r['url']}")
        if reappeared:
            print(f"\nChronicle market(s) that RE-APPEARED ({len(reappeared)}):")
            for r in reappeared:
                print(f"  ~ {r['pair']} on {r['chain']} -- ${r['valueUsd']:,.2f}")
        if dropped:
            print(f"\nChronicle market(s) no longer listed ({len(dropped)}, kept in history):")
            for r in dropped:
                print(f"  - {r['pair']} on {r['chain']} (last seen {r['lastSeenAt']})")
        if not (new or reappeared or dropped):
            print(f"\nNo changes since last run ({history.get('lastRunAt') or 'first run'}).")

        with open(history_path, "w") as fh:
            json.dump(history, fh, indent=2)
        print(f"\nHistory updated: {history_path} ({len(history['markets'])} market(s) tracked total)", file=sys.stderr)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(
                {
                    "chronicleMarkets": results,
                    "totalValueUsd": total,
                    "listedMarketsChecked": len(markets),
                    "errors": errors,
                },
                fh,
                indent=2,
            )
        print(f"\nWrote {args.json}", file=sys.stderr)

    if args.csv:
        import csv

        with open(args.csv, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["pair", "chain", "value_usd", "market_id", "url"])
            for r in results:
                writer.writerow([r["pair"], r["chain"], f"{r['valueUsd']:.2f}", r["marketId"], r["url"]])
        print(f"Wrote {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
