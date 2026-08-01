# Phase II.2 findings

All estimates below are descriptive unless explicitly labelled otherwise. `CI unavailable` means the saved derived input does not contain the replication-level information needed to reconstruct that interval without touching raw results.

## H1_exact_engine_validation

H1 is supported only as a point-estimate agreement check: the largest saved absolute exact-loss difference from M/M/1/K theory is reported below; no uncertainty interval was retained for this comparison.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2-20260731T155643071963Z-2e8b6e3ea6`; commit: `fbfe1698`.
- Source table/file: `tables/exact_validation.csv` / `derived/exact_validation_retained.csv`.
- Filters: theory_applicable=true; M/M/1/K
- Grouping keys: rho, capacity; aggregation: one saved exact-result mean per condition.
- Units: absolute packet-loss-probability difference; sample size: `{"condition_rows": 24, "replications_per_condition": 30}`.
- Estimate: `{"capacity": 16, "condition_rows": 24, "max_absolute_difference": 0.001493697932696, "replications_per_condition": 30, "rho": 1.1}`. CI: `{"available": false, "reason": "the retained exact-validation table contains condition means and n, but no replication-level values or saved CI"}`.

## H2_service_error_bias_relationship

H2 is supported as a descriptive association: configuration-mean signed service-duration error and midpoint loss bias are strongly positively associated in the preload_all primary analysis; this is not a causal estimate.

- Status: `supported`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `derived/timing_relationships.csv` / `derived/timing_bias_configuration.parquet`.
- Filters: arrival_scheduling_mode=preload_all; policies=arrival_first,departure_first; exact reference joined by workload_id
- Grouping keys: rho, capacity, delta, quantizer, arrival_scheduling_mode; aggregation: AF/DF average within each workload, then mean of 30 paired workloads per configuration; OLS with HC3 and leave-one-configuration-out CV.
- Units: midpoint loss-probability bias per signed service-duration error; sample size: `{"configuration_rows": 648, "paired_workload_rows": 19440, "replications_per_configuration": 30}`.
- Estimate: `{"cv_mae": 0.0007297859062992, "cv_rmse": 0.0025300639459907, "folds": 648, "hc3_se": 0.0233628117075885, "intercept": 3.0270159570709185e-05, "pearson": 0.8520588904231846, "r_squared": 0.7260043527491877, "slope": 0.2829222721025486, "spearman": 0.8399255692403554}`. CI: `{"available": true, "high": 0.3287133830494221, "level": 0.95, "low": 0.2371311611556751, "method": "HC3 normal-approximation interval for OLS slope"}`.

## H2_maximum_configuration_bias

H2 maximum configuration-mean bias identifies the largest saved absolute midpoint-bias configuration in the primary analysis; it is an observed configuration summary, not a worst-case guarantee beyond the sampled design.

- Status: `supported`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `derived/timing_bias_configuration.parquet` / `derived/timing_bias_configuration.parquet`.
- Filters: arrival_scheduling_mode=preload_all; policies=arrival_first,departure_first; exact reference joined by workload_id
- Grouping keys: rho, capacity, delta, quantizer; aggregation: maximum absolute value over saved configuration means.
- Units: packet-loss probability; sample size: `{"configuration_rows_searched": 648, "paired_workload_rows_selected_configuration": 30}`.
- Estimate: `{"absolute_midpoint_bias": 0.03597633333333334, "configuration_bootstrap_ci95": [-0.03681299999999999, -0.03514030833333334], "configuration_id": "1.25|16|0.1|floor|preload_all", "signed_midpoint_bias": -0.03597633333333334}`. CI: `{"available": true, "high": -0.03514030833333334, "level": 0.95, "low": -0.03681299999999999, "method": "bootstrap over the 30 paired workload rows in the selected configuration"}`.

## H2_quantizer_ceiling

H2 quantizer-stratified descriptive result (ceiling): the configuration-mean midpoint bias and AF–DF loss gap are reported separately; this stratum does not establish a mechanism.

- Status: `supported`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/quantizer_bias_order_gap.csv` / `derived/timing_bias_configuration.parquet`.
- Filters: arrival_scheduling_mode=preload_all; policies=arrival_first,departure_first; exact reference joined by workload_id; quantizer=ceiling
- Grouping keys: rho, capacity, delta, quantizer; aggregation: mean across configuration rows; bootstrap over configurations.
- Units: packet-loss probability; sample size: `{"configuration_rows": 216, "paired_workload_rows": 6480}`.
- Estimate: `{"mean_af_df_loss_gap": 0.001122820987654321, "mean_midpoint_signed_bias": 0.0023477901234567897}`. CI: `{"af_df_gap": {"available": true, "high": 0.0016893427469135802, "level": 0.95, "low": 0.0006405345679012344, "method": "bootstrap over configuration means"}, "midpoint_bias": {"available": true, "high": 0.0031497843364197515, "level": 0.95, "low": 0.0016489231867283947, "method": "bootstrap over configuration means"}}`.

