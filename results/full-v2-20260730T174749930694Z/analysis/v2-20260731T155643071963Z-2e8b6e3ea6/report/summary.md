# Juncture Phase II campaign summary

analysis=v2-20260731T155643071963Z-2e8b6e3ea6; run=full-v2-20260730T174749930694Z; commit=5247956af3f193511b7b7241b7b3b80a257198aa

## Scope and canonical estimand

The primary analysis is **preload_all only**. It contains 19,440 AF/DF-paired workload observations and 648 one-row-per-configuration predictor observations. `schedule_next_after_transition` is retained only in separately labelled robustness files and is never pooled into a primary table, figure, model, or conclusion.

## Main quantitative results

Fine-resolution collision scaling used 2,160 workload-design log-log slopes, summarized into 72 rho/capacity/quantizer conditions. The mean workload-design slope was 0.98001; condition mean slopes ranged from 0.919921 to 1.03087. The critical-collision configuration model used 648 rows, had R²=0.8448, and coefficient 0.454996 with bootstrap 95% CI [0.453752, 0.456207].

## Interpretation boundary

All regression and diagnostic statements are descriptive associations within this simulation design. `random_order` was not run in full-v2 and therefore contributes no result. The corrected aggregation changes the unit of inference and presentation: it replaces AF/DF- and architecture-duplicated primary rows with AF/DF-midpoint workload slopes and configuration-level predictor rows.
