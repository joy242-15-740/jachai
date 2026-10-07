# What the on-site checks show

Synthetic fast-profile data only. Analysts decide. Nothing here blocks a shop. The hidden label is used to grade, and thresholds are fit on validation targets from rules and past cases. The test split is not scored. Reference-world reports (`reports/validation_evaluation.md`, `reports/final_test.md`, `reports/summary.md`) are unchanged. Every number below is copied from a file under `reports/onsite/ai/`.

## Which model we keep

We compared rules, a shared-payer count, logistic regression, random forest, XGBoost, LightGBM, isolation forest and a small autoencoder on the same 43 point-in-time columns and the same shop-and-time split. Three fast seeds (42, 7, 2026). Mean validation size is 1,823 payments and 26 misuse payments, and about 56 shops with 3 misuse shops.

We keep LightGBM. Random forest leads mean supervised payment PR-AUC by 0.310, and it leads on all three seeds, but that gap sits inside the combined seed-to-seed standard deviation of 0.506. The bar set before the run was a gap larger than that spread. LightGBM’s validation payment precision is 0.374 ± 0.331, recall 0.620 ± 0.182, F1 0.435 ± 0.286, false-positive rate 0.015 ± 0.011, PR-AUC 0.363 ± 0.284, misuse taka caught 0.709 ± 0.060. It trains in about 0.23 seconds. Rules still have the lower false-positive rate (0.002 ± 0.001). The shared-payer count does not separate rings from neighbours (PR-AUC 0.012 ± 0.011). Shop metrics rest on about three misuse shops, so they swing widely. Full cells: `reports/onsite/ai/model_comparison.md`.

## Which feature groups carry the score

The same LightGBM, now with four extra columns, was opened by group. TreeSHAP (LightGBM’s own contributions) says the amount group — round amounts, size versus the usual basket, and payments just under the incentive cap — is 0.576 ± 0.028 of the mean absolute contribution. Scrambling that group drops validation PR-AUC by 0.318 ± 0.276. Retraining without it does not show a stable PR-AUC drop (0.001 ± 0.127): other columns can stand in, and the seed spread is wide. The payer’s running day total is the next group (SHAP share 0.132 ± 0.023, permutation drop 0.131 ± 0.071). Shop history and who-and-where are smaller. Timing and money-in-then-out are near the bottom on this sample.

Four mechanism columns were added because they were missing as explicit measures: payer repeat rate, one-time-payer share, hour versus the shop’s own usual hour, and minutes since the last top-up or remittance. Together they are the `mechanism` group: SHAP share 0.044 ± 0.004, permutation PR-AUC drop 0.011 ± 0.011, retrain PR-AUC drop 0.009 ± 0.020. Dropping each column alone moves PR-AUC by about zero, inside a spread of a few thousandths. On this fast sample they are a small slice of the score. The stories in the table are hypotheses; the evidence column is the measurement. Mean validation size in that run is N=1,823 payments, 26 positives. Source: `reports/onsite/ai/feature_justification.md`.

## Where the score holds, and where the sample is thin

The robustness run is one fast seed (42), validation N=1,416 payments, 40 misuse. It uses the extended feature set, so its recall is not the three-seed LightGBM number above.

Two misuse patterns appear in that validation window. Round-amount cash desk: 9 of 14 flagged (recall 0.643). Limit bypass: 10 of 26 flagged (recall 0.385). Remittance drain, incentive splitting, P2P disguise and the held-out turnover burst have zero validation payments here.

Honest look-alikes are quiet in this slice, on small counts. Wholesaler payments: 0 flagged of 15. Electronics: 0 of 21. New-shop ramp: 0 of 22. Haat-day spike pattern: 0 of 49. Festival spikes: 0 payments. Durga Puja in the config is 2026-10-16 to 2026-10-21, and this calendar ends 2026-10-15, so the empty festival cell is the calendar.

The fast validation window starts after 1 Oct, so it has no “before” half. On train shops, which the model has already seen, recall is 0.527 before 1 Oct (N=12,373, positives=188) and 0.359 on or after 1 Oct (N=6,827, positives=156). Mean score barely moves (0.014 to 0.015). Validation, all after the change, has recall 0.475, precision 1.000, false-positive rate 0.000 (N=1,416, positives=40). That before/after contrast is a description of training rows, not a holdout test of the regime change.

