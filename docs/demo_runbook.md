# Jachai demo and submission runbook

## Two-minute judge demo

1. **Homepage (15 seconds):** say, “Jachai prioritizes synthetic Bangla QR
   merchant activity for human review; it never declares guilt or blocks
   automatically.” Point to the animated evidence and policy summaries.
2. **Alert queue (20 seconds):** filter by review/high band and explain that the
   queue is ranked by fused risk with a neutral top reason.
3. **Case view (40 seconds):** open one case; show payment, shop and network
   scores, top-three evidence reasons, timeline and graph. Record a decision
   with a reason and show the append-only history.
4. **Merchant notice (15 seconds):** show the polite Bangla notice and appeal
   route. Explain that merchant text never goes to an LLM.
5. **Policy simulator (30 seconds):** move analyst capacity or fee-rate sliders
   and compare the five policies. State clearly that displayed taka values are
   fast-profile synthetic demo outputs, not forecasts.
6. **Trust page (20 seconds):** show fairness slices, limitations and final-test
   evidence. Say that rules win on the normal synthetic world and final test,
   while Jachai is more robust in the tested non-round evasion scenario.

## Local launch

```bash
make demo-data     # only if fast artifacts need rebuilding
make api-fast      # terminal 1, http://localhost:8000
make web           # terminal 2, http://localhost:3000
```

The frontend falls back to bundled generated demo JSON if the API is
unreachable. Decision writes and live slider requests require the API.

## Pre-submission checks

```bash
make test
cd frontend && npm run build
git status --short
git log --oneline -12
```

- Replace the README live deployment TODO only after both URLs open in a private
  browser window.
- Confirm the GitHub repository is public and the latest commit is pushed.
- Never expose `.env`, `LLM_API_KEY`, tokens, generated SQLite files or real PII.
- Check the organizer's exact submission form, deadline and required file type.
- Record the video with the evidence-status labels visible.

## Honest answers for judges

**Why not use only rules?** Rules are strong and win in the normal synthetic
validation. Learned and network evidence add ranking context and were more
robust in the tested amount-evasion scenario; Jachai presents both honestly.

**Does the LLM detect misuse?** No. Models and configured rules produce scores.
The optional LLM can only reword an English note and is guarded by a validator.

**Is this ready for real merchants?** No. It is a synthetic prototype proving
the workflow. A real pilot needs representative data, governance, security,
calibration, fairness review, monitoring and appeal operations.

**Why human review?** Evidence can be incomplete and legitimate commerce can
look unusual. A person sees the context, records a reason and controls every
action.

**What remains unvalidated?** Real-world calibration, fairness, operational
performance and financial impact. Current-fusion validation and the single final
synthetic test exist, but they do not establish production performance.
