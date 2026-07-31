# Methodology

analysis=v2-20260731T155643071963Z-2e8b6e3ea6; run=full-v2-20260730T174749930694Z; commit=5247956af3f193511b7b7241b7b3b80a257198aa

## Inputs and preservation

This versioned analysis reads only the completed raw Parquet tables. Their SHA-256 values are recorded in `provenance.json`; no raw campaign file is rewritten. Collision denominators cover complete timestamp batches from the first measured arrival through the final measured-arrival batch, including recursive same-tick events and excluding post-final drain.

## Primary collision scaling

The canonical architecture is `preload_all`. For each workload-design (workload identity plus quantizer) and each valid fine delta (`0 < delta <= 0.003`), the arrival-first and departure-first collision-event fractions are averaged first. One log-log slope is then fitted to positive midpoint rates for that workload-design. The 2,160 slopes are summarized by rho, capacity, and quantizer into 72 conditions with mean, SD, median, IQR, and condition-specific 10,000-resample 95% bootstrap intervals. Source: `derived/collision_scaling_workload_slopes.csv` and `derived/collision_scaling_summary.csv`.

## Predictor models and validation

AF/DF policy gaps and collision rates are paired at workload level, then averaged over 30 workload replications into exactly one experimental-configuration row. Thus 19,440 paired workload rows produce 648 predictor rows. Bootstrap coefficient intervals resample workload-paired replications within configuration (1,000 resamples). Leave-configuration-out validation uses 648 folds; a configuration is never present in both a training and test fold. Sources: `derived/predictor_workload_rows.parquet`, `derived/predictor_rows.parquet`, and `derived/predictor_models.csv`.

## Robustness and non-primary scopes

`schedule_next_after_transition` is analysed only in `robustness_*` outputs and `derived/architecture_robustness_comparison.csv`. It is not a second primary scheduler observation. `random_order` has no full-v2 rows and is explicitly reported as unavailable.