## H2_quantizer_floor

H2 quantizer-stratified descriptive result (floor): the configuration-mean midpoint bias and AF–DF loss gap are reported separately; this stratum does not establish a mechanism.

- Status: `supported`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/quantizer_bias_order_gap.csv` / `derived/timing_bias_configuration.parquet`.
- Filters: arrival_scheduling_mode=preload_all; policies=arrival_first,departure_first; exact reference joined by workload_id; quantizer=floor
- Grouping keys: rho, capacity, delta, quantizer; aggregation: mean across configuration rows; bootstrap over configurations.
- Units: packet-loss probability; sample size: `{"configuration_rows": 216, "paired_workload_rows": 6480}`.
- Estimate: `{"mean_af_df_loss_gap": 0.0011679351851851853, "mean_midpoint_signed_bias": -0.00220121450617284}`. CI: `{"af_df_gap": {"available": true, "high": 0.0017472506944444443, "level": 0.95, "low": 0.0006573324845679009, "method": "bootstrap over configuration means"}, "midpoint_bias": {"available": true, "high": -0.0015599672839506178, "level": 0.95, "low": -0.002911116550925926, "method": "bootstrap over configuration means"}}`.

## H2_quantizer_nearest

H2 quantizer-stratified descriptive result (nearest): the configuration-mean midpoint bias and AF–DF loss gap are reported separately; this stratum does not establish a mechanism.

- Status: `supported`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/quantizer_bias_order_gap.csv` / `derived/timing_bias_configuration.parquet`.
- Filters: arrival_scheduling_mode=preload_all; policies=arrival_first,departure_first; exact reference joined by workload_id; quantizer=nearest
- Grouping keys: rho, capacity, delta, quantizer; aggregation: mean across configuration rows; bootstrap over configurations.
- Units: packet-loss probability; sample size: `{"configuration_rows": 216, "paired_workload_rows": 6480}`.
- Estimate: `{"mean_af_df_loss_gap": 0.0011481759259259262, "mean_midpoint_signed_bias": -1.2736111111111388e-05}`. CI: `{"af_df_gap": {"available": true, "high": 0.0017377720679012348, "level": 0.95, "low": 0.0006616320987654324, "method": "bootstrap over configuration means"}, "midpoint_bias": {"available": true, "high": -4.11875000000024e-06, "level": 0.95, "low": -2.2270138888889297e-05, "method": "bootstrap over configuration means"}}`.

## H3_zero_censoring_complete

H3 zero-censoring audit (complete): 1161 workload-design fits (53.750%) fall in this category; exponents use positive rates only and do not replace zeros with epsilon.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/collision_zero_censoring.csv` / `derived/collision_zero_censoring_summary.csv`.
- Filters: preload_all; delta>0 and delta<=0.003; policy-neutral AF/DF collision rate
- Grouping keys: workload_id, rho, capacity, quantizer; aggregation: one log-log slope per workload-design using positive fine-delta rates.
- Units: log-log collision-rate exponent; sample size: `{"category_rows": 1161, "workload_design_rows": 2160}`.
- Estimate: `{"count": 1161, "mean_exponent": 0.9280284037487458, "median_exponent": 0.9357116219500576, "percent": 53.75}`. CI: `{"available": true, "high": 0.9329108282978296, "level": 0.95, "low": 0.9232233818255852, "method": "bootstrap over workload-design exponents"}`.

## H3_zero_censoring_one_missing

H3 zero-censoring audit (one_missing): 779 workload-design fits (36.065%) fall in this category; exponents use positive rates only and do not replace zeros with epsilon.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/collision_zero_censoring.csv` / `derived/collision_zero_censoring_summary.csv`.
- Filters: preload_all; delta>0 and delta<=0.003; policy-neutral AF/DF collision rate
- Grouping keys: workload_id, rho, capacity, quantizer; aggregation: one log-log slope per workload-design using positive fine-delta rates.
- Units: log-log collision-rate exponent; sample size: `{"category_rows": 779, "workload_design_rows": 2160}`.
- Estimate: `{"count": 779, "mean_exponent": 1.0286117829685897, "median_exponent": 1.0235009249269875, "percent": 36.06481481481482}`. CI: `{"available": true, "high": 1.0363359073127707, "level": 0.95, "low": 1.0211165350894498, "method": "bootstrap over workload-design exponents"}`.

