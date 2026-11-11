#!/usr/bin/env python3
"""
Sums every protocol's `chronicle_total.json` (one per DataFeeds/<protocol>/
folder, e.g. morpho/chronicle_total.json, Sky/chronicle_total.json) into a
single Data Feeds TVS grand total.

This script does no on-chain/API work itself -- it only reads files that
each protocol's own script (morpho_curators.py, sky_ilks.py, ...) already
wrote. Run those first (or just re-run them whenever you want fresh
numbers), then run this to get the combined total.

Never hand-edit the per-protocol chronicle_total.json files or this
script's own output -- everything here is regenerated from source.

Usage:
    python3 chronicle_total_tvs.py
    python3 chronicle_total_tvs.py --json data_feeds_tvs.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATAFEEDS_DIR = Path(__file__).parent
DEFAULT_JSON_PATH = DATAFEEDS_DIR / "data_feeds_tvs.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", default=str(DEFAULT_JSON_PATH), help=f"write the combined total to this path (default: {DEFAULT_JSON_PATH})")
    parser.add_argument("--no-output", action="store_true", help="skip writing --json")
    args = parser.parse_args()

    totals = []
    for total_file in sorted(DATAFEEDS_DIR.glob("*/chronicle_total.json")):
        with open(total_file) as fh:
            data = json.load(fh)
        data["_sourceFile"] = str(total_file.relative_to(DATAFEEDS_DIR))
        totals.append(data)

    if not totals:
        print("No chronicle_total.json files found under DataFeeds/*/ -- run each protocol's script first.", file=sys.stderr)
        sys.exit(1)

    grand_total = sum(t["totalUsd"] for t in totals)

    print(f"{'Protocol':20s} {'Total (USD)':>18s}  Generated at                     Source")
    print("-" * 100)
    for t in sorted(totals, key=lambda x: x["totalUsd"], reverse=True):
        print(f"{t['protocol']:20s} {t['totalUsd']:>18,.2f}  {t.get('generatedAt', '?'):32s}  {t['_sourceFile']}")
    print("-" * 100)
    print(f"{'TOTAL (Data Feeds TVS)':20s} {grand_total:>18,.2f}")

    if not args.no_output:
        with open(args.json, "w") as fh:
            json.dump(
                {
                    "totalUsd": round(grand_total, 2),
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "components": [
                        {"protocol": t["protocol"], "totalUsd": t["totalUsd"], "generatedAt": t.get("generatedAt"), "sourceFile": t["_sourceFile"]}
                        for t in totals
                    ],
                },
                fh,
                indent=2,
            )
        print(f"\nWrote {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
