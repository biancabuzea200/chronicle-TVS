#!/usr/bin/env python3
"""
Sources SparkLend's (spark.finance, an Aave V3 fork) reserve data and USD
valuation directly from its own on-chain contracts -- no DefiLlama, no
CoinGecko. Every reserve counts in full toward Component 2 (Data Feeds
TVS), per the scope decision in README.md. `is_chronicle`/`chronicle_note`
per reserve are kept as informational evidence, not a total gate.

Usage:
    pip install requests pycryptodome
    python3 spark_reserves.py
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from Crypto.Hash import keccak

DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"
# Last-verified fallback if the hardcoded entry point itself is ever wrong --
# see docstring for how this was verified. Everything downstream (Pool,
# AaveOracle) is resolved live from this, every run.
POOL_ADDRESSES_PROVIDER = "0x02C3eA4e34C0cBd694D2adFa2c690EECbC1793eE"

DEFAULT_CSV_PATH = Path(__file__).parent / "spark_reserves.csv"
DEFAULT_JSON_PATH = Path(__file__).parent / "spark_reserves.json"
DEFAULT_OVERVIEW_CSV_PATH = Path(__file__).parent / "spark_chronicle_overview.csv"
DEFAULT_TOTAL_PATH = Path(__file__).parent / "chronicle_total.json"

# Getter names used by LST-style price sources that don't directly expose
# chronicle()/description() themselves but wrap a confirmed source instead
# (e.g. wstETH's oracle = stETH/ETH rate * ethSource()'s ETH/USD price).
WRAPPER_GETTERS = ["ethSource()", "btcSource()"]


def keccak_selector(signature: str) -> str:
    k = keccak.new(digest_bits=256)
    k.update(signature.encode())
    return k.hexdigest()[:8]


SEL = {
    "getPool()": keccak_selector("getPool()"),
    "getPriceOracle()": keccak_selector("getPriceOracle()"),
    "getReservesList()": keccak_selector("getReservesList()"),
    "getReserveData(address)": keccak_selector("getReserveData(address)"),
    "getSourceOfAsset(address)": keccak_selector("getSourceOfAsset(address)"),
    "getAssetPrice(address)": keccak_selector("getAssetPrice(address)"),
    "BASE_CURRENCY_UNIT()": keccak_selector("BASE_CURRENCY_UNIT()"),
    "description()": keccak_selector("description()"),
    "chronicle()": keccak_selector("chronicle()"),
    "balanceOf(address)": keccak_selector("balanceOf(address)"),
    "decimals()": keccak_selector("decimals()"),
    "symbol()": keccak_selector("symbol()"),
}
for getter in WRAPPER_GETTERS:
    SEL[getter] = keccak_selector(getter)


def rpc_call(rpc_url, to, data):
    resp = requests.post(
        rpc_url,
        json={"jsonrpc": "2.0", "method": "eth_call", "params": [{"to": to, "data": data}, "latest"], "id": 1},
        timeout=20,
    )
    resp.raise_for_status()
    j = resp.json()
    return None if "error" in j else j.get("result")


def addr_from_word(hexres):
    if not hexres or len(hexres) < 66:
        return None
    a = "0x" + hexres[-40:]
    return a if int(a, 16) != 0 else None


def uint_from_word(hexres):
    return int(hexres, 16) if hexres else None


def words(hexres):
    h = hexres[2:]
    return [h[i : i + 64] for i in range(0, len(h), 64)]


def decode_addr_array(hexres):
    w = words(hexres)
    length = int(w[1], 16)
    return ["0x" + x[-40:] for x in w[2 : 2 + length]]


def decode_string(hexres):
    try:
        w = words(hexres)
        length = int(w[1], 16)
        return bytes.fromhex("".join(w[2:]))[:length].decode("utf-8", errors="replace")
    except Exception:
        return None


def classify_source(rpc_url, source_addr):
    """Returns (is_chronicle, chronicle_addr, note) for a price-source address,
    checking direct chronicle()/description() first, then one level of
    ethSource()/btcSource() wrapping. Never guesses -- an address with
    neither is left unconfirmed."""
    desc_res = rpc_call(rpc_url, source_addr, "0x" + SEL["description()"])
    desc = decode_string(desc_res) if desc_res else None
    chron_res = rpc_call(rpc_url, source_addr, "0x" + SEL["chronicle()"])
    chron = addr_from_word(chron_res) if chron_res else None
    if chron:
        return True, chron, desc or "direct chronicle() getter"

    for getter in WRAPPER_GETTERS:
        wrapped_res = rpc_call(rpc_url, source_addr, "0x" + SEL[getter])
        wrapped = addr_from_word(wrapped_res) if wrapped_res else None
        if wrapped:
            inner_desc_res = rpc_call(rpc_url, wrapped, "0x" + SEL["description()"])
            inner_desc = decode_string(inner_desc_res) if inner_desc_res else None
            inner_chron_res = rpc_call(rpc_url, wrapped, "0x" + SEL["chronicle()"])
            inner_chron = addr_from_word(inner_chron_res) if inner_chron_res else None
            if inner_chron:
                return True, inner_chron, f"wraps {getter[:-2]} -> {inner_desc or 'confirmed Chronicle aggregator'}"

    return False, None, None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rpc", default=DEFAULT_RPC, help=f"Ethereum JSON-RPC endpoint (default: {DEFAULT_RPC})")
    parser.add_argument("--csv", default=str(DEFAULT_CSV_PATH))
    parser.add_argument("--json", default=str(DEFAULT_JSON_PATH))
    parser.add_argument("--overview-csv", default=str(DEFAULT_OVERVIEW_CSV_PATH))
    parser.add_argument("--total-json", default=str(DEFAULT_TOTAL_PATH))
    parser.add_argument("--no-output", action="store_true")
    args = parser.parse_args()
    if args.no_output:
        args.csv = args.json = args.overview_csv = args.total_json = None

    print(f"Resolving Pool/AaveOracle from PoolAddressesProvider ({POOL_ADDRESSES_PROVIDER})...", file=sys.stderr)
    pool = addr_from_word(rpc_call(args.rpc, POOL_ADDRESSES_PROVIDER, "0x" + SEL["getPool()"]))
    oracle = addr_from_word(rpc_call(args.rpc, POOL_ADDRESSES_PROVIDER, "0x" + SEL["getPriceOracle()"]))
    base_unit = uint_from_word(rpc_call(args.rpc, oracle, "0x" + SEL["BASE_CURRENCY_UNIT()"]))
    print(f"  Pool={pool}  AaveOracle={oracle}  BASE_CURRENCY_UNIT={base_unit}", file=sys.stderr)

    reserves = decode_addr_array(rpc_call(args.rpc, pool, "0x" + SEL["getReservesList()"]))
    print(f"{len(reserves)} reserve(s) found. Reading price source, aToken balance, and price for each...", file=sys.stderr)

    results = []
    for asset in reserves:
        sym_res = rpc_call(args.rpc, asset, "0x" + SEL["symbol()"])
        symbol = decode_string(sym_res) if sym_res else "?"
        dec_res = rpc_call(args.rpc, asset, "0x" + SEL["decimals()"])
        decimals = uint_from_word(dec_res) if dec_res else 18

        reserve_data = rpc_call(args.rpc, pool, "0x" + SEL["getReserveData(address)"] + asset[2:].rjust(64, "0"))
        # ReserveData struct: configuration(uint256), liquidityIndex(uint128,pad),
        # currentLiquidityRate(uint128,pad), variableBorrowIndex, currentVariableBorrowRate,
        # currentStableBorrowRate, lastUpdateTimestamp(+accruedToTreasury packed),
        # aTokenAddress is the 9th word (index 8) in Aave V3's ReserveData layout.
        a_token = addr_from_word("0x" + words(reserve_data)[8]) if reserve_data else None

        locked_tokens = None
        if a_token:
            bal_res = rpc_call(args.rpc, asset, "0x" + SEL["balanceOf(address)"] + a_token[2:].rjust(64, "0"))
            locked_raw = uint_from_word(bal_res)
            if locked_raw is not None:
                locked_tokens = locked_raw / (10 ** decimals)

        price_res = rpc_call(args.rpc, oracle, "0x" + SEL["getAssetPrice(address)"] + asset[2:].rjust(64, "0"))
        price_raw = uint_from_word(price_res)
        price_usd = price_raw / base_unit if (price_raw is not None and base_unit) else None

        source = addr_from_word(rpc_call(args.rpc, oracle, "0x" + SEL["getSourceOfAsset(address)"] + asset[2:].rjust(64, "0")))
        is_chronicle, chronicle_addr, chronicle_note = (False, None, None)
        if source:
            is_chronicle, chronicle_addr, chronicle_note = classify_source(args.rpc, source)

        value_usd = locked_tokens * price_usd if (locked_tokens is not None and price_usd is not None) else None

        results.append(
            {
                "symbol": symbol,
                "asset": asset,
                "aToken": a_token,
                "lockedTokens": locked_tokens,
                "priceUsd": price_usd,
                "valueUsd": value_usd,
                "source": source,
                "isChronicle": is_chronicle,
                "chronicleAddress": chronicle_addr,
                "chronicleNote": chronicle_note,
            }
        )
        flag = "CHRONICLE" if is_chronicle else "unconfirmed"
        print(f"  {symbol:8s} locked={locked_tokens:>20,.4f}  price=${price_usd:>14,.4f}  value=${value_usd:>18,.2f}  [{flag}]", file=sys.stderr)

    chronicle_reserves = [r for r in results if r["isChronicle"]]
    priced = [r for r in results if r["valueUsd"] is not None]
    # Per an explicit scope decision (see README.md): every reserve counts
    # toward the total, not just the ones with an individually confirmed
    # Aggor/Chronicle source. is_chronicle is kept as real, useful
    # per-reserve evidence, but no longer gates the total below.
    chronicle_total = sum(r["valueUsd"] for r in priced)
    print(f"\n{len(chronicle_reserves)}/{len(results)} reserve(s) individually confirmed Chronicle-involved (live on-chain, not guessed).")
    print(f"Total across all {len(priced)} priced reserves (per scope decision in README.md): ${chronicle_total:,.2f}")

    if args.csv:
        import csv

        with open(args.csv, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["symbol", "asset", "locked_tokens", "price_usd", "value_usd", "is_chronicle", "chronicle_address", "chronicle_note", "source", "aToken"])
            for r in results:
                writer.writerow(
                    [
                        r["symbol"], r["asset"],
                        f"{r['lockedTokens']:.6f}" if r["lockedTokens"] is not None else "",
                        f"{r['priceUsd']:.6f}" if r["priceUsd"] is not None else "",
                        f"{r['valueUsd']:.2f}" if r["valueUsd"] is not None else "",
                        r["isChronicle"], r["chronicleAddress"] or "", r["chronicleNote"] or "",
                        r["source"] or "", r["aToken"] or "",
                    ]
                )
        print(f"\nWrote {args.csv}", file=sys.stderr)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"poolAddressesProvider": POOL_ADDRESSES_PROVIDER, "pool": pool, "aaveOracle": oracle, "reserves": results}, fh, indent=2)
        print(f"Wrote {args.json}", file=sys.stderr)

    if args.overview_csv:
        import csv

        with open(args.overview_csv, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["symbol", "locked_tokens", "price_usd", "value_usd", "is_chronicle_confirmed", "chronicle_note"])
            for r in sorted(priced, key=lambda x: x["valueUsd"] or -1, reverse=True):
                writer.writerow(
                    [
                        r["symbol"],
                        f"{r['lockedTokens']:.6f}" if r["lockedTokens"] is not None else "",
                        f"{r['priceUsd']:.6f}" if r["priceUsd"] is not None else "",
                        f"{r['valueUsd']:.2f}" if r["valueUsd"] is not None else "",
                        r["isChronicle"],
                        r["chronicleNote"] or "",
                    ]
                )
            writer.writerow(["TOTAL (all reserves, per scope decision)", "", "", f"{chronicle_total:.2f}", "", ""])
        print(f"Wrote {args.overview_csv}", file=sys.stderr)

    if args.total_json:
        with open(args.total_json, "w") as fh:
            json.dump(
                {
                    "protocol": "Spark",
                    "totalUsd": round(chronicle_total, 2),
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "breakdownFile": Path(args.overview_csv).name if args.overview_csv else None,
                },
                fh,
                indent=2,
            )
        print(f"Wrote {args.total_json}", file=sys.stderr)


if __name__ == "__main__":
    main()