## H3_zero_censoring_two_or_more_missing

H3 zero-censoring audit (two_or_more_missing): 220 workload-design fits (10.185%) fall in this category; exponents use positive rates only and do not replace zeros with epsilon.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/collision_zero_censoring.csv` / `derived/collision_zero_censoring_summary.csv`.
- Filters: preload_all; delta>0 and delta<=0.003; policy-neutral AF/DF collision rate
- Grouping keys: workload_id, rho, capacity, quantizer; aggregation: one log-log slope per workload-design using positive fine-delta rates.
- Units: log-log collision-rate exponent; sample size: `{"category_rows": 220, "workload_design_rows": 2160}`.
- Estimate: `{"count": 220, "mean_exponent": 1.08223733060228, "median_exponent": 1.0650042419468555, "percent": 10.185185185185183}`. CI: `{"available": true, "high": 1.0998063046814213, "level": 0.95, "low": 1.0645620673691971, "method": "bootstrap over workload-design exponents"}`.

## H3_condition_level_scaling

H3 condition-level scaling is descriptively near linear on the configured fine-delta range after averaging policy-neutral collision rates within condition; it does not imply a universal exponent.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/collision_scaling.csv` / `derived/collision_condition_exponents.csv`.
- Filters: preload_all; delta>0 and delta<=0.003; positive condition-mean collision rates
- Grouping keys: rho, capacity; aggregation: one log-log slope per rho/capacity condition after policy-neutral AF/DF and workload averaging.
- Units: log-log collision-rate exponent; sample size: `{"condition_rows": 24, "fine_deltas_per_condition": 6}`.
- Estimate: `{"maximum": 1.0354788569497315, "mean": 0.993294029914924, "mean_r_squared": 0.9996531802976528, "median": 0.994964781619176, "minimum": 0.9427885457891162}`. CI: `{"available": true, "high": 1.000616543126576, "level": 0.95, "low": 0.9858911174325615, "method": "bootstrap over 24 condition exponents"}`.

## H3_complete_case_scaling

H3 complete-case workload scaling is lower than the all-condition summary and is reported separately because zero-censoring changes the retained fine-delta support.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/collision_zero_censoring.csv` / `derived/collision_zero_censoring_audit.csv`.
- Filters: status=complete; preload_all; six positive configured fine deltas
- Grouping keys: workload_id, rho, capacity, quantizer; aggregation: mean of one positive-rate log-log slope per complete workload-design.
- Units: log-log collision-rate exponent; sample size: `{"all_workload_design_rows": 2160, "complete_case_rows": 1161}`.
- Estimate: `{"mean": 0.9280284037487458, "median": 0.9357116219500576}`. CI: `{"available": true, "high": 0.9329860049805566, "level": 0.95, "low": 0.9231234641495631, "method": "bootstrap over complete-case workload-design exponents"}`.

## H4_predictor_total

H4 retained predictor model (total) is an association model evaluated by grouped leave-one-configuration-out validation; it is not a direct causal estimator.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2-20260731T155643071963Z-2e8b6e3ea6`; commit: `fbfe1698`.
- Source table/file: `tables/predictor_comparison.csv` / `derived/predictor_models_retained.csv`.
- Filters: primary preload_all retained predictor configurations
- Grouping keys: analysis_configuration_id; aggregation: saved workload-paired configuration model with grouped validation.
- Units: packet-loss-probability gap per model predictor unit; sample size: `{"configuration_rows": 648, "folds": 648, "train_test_groups_disjoint": true}`.
- Estimate: `{"coefficient": 0.0001962191018393, "coefficient_name": "coefficient_const", "cv_rmse": 0.0035675962309885, "folds": 648, "r_squared": 0.2403652877014775}`. CI: `{"available": true, "high": 0.0001992238350823, "level": 0.95, "low": 0.0001933346441697, "method": "replication-level bootstrap, 1,000 resamples"}`.

