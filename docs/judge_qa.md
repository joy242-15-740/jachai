# Judge Q&A: likely questions, short answers

Every member should be able to give these answers. Numbers come from
`reports/summary.md` and `reports/final_test.md` (synthetic data only).

**How do you get labels without ground truth?**
Weak supervision. Eight simple rules (one per misuse typology, two for honest
behaviour) vote "misuse", "honest" or "no opinion", and a weighted vote combines
them. On rule votes alone the model just copied the rules, so we added sparse,
dated, shop-level past investigations (7% of shops, biased towards rule-flagged
shops, some with wrong verdicts) as higher-weight evidence. The hidden truth is
only used to grade results.

**Isn't it circular to test on a world you designed?**
Yes, and we say so. The world and the rules came from the same typologies, so
rules look unrealistically strong on the normal world (PR-AUC 0.899 vs 0.774 for
Jachai on validation; 0.843 vs 0.584 on the final test). The fairer tests are
evasion, ring detection and a held-out pattern; see `reports/circularity_note.md`.

**What if you accuse an honest shop?**
We don't accuse. The queue says "needs review"; a named analyst decides with a
written reason in an append-only, hash-chained log; nothing is blocked
automatically; the merchant notice is polite and invites an explanation, with an
appeal form. On the final test Jachai's review band still contained 27 honest
shops (rules 11, blanket limit 44), which is why a human decides.

**What happens when misusers adapt?**
We tested one adaptation: no round amounts, system not retrained. Jachai kept more
of its performance than rules (PR-AUC 0.599 vs 0.588; value recall 0.893 vs 0.739)
and still found limit-bypass rings (recall 0.591 vs 0.024). Only one evasion
strategy was tested; more are needed.

**What's the business value for upay?**
Analyst time goes to the strongest cases instead of capping every shop; honest
big sellers are not hit by one city-wide cap; confirmed high-demand cash-out
points become agent leads, moving cash-out into a licensed, fee-earning channel.
The simulator shows the trade-offs; it is a diagnostic, not a forecast.

**What about P2P Bangla QR from 1 November?**
The generator has a what-if switch for business payments disguised as personal
transfers to the owner's wallet, and a shop-level rule watches how many different
people pay that wallet. It is a scenario, not validated evidence.

**Why not just use the rules?**
On our synthetic normal world, rules were better, and we report that. Rules break
when behaviour shifts: under evasion they lost most ring detection. Jachai keeps
the rules as one input and adds evidence that still works when the rules'
assumptions fail, plus explanations, a network view and a policy simulator. Real
data would decide the balance.

**Is the test result trustworthy?**
The test set was accessed once, after the system was frozen, and logged in
`reports/test_access_log.md`. That log also records one earlier design diagnostic
that read test-shop labels (no metric, no tuning) and that the agreed fusion
success criteria were not all met before the final test.

**What did each member build?**
*To be filled in by the team (git history alone does not show it):*
- K.M. Sajidul Haq (Captain): …
- Tanjimul Astak Siam: …
- Mohammed Muntasir Rahman Joy: …
