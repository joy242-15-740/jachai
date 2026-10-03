# Jachai (যাচাই)

AI merchant-transaction integrity engine for Bangla QR. Built for AI DEV FEST
2026 AI Hackathon (DIU CPC × upay), Track 05: Merchant & Agent Intelligence.

> Status: repository scaffold only. No models yet. Sections marked **TODO** are
> filled in as the work lands.

## 1. Project overview

For every Bangla QR payment and every shop, Jachai answers one question:
**is this real commerce or a hidden cash-out?** It explains why, and a human
analyst decides what to do.

The problem: a customer "pays" a shop Tk 10,000 by Bangla QR, buys nothing, and
gets about Tk 9,815 back in cash. The shop works as an unlicensed cash-out
point, the customer gets around the Tk 30,000 cash-out limit, and upay loses fee
revenue. Bangladesh Bank requires acquirers to monitor merchants with unusual
patterns. Jachai is a tool for that job.

Our approach: don't limit every shop. Find the few running hidden cash-outs,
protect honest shopkeepers, and turn the leak into new upay agents.

All data is synthetic. Results on synthetic data show that the method works.
They do not prove real-world accuracy.

## 2. Features

Planned (none built yet):

- Synthetic Bangla QR world with injected misuse patterns and honest
  look-alikes. **TODO**
- Payment risk score, shop risk score and payer–shop network score. **TODO**
- Fused risk band (low / review / high) with the top reasons for each case.
  **TODO**
- Case notes in English and merchant notices in Bangla. An LLM only rewords
  structured evidence, with a template fallback. **TODO**
- Policy simulator that replays one month under five policies. **TODO**
- Analyst dashboard. The analyst makes every decision; nothing is blocked
  automatically. **TODO**

## 3. Technology stack

- **ML and data:** Python 3.11+, pandas, NumPy, scikit-learn, LightGBM,
  NetworkX, SHAP (planned)
- **Backend:** FastAPI, Pydantic v2 (planned)
- **Frontend:** Next.js, TypeScript, Tailwind, Recharts (planned)
- **Quality:** pytest, ruff, GitHub Actions CI

Every external component and its licence is listed in
[docs/third_party.md](docs/third_party.md).

## 4. Requirements

- Python 3.11 or newer (`python3.12` or `python3.11` on your PATH)
- GNU Make
- Git
- Node.js (version TBD) for the frontend. **TODO**

## 5. Installation and setup

```bash
git clone <repo-url> jachai
cd jachai
cp .env.example .env
make install
```

`make install` creates `.venv/` and installs the `ml` and `backend` packages in
editable mode with their dev tools.

## 6. Environment variables

Copy `.env.example` to `.env`. Never commit `.env`. All values in
`.env.example` are placeholders.

| Variable | Purpose | Example |
| --- | --- | --- |
| `LLM_PROVIDER` | Optional LLM provider for rewording notes. Empty = template fallback. | *(empty)* |
| `LLM_API_KEY` | API key for that provider. | `your-llm-api-key-here` |
| `LLM_MODEL` | Model name for that provider. | *(empty)* |
| `JACHAI_SEED` | Random seed for the synthetic world. | `42` |
| `JACHAI_DATA_DIR` | Where generated data is written. | `data` |
| `JACHAI_REPORTS_DIR` | Where metrics and figures are written. | `reports` |
| `API_HOST` | Backend bind host. | `127.0.0.1` |
| `API_PORT` | Backend port. | `8000` |
| `NEXT_PUBLIC_API_URL` | Backend URL used by the dashboard. | `http://localhost:8000` |

## 7. Run and build commands

```bash
make help      # list all commands
make install   # create .venv and install packages
make world     # generate synthetic data         (TODO)
make train     # train all models                (TODO)
make eval      # write metrics to reports/       (TODO)
make api       # run FastAPI on :8000            (TODO)
make web       # run Next.js on :3000            (TODO)
make test      # ruff + pytest
make format    # auto-fix lint and formatting
make clean     # remove .venv and caches
```

Targets marked TODO are stubs: they print "not implemented yet" and exit
with an error, so an empty run is never mistaken for real output.

## 8. Live deployment URL

**TODO**: not deployed yet.

## 9. Testing instructions

```bash
make test
```

This runs `ruff check` and `ruff format --check` on the whole repo, then
`pytest` on `ml/tests` and `backend/tests`. GitHub Actions runs the same checks
on every push and pull request (`.github/workflows/ci.yml`).

## 10. Other configuration

- Business rules (thresholds, policies, misuse patterns, world settings) live
  in `configs/*.yaml`, never inside model code or LLM prompts. **TODO**: fill
  in the files.
- Data assumptions: [data/ASSUMPTIONS.md](data/ASSUMPTIONS.md)
- Competition rules checklist: [RULES_CHECKLIST.md](RULES_CHECKLIST.md)
- AI usage log: [docs/ai_usage.md](docs/ai_usage.md)
- Linting and formatting: ruff, configured in `ruff.toml` at the repo root.

### Repository layout

```
configs/        world, patterns, thresholds, rules (YAML)
data/           generated data (gitignored) + ASSUMPTIONS.md
ml/jachai/      world, labels, features, models, explain, simulate, eval
ml/tests/
backend/app/    FastAPI service
backend/tests/
frontend/       Next.js dashboard
reports/        generated metrics, figures, summary.md
docs/           report, data card, model card, third_party.md, ai_usage.md
```
