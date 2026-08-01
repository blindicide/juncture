# Limitations and interpretation boundaries

1. **Primary scope only.** Primary conclusions apply to preload_all AF/DF paired observations in the configured scenarios. schedule_next_after_transition is a separately labelled architecture robustness comparison, not an additional primary sample or scheduler-mode duplicate.

2. **No causal claim.** Correlations, OLS coefficients, and predictor fits are descriptive associations under the saved design. They do not identify causal effects of quantization error, collision rates, queue capacity, or scheduling policy. In particular, the critical-rate coefficient is below one in the retained single-predictor model and is not a direct estimator.

3. **Zero censoring changes support.** Log-log slopes exclude zero collision rates because `log(0)` is undefined. The audit reports complete, one-missing, and two-or-more-missing categories; condition-level and complete-case summaries answer different descriptive questions and should not be collapsed into a universal exponent.

4. **Uncertainty availability differs by output.** Timing slopes use HC3 intervals; selected means and scaling summaries use stated bootstraps. The saved exact validation table has no replication-level CI, and the focused architecture count audit has no resampling interval. These are reported as unavailable rather than reconstructed from raw data.

5. **Policy coverage.** random_order is absent from the principal saved Phase II.2 inputs. It is explicitly not tested; no result is imputed. Insertion_order is examined only in the focused architecture synthesis and is not part of primary timing-bias, scaling, or predictor analyses.

6. **Saved-data boundary.** This refresh intentionally uses existing v2.2 derived/tables/figures only. It neither reruns simulations nor regenerates raw data, so it cannot recover analyses requiring unavailable replication-level exact-validation data or absent policies.