## H4_predictor_mixed

H4 retained predictor model (mixed) is an association model evaluated by grouped leave-one-configuration-out validation; it is not a direct causal estimator.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2-20260731T155643071963Z-2e8b6e3ea6`; commit: `fbfe1698`.
- Source table/file: `tables/predictor_comparison.csv` / `derived/predictor_models_retained.csv`.
- Filters: primary preload_all retained predictor configurations
- Grouping keys: analysis_configuration_id; aggregation: saved workload-paired configuration model with grouped validation.
- Units: packet-loss-probability gap per model predictor unit; sample size: `{"configuration_rows": 648, "folds": 648, "train_test_groups_disjoint": true}`.
- Estimate: `{"coefficient": 0.0002354302852778, "coefficient_name": "coefficient_const", "cv_rmse": 0.0036210434342292, "folds": 648, "r_squared": 0.2156994394645258}`. CI: `{"available": true, "high": 0.0002384534296453, "level": 0.95, "low": 0.0002323862097873, "method": "replication-level bootstrap, 1,000 resamples"}`.

## H4_predictor_critical

H4 retained predictor model (critical) is an association model evaluated by grouped leave-one-configuration-out validation; it is not a direct causal estimator. The critical-rate coefficient is below one and must not be interpreted as a direct estimator.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2-20260731T155643071963Z-2e8b6e3ea6`; commit: `fbfe1698`.
- Source table/file: `tables/predictor_comparison.csv` / `derived/predictor_models_retained.csv`.
- Filters: primary preload_all retained predictor configurations
- Grouping keys: analysis_configuration_id; aggregation: saved workload-paired configuration model with grouped validation.
- Units: packet-loss-probability gap per model predictor unit; sample size: `{"configuration_rows": 648, "folds": 648, "train_test_groups_disjoint": true}`.
- Estimate: `{"coefficient": -0.0002217767022179, "coefficient_name": "coefficient_const", "cv_rmse": 0.0016198964528441, "folds": 648, "r_squared": 0.8447784824772924}`. CI: `{"available": true, "high": -0.0002188390286543, "level": 0.95, "low": -0.0002249230277394, "method": "replication-level bootstrap, 1,000 resamples"}`.

## H4_predictor_multivariable

