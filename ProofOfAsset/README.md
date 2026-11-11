# Proof-of-Asset TVS (Component 1)

Computes Component 1 of Total TVS per [`methodology.md`](../methodology.md):
total AUM of every tokenized fund with a live Chronicle Proof-of-Asset
integration, as shown on https://chroniclelabs.org/dashboard/proof-of-asset.

## Setup

```
pip install -r requirements.txt
playwright install chromium
```

(A real browser is required: the dashboard sits behind Vercel's bot-challenge,
which returns HTTP 429 to plain HTTP clients like `curl` or `requests`.)

## Run

```
python3 poa_tvs.py
python3 poa_tvs.py --json poa_snapshot.json --csv poa_funds.csv
```

Prints each fund and its value, applies the "one fund, one count" rule
(cards reporting an identical value are duplicate feeds -- e.g. a NAV feed
and its 24/7 price-proxy feed -- for the same underlying fund, and are only
counted once), then prints the total and cross-checks it against the
dashboard's own headline `proofOfAssetValueSecured` figure.

## How it works

The dashboard is a Next.js app; fund values aren't served by a plain REST
endpoint, they're embedded in the page's React Server Components payload
(`self.__next_f.push(...)` script tags). The script loads the page with a
headless Chromium (Playwright), reconstructs that payload, and parses the
fund list straight out of it.
