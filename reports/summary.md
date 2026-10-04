# Jachai results summary

This document only summarizes artifacts already present in `reports/`. No model
was trained, no world was regenerated, no validation was rerun, and the final
test set was not evaluated to create it. All results use synthetic data and show
whether the method works in that synthetic setting—not expected production
accuracy or financial impact.

## Evidence status

- **VALIDATION — 3 seeds:** mean ± standard deviation over seeds 42, 7 and
  2026, on validation shops/dates. These are repeatability checks, not final
  test results.
- **SINGLE-SEED / DIAGNOSTIC:** one synthetic run; useful for a demo or a
  directional check only.
- **UNVALIDATED:** implemented after the three-seed report, or not evaluated
  against hidden truth in an existing report.
- **FINAL TEST:** not evaluated. The access log records one earlier diagnostic
  that touched test-shop labels but computed no test metric and tuned no
  threshold. See [test_access_log.md](test_access_log.md).

The three-seed full-system figures below describe the fusion evaluated in
[validation_evaluation.md](validation_evaluation.md). The current fusion adds
rules as an input; that change is **UNVALIDATED** and these figures must not be
presented as validation of the current system.

## System versus baselines — VALIDATION, 3 seeds, previous fusion

At the analyst-capacity budget (`k=10` validation shops per seed), rules were
strongest on the normal synthetic world. At the fused system's review/high-band
budget (43, 52 and 46 shops by seed), the same ordering remained. This result
weakens the pitch and is reported directly: the generator and rules share the
same typology definitions, which favours the rules.

| shop-level method | PR-AUC | precision @ k | misuse-value recall @ k | honest shops @ k | recall at band budget | misuse-value recall at band budget |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Previous fused system | 0.740 ± 0.068 | 0.833 ± 0.047 | 0.269 ± 0.058 | 1.667 ± 0.471 | 0.771 ± 0.063 | 0.926 ± 0.009 |
| Rules only | 0.899 ± 0.033 | 1.000 ± 0.000 | 0.586 ± 0.064 | 0.000 ± 0.000 | 0.906 ± 0.077 | 0.971 ± 0.024 |
| Blanket limit | 0.137 ± 0.019 | 0.000 ± 0.000 | 0.000 ± 0.000 | 10.000 ± 0.000 | 0.108 ± 0.024 | 0.191 ± 0.068 |

Source: [validation_evaluation.md](validation_evaluation.md). The earlier
single-seed payment/shop baseline table is retained in
[baselines.md](baselines.md), but the three-seed comparison above is the more
repeatable evidence.

## Matched-budget payment comparison — VALIDATION, 3 seeds

This comparison gives each method exactly the same number of payment flags.
At the rules' budget (296.333 ± 35.160 flags), the weak+cases model did not show
a clear advantage. At the larger analyst-capacity budget (`k=1,000` payments),
it ranked more misuse value and flagged fewer distinct honest shops.

| budget and method | precision | recall | misuse-value recall | honest shops flagged |
| --- | ---: | ---: | ---: | ---: |
| Rules budget — rules | 0.787 ± 0.040 | 0.359 ± 0.010 | 0.435 ± 0.037 | 56.333 ± 4.497 |
| Rules budget — weak + cases | 0.771 ± 0.010 | 0.354 ± 0.029 | 0.494 ± 0.047 | 58.333 ± 4.110 |
| `k=1,000` — rules | 0.243 ± 0.038 | 0.373 ± 0.014 | 0.446 ± 0.037 | 339.667 ± 0.471 |
| `k=1,000` — weak + cases | 0.402 ± 0.075 | 0.614 ± 0.023 | 0.726 ± 0.049 | 302.667 ± 34.874 |

Source: [ablation.md](ablation.md).

## Evasion and ring evidence — VALIDATION, 3 seeds, previous fusion

When misuse amounts were made non-round and the system was **not retrained**,
the previous fusion became more robust than rules at the equal band budget:

