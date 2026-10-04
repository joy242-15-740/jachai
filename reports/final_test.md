# Final frozen-system test evaluation

**FINAL TEST — single access.** Synthetic data only. The current full system was trained on train rows, thresholds were frozen on validation, and hidden test truth was read only for this report. No tuning may follow these results.

Test shops: 615; misuse shops: 71; analyst-capacity k: 10; matched band budget: 70; held-out pattern: `turnover_burst`.

## System and baselines at matched budgets

| method | pr_auc | k_precision | k_recall | k_value_recall | k_honest_shops | bands_precision | bands_recall | bands_value_recall | bands_honest_shops |
|---|---|---|---|---|---|---|---|---|---|
| Jachai with rules | 0.584 | 0.800 | 0.113 | 0.169 | 2 | 0.614 | 0.606 | 0.774 | 27 |
| Rules only | 0.843 | 1 | 0.141 | 0.249 | 0.000 | 0.843 | 0.831 | 0.894 | 11 |
| Blanket limit | 0.486 | 1 | 0.141 | 0.277 | 0.000 | 0.371 | 0.366 | 0.549 | 44 |

## Recall by pattern at the matched band budget

| method | recall_round_amount_cash_desk | recall_remittance_drain | recall_turnover_burst | recall_limit_bypass | recall_incentive_splitting |
|---|---|---|---|---|---|
| Jachai with rules | 1 | 0.833 | 0.133 | 0.933 | 1 |
| Rules only | 1 | 1 | 0.600 | 1 | 1 |
| Blanket limit | 0.300 | 0.333 | 0.700 | 0.000 | 0.000 |

These results describe a synthetic test partition, not real-world accuracy or financial impact.
