# Data card: Jachai synthetic world

## Summary

Jachai uses only generated data. The reference world contains 3,000 synthetic
shops, 30,000 synthetic customers and 600 synthetic agents over 120 days from
1 July to 28 October 2026. The fast development profile contains 300 shops,
3,000 customers and 60 agents over 30 days from 16 September to 15 October
2026. IDs are random strings; there are no real names, phone numbers, NIDs,
accounts or real transaction records.

Sources: [reference world summary](../reports/world_summary.md),
[fast world summary](../reports/fast/world_summary.md), and
[data assumptions](../data/ASSUMPTIONS.md).

## Intended use

- Develop and demonstrate point-in-time merchant-transaction integrity
  features, models, explanations and policy simulation.
- Test whether a workflow can prioritize synthetic cases while preserving
  human review.
- Compare methods under known synthetic truth.

It is not a representative sample of upay, Bangla QR, Bangladesh merchants or
customers. It must not be used to estimate real prevalence, accuracy, revenue,
fairness or enforcement impact.

## Tables and entities

- Shops: category, area type, size tier, synthetic location, opening date and
  number of QR codes.
- Customers and agents: synthetic IDs, locations and account metadata.
- Events: QR payments, remittances, add-money, dated past cases, and optional
  P2P transfers behind a scenario switch.
- Generated hidden truth: misuse label and pattern at payment/shop level. These
  fields are evaluation-only and are removed from API-facing public views.

## Generation and scenarios

The seeded generator creates category-specific basket distributions, ordinary
commerce, six misuse typologies and honest look-alikes. The reference report
contains round-amount cash desks, remittance drain, turnover bursts, limit
bypass and post-1-October incentive splitting; P2P disguise is off in that
reported world. Honest look-alikes include large-ticket retail, haat-day
spikes, phone purchases, bulk grocery/clothing/pharmacy purchases and new-shop
ramp-up.

The world contains a 1 October regime change. All figures are fictional and
controlled by configuration. Re-running with the same seed is deterministic.

## Labels and observable supervision

Hidden true labels are available only to evaluation. Training uses labeling
functions and sparse, biased, dated shop-level cases. In the reference world,
210 shops have observable past cases; this is deliberately incomplete and
noisy. The fast world has 21 past cases, 11 closed cases and five misuse shops
among those cases.

The case-coverage experiment shows that more synthetic cases can help, but the
5%→10% movement is within three-seed noise. See
[label-source ablation](../reports/ablation.md).

## Splits and leakage controls

Evaluation splits by shop and time. A shop does not appear across train and
test, thresholds are frozen on validation, and one misuse pattern is held out
from training. The final test set is reserved for one final evaluation. The
single-feature leakage report passes its configured 0.95 strength threshold,
although amount-relative-to-category remains strong at 0.943 and deserves
continued scrutiny.

Sources: [leakage check](../reports/leakage_check.md) and
[test access log](../reports/test_access_log.md).

## Privacy and safety

- Synthetic data only; no real PII is required or accepted.
- Public API views remove hidden truth columns.
- Merchant-facing text asks for no personal data in the demo.
- Synthetic location and demographic-like group labels must not be mistaken
  for real people or communities.

## Known biases and gaps

- The generator and rules share the same written typologies, creating
  circularity that favours the rules.
- Ticket sizes, geography, merchant mix, behavior and case processes are
  assumptions, not measurements from deployment.
- Pattern and subgroup counts are small in some validation/test slices.
- P2P disguise is not present in the reported reference or fast world.
- Adaptive adversaries, data outages, duplicate identities, account takeover,
  collusion outside the generated graph and concept drift are incomplete.
- Fairness on synthetic groups does not establish fairness for real merchants.

## Maintenance

Changes to generation assumptions belong in `configs/`, must update
`data/ASSUMPTIONS.md`, and require regenerated reports with seed and config
fingerprint recorded. Generated transaction data remains gitignored; summaries
and assumptions are committed.

