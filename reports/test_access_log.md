# Test-set access log

The test set (test shops × test dates, see `ml/jachai/eval/splits.py`) may be
evaluated **once**, for the final frozen system. Every decision about it and every
access to it is recorded here, newest last. Nothing may be tuned after a test
access.

| Date (UTC+6) | Who | Event | Model / system fingerprint | Test accessed? |
| --- | --- | --- | --- | --- |
| 2026-10-04 03:19 | kmsajid044-ship-it (team decision) | Payment model (weak + cases) ready, but test evaluation **deferred**: the test set is reserved for the final system (payment + shop + network scores + fusion) with all thresholds frozen on validation. | none | **No** |
| 2026-10-04 03:33 | Claude Code (reported to kmsajid044-ship-it) | **Design diagnostic touched test-shop labels.** While debugging why the network ring flag never fired, a diagnostic computed ring-shop community sizes using the true pattern of ALL shops, including test shops. No test metric was computed and no threshold was tuned on it; it informed a redesign of the ring links that follows the brief's definition (same-day spending above part of the cash-out limit across several shops). From now on, diagnostics use train and validation shops only. | none | **Labels only, no evaluation** |
| 2026-10-04 10:28 | Codex (explicitly requested by kmsajid044-ship-it) | **Single final evaluation.** Ran `make eval-final` after current-fusion three-seed validation completed. Results were written once to `reports/final_test.json` and `.md`; no tuning may follow. | git `466e621`; frozen configs | **Yes — final** |
