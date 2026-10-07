# Jachai: codebase review and production-readiness plan

Date: 2026-10-07. Reviewed state: `main` at `c97794f` merged with the font branch
(`cursor/dashboard-fonts-b8e9`). Everything below was checked by running the code,
not by reading it alone.

## 1. How the review was done

| Check | Result |
| --- | --- |
| `make test` (ruff + 187 pytest tests, ml + backend) | lint failed on `main` (trailing whitespace from commit `c97794f`); pytest 187 passed. Fixed in this branch. |
| Every API route on the live fast-profile API (`make api-fast`) | 11 routes, all return the documented shape; queue totals agree with `/overview`; decision log append + history verified; validation errors return 422. |
| The same sweep on the cached store (`JACHAI_CACHED_STORE=1`, what Vercel runs) | Import failure (see F1). After the fix: all routes answer; differences listed in F3–F6. |
| Public deployment probes | `https://jachai-api.vercel.app/*` returned `500 FUNCTION_INVOCATION_FAILED` on every route. The dashboard at `https://jachai-eta.vercel.app` therefore ran on bundled demo JSON with no visible notice (F1, F2). |
| Frontend `tsc --noEmit` and `next build` | Both pass. 8 routes build; no ESLint is configured. |
| Browser check (Chrome) | Agrandir Grand Heavy renders for headlines and the wordmark; the demo-mode notice reappears when the API is unreachable. |

## 2. Component inventory and status

### Backend (`backend/app`, FastAPI)

| Route | Live store | Cached store (Vercel) | Used by UI |
| --- | --- | --- | --- |
| `GET /health` | ok | ok, but reports model/world dirs instead of which store is loaded | no |
| `GET /metrics` | ok (serves `reports/`; `simulator/results.json` missing on the fast profile) | all reports "missing" on Vercel: `REPORTS_DIR=reports/fast` is not committed | trust page, walkthrough |
| `GET /overview` | ok | ok after F1 fix | home |
| `GET /cases`, `?band=`, `?limit=` | ok, sorted by risk | ok | queue, notice, home |
| `GET /cases/{id}` | ok: reasons, 5 riskiest payments, 30-day timeline, neighbourhood, brief, recommendation, decisions | ok for the 25 bundled cases; thin stub for the other alert shops | case page |
| `POST /cases/{id}/decision` | ok, append-only SQLite with hash chain | ok but the SQLite file is `/tmp` on Vercel: decisions vanish on cold start | case page |
| `GET /shops/{id}` | ok for all 300 shops | 404 for the 264 non-alert shops | no |
| `GET /shops/{id}/peer-trend` | ok (percentiles, 14-day history, 7-day line) | `available: false` by design; 404 for non-alert shops | case page |
| `POST /simulate` | ok, real replay; invalid sliders 422 | linear scaling of one cached run, not a replay; invalid sliders accepted (200) | simulator, home tile |
| `GET /fairness` | ok | ok | trust page |
| `POST /score/transaction` | ok, real point-in-time features (about 1 s on the fast world) | hand-written heuristic score and reasons; unknown payer accepted | no |

Supporting modules: `store.py` (scores the world once at start-up), `cached_store.py`,
`audit.py` (append-only, tamper-evident), `recommend.py` (rules from `configs/rules.yaml`),
`overview.py`, `peer_trend.py`, `export_demo.py` / `export_reference_demo.py`,
`settings.py`, `api/index.py` + `vercel.json` (serverless entry).

### Frontend (`frontend`, Next.js 16 App Router)

