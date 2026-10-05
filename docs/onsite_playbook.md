# On-site playbook (final day)

New requirements on the final day are usually small changes to rules, thresholds,
wording or the simulator. Make them in config where possible, then run:

```bash
make onsite-refresh
```

This rebuilds the fast-profile world, retrains the fast system, re-runs the
simulator, refreshes the dashboard's demo JSON and runs the full test suite. It
takes about **30 seconds** (measured on the team laptop). Commit and push each
change within the on-site window (HR 5.5, 8.3), with a clear message.

Fast-profile numbers are for the demo only. Do **not** re-run the final test:
it was used once (`reports/test_access_log.md`). Reference results stay as
reported in `reports/summary.md`; say so if asked.

## Change recipes

| Request | Edit | Verified with `make onsite-refresh` |
| --- | --- | --- |
| Reword a reason (English or Bangla) | `configs/reason_codes.yaml` → `templates` | yes |
| Make the review / high bands stricter or looser | `configs/thresholds.yaml` → `bands` | yes |
| Change a simulator default (capacity, limit, fee, acceptance) | `configs/simulator.yaml` → `params` | yes |
| Change a labeling-function threshold or weight | `configs/rules.yaml` → `labeling_functions` | covered by tests |
| Turn a misuse pattern or look-alike on/off, or resize it | `configs/patterns.yaml` → `patterns` | covered by tests |
| Change the cash-out limit or incentive cap | `configs/world.yaml` → `regulation` | covered by tests |
| Add a decision type or API field | `backend/app/` and `backend/tests/` | `make test` |
| Change dashboard text or layout | `frontend/app/` | `make web-check` and `make web-build` |

"Verified" means a temporary edit of that kind was applied, `make onsite-refresh`
passed, and the change showed up in the demo data, before the edit was reverted.

## Checklist for each change

1. Edit the config or code.
2. `make onsite-refresh` (and `make web-check` for frontend edits).
3. Look at the affected screen (`make api-fast` + `make web`, or demo mode).
4. Commit with a clear message and push.
5. Add a line to `docs/ai_usage.md` if an AI tool helped.