Calibration against the hidden label piles 1,371 of 1,416 payments into the 0–0.1 bin (mean predicted about 0, observed misuse rate 0.007). The top bin, 0.9–1.0, has 14 payments and all 14 are misuse. Bins in between have 1 to 18 payments, so the middle of the reliability plot is too thin to read. The calibrator was fit to validation targets, not to the hidden label.

Of 19 flagged misuse payments, all 19 have an expected reason code somewhere in the top 3 (share 1.000). The top reason itself is an expected code for 2 of 19 (share 0.105). The expected lists are a hypothesis. The injected story is usually present and usually not the lead reason.

Honest shops that share a payer with another honest shop in the same zone: 219 at the 2026-10-07 network snapshot. The existing ring flag is on for 2 of them (rate 0.009). Among 16 eligible misuse shops the ring rate is 0.438. Sharing regulars in a market rarely produces a ring flag under the current rule.

The LLM validator was not called against a live model. On 7 constructed notes it rejected 6. It accepts a note that copies evidence numbers and rejects an empty note, accusation words, a promise, an invented number, and the number-word “nine”. The project’s own analyst template, which prints risk to four decimal places (`0.4200`), is rejected against evidence that stringifies the same risk as `0.42`. The API never sends the template through that check; it is the fallback when a rewording fails.

## What peer and trend adds

The payment, shop and network scores still set the queue. Peer and trend is a separate cue on the case page (`GET /shops/{id}/peer-trend`). For the shop’s category, area and size it shows the percentile of turnover, round-amount share and distant-payer share. It also draws the last 14 days of mean payment score, extends a straight line seven days, and sets a rising flag when the slope is positive and the day-7 line is at least 0.02 above today. The flag does not change a band and does not block the shop.

The early-warning check asks a narrower question: rising, and still under the payment threshold today, and then a later validation day within seven days crosses that threshold. The horizon stops at validation end so the test period stays unread. Seed 42, threshold 0.667: 212 validation shop-days had a later validation day. 16 were early warnings. 1 of those 16 crossed the threshold inside the observed window (share 0.062). 3 of the 16 sat on a misuse shop. The window is a few days long, so this check cannot yet show that a rising flag is an early warning that usually enters review.

## When the pattern changes

Misuse payments were altered in three cumulative rounds, then scored with the frozen model and with a model retrained on simulated analyst verdicts. The verdicts use the configured noise (15% of misuse shops cleared, 5% of honest shops marked misuse). The model sees the noisy verdict, not the raw label. Only train shops are reviewed.

On seed 42 validation (N=1,416, positives=40) frozen recall starts at 0.475. After round amounts are removed it falls to 0.175. Retraining lifts recall to 1.000 and lifts the false-positive rate to 0.073. Spreading about half the misuse payments onto other shops in the same split drops frozen recall to 0.100 and retrained recall to 0.025; that retrain does not repair the drop, and the misuse-shop count in validation rises from 4 to 14 because the payments moved. Halving the amounts as well leaves frozen recall at 0.050. Retraining reaches 0.800 recall with a false-positive rate of 0.195. A recall gain from shop-level verdicts comes with more honest flags. One seed.

## Tables

### Payment comparison, mean ± std, three seeds

N=1,823, positives=26. Source: `reports/onsite/ai/model_comparison.md`.

