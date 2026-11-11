#!/usr/bin/env python3
"""
Computes Component 1 (Proof-of-Asset TVS) of Chronicle's Total TVS, per methodology.md:
    "Proof of Asset TVS is the total AUM of every tokenized fund that has a live
    Chronicle Proof-of-Asset integration, as shown on the Chronicle PoA dashboard."

Source: https://chroniclelabs.org/dashboard/proof-of-asset

The dashboard is a Next.js app behind Vercel's bot-challenge, so a plain HTTP
request gets a 429. This script drives a real (headless) browser with
Playwright, then reads the fund data straight out of the page's embedded
React Server Components payload (the same data the dashboard renders from) --
there is no public REST endpoint that returns fund values.

Per the "one fund, one count" rule, two cards that report the exact same
`tvs` value are treated as two feeds on one underlying fund (e.g. a NAV feed
and its 24/7 price-proxy feed) and are only counted once.

Usage:
    pip install playwright
    playwright install chromium
    python3 poa_tvs.py [--json out.json] [--csv out.csv]
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

DASHBOARD_URL = "https://chroniclelabs.org/dashboard/proof-of-asset"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)\s*</script>", re.DOTALL)


def fetch_rendered_html() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        resp = page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=60_000)
        if resp is None or resp.status != 200:
            status = resp.status if resp else "no response"
            raise RuntimeError(f"Failed to load dashboard (status={status})")
        page.wait_for_timeout(2000)  # let any late client-side rendering settle
        html = page.content()
        browser.close()
        return html


def extract_flight_buffer(html: str) -> str:
    """Concatenate the Next.js RSC ("flight") string chunks embedded in <script> tags."""
    chunks = []
    for m in PUSH_RE.finditer(html):
        try:
            arr = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if len(arr) >= 2 and isinstance(arr[1], str):
            chunks.append(arr[1])
    if not chunks:
        raise RuntimeError(
            "Could not find any Next.js flight data in the page -- "
            "the dashboard's markup may have changed."
        )
    return "".join(chunks)


def parse_funds(buf: str):
    dec = json.JSONDecoder()

    try:
        idx = buf.index('{"data":[{"name":')
    except ValueError as e:
        raise RuntimeError("Could not locate the fund list in the page data.") from e
    fund_payload, _ = dec.raw_decode(buf, idx)
    funds = fund_payload["data"]

    site_figures = None
    try:
        idx2 = buf.index('{"totalValueSecured"')
        site_figures, _ = dec.raw_decode(buf, idx2)
    except ValueError:
        pass  # optional cross-check data; not required

    return funds, site_figures


def dedupe_funds(funds):
    """Collapse cards that share an identical tvs value (same fund, multiple feeds)."""
    seen_tvs = set()
    unique = []
    dropped = []
    for f in funds:
        tvs = f["tvs"]
        if tvs in seen_tvs:
            dropped.append(f)
            continue
        seen_tvs.add(tvs)
        unique.append(f)
    return unique, dropped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="write full results to this JSON file")
    parser.add_argument("--csv", help="write the fund table to this CSV file")
    args = parser.parse_args()

    print(f"Fetching {DASHBOARD_URL} ...", file=sys.stderr)
    html = fetch_rendered_html()
    buf = extract_flight_buffer(html)
    funds, site_figures = parse_funds(buf)
    unique, dropped = dedupe_funds(funds)
    unique.sort(key=lambda f: f["tvs"], reverse=True)

    total = sum(f["tvs"] for f in unique)

    print(f"\n{'Fund':50s} {'Slug':38s} {'Value (USD)':>18s}")
    print("-" * 110)
    for f in unique:
        print(f"{f['name']:50s} {f['slug']:38s} {f['tvs']:>18,.2f}")

    if dropped:
        print(f"\nExcluded as duplicate feeds of an already-counted fund (\"one fund, one count\"):")
        for f in dropped:
            print(f"  - {f['name']} ({f['slug']}) -- tvs matches another card")

    print(f"\n{'Funds counted:':30s} {len(unique)}")
    print(f"{'Total Proof-of-Asset TVS:':30s} ${total:,.2f}")

    if site_figures:
        reported = site_figures.get("proofOfAssetValueSecured")
        reported_count = site_figures.get("tokenizedFundsCount")
        if reported is not None:
            match = "OK" if abs(reported - total) < 0.01 else "MISMATCH"
            print(f"\nCross-check vs. dashboard's own headline figure: ${reported:,.2f} [{match}]")
        if reported_count is not None and reported_count != len(unique):
            print(f"Note: dashboard reports {reported_count} tokenized funds, computed {len(unique)}")

    snapshot_at = datetime.now(timezone.utc).isoformat()

    if args.json:
        payload = {
            "snapshotAt": snapshot_at,
            "source": DASHBOARD_URL,
            "funds": [
                {"name": f["name"], "slug": f["slug"], "issuer": f.get("issuer"), "valueUsd": f["tvs"]}
                for f in unique
            ],
            "excludedDuplicateFeeds": [
                {"name": f["name"], "slug": f["slug"], "valueUsd": f["tvs"]} for f in dropped
            ],
            "totalProofOfAssetTvsUsd": total,
            "dashboardReportedTotalUsd": site_figures.get("proofOfAssetValueSecured") if site_figures else None,
        }
        with open(args.json, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nWrote {args.json}", file=sys.stderr)

    if args.csv:
        import csv

        with open(args.csv, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["name", "slug", "issuer", "value_usd"])
            for f in unique:
                writer.writerow([f["name"], f["slug"], f.get("issuer", ""), f"{f['tvs']:.2f}"])
        print(f"Wrote {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
