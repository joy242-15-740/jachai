# AI usage log

One row per AI-assisted task (General Rules GR 5.6, 7.4). Append at the end of
every task.

| Date time | Member | Tool | Phase | What was generated | Reviewed by |
| --- | --- | --- | --- | --- | --- |
| 2026-10-04 02:04 | kmsajid044-ship-it | Claude Code (Claude Opus 5.5) | 72h build: scaffold | Repo layout, README (10 sections), ml + backend pyprojects, ruff/pytest config, smoke tests, Makefile, GitHub Actions CI, docs/third_party.md, docs/ai_usage.md | pending: kmsajid044-ship-it |
| 2026-10-04 02:27 | kmsajid044-ship-it | Claude Code (Claude Opus 5.5) | 72h build: synthetic world | ml/jachai/world (config loader, base generator, 6 misuse + 4 hard-negative injectors, label noise, summary, CLI), configs/world.yaml + patterns.yaml, data/ASSUMPTIONS.md, world tests, make world | pending: kmsajid044-ship-it |
| 2026-10-04 02:50 | kmsajid044-ship-it | Claude Code (Claude Opus 5.5) | 72h build: features, weak labels, baselines | ml/jachai/features (payment/payer/shop, point-in-time), ml/jachai/labels (8 labeling functions, weighted vote), eval/metrics + baselines + leakage check + probe, make eval, thresholds.yaml + rules.yaml, world made harder after leakage check (configs + ASSUMPTIONS.md), tests | pending: kmsajid044-ship-it |
