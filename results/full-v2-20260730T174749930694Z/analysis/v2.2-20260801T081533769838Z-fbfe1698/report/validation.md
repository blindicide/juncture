# Validation and audit trail

**Input and scope checks.** `source_runs.json` records principal raw hashes for `full-v2-20260730T174749930694Z`, focused-run raw hashes for `insertion-architecture-v2-20260730T092338223105Z`, and the baseline provenance hash. The primary derived timing table contains only `preload_all` (True), has 648 rows, and its configuration identifier is unique (`True`). It is derived from 19,440 workload-paired rows with replication count range 30–30.

**Censoring checks.** The audit has 2,160 workload-design rows and no epsilon-adjusted zero-rate field. Its categories sum to 2,160; positive-rate support and min/max included delta are retained per row in `derived/collision_zero_censoring_audit.csv`. The condition table has 24 rho/capacity rows, one slope per condition.

**Architecture checks.** The focused summary has 2 architecture rows with pair counts totaling 1,080. In each row, the four exclusive match categories sum to 100%: preload_all=100.000000%; schedule_next_after_transition=100.000000%. Explicit-policy stability has 540 paired rows and is reported without pooling it into primary data.

**Predictor checks.** The retained table has 4 models over 648 primary configurations; every model records 648 grouped folds and `train_test_groups_disjoint=True`.

**Publication checks.** `manifests/figures.csv` records 36 EN/RU PNG/SVG/PDF figure assets. `manifests/artifacts.csv` hashes every current derived, table, figure, and report artifact. This report refresh deliberately does not claim that theory has a CI, does not treat excluded zeros as observed log values, and does not add absent random_order data.
