# Test-set access log

The test set (test shops × test dates, see `ml/jachai/eval/splits.py`) may be
evaluated **once**, for the final frozen system. Every decision about it and every
access to it is recorded here, newest last. Nothing may be tuned after a test
access.

| Date (UTC+6) | Who | Event | Model / system fingerprint | Test accessed? |
| --- | --- | --- | --- | --- |
| 2026-10-04 03:19 | kmsajid044-ship-it (team decision) | Payment model (weak + cases) ready, but test evaluation **deferred**: the test set is reserved for the final system (payment + shop + network scores + fusion) with all thresholds frozen on validation. | none | **No** |
