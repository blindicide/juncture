# Phase II.2 publication summary

This report refresh reads only existing v2.2 derived artifacts in `v2.2-20260801T081533769838Z-fbfe1698`; it does not rerun simulation, regenerate workloads, or alter raw results. The canonical analysis is `preload_all` only: 19,440 AF/DF-paired workload rows were aggregated to 648 unique configuration rows, each with 30 workload replications.

The service-error/bias association has Pearson 0.852059, Spearman 0.839926, HC3 slope 0.282922 (95% CI [0.237131, 0.328713]), R² 0.726004, and grouped CV RMSE/MAE 0.002530/0.000730 across 648 configuration-held-out folds [H2_service_error_bias_relationship].

The zero-censoring audit covers 2,160 workload-design fits: 1,161 complete (53.750%), 779 with one missing positive rate, and 220 with two or more missing. Condition exponents average 0.993294; complete-case workload exponents average 0.928028 (95% CI [0.923123, 0.932986]) [H3_condition_level_scaling; H3_complete_case_scaling].

Insertion-order results come from the separately selected verified focused run `insertion-architecture-v2-20260730T092338223105Z`. In preload_all, insertion matches AF only in 93.888889% of pairs; schedule_next_after_transition is labelled robustness-only and matches DF only in 93.888889% [H5_architecture_preload_all; H5_architecture_schedule_next_after_transition].

Retained predictor models and the exact-engine comparison are reported as saved analyses with their stated uncertainty limits. No random_order observation is available, and no causal, universal, or direct-estimator claim is made [H1_exact_engine_validation; H4_predictor_critical; H6_random_order_scope; H7_scope_and_causal_limit].
