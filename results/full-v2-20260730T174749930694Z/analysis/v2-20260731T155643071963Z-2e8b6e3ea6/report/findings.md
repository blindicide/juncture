# Findings

analysis=v2-20260731T155643071963Z-2e8b6e3ea6; run=full-v2-20260730T174749930694Z; commit=5247956af3f193511b7b7241b7b3b80a257198aa

Each hypothesis below identifies its status, source, filters, aggregation unit, row count, estimate, and available interval.

## H1_exact_theory_validation: supported

H1: the exact engine agrees with the M/M/1/K reference on eligible workloads

- Source: `derived/theory_validation.csv`
- Filters: preload_all exact rows; exponential arrivals and services; all 24 rho-by-capacity conditions
- Aggregation unit: condition mean over 30 replications
- Row count: 24
- Estimate: `{"capacity": 16, "maximum_absolute_loss_difference": 0.001493697932696, "rho": 1.1}`
- Interval: `{"available": false, "reason": "theory-validation table contains no replication-level confidence interval"}`
- Interpretation: Exact-engine agreement is a validation result, not a causal claim about quantization.

## H2_collision_scaling: supported

H2: collision-event frequency scales approximately linearly with fine timestamp resolution

- Source: `derived/collision_scaling_workload_slopes.csv, derived/collision_scaling_summary.csv`
- Filters: preload_all only; delta > 0 and delta <= 0.003; arrival_first and departure_first averaged within workload-design and delta before fitting
- Aggregation unit: one log-log slope per workload-design, then summary by rho, capacity, and quantizer
- Row count: {'workload_design_slopes': 2160, 'condition_summaries': 72}
- Estimate: `{"mean_workload_design_slope": 0.9800100779709847, "range_of_condition_mean_slopes": [0.9199209628524304, 1.0308733807738162]}`
- Interval: `{"available": true, "pooled_interval": null, "resamples": 10000, "rows": 72, "source_column_pair": ["bootstrap_ci95_low", "bootstrap_ci95_high"], "type": "condition-specific 95% bootstrap CI"}`
- Interpretation: The estimate is descriptive across the configured grid; no pooled causal or universal scaling claim is made.

## H3_af_df_ordering_sensitivity: supported

H3: deterministic within-tick order changes packet-loss outcomes

- Source: `derived/paired_bias_decomposition.parquet, derived/predictor_rows.parquet`
- Filters: preload_all only; exact workload reference joined by workload identity; paired arrival_first/departure_first observations
- Aggregation unit: workload-paired AF/DF difference; configuration means use 30 workload replications
- Row count: {'paired_workloads': 19440, 'configuration_rows': 648}
- Estimate: `{"exact_inside_deterministic_interval_fraction": 0.5004115226337449, "mean_absolute_policy_gap": 0.0012032551440329222}`
- Interval: `{"available": true, "pooled_interval": null, "rows": 648, "source_columns": ["policy_gap_bootstrap_ci95_low", "policy_gap_bootstrap_ci95_high"], "type": "configuration-specific 95% workload-replication bootstrap"}`
- Interpretation: This is a paired simulation contrast, not evidence of a causal mechanism outside the model.

## H4_critical_collision_predictor: supported

H4: critical acceptance-difference rate is associated with AF/DF policy sensitivity

- Source: `derived/predictor_models.csv, derived/predictor_rows.parquet`
- Filters: preload_all only; one AF/DF-paired mean row per experimental configuration
- Aggregation unit: 648 configuration-level means from 19,440 workload-paired rows; leave-configuration-out validation
- Row count: 648
- Estimate: `{"critical_rate_coefficient": 0.4549963914332999, "cv_rmse": 0.0016198964528441, "r_squared": 0.8447784824772924}`
- Interval: `{"available": true, "coefficient_ci": [0.4537515819817469, 0.4562070583723092], "resamples": 1000, "type": "95% bootstrap over workload-paired replications within configuration"}`
- Interpretation: Association only; regression coefficients are not causal estimates.

## H5_quantizer_timing_diagnostics: limited

H5: quantizer timing diagnostics are associated with observed outcomes

- Source: `derived/quantization_diagnostics.csv, derived/quantization_correlations.csv`
- Filters: preload_all quantized rows; descriptive quantizer, rho, capacity, delta, and policy summaries
- Aggregation unit: configuration summary and pairwise descriptive correlation
- Row count: {'diagnostic_rows': 1944, 'correlation_rows': 8}
- Estimate: `{"error_metric": "arrival_quantization_error_signed_mean", "largest_absolute_pearson": 0.0346980198484252, "outcome": "mean_waiting_time"}`
- Interval: `{"available": false, "reason": "correlation table reports no confidence intervals"}`
- Interpretation: Diagnostics are descriptive associations and do not establish a causal effect of quantization error.

## H6_insertion_and_architecture_robustness: limited

H6: insertion-order behavior is scheduler-architecture dependent while explicit-order primary results remain distinct

- Source: `derived/insertion_architecture.parquet, derived/architecture_robustness_comparison.csv`
- Filters: primary insertion table: preload_all only; architecture comparison: preload_all versus separately labelled schedule_next_after_transition
- Aggregation unit: paired workload rows for insertion; one matched configuration row for robustness comparison
- Row count: {'primary_insertion_pairs': 19440, 'architecture_comparisons': 648}
- Estimate: `{"insertion_count_match_fraction": {"insertion_matches_arrival_first_counts": 1.0, "insertion_matches_departure_first_counts": 0.37222222222222223}, "maximum_absolute_critical_rate_robustness_difference": 0.0013603333333333}`
- Interval: `{"available": false, "reason": "no architecture-comparison confidence interval is published"}`
- Interpretation: schedule_next_after_transition is a robustness result only and is never pooled with primary observations.

## H7_random_order_variance: not tested

H7: random-order tie-breaking has measurable within-workload variance

- Source: `derived/random_order_scope.csv`
- Filters: full-v2 campaign
- Aggregation unit: not applicable
- Row count: 0
- Estimate: `null`
- Interval: `{"available": false, "reason": "random_order is absent from this run"}`
- Interpretation: No random_order tasks are present in this full-v2 run; no random-order finding is estimated.
