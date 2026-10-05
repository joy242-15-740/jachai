# AGENTS.md — Jachai (যাচাই)

Read this file fully before every task. It is the source of truth for this repo.

## What we are building

Jachai is an AI merchant-transaction integrity engine for Bangla QR, built for
AI DEV FEST 2026 AI Hackathon (DIU CPC × upay), Track 05 (Merchant & Agent
Intelligence) with a Trust & Risk engine.

It answers one question for every Bangla QR payment and every shop:
**real commerce, or a hidden cash-out?** It explains why, and a human decides.

Problem in one line: a customer "pays" a shop Tk 10,000 by Bangla QR, buys
nothing, and gets ~Tk 9,815 cash back. Shops act as unlicensed cash-out points;
customers bypass the Tk 30,000 cash-out limit and leave no trail; upay loses fee
revenue and pays Tk 5–8 per Tk 1,000 on off-us QR. Bangladesh Bank requires
acquirers to monitor merchants with unusual patterns and stop splitting and
cash-outs. Jachai is a tool for that duty.

Pitch: "Don't limit every shop. Find the few running hidden cash-outs, protect
honest shopkeepers, and turn the leak into new upay agents."

## Non-negotiable rules

1. **Synthetic data only.** No real names, phone numbers, NIDs or any real
   personal data. IDs are random strings.
2. **Never copy code, text or design from other teams' repositories.**
   Disqualification risk (rulebook 9.1). Use only our own code plus open-source
   libraries.
3. **Small, frequent commits.** One logical change per commit, with a clear
   message ("add remittance-drain pattern", "fix SHAP output shape"). Never a
   single big upload (rulebook 5.2, 5.3).
4. **The LLM never decides.** It only rewords structured evidence. Scores come
   from models; actions come from business rules in `configs/`; a human
   approves every action.
5. **Business rules live in `configs/*.yaml`**, never hard-coded inside models
   or LLM prompts.
6. **No automatic blocking.** The system recommends; the analyst decides.
7. **Every number shown in the UI or report is produced by code**, never typed
   by hand. Results are written to `reports/`.
8. **Secrets** only via environment variables. `.env.example` uses placeholders.
9. **Honest claims.** Synthetic results prove the method, not real-world
   accuracy. Never claim 100% detection.

## Competition rules compliance (check before every commit and submission)

Source: AI DEV FEST 2026 AI Hackathon Rulebook (HR), General Rules (GR) and
the DIU CPC × upay Student Project Guideline (SG).

**Building**
- [ ] All challenge-specific work happens inside the official 72-hour window
      and the on-site period. No pre-built Jachai code (HR 4.1, 4.3, 9.3).
- [ ] Only general-purpose open-source components are reused; each is
      listed in `docs/third_party.md` (HR 4.2, 4.4, 9.2).
- [ ] No copying from other teams; no sharing our code, prompts, files or
      contest info with any other team (HR 9.1, GR 4.2, 4.4).
- [ ] No external human help during the contest (GR 4.1). User interviews
      only if organisers confirm in writing.
- [ ] Each member uses their own AI account, no shared accounts (GR 5.3).
- [ ] Keep AI prompt and development history; disclose tools if judges ask
      (GR 5.6). We are responsible for all AI-generated code (GR 5.4).
- [ ] No use of AI to get leaked or restricted contest material (GR 5.5).
- [ ] Synthetic, public or self-generated data only; no real PII (SG 11, 14).

**Repository**
- [ ] Public GitHub repo (HR 5.1).
- [ ] Continuous, step-by-step commits in both the 72-hour phase and the
      on-site phase; no single final upload (HR 5.2, 5.3).
- [ ] Code pushed before the initial deadline; on-site updates pushed within
      the on-site time (HR 5.5, 8.3).
- [ ] README.md has all 10 required sections: project overview, features,
      technology stack, requirements, installation and setup, environment
      variables (placeholders only), run and build commands, live deployment
      URL, testing instructions, other configuration (HR 6.1, 6.2).

**Submission (by T+72h)**
- [ ] Video: how it works, features and AI components, real-life impact
      (HR 7.2).
- [ ] Project report: problem, idea, solution, key features, AI approach,
      real-life impact (HR 7.3).
- [ ] Public repo link + required project files, through the official channel
      and format, before the deadline; check it opens (HR 7.1, 7.4, GR 6.1,
      8.1). No late submissions (GR 6.2).

**Final day (7 Oct)**
- [ ] Every member can explain design, implementation and AI components
      (HR 4.5, 9.4).
- [ ] Bring own devices, valid institutional ID, backup internet (HR 2.3,
      GR 1.2, 2.2).
- [ ] Only officially registered members; no substitutions (HR 2.2).
- [ ] Report technical problems immediately through official channels
      (GR 7.5, 10.3). Follow organiser and judge instructions (GR 7.1).
- [ ] Never interfere with contest systems, network or other teams (GR 7.2,
      7.3).

**Responsible AI (SG 14)**: privacy, explainability, fairness check,
security (prompt injection, access control), human oversight, transparency
(label model output vs rule vs generated text vs assumption), no harmful
automation.

## Competition rules Codex must enforce

These come from the AI Hackathon Rulebook (HR), the General Rules (GR) and the
Student Project Guideline (SG). If a request would break one, stop and say so.

