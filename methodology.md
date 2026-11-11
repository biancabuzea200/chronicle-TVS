Chronicle Total TVS Methodology

Definition
Total TVS is the sum of two components, measured at the same snapshot time:
Total TVS: TVS Proof of Asset + TVS Data Feeds

Component 1: Proof-of-Asset TVS
Proof of Asset TVS is the total AUM of every tokenized fund that has a live Chronicle Proof-of-Asset integration, as shown on the Chronicle PoA dashboard.
Inclusion Rules:
Live integration only. The fund must have an active Chronicle Proof of Asset feed at the snapshot time. 
One fund, one count. If a fund has more than one Chronicle feed (for example, a NAV feed and a 24/7 price proxy), its AUM is counted once.
Value = AUM as reported by the dashboard. This is the fund's total assets under management as verified by Chronicle, not just the onchain token supply.
All chains combined. Counted per fund, not per chain, so a fund issued on several chains is not counted more than once.


Component 2: Data Feeds TVS
Data Feeds TVS is the total value secured by every market/vault/protocol integration that relies on a live Chronicle data feed in production.
Inclusion Rules:
Live integration only. The integration must have an active Chronicle feed deployed in production at the snapshot time.

Value = total value of the integration (e.g. a market's total supplied TVL) that relies on the Chronicle feed for its price data. 