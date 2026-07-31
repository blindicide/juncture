# Juncture

Juncture is a reproducible study of whether finite timestamp resolution changes results in a finite-capacity single-server queue. It compares an exact continuous-time M/M/1/K reference with integer-tick simulations where arrivals and departures can share a timestamp.

The queue capacity `K` includes the job in service. Workloads are generated once per replication and reused by all event-ordering policies, separating workload randomness from tie-breaking randomness.

## Installation

```bash
python -m pip install -e '.[dev]'
```

## Run

```bash
juncture run --config configs/smoke.yaml --workers 2
juncture analyze --run-dir results/<run_id> --analysis-config configs/analysis_v2.yaml
juncture paper-assets --analysis-dir results/<run_id>/analysis/<analysis_id>
juncture verify-run --run-dir results/<run_id>
```

Use `juncture resume --run-dir results/<run_id>` after interruption. Results contain the resolved configuration, provenance, deterministic task manifest/status, raw exact and quantized Parquet tables, derived tables, figures, and a traceable report. The full study is launched with `juncture run --config configs/full.yaml --workers N`; it is intentionally not run automatically.

Exact simulations are checked against the M/M/1/K stationary full-state probability. Quantized models deliberately have different semantics and are not compared directly with that formula.

## Phase II

Schema-v2 runs add deterministic cryptographic identities, independent workload/tie/quantization seeds, measurement-window collision counters, timing diagnostics, and configurable arrival-scheduling architectures. `analyze` creates an immutable, versioned analysis below the run; it never rewrites a historical run's `derived`, `figures`, `tables`, or `report` directories. Schema-1 inputs require explicit legacy opt-in and retain the label `legacy_collision_event_fraction`.

For Phase II publication, `preload_all` is the canonical architecture. The analysis keeps
`schedule_next_after_transition` in separately labelled robustness outputs, never mixed into
primary tables or models. Collision scaling averages AF/DF within a workload-design and delta
before fitting one workload-level slope. Predictor models first aggregate paired workload
estimates to one experimental-configuration row and use replication-level bootstrap intervals.

Use the permitted validation workflow before any large campaign:

```bash
juncture run --config configs/smoke_v2.yaml --workers 2
juncture verify-run --run-dir results/<smoke_run>
juncture analyze --run-dir results/<smoke_run> --analysis-config configs/analysis_v2.yaml
juncture paper-assets --analysis-dir results/<smoke_run>/analysis/<analysis_id>
```

`full_v2.yaml`, `collision_scaling_v2.yaml`, `quantizer_bias_v2.yaml`, and `random_order_v2.yaml` are definitions only until an explicit campaign authorization. See `docs/phase2_corrections.md` for Phase I limitations and rerun requirements.
