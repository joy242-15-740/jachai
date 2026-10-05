# Jachai results summary

This document summarizes generated artifacts in `reports/`. The current frozen
fusion was validated over three seeds and evaluated once on the final synthetic
test. These results show behavior in the configured synthetic setting—not
expected production accuracy or financial impact.

## Evidence status

- **VALIDATION — 3 seeds:** mean ± standard deviation over seeds 42, 7 and
  2026, on validation shops/dates. These are repeatability checks, not final
  test results.
- **SINGLE-SEED / DIAGNOSTIC:** one synthetic run; useful for a demo or a
  directional check only.
- **FINAL TEST — SINGLE ACCESS:** current frozen system, 615 test shops and 71
  misuse shops. No tuning may follow. See [final_test.md](final_test.md) and
  [test_access_log.md](test_access_log.md).

The three-seed figures below describe the current fusion, including rules as an
equal-weight input. The agreed success criteria for adding rules to fusion were **not all met**: evasion (0.599 vs 0.588 PR-AUC) and ring recall (0.823 normal / 0.591 evasion vs 0.805 / 0.024) were met, but the normal-world criterion (within 0.02 PR-AUC of rules) was not (0.774 vs 0.899). Source: the computed success checks in [validation_evaluation.md](validation_evaluation.md).

## System versus baselines — VALIDATION, 3 seeds, current fusion

At the analyst-capacity budget (`k=10` validation shops per seed), rules were
strongest on the normal synthetic world. At the fused system's review/high-band
budget (43, 51 and 45 shops by seed), the same ordering remained. This result
weakens the pitch and is reported directly: the generator and rules share the
same typology definitions, which favours the rules.

| shop-level method | PR-AUC | precision @ k | misuse-value recall @ k | honest shops @ k | recall at band budget | misuse-value recall at band budget |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Jachai with rules | 0.774 ± 0.059 | 0.867 ± 0.125 | 0.207 ± 0.081 | 1.333 ± 1.247 | 0.820 ± 0.045 | 0.947 ± 0.005 |
| Rules only | 0.899 ± 0.033 | 1.000 ± 0.000 | 0.586 ± 0.064 | 0.000 ± 0.000 | 0.898 ± 0.078 | 0.968 ± 0.025 |
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

## Evasion and ring evidence — VALIDATION, 3 seeds, current fusion

When misuse amounts were made non-round and the system was **not retrained**,
the current fusion was more robust than rules at the equal band budget:

| evasion-world method | PR-AUC | precision | recall | misuse-value recall |
| --- | ---: | ---: | ---: | ---: |
| Jachai with rules | 0.599 ± 0.024 | 0.573 ± 0.040 | 0.738 ± 0.048 | 0.893 ± 0.013 |
| Rules only | 0.588 ± 0.051 | 0.433 ± 0.041 | 0.560 ± 0.068 | 0.739 ± 0.053 |

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

## Final test — SINGLE ACCESS

At the matched 70-shop band budget, Jachai with rules achieved PR-AUC `0.584`,
precision `0.614`, recall `0.606` and misuse-value recall `0.774`. Rules achieved
PR-AUC `0.843`, precision `0.843`, recall `0.831` and value recall `0.894`.
Held-out turnover-burst recall was `0.133` for Jachai and `0.600` for rules.
The honest conclusion is that rules were stronger on this synthetic final test.
Real-world calibration, operational latency at scale, fairness on real merchants
and production financial impact remain unvalidated.
