# Limitations

analysis=v2-20260731T155643071963Z-2e8b6e3ea6; run=full-v2-20260730T174749930694Z; commit=5247956af3f193511b7b7241b7b3b80a257198aa

1. `random_order` is absent from full-v2. H7 is not tested; no random-order variance estimate is fabricated.

2. Exact-theory validation has 24 condition means but no confidence intervals in `derived/theory_validation.csv`; agreement should not be read as a formal uncertainty-calibrated test.

3. Predictor regressions and timing correlations are descriptive associations. The 648 grouped folds prevent configuration leakage, but they do not turn coefficients into causal effects.

4. `schedule_next_after_transition` is a labelled robustness architecture, not an additional primary sample. It remains separated in `robustness_*` files and the architecture comparison.

5. The corrected aggregation changes presentation and inferential units: primary scaling is AF/DF-midpoint, workload-design based; predictor models use one configuration mean. Therefore prior AF/DF-separated or mode-pooled numerical summaries are superseded, not directly comparable primary estimates.
