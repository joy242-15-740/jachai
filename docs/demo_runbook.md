# Jachai demo and submission runbook

## Three-minute live demo

Use this exact sequence. It tells one coherent story and avoids turning the demo
into a dashboard tour.

| Time | Screen | One thing to say |
| --- | --- | --- |
| 0:00–0:25 | Homepage | “A merchant QR payment can hide a cash-out. Jachai protects honest shops by reviewing the few that need context—not by limiting everyone.” |
| 0:25–0:50 | Alert queue | “This queue uses payment, shop and network evidence. It says ‘needs review’, never fraud.” |
| 0:50–1:25 | One case | “Open the evidence: payment behaviour, implausible turnover and linked payers combine into a priority. The analyst sees reasons and a timeline.” |
| 1:25–1:45 | Merchant notice | “Before any action, the merchant gets a respectful Bangla explanation and an appeal route. The system does not accuse or block automatically.” |
| 1:45–2:20 | Policy simulator | “Compare five choices with the same synthetic replay. A blanket limit can harm honest shops; targeted review makes the trade-off visible.” |
| 2:20–2:50 | Trust page | “Rules are stronger on our normal synthetic world. Under our configured non-round evasion test, Jachai is more robust because it adds shop and network context. We show both results.” |
| 2:50–3:00 | Homepage | “Jachai: don’t restrict every merchant; review the few that need context. A human makes every decision.” |

The production dashboard uses cached, code-generated fast-profile cases for
reliable demonstration. Do not call it live production ML serving; all displayed
data is synthetic and the full local model path is described in the README.

Each member should rehearse the [30-second explanation card](team_brief.md)
before the demo.

## Local launch

```bash
make demo-data     # only if fast artifacts need rebuilding
make api-fast      # terminal 1, http://localhost:8000
make web           # terminal 2, http://localhost:3000
```

Production URLs:

- Dashboard: <https://jachai-eta.vercel.app>
- Fast-profile demo API: <https://jachai-api.vercel.app>

The production frontend calls the public API and falls back to bundled generated
demo JSON if it is unreachable. Decision writes and live slider requests use the
API. Its serverless SQLite file is temporary, so do not present the public demo
decision history as durable storage.

## Pre-submission checks

```bash
make test
cd frontend && npm run build
git status --short
git log --oneline -12
```

- Confirm both live URLs open in a private browser window.
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
