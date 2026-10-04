# Jachai project report

## Problem

Bangla QR merchant payments can be misused as hidden cash-out: a payer sends a
merchant a QR payment, receives cash instead of goods, and bypasses the normal
cash-out path. Blanket limits can also restrict honest merchants. Jachai asks a
narrower question: which payments and shops need human review, and what evidence
made them unusual?

## Solution

Jachai is a synthetic-data prototype for merchant-transaction integrity. It
generates a configurable world, computes point-in-time payment, payer, shop and
network features, and combines three risk components:

1. a calibrated LightGBM payment score trained from weak labels and sparse,
   dated cases;
2. a shop score based on expected turnover and peer-group isolation; and
3. a payer–shop network score for diversity, distance, communities and rings.

Configured fusion produces a low, review or high band. SHAP and transparent
component contributions become structured reason codes. The optional LLM may
only reword the English analyst note; a validator rejects invented numbers,
accusations and promises. Bangla merchant text always comes from a local polite
template. The system recommends; a human records every decision and reason.

## Key features

- Seeded synthetic data with six misuse patterns and honest look-alikes.
- Shop-and-time evaluation splits, a held-out pattern and leakage checks.
- Alert queue, evidence-rich case view and append-only hash-chained audit log.
- Five-policy simulator comparing no action, blanket limits, rules, targeted
  review and targeted review plus agent conversion.
- Fairness slices, evidence-status labels, data/model cards and limitations.
- API-backed dashboard with generated static demo data when the API is offline.
- Persistent light/dark themes, Bangla font support and reduced-motion support.

## AI approach and evidence

On three synthetic validation seeds, the previous fusion reached shop PR-AUC
`0.740 ± 0.068`; rules reached `0.899 ± 0.033`. This honestly weakens any claim
that fusion is always better: the generator and rules share typology definitions.
At an equal 1,000-payment budget, weak labels plus dated cases achieved
`0.726 ± 0.049` misuse-value recall versus `0.446 ± 0.037` for rules. Under the
non-round evasion test, the previous fusion achieved `0.869 ± 0.019` value
recall versus `0.754 ± 0.032` for rules at the same band budget.

These are synthetic validation findings, not real-world accuracy. The current
rules-in-fusion change is **UNVALIDATED**, and the final test has not been run.
The authoritative tables and evidence labels are in
[reports/summary.md](../reports/summary.md).

## Potential impact

The intended operational value is prioritization: focus limited analyst time on
the cases with the strongest combined evidence, reduce unnecessary restrictions
on honest shops, identify possible agent-conversion leads and keep every action
under human control. The simulator makes assumptions and trade-offs visible; it
does not forecast production taka impact.

## Responsible AI

Jachai contains no real personal data. Hidden synthetic truth is evaluation-only
and is not exposed by the API. There is no automatic blocking, accusation or
merchant contact. Decisions require a human reason, merchant language is polite,
and an appeal preview is included. Synthetic fairness checks can expose software
problems but cannot establish real-world fairness. Production use would require
representative data, security controls, governance, calibration, monitoring and
a staged pilot.

## Technology and reproducibility

The backend and ML stack uses Python 3.12, pandas, NumPy, scikit-learn,
LightGBM, NetworkX, FastAPI and Pydantic. The dashboard uses Next.js,
TypeScript, Tailwind and Recharts. Dependencies and licences are recorded in
[third_party.md](third_party.md). Use `make test` for the fixture-only quality
suite and `make demo-data` for the isolated fast-profile demo artifacts.

## Limitations

All data and outcomes are synthetic. The generator/rules relationship creates
circularity, some slices are small, only one evasion strategy is tested, and
there is no deployment evidence. SQLite, static demo JSON and the optional LLM
path are prototype choices. Full claim boundaries are in
[limitations.md](limitations.md).