H4 retained predictor model (multivariable) is an association model evaluated by grouped leave-one-configuration-out validation; it is not a direct causal estimator.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2-20260731T155643071963Z-2e8b6e3ea6`; commit: `fbfe1698`.
- Source table/file: `tables/predictor_comparison.csv` / `derived/predictor_models_retained.csv`.
- Filters: primary preload_all retained predictor configurations
- Grouping keys: analysis_configuration_id; aggregation: saved workload-paired configuration model with grouped validation.
- Units: packet-loss-probability gap per model predictor unit; sample size: `{"configuration_rows": 648, "folds": 648, "train_test_groups_disjoint": true}`.
- Estimate: `{"coefficient": 0.0016096087915835, "coefficient_name": "coefficient_const", "cv_rmse": 0.0013568498364528, "folds": 648, "r_squared": 0.8925305839088311}`. CI: `{"available": true, "high": 0.0016219968086732, "level": 0.95, "low": 0.0015966170142156, "method": "replication-level bootstrap, 1,000 resamples"}`.

## H5_architecture_preload_all

H5 insertion-order matching for preload_all is descriptive robustness evidence from the focused architecture run; it is not included in primary preload_all timing or scaling observations.

- Status: `limited`.
- Source run: `insertion-architecture-v2-20260730T092338223105Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/architecture_comparison.csv` / `derived/insertion_architecture_summary.csv`.
- Filters: arrival_scheduling_mode=preload_all; policies=AF,DF,insertion_order
- Grouping keys: workload_id, rho, capacity, delta, quantizer, arrival_scheduling_mode; aggregation: exact integer equality of accepted/dropped/completed counts; loss distances summarized over pairs.
- Units: percent of paired workload/configurations; absolute packet-loss-probability distance; sample size: `{"paired_workload_configuration_rows": 540}`.
- Estimate: `{"matches_af_only_percent": 93.88888888888889, "matches_both_percent": 6.111111111111111, "matches_df_only_percent": 0.0, "matches_neither_percent": 0.0, "max_distance_af": 0.0, "max_distance_df": 0.00358, "mean_distance_af": 0.0, "mean_distance_df": 0.0005852222222222, "paired_count": 540}`. CI: `{"available": false, "reason": "focused architecture results are paired deterministic count comparisons; no resampling interval was specified or saved"}`.

## H5_architecture_schedule_next_after_transition

H5 insertion-order matching for schedule_next_after_transition is descriptive robustness evidence from the focused architecture run; it is not included in primary preload_all timing or scaling observations.

- Status: `limited`.
- Source run: `insertion-architecture-v2-20260730T092338223105Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/architecture_comparison.csv` / `derived/insertion_architecture_summary.csv`.
- Filters: arrival_scheduling_mode=schedule_next_after_transition; policies=AF,DF,insertion_order
- Grouping keys: workload_id, rho, capacity, delta, quantizer, arrival_scheduling_mode; aggregation: exact integer equality of accepted/dropped/completed counts; loss distances summarized over pairs.
- Units: percent of paired workload/configurations; absolute packet-loss-probability distance; sample size: `{"paired_workload_configuration_rows": 540}`.
- Estimate: `{"matches_af_only_percent": 0.0, "matches_both_percent": 6.111111111111111, "matches_df_only_percent": 93.88888888888889, "matches_neither_percent": 0.0, "max_distance_af": 0.00358, "max_distance_df": 0.0, "mean_distance_af": 0.0005852222222222, "mean_distance_df": 0.0, "paired_count": 540}`. CI: `{"available": false, "reason": "focused architecture results are paired deterministic count comparisons; no resampling interval was specified or saved"}`.

## H5_explicit_policy_stability

H5 explicit AF and DF policies have identical accepted and dropped counts across the two scheduling architectures in the focused comparison; the recorded loss differences are reported rather than assumed to be zero.

- Status: `limited`.
- Source run: `insertion-architecture-v2-20260730T092338223105Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `tables/architecture_comparison.csv` / `derived/explicit_architecture_stability.parquet`.
- Filters: policies=arrival_first,departure_first; preload_all versus schedule_next_after_transition
- Grouping keys: workload_id, rho, capacity, delta, quantizer; aggregation: exact integer equality rates and absolute loss differences across architecture pairs.
- Units: percent exact equality; absolute packet-loss-probability difference; sample size: `{"paired_workload_configuration_rows": 540}`.
- Estimate: `{"arrival_first": {"accepted_equal_percent": 100.0, "dropped_equal_percent": 100.0, "max_loss_difference": 0.0, "mean_loss_difference": 0.0}, "departure_first": {"accepted_equal_percent": 100.0, "dropped_equal_percent": 100.0, "max_loss_difference": 0.0, "mean_loss_difference": 0.0}}`. CI: `{"available": false, "reason": "focused explicit-policy comparison is a complete paired deterministic count audit, not a resampled estimate"}`.

## H6_random_order_scope

H6 is not tested: no random_order policy observation is present in the principal Phase II.2 saved inputs, so no random-order result is inferred or fabricated.

- Status: `not_tested`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `source_runs.json` / `derived/timing_bias_workload_pairs.parquet`.
- Filters: policy=random_order
- Grouping keys: not applicable; aggregation: absence check in saved primary derived input.
- Units: not applicable; sample size: `{"rows": 0}`.
- Estimate: `{"available_rows": 0}`. CI: `{"available": false, "reason": "no saved random_order observations"}`.

## H7_scope_and_causal_limit

H7 is limited: the saved analyses establish descriptive associations and reproducibility checks within their configured scenarios, not causal effects, universal scaling laws, or unmeasured-policy comparisons.

- Status: `limited`.
- Source run: `full-v2-20260730T174749930694Z`; source analysis: `v2.2-20260801T081533769838Z-fbfe1698`; commit: `fbfe1698`.
- Source table/file: `report/limitations.md` / `source_runs.json`.
- Filters: primary preload_all analysis scope
- Grouping keys: not applicable; aggregation: scope statement based on saved analysis design.
- Units: not applicable; sample size: `{"configuration_rows": 648}`.
- Estimate: `{"paired_workload_rows": 19440, "primary_configuration_rows": 648}`. CI: `{"available": false, "reason": "scope limitation, not an estimand"}`.
