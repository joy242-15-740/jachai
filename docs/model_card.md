# Model card: Jachai merchant-transaction integrity system

## Model overview

Jachai is a human-review prioritization system for synthetic Bangla QR
transactions and shops. It combines:

1. a calibrated LightGBM payment model trained on soft targets from weak rules
   and sparse dated cases;
2. a shop score using expected-turnover residuals and peer-group Isolation
   Forest scores;
3. a payer–shop network score using linking payers, community/ring evidence and
   distant-payer share; and
4. configured rank-based fusion into low, review and high bands.

It returns scores and evidence. It does not determine guilt and does not block,
restrict, contact or convert a merchant automatically.

## Intended use

- Rank synthetic merchant cases for a trained analyst.
- Show why a payment or shop needs review.
- Compare monitoring policies in a synthetic replay.
- Support an analyst's documented decision after reviewing context and a
  merchant explanation.

## Out-of-scope use

- Automatic adverse action, criminal allegation or legal determination.
- Real deployment without representative data, governance review, security and
  privacy assessment, calibration, monitoring, appeal operations and a staged
  pilot.
- Decisions based on a score alone or use outside merchant QR integrity.

## Inputs and outputs

Inputs are point-in-time transaction history, synthetic shop/customer metadata,
money-in events and payer–shop graph features. Features must use only
information available at scoring time. Outputs are payment and component
scores, a fused risk score/band, top reason codes, an English analyst note, a
local Bangla notice preview and a policy-simulator result.

The optional LLM only rewords the English analyst note. A validator rejects
numbers absent from evidence, accusation terms and promises; rejection or API
failure returns a deterministic template. Merchant text is always a local
template and is never sent to the LLM.

## Training and supervision

The payment model learns from weak-label votes and sparse dated past cases;
hidden truth is not a training target. Shop and network components are fit or
computed from synthetic history. Thresholds are selected on validation and
then frozen. The held-out pattern is absent from training and validation and is
reserved for the final test and was accessed once after the system was frozen.

## Evaluation status

**Three-seed validation exists for the current rules-in-fusion configuration.**
On the normal synthetic world, rules outperform it; under round-amount evasion,
the current fusion is more robust at the matched band budget. The
weak+cases payment model improves ranking over rules across three seeds, with
the strongest fair comparison at equal analyst budget.

The frozen system was evaluated once on the synthetic final test. Rules were
stronger overall, including on the held-out turnover-burst pattern. No tuning may
follow these results. See [results summary](../reports/summary.md).

## Reported metrics

For the current fusion on three validation seeds: shop PR-AUC is
0.774 ± 0.059 and misuse-value recall at its band budget is 0.947 ± 0.005.
Rules score 0.899 ± 0.033 PR-AUC and 0.968 ± 0.025 value recall on the same
normal world. Under non-round evasion, fusion value recall is 0.893 ± 0.013
versus rules at 0.739 ± 0.053. Final-test PR-AUC was 0.584 for Jachai and 0.843
for rules. These are synthetic, not production, metrics. The agreed success
criteria for adding rules to fusion were not all met on validation: the evasion
and ring criteria were met, the normal-world criterion (within 0.02 PR-AUC of
rules) was not (0.774 vs 0.899).

## Explainability and human oversight

- LightGBM contribution values are grouped into reason codes.
- Fusion components contribute transparent weighted ranks.
- English and Bangla reason templates include only row-derived values.
- Analyst decisions require a reason and are appended to a hash-chained SQLite
  audit log.
- Even a recorded restriction is an instruction for people; the software takes
  no automatic action.

## Fairness and safety

The API can report validation false-alarm rates by area type, shop size and
category. Synthetic slices are useful for detecting obvious implementation
problems but cannot establish real-world fairness. Before deployment, review
false positives, value and error rates across operationally relevant groups,
especially small groups; investigate causes; set minimum sample requirements;
and provide notice and appeal routes.

## Monitoring needed before deployment

- Feature availability, missingness and point-in-time correctness.
- Score and calibration drift, alert volume and analyst capacity.
- False positives, reversals and merchant appeals by group.
- Evasion, new typologies and network-graph failure modes.
- LLM validation/fallback rate without logging secrets or merchant text.
- Decision consistency and audit-log integrity.

## Provenance

Primary evidence is in [reports/summary.md](../reports/summary.md),
[validation_evaluation.md](../reports/validation_evaluation.md),
[ablation.md](../reports/ablation.md), [circularity_note.md](../reports/circularity_note.md)
and [test_access_log.md](../reports/test_access_log.md).
