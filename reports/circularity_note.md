# Circularity note

The synthetic world (`ml/jachai/world/patterns/`) and the rules
(`ml/jachai/labels/functions.py`, `configs/rules.yaml`) were both written by the
team from the same reported project misuse typologies.

Consequence: on the normal synthetic world the rules match the injected patterns
almost exactly, so a rules-only detector looks far stronger than it would on real
data, where misuse is messier, mixes tactics and adapts once it is noticed.
Numbers on the normal world therefore flatter the rules.

Fairer tests of whether Jachai generalises beyond what we wrote down:

1. **Evasion test**: misusers stop using round amounts (`make validate`); the
   system is not retrained.
2. **Ring detection**: limit-bypass rings found through the payer-shop network
   rather than a hand-written rule.
3. **Held-out pattern**: one misuse pattern is never used for training or
   tuning; it is measured once, in the final test evaluation.

Jachai layers the rules into its fused score (machine learning on top of rules,
as in industry practice) so it does not throw away what the rules know, and adds
evidence that keeps working when the rules' assumptions break.

Results: `reports/validation_evaluation.md`.
