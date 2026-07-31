# Validation

analysis=v2-20260731T155643071963Z-2e8b6e3ea6; run=full-v2-20260730T174749930694Z; commit=5247956af3f193511b7b7241b7b3b80a257198aa

## Campaign integrity

`juncture verify-run` completed with 118,080 manifest tasks and no errors. Raw SHA-256 values match analysis provenance: exact `8451d2a5ebeb8b527169f241347ff3393031e2d343410f887497e0451fcab953` and quantized `5aaac2e35f601a9a8e3031e032f3a00bcd397cc7cc9620299e3aa9c6590ebcbd`.

## Analysis consistency checks

Primary architecture only: `True`. Primary scaling has no policy column: `True`. Predictor configuration rows are unique: `True`. Primary/robustness outputs are separated: `True`. The report covers 2,160 slopes, 19,440 predictor workload rows, and 648 predictor configurations.

## Exact-theory check

All 24 primary exact conditions are M/M/1/K eligible. The largest absolute packet-loss difference is 0.0014937 at rho=1.1 and K=2e+01. `derived/theory_validation.csv` reports condition means but no confidence intervals; that uncertainty limitation remains explicit.

## Publication provenance

`figures/manifest.csv` hashes each figure rendition and `artifact_manifest.csv` hashes report, table, and figure artifacts. The report is generated from derived files only; no conclusion is calculated directly from raw simulation state.
