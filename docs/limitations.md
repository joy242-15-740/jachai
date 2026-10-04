# Limitations and claim boundaries

## Synthetic data

All entities, transactions, labels, cases and outcomes are generated. The
results demonstrate software behavior under assumptions chosen by the team;
they do not estimate real misuse prevalence, detection accuracy, merchant harm,
fee recovery or agent conversion. There is no real deployment data.

## Circularity

The rules and synthetic misuse patterns were designed from the same typology
descriptions. This makes normal-world rule performance unusually strong and can
also reward learned models for reproducing generator choices. Rules outperform
the previous fusion in the reported normal-world validation. Evasion and ring
checks reduce—but do not remove—this circularity.

## Small and unstable slices

Some misuse patterns, case-coverage levels, fairness groups and held-out test
slices contain few shops. Mean ± standard deviation over three seeds helps, but
does not make small counts representative. The cases-only ablation trained in
only one of three seeds. The held-out pattern is confined to the final test and
has no reported final count or metric yet. Subgroup rates and pattern recall can
move sharply with one shop.

## Unvalidated current fusion

The three-seed full-system report evaluates the previous fusion. Rules were
later added as an explicit fusion input. The fast-profile artifact confirms the
implementation but is only a single-seed development artifact. The current
rules-in-fusion configuration is therefore **UNVALIDATED**; results from the
previous fusion cannot be relabelled as its results.

## Test-set status

The final test evaluation has not run. The access log records that an earlier
network diagnostic inspected true pattern labels for all shops, including test
shops, while debugging ring construction. It produced no test metric and tuned
no threshold, but it weakens the ideal isolation story and must be disclosed.
No tuning should follow the single final test evaluation.

## Labels and feedback

Weak labels encode rule assumptions. Dated past cases are sparse, biased and
sometimes noisy. A model can learn investigation practice rather than misuse,
and retraining on analyst decisions can amplify inconsistent or discriminatory
decisions. Case-only supervision was unstable in the reported seeds.

## Coverage and evasion

The generator covers named patterns, not every form of hidden cash-out or
legitimate commerce. Misusers can change amounts, timing, payer mix, shops,
identities or channels. The non-round evasion test is only one adaptation.
P2P disguise is behind a scenario switch and absent from the reported worlds.

## Fairness

Area type, size and category are synthetic. Passing a fairness check on those
groups would not prove fairness for real merchants. Small group counts create
unstable false-alarm rates. Real deployment would require representative data,
local context, review of proxy effects, appeal outcomes and ongoing monitoring.

## Explanations and LLM

Feature contributions explain the model score, not the real cause of a
transaction. Human-readable reasons can sound more certain than the evidence.
The optional LLM is limited to English rewording and guarded by validation, but
validators cannot guarantee good judgment or complete context. Bangla merchant
text is a local template and still needs native-language, legal and operational
review before use.

## Simulator

Policy outcomes depend on assumed analyst recall, false-confirm rate, fee rate,
limits, acceptance and displacement. The headline simulator artifact uses the
fast profile, one replay seed and 15 days. Its taka values are demo outputs, not
forecasts. In that run no agent signed and no misuse value was rerouted.

## Operations and security

The demo lacks production authentication, authorization, encryption/key
management, rate limiting, resilient serving, model registry, drift alerts,
case-management integration and a real appeal workflow. SQLite and bundled JSON
are demo choices. A hash chain can reveal modification but is not a substitute
for access control, backups or external immutable storage.

## Appropriate claim

Jachai is a synthetic-data prototype showing a configurable, explainable,
human-in-the-loop workflow. It is not a proven detector for real upay traffic
and never supports a claim of perfect detection or automatic guilt.

