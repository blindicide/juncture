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
juncture analyze --run-dir results/<run_id>
juncture plot --run-dir results/<run_id> --language en
juncture tables --run-dir results/<run_id>
juncture report --run-dir results/<run_id>
```

Use `juncture resume --run-dir results/<run_id>` after interruption. Results contain the resolved configuration, provenance, deterministic task manifest/status, raw exact and quantized Parquet tables, derived tables, figures, and a traceable report. The full study is launched with `juncture run --config configs/full.yaml --workers N`; it is intentionally not run automatically.

Exact simulations are checked against the M/M/1/K stationary full-state probability. Quantized models deliberately have different semantics and are not compared directly with that formula.