| Page / component | Data source | Status |
| --- | --- | --- |
| `/` `Overview.tsx` | `/overview`, `/cases?limit=1`, `/simulate {}` | ok; every figure from the API or its exported JSON |
| `/queue` | `/cases?limit=200` | ok; `?band=` filter in the URL |
| `/cases/[id]` `CaseView.tsx` | `/cases/{id}`, `POST decision`, `PeerTrendPanel` | ok; decisions only with the live API |
| `/examples/[key]` | `public/demo/reference/*` | ok, read-only reference-world cases |
| `/notice` | `/cases?limit=25`, `/cases/{id}` | ok; appeal form is a preview only (nothing stored) |
| `/simulator` | `POST /simulate`, demo grid fallback | ok; demo mode snaps to the nearest of 48 real runs |
| `/trust` + `EvasionToggle` | `/fairness`, `/metrics` | ok; three summary cards carry typed numbers (F8) |
| `JudgeWalkthrough` | reference examples, demo grid, `/metrics` | ok |
| `lib/api.ts` | `getData` = live then `/demo/*.json` after a 3 s timeout | ok; the demo notice is the only signal (restored, F2) |

### ML (`ml/jachai`)

World generator, features, labels, LightGBM payment model with isotonic calibration,
shop model, network (NetworkX), fusion, trend, simulator, evaluation. 25 test files.
Not changed by this review; findings here are about serving, not modelling.

## 3. Findings

Severity: P0 = the product is wrong or down; P1 = wrong numbers or silent failure;
P2 = production hardening; P3 = PRD features not yet built.

| # | Sev | Finding | Status |
| --- | --- | --- | --- |
| F1 | P0 | `backend/app/overview.py` imported `app.store`, which imports `jachai.models.network` (NetworkX) and `jachai.system` (LightGBM). Vercel installs only `requirements.txt` (FastAPI, pydantic, numpy, pandas, PyYAML), so the public API crashed at import on every route. | Fixed: shared constants moved to `app/common.py`; `backend/tests/test_cached_mode.py` runs the cached API with the ML libraries blocked. |
| F2 | P0 | Commit `c97794f` emptied `SourceNote`, so a dashboard running on bundled sample data showed no "Demo mode" notice. Project rule: synthetic/sample data is always labelled. | Fixed: notice restored. |
| F3 | P1 | Cached `POST /simulate` scales one run linearly (capacity 5 gives C = 1.13 M stopped; the real replay gives 4.09 M) and accepts invalid sliders. The frontend's own fallback (nearest of 48 real runs) is more faithful than the live cached API. | Plan WP-2 |
| F4 | P1 | Cached `POST /score/transaction` returns a hand-written score (0.12 + 0.28 + 0.4) and two fixed reasons, with threshold 0.65 instead of the model's 0.6667, and accepts unknown payers. The route is not used by the UI. | Plan WP-2 |
| F5 | P1 | `/metrics` on Vercel serves `reports/fast`, which is git-ignored, so validation evidence (evasion toggle, walkthrough step 6) disappears when the API is live. `vercel.json` also lists `models/fast/**` and `data/fast/world/**`, which are not committed. | Plan WP-2 |
| F6 | P1 | Cached `GET /shops/{id}` and peer-trend return 404 for 264 of 300 shops; the demo exporter writes no `peer-trend-*.json`, so `PeerTrendPanel` requests a file that never exists in demo mode. | Plan WP-2 |
| F7 | P1 | Decisions on Vercel go to `/tmp/jachai-audit.sqlite3` and are lost on cold start; the hash chain restarts from genesis. | Plan WP-3 |
| F8 | P1 | Trust page cards type "PR-AUC 0.774 vs 0.899" and "0.584 vs 0.843". They match `reports/validation_evaluation.md` and `reports/final_test.md` today but are not read from them; `final_test.json` is not in `METRIC_REPORTS`. | Plan WP-1 |
| F9 | P1 | `main` CI is red: `make test` fails on ruff W291 (trailing whitespace) from `c97794f`; a VS Code `.cph` scratch file was committed. | Fixed. |
| F10 | P2 | No authentication or roles on any route; `analyst` is a free-text field on `POST decision`. CORS is correct (foreign origins rejected). | Plan WP-3 |
| F11 | P2 | `/health` does not say whether a store is loaded or which one (live / cached / none). No request logging, request ids or error reporting. | Plan WP-3 |
| F12 | P2 | No frontend CI (typecheck, build) and no ESLint; no frontend tests at all. CI runs only `make test`. | Plan WP-4 |
| F13 | P2 | `getData` silently falls back to demo JSON on any non-2xx or a 3 s timeout; a slow cold start can flip a page to sample data mid-session. | Plan WP-4 |
| F14 | P2 | `.env.example` lists `LLM_PROVIDER`, `API_HOST`, `API_PORT`, `JACHAI_REPORTS_DIR` which the backend never reads (`REPORTS_DIR` is the real one). | Plan WP-5 |
| F15 | P2 | Reason strings from `configs/reason_codes.yaml` say "Tk"; the UI and PRD use "৳". ML and backend tests assert the "Tk" wording. | Plan WP-5 |
| F16 | P2 | Agrandir ships under Pangram Pangram's personal licence (personal use only). Five of the nine uploaded cuts are unused (Narrow, Thin Italic, Tight, Wide Black Italic, Wide Light, about 250 KB). `@fontsource/inter` remains a dependency although Inter is vendored in `public/fonts/inter`. | Plan WP-5, decision needed before commercial use |
| F17 | P2 | `Store` scores the whole world at start-up and `score_transaction` rebuilds features for the whole world per call: fine for a demo, not production latency. The full API cannot run on Vercel (LightGBM needs libgomp). | Plan WP-6 |
| F18 | P3 | PRD items not built: appeal submission is a preview; no `/api/v1` prefix; `/score/transaction` has no UI; no landing page sections beyond the dashboard. | Plan WP-7 |

