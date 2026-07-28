# Experiment plan

`smoke.yaml` tests the end-to-end pipeline. `pilot.yaml` profiles a reduced policy map. `full.yaml` covers the primary E2 grid. `validation.yaml` supports exact-engine theory checks; `random_order.yaml` and `robustness.yaml` provide focused extensions.
# Phase II execution guardrail

Run `smoke_v2.yaml`, `verify-run`, versioned `analyze`, and `paper-assets` before any corrected pilot. Do not execute `full_v2.yaml`, `quantizer_bias_v2.yaml`, or `random_order_v2.yaml` without explicit authorization. Use no more than the authorized worker count.