| Rule | What it means for code work |
| --- | --- |
| HR 4.1, 9.3 | All challenge-specific code is written inside the official development period. Do not import any pre-built Jachai-like solution. |
| HR 4.2, 4.3 | Open-source libraries, pretrained models and public APIs are fine; general-purpose components are fine. |
| HR 4.4, 9.2 | Record every external library, model, API, dataset and service with its licence in `docs/third_party.md` as soon as it is added. |
| HR 4.5, 9.4 | Explain non-obvious code in comments and in `docs/` so every team member can explain design, implementation and AI parts. |
| HR 5.1–5.5 | Public repo; small step-by-step commits pushed often; on-site changes committed and pushed within the on-site window. |
| HR 6 | README keeps all 10 required sections current; secrets as placeholders only. |
| HR 9.1, GR 4.2, 4.4 | Never copy from or share with other teams: no code, prompts, data or files in either direction. |
| GR 5.4 | The team is responsible for all AI-generated code; review it, test it, understand it. |
| GR 5.5, 7.2 | Never access or try to access contest systems, leaked material, judges' tools or other teams' private work. |
| GR 5.6, 7.4 | Keep development history verifiable: meaningful commit messages and the AI usage log in `docs/ai_usage.md`. |
| SG 11, 14 | Synthetic or public data only; no real personal data; responsible-AI principles in every feature. |

At the end of every task, append one line to `docs/ai_usage.md`:
`YYYY-MM-DD HH:MM | member | tool | phase | what was generated | reviewed by`.

## Architecture

```
synthetic world → features → three scores → fusion + reasons → API → dashboard → analyst decision → label → retrain
```

- **Payment score**: LightGBM on weak labels, calibrated probability.
- **Shop score**: turnover-plausibility regression (expected turnover from
  category, area type, size) + Isolation Forest within peer group.
- **Network score**: payer–shop bipartite graph (NetworkX); payer diversity,
  shared-payer communities, ring detection.
- **Fusion**: documented weighted combination → risk band (low / review / high).
- **Explanation**: SHAP top-3 drivers → LLM rewording (English case note,
  Bangla merchant notice) with a template fallback and a validator that rejects
  any invented number.
- **Policy simulator**: replay the same month under five policies.

## Repo layout

```
configs/        world.yaml, patterns.yaml, thresholds.yaml, rules.yaml
data/           generated data (gitignored) + ASSUMPTIONS.md (committed)
ml/jachai/
  world/        synthetic generator
  labels/       labeling functions + weak-label aggregation
  features/     feature engineering (only uses info available at payment time)
  models/       payment, shop, network, fusion
  explain/      SHAP + reason codes
  simulate/     policy simulator
  eval/         splits, metrics, ablation, evasion, fairness
ml/tests/
backend/app/    FastAPI service
backend/tests/
frontend/       Next.js dashboard
reports/        generated metrics, figures, summary.md
docs/           report, data card, model card, third_party.md
```

## Tech stack

Python 3.11+, pandas, NumPy, scikit-learn, LightGBM, NetworkX, SHAP, FastAPI,
Pydantic v2, pytest, ruff. Frontend: Next.js + TypeScript + Tailwind, Recharts
for charts, a graph library for the network view. LLM optional via env var,
template fallback when absent.

## Domain facts (use in configs and docs, with sources in docs/)

- Agent cash-out charge: Tk 13–18.50 per Tk 1,000 (≈1.5–1.85%).
- Bangladesh Bank cash-out limit referenced in reporting: Tk 30,000.
- From 1 Oct 2026: Bangla QR MDR and IRF zero, instant merchant credit,
  incentive on payments up to Tk 2,000 (splitting prohibited).
- From 1 Nov 2026: P2P Bangla QR (reverse risk: business payments disguised
  as personal transfers).
- One merchant account can carry 4–5 Bangla QR codes from different providers.

## Misuse patterns to inject (configs/patterns.yaml)

1. Round-amount cash desk (round amounts, diverse payers, after hours).
2. Remittance drain (payer receives remittance, pays ~all of it to a distant
   shop, account goes dormant).
3. Turnover burst (small shop receives Tk 5-lakh-scale bursts from different
   locations).
4. Limit bypass (> Tk 30,000/day spread across several shops).
5. Incentive splitting (repeated payments just under Tk 2,000 after 1 Oct).
6. P2P disguise (scenario switch, after 1 Nov).

Hard negatives (honest look-alikes): electronics shops and wholesalers with
genuine large round tickets, Eid and haat-day spikes, new shops ramping up.
Add label noise (missed and false labels).

## Evaluation protocol (teachers will check this)

- Split by **shop and by time**; no shop appears in both train and test.
- Thresholds frozen on validation; test set used **once**.
- Baselines: rules-only and blanket merchant limit.
- **Hold out one misuse pattern** entirely from training.
- Sanity check: no single feature predicts the label alone with very high AUC.
- Metrics: PR-AUC, precision@k (analyst capacity), value-weighted recall
  (share of misuse taka caught), false-positive rate on honest shops.
- Ablation by feature group; evasion test (remove round amounts).
- Fairness: FPR by area type (urban / district / rural), shop size, category.

## Commands (keep this section up to date)

```
make world      # generate synthetic data
make train      # train all models
make eval       # write reports/
make api        # run FastAPI on :8000
make web        # run Next.js on :3000
make test       # pytest + ruff
```

## Definition of done for any task

- Code runs from a clean clone using README steps.
- Tests added or updated and passing (`make test`).
- No hard-coded secrets or real personal data.
- README or docs updated if behaviour changed.
- Committed with a clear message.