## 4. Plan

Ordered by value. Each package is one PR; each lists the files it touches and how it
is accepted. Nothing retrains a model, nothing blocks a shop automatically, and the
wording stays "needs review", never "fraud".

### WP-0 (this branch): stop the bleeding
- `app/common.py` + cached-mode regression test (F1), demo notice (F2), lint and
  scratch-file cleanup (F9), Agrandir served from `public/Agrandir` with Clash Display
  as fallback.
- Accept: `make test` green; `jachai-api.vercel.app/health` returns JSON after deploy;
  the dashboard shows the live overview without the demo notice.

### WP-1: every number on screen comes from the API
- `backend/app/main.py`: add `final_test.json` to `METRIC_REPORTS`.
- `frontend/app/trust/page.tsx`: compute the three evidence cards from
  `/metrics` (`validation_evaluation.json` means, `final_test.json`), showing "—" when
  a report is missing (F8).
- Accept: no numeric literal in `trust/page.tsx`; a test asserts the card text equals
  the report values.

### WP-2: the cached (Vercel) store tells the truth
- `cached_store.py::simulate`: snap to the nearest run in `simulate-grid.json` (same
  rule as the frontend) and recompute fees exactly; validate sliders with the same
  pydantic params model so invalid input is 422 (F3).
- `cached_store.py::score_transaction`: remove the heuristic. Return 501 with a clear
  note ("point-in-time scoring needs the live API") or export a small table of real
  scored examples and serve only those (F4).
- `api/index.py`: `REPORTS_DIR=reports` (committed reference reports); drop the
  uncommitted globs from `vercel.json` (F5).
- `export_demo.py`: write `peer-trend-{id}.json` for the bundled cases; `cached_store`
  serves them and `has_shop` covers every shop in `cases.json` plus the exported
  profiles (F6). Remove the never-matching demo fallback from `PeerTrendPanel`, or
  keep it now that the file exists.
- Accept: `test_cached_mode.py` extended with simulate-snap, 422 on bad sliders,
  peer-trend available for a bundled case, `/metrics` lists no missing reference report.

### WP-3: operate it (auth, audit, health, logging)
- Auth: OIDC/SSO (or a signed service token for the demo) in front of `POST` routes;
  the analyst id comes from the token, not the body. Read routes may stay public for
  the synthetic demo but must be behind auth for real data (F10).