| Model | Precision | Recall | F1 | FPR | PR-AUC | Misuse taka |
| --- | --- | --- | --- | --- | --- | --- |
| Rules | 0.659 ± 0.250 | 0.436 ± 0.202 | 0.478 ± 0.076 | 0.002 ± 0.001 | 0.301 ± 0.116 | 0.459 ± 0.190 |
| Graph | 0.017 ± 0.018 | 0.483 ± 0.501 | 0.031 ± 0.033 | 0.486 ± 0.463 | 0.012 ± 0.011 | 0.397 ± 0.531 |
| LogReg | 0.510 ± 0.302 | 0.550 ± 0.272 | 0.424 ± 0.161 | 0.008 ± 0.006 | 0.484 ± 0.127 | 0.580 ± 0.248 |
| RF | 0.524 ± 0.423 | 0.512 ± 0.135 | 0.439 ± 0.166 | 0.006 ± 0.005 | 0.673 ± 0.222 | 0.586 ± 0.154 |
| XGBoost | 0.461 ± 0.469 | 0.518 ± 0.141 | 0.399 ± 0.233 | 0.010 ± 0.009 | 0.455 ± 0.390 | 0.606 ± 0.109 |
| LightGBM | 0.374 ± 0.331 | 0.620 ± 0.182 | 0.435 ± 0.286 | 0.015 ± 0.011 | 0.363 ± 0.284 | 0.709 ± 0.060 |
| IsoForest | 0.483 ± 0.261 | 0.641 ± 0.304 | 0.517 ± 0.242 | 0.007 ± 0.000 | 0.524 ± 0.290 | 0.833 ± 0.092 |
| Autoenc | 0.230 ± 0.234 | 0.519 ± 0.201 | 0.284 ± 0.226 | 0.026 ± 0.011 | 0.193 ± 0.191 | 0.660 ± 0.151 |

### Feature groups

Positive drop means removing the group hurt. Source: `reports/onsite/ai/feature_justification.md`.

| Group | SHAP share | Permutation PR-AUC drop | Retrain PR-AUC drop |
| --- | --- | --- | --- |
| amount | 0.576 ± 0.028 | 0.318 ± 0.276 | 0.001 ± 0.127 |
| timing | 0.013 ± 0.007 | 0.009 ± 0.016 | -0.004 ± 0.022 |
| payer_day | 0.132 ± 0.023 | 0.131 ± 0.071 | 0.000 ± 0.146 |
| money_in_then_out | 0.007 ± 0.004 | 0.002 ± 0.002 | -0.002 ± 0.017 |
| who_and_where | 0.106 ± 0.027 | 0.019 ± 0.067 | 0.017 ± 0.055 |
| payer_history | 0.010 ± 0.002 | 0.019 ± 0.035 | 0.008 ± 0.016 |
| shop_history | 0.111 ± 0.029 | 0.065 ± 0.036 | 0.010 ± 0.014 |
| mechanism | 0.044 ± 0.004 | 0.011 ± 0.011 | 0.009 ± 0.020 |

| Mechanism column | SHAP mean abs | PR-AUC drop when dropped alone |
| --- | --- | --- |
| payer_repeat_rate | 0.020 ± 0.017 | -0.002 ± 0.004 |
| one_time_payer_share_30d | 0.018 ± 0.012 | -0.001 ± 0.001 |
| hour_vs_shop_median_30d | 0.009 ± 0.006 | -0.003 ± 0.002 |
| minutes_since_inflow | 0.015 ± 0.003 | -0.000 ± 0.006 |

| Feature group | Real-world mechanism it captures | Evidence |
| --- | --- | --- |
| amount | Round amounts, unusual basket size, payments just under the incentive cap. Hypothesis: cash desk and cap-splitting. | SHAP share 0.576 ± 0.028; permutation drop 0.318 ± 0.276; retrain drop 0.001 ± 0.127 (N≈1823, positives≈26). |
| timing | Hour, Friday, outside opening hours. Hypothesis: desks that run when the shop would be shut. | SHAP share 0.013 ± 0.007; permutation drop 0.009 ± 0.016; retrain drop -0.004 ± 0.022. |
| payer_day | Payer’s total so far today versus the daily limit. Hypothesis: limit bypass across shops. | SHAP share 0.132 ± 0.023; permutation drop 0.131 ± 0.071; retrain drop 0.000 ± 0.146. |
| money_in_then_out | Money in, then a payment, in a short window. Hypothesis: a drain of a fresh top-up or remittance. | SHAP share 0.007 ± 0.004; permutation drop 0.002 ± 0.002; retrain drop -0.002 ± 0.017. |
| who_and_where | First visit and distance from home. Hypothesis: strangers who do not live nearby. | SHAP share 0.106 ± 0.027; permutation drop 0.019 ± 0.067; retrain drop 0.017 ± 0.055. |
| payer_history | Recent payer volume, shops, round share, account age. Hypothesis: a young, busy account. | SHAP share 0.010 ± 0.002; permutation drop 0.019 ± 0.035; retrain drop 0.008 ± 0.016. |
| shop_history | Turnover, round receipts, night share, strangers, peers. Hypothesis: unlike itself and unlike similar shops. | SHAP share 0.111 ± 0.029; permutation drop 0.065 ± 0.036; retrain drop 0.010 ± 0.014. |
| mechanism | Repeat rate, one-time payers, usual hour, minutes since money in. Hypothesis: the same stories at a finer grain. | SHAP share 0.044 ± 0.004; permutation drop 0.011 ± 0.011; retrain drop 0.009 ± 0.020. |