| evasion-world method | PR-AUC | precision | recall | misuse-value recall |
| --- | ---: | ---: | ---: | ---: |
| Previous fused system | 0.620 ± 0.049 | 0.533 ± 0.073 | 0.693 ± 0.060 | 0.869 ± 0.019 |
| Rules only | 0.588 ± 0.051 | 0.434 ± 0.032 | 0.568 ± 0.057 | 0.754 ± 0.032 |

The ring flag alone had modest overall PR-AUC (0.235 ± 0.057), but recovered
93.1% mean recall on limit-bypass shops at the band budget across the three
reported seeds (seed values 0.909, 0.955 and 0.929). This is specialized
evidence: it does not establish strong general detection by the network score.

Source: [validation_evaluation.md](validation_evaluation.md) and its
[JSON artifact](validation_evaluation.json).

## Label-source ablation — VALIDATION, 3 seeds

| training target | payment PR-AUC | value recall at own frozen threshold | seeds successfully trained |
| --- | ---: | ---: | ---: |
| Rules only detector | 0.301 ± 0.004 | 0.435 ± 0.037 | 3 |
| Weak labels only | 0.337 ± 0.028 | 0.636 ± 0.004 | 3 |
| Weak labels + dated past cases | 0.483 ± 0.006 | 0.689 ± 0.073 | 3 |
| Cases only | 0.026 ± 0.000 | 0.796 ± 0.000 | 1 |

Weak labels plus cases ranked better than rules in all three seeds. Cases alone
were not trainable in two seeds because there was no misuse example available
for learning or tuning; its one-seed value-recall figure comes with very low
precision and must not be used as evidence that cases-only works.

Source: [ablation.md](ablation.md).

## Past-case coverage curve — VALIDATION, 3 seeds

| case coverage | payment PR-AUC | misuse-value recall | precision at rules budget |
| --- | ---: | ---: | ---: |
| 2% | 0.423 ± 0.015 | 0.609 ± 0.057 | 0.757 ± 0.030 |
| 5% | 0.523 ± 0.031 | 0.695 ± 0.067 | 0.805 ± 0.038 |
| 10% | 0.558 ± 0.044 | 0.680 ± 0.019 | 0.788 ± 0.027 |

The 2%→5% PR-AUC increase is larger than the reported seed variation. The
5%→10% wiggle is within seed-to-seed noise: value recall and matched-budget
precision do not improve monotonically. Do not select or advertise 10% as an
optimum from this curve.

## Policy simulator headlines — FAST PROFILE, SINGLE-SEED / DIAGNOSTIC

These are a 15-day replay with 300-shop development-scale artifacts, replay
seed 1042 and policy seed 7. They are **not validation results**, do not use the
test set, and are not forecasts of real taka impact.

| policy | misuse Tk stopped | fees recaptured Tk | honest shops restricted | genuine sales blocked Tk | alerts/day | agent leads |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Do nothing | 0 | 0 | 0 | 0 | 0.0 | 0 |
| Blanket limit | 1,546,900 | 14,309 | 12 | 2,019,130 | 0.0 | 0 |
| Rules only | 4,535,569 | 41,954 | 0 | 0 | 2.0 | 0 |
| Jachai targeted | 4,546,756 | 42,057 | 0 | 0 | 3.533 | 0 |
| Jachai + convert | 4,546,756 | 42,057 | 0 | 0 | 3.533 | 1 |

No agent was signed and no misuse taka was rerouted in this replay. The tiny
difference between rules and targeted Jachai is not robust evidence. Source:
[fast/simulator/results.md](fast/simulator/results.md).

## What remains UNVALIDATED

- The current rules-in-fusion change shown in
  [fast/system_training.json](fast/system_training.json).
- The complete current system on multiple validation seeds.
- The held-out misuse pattern: the existing validation report says those shops
  are all in the untouched final test partition.
- Final test performance, real-world calibration, operational latency at real
  scale, fairness on real merchants, and any production financial impact.