- Audit: keep the append-only hash-chained design; move storage to Postgres (or
  Vercel Postgres/Turso) behind the same `AuditLog` interface; keep SQLite for local
  dev and tests. Add `GET /audit/verify` for the chain check (F7).
- `/health`: add `store: live | cached | none`, `as_of`, model fingerprint; readiness
  separate from liveness (F11).
- Structured JSON logging with request ids; `X-Request-ID` echoed; error reporting
  hook (Sentry or equivalent) in both apps; rate limit on `POST` routes.
- Accept: decisions survive a redeploy; `/health` on Vercel reports `cached`.

### WP-4: quality gates
- `.github/workflows/ci.yml`: add a `web` job (`npm ci`, `npm run typecheck`,
  `npm run lint`, `npm run build`) and run the cached-mode test with a minimal
  `requirements.txt` virtualenv so the Vercel runtime is simulated in CI (F12).
- Add ESLint (`eslint-config-next`) and a `lint` script; fix what it reports.
- Frontend tests: Vitest for `lib/api.ts` formatters and `fromGrid`; one Playwright
  smoke test (queue → case → decision disabled in demo, enabled live).
- `lib/api.ts`: make the timeout configurable, retry once before falling back, keep
  `source` in page state and never switch from live to demo within a session without
  showing the notice (F13).
- Accept: CI blocks on type, lint, build and tests for both apps.

### WP-5: keep only what is used
- `.env.example`: remove `LLM_PROVIDER`, `API_HOST`, `API_PORT`, `JACHAI_REPORTS_DIR`;
  document `JACHAI_CACHED_STORE`, `DEMO_DATA_DIR`, `SIMULATOR_GRID_PATH` (F14).
- Reason templates: "Tk" → "৳" in `configs/reason_codes.yaml`, `recommend.py`,
  `cached_store.py`, and the tests that assert them (F15).
- Fonts: delete the five unused Agrandir cuts (team decision), drop the
  `@fontsource/inter` dependency (woff2 files are vendored), decide whether Clash
  Display stays as fallback. Obtain a commercial Agrandir web licence before any
  non-personal deployment (F16).
- Remove `frontend/public/demo/health.json` (nothing reads it).
- Accept: `rg "Tk "` returns nothing outside `docs/`; `npm ls` has no unused deps.

### WP-6: run the real model in production
- Container for the full API (`python:3.12-slim` + libgomp) with the trained
  artifacts baked or pulled from object storage; deploy to a container host (Fly.io,
  Cloud Run, Render). Vercel keeps only the dashboard and, if wanted, the cached API
  as a read-only mirror (F17).
- Scoring service: precompute payer/shop daily state so `score_transaction` reads
  state instead of rebuilding features from the whole world; target < 200 ms.
- Nightly job: rescore the day, refresh `/overview`, export demo JSON; never retrain
  without the documented approval path.
- Accept: p95 latency targets met on the reference world; the same tests pass
  against the container.

### WP-7: PRD alignment (after WP-1 to WP-4)
- `POST /appeals` with storage and a status in the case view; the Bangla appeal form
  stops being a preview.
- API versioning: mount routes under `/api/v1` and keep the current paths as aliases
  for one release.
- A small "score a payment" panel on the case page using `/score/transaction` (live
  only), since the route exists and is tested.
- Landing page sections from the PRD, if still wanted for the pitch.

### Out of scope on purpose
- Changing model, thresholds or fusion weights: evidence in `reports/` would go stale.
- Any automatic restriction or merchant contact.
- Replacing synthetic data with real transactions before WP-3 (auth, audit, logging)
  and a data-protection review are done.

## 5. Decisions needed from the team
1. Agrandir licence: keep the free personal-licence files for the hackathon only, or
   buy the web licence before a public commercial deployment.
2. Whether `POST /score/transaction` should exist on the cached API at all (501 vs
   exported real examples).
3. Audit storage target for production (Postgres vs managed SQLite such as Turso).
4. Whether the five unused Agrandir cuts and the Clash Display fallback are removed.