### Patterns, look-alikes, regime, calibration, reasons, rings

Seed 42. Source: `reports/onsite/ai/robustness.md`.

| Pattern | N | Positives | Flagged | Recall |
| --- | --- | --- | --- | --- |
| round_amount_cash_desk | 14 | 14 | 9 | 0.643 |
| limit_bypass | 26 | 26 | 10 | 0.385 |
| remittance_drain, incentive_splitting, p2p_disguise, turnover_burst | 0 | 0 | 0 | n/a |

| Look-alike slice | Honest payments | Flagged | FPR |
| --- | --- | --- | --- |
| wholesalers | 15 | 0 | 0.000 |
| electronics | 21 | 0 | 0.000 |
| festival spikes | 0 | 0 | n/a |
| new shops | 22 | 0 | 0.000 |

| Slice | N | Positives | Mean score | Recall | Precision | FPR |
| --- | --- | --- | --- | --- | --- | --- |
| train shops, before 1 Oct | 12,373 | 188 | 0.014 | 0.527 | 0.900 | 0.001 |
| train shops, on or after 1 Oct | 6,827 | 156 | 0.015 | 0.359 | 0.933 | 0.001 |
| validation shops | 1,416 | 40 | 0.017 | 0.475 | 1.000 | 0.000 |

| Predicted bin | N | Mean predicted | Observed misuse rate |
| --- | --- | --- | --- |
| 0.0–0.1 | 1,371 | 0.000 | 0.007 |
| 0.1–0.2 | 2 | 0.144 | 0.500 |
| 0.2–0.3 | 18 | 0.234 | 0.556 |
| 0.3–0.4 | 1 | 0.348 | 0.000 |
| 0.4–0.5 | 4 | 0.444 | 0.000 |
| 0.5–0.6 | 1 | 0.551 | 1.000 |
| 0.6–0.7 | 5 | 0.667 | 1.000 |
| 0.7–0.8 | 0 | n/a | n/a |
| 0.8–0.9 | 0 | n/a | n/a |
| 0.9–1.0 | 14 | 1.000 | 1.000 |

SHAP top-3 overlap 1.000 and top-1 overlap 0.105 on 19 flagged misuse payments. False ring rate 2/219 = 0.009. Validator rejects 6 of 7 fixtures; live calls 0.

### Peer and trend, and the adaptive rounds

| Check | Count | Share |
| --- | --- | --- |
| Validation shop-days with a later validation day | 212 | |
| Early warning | 16 | |
| Entered review within the observed horizon | 1 | 0.062 |
| Early warning on a misuse shop | 3 | |

| Round | Frozen recall | Retrained recall | Retrained FPR | N | Positives | Misuse shops |
| --- | --- | --- | --- | --- | --- | --- |
| 0 no adaptation | 0.475 | 0.475 | 0.000 | 1,416 | 40 | 4 |
| 1 drop round amounts | 0.175 | 1.000 | 0.073 | 1,416 | 40 | 4 |
| 2 also spread across shops | 0.100 | 0.025 | 0.000 | 1,416 | 40 | 14 |
| 3 also halve amounts | 0.050 | 0.800 | 0.195 | 1,416 | 40 | 17 |
