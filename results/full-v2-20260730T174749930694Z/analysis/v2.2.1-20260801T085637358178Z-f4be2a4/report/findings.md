# Traceable corrected findings

## predictor_total_coefficient

The retained total predictor coefficient is selected by the canonical term `total_collision_rate`, not by row position or intercept.

Source: `derived/predictor_models_retained.csv`; selector: `model=total; coefficient_total_collision_rate; term != const`; estimate: `{"coefficient": 0.0380521694396377, "cv_mae": null, "cv_rmse": 0.0035675962309885, "hc3_standard_error": 0.0064858205495837, "r_squared": 0.2403652877014775}`.


## predictor_mixed_coefficient

The retained mixed predictor coefficient is selected by the canonical term `mixed_collision_rate`, not by row position or intercept.

Source: `derived/predictor_models_retained.csv`; selector: `model=mixed; coefficient_mixed_collision_rate; term != const`; estimate: `{"coefficient": 0.0748084413379901, "cv_mae": null, "cv_rmse": 0.0036210434342292, "hc3_standard_error": 0.0128013128493205, "r_squared": 0.2156994394645258}`.


## predictor_critical_coefficient

The retained critical predictor coefficient is selected by the canonical term `critical_collision_rate`, not by row position or intercept.

Source: `derived/predictor_models_retained.csv`; selector: `model=critical; coefficient_critical_collision_rate; term != const`; estimate: `{"coefficient": 0.4549963914332999, "cv_mae": null, "cv_rmse": 0.0016198964528441, "hc3_standard_error": 0.0229716415407328, "r_squared": 0.8447784824772924}`.


## predictor_multivariable_coefficient

The retained multivariable predictor coefficient is selected by the canonical term `critical_collision_rate`, not by row position or intercept.

Source: `derived/predictor_models_retained.csv`; selector: `model=multivariable; coefficient_critical_collision_rate; term != const`; estimate: `{"coefficient": 0.5450458073372376, "cv_mae": null, "cv_rmse": 0.0013568498364528, "hc3_standard_error": 0.0215721895631533, "r_squared": 0.8925305839088311}`.


## condition_scaling_rho_1_k_8

The primary collision-frequency figure shows the selected central rho=1.0, K=8 condition on logarithmic delta and frequency axes.

Source: `derived/collision_condition_exponents.csv`; selector: `rho=1.0; capacity=8`; estimate: `{"exponent": 0.9977951070437552, "r_squared": 0.9999265913820256}`.


## censor_complete

The zero-censoring audit retains the `complete` category separately.

Source: `derived/collision_zero_censoring_summary.csv`; selector: `status=complete`; estimate: `{"count": 1161, "mean_exponent": 0.9280284037487458, "percent": 53.75}`.


## censor_one_missing

The zero-censoring audit retains the `one_missing` category separately.

Source: `derived/collision_zero_censoring_summary.csv`; selector: `status=one_missing`; estimate: `{"count": 779, "mean_exponent": 1.0286117829685897, "percent": 36.06481481481482}`.


## censor_two_or_more_missing

The zero-censoring audit retains the `two_or_more_missing` category separately.

Source: `derived/collision_zero_censoring_summary.csv`; selector: `status=two_or_more_missing`; estimate: `{"count": 220, "mean_exponent": 1.08223733060228, "percent": 10.185185185185183}`.


## service_error_bias_relationship

Signed service-duration error has a saved descriptive relationship with midpoint bias; no causal interpretation is made.

Source: `derived/timing_relationships.csv`; selector: `model=service_signed`; estimate: `{"cv_rmse": 0.0025300639459907, "pearson": 0.8520588904231846, "r_squared": 0.7260043527491877, "slope": 0.2829222721025486}`.


## quantizer_floor

The floor quantizer row reports configuration-level midpoint bias, ordering gap, service-time error, and zero-tick fraction.

Source: `tables/quantizer_summary.csv`; selector: `quantizer=floor`; estimate: `{"absolute_midpoint_bias": 0.22550262345679017, "absolute_policy_gap": 0.1173503086419753, "absolute_service_error": 0.007923144711672834, "pearson": 0.8520588904231846, "signed_midpoint_bias": -0.22012145061728397, "signed_service_error": -0.007923144711672834, "zero_tick_fraction": 2.431508614623636e-08}`.


## quantizer_nearest

The nearest quantizer row reports configuration-level midpoint bias, ordering gap, service-time error, and zero-tick fraction.

Source: `tables/quantizer_summary.csv`; selector: `quantizer=nearest`; estimate: `{"absolute_midpoint_bias": 0.014667746913580294, "absolute_policy_gap": 0.11522067901234571, "absolute_service_error": 0.00401217989739275, "pearson": 0.8520588904231846, "signed_midpoint_bias": -0.001273611111111139, "signed_service_error": -5.0716262468181575e-05, "zero_tick_fraction": 2.574064998968646e-08}`.


## quantizer_ceiling

The ceiling quantizer row reports configuration-level midpoint bias, ordering gap, service-time error, and zero-tick fraction.

Source: `tables/quantizer_summary.csv`; selector: `quantizer=ceiling`; estimate: `{"absolute_midpoint_bias": 0.2410185185185185, "absolute_policy_gap": 0.11252592592592595, "absolute_service_error": 0.008125948779533428, "pearson": 0.8520588904231846, "signed_midpoint_bias": 0.23477901234567897, "signed_service_error": 0.008125948779533427, "zero_tick_fraction": 2.5840067334996352e-08}`.


## capacity_delta_01_k_1

At δ=0.1 and K=1, the table compares absolute ordering gap, midpoint bias, and their ratios within the primary architecture.

Source: `tables/capacity_delta_01.csv`; selector: `capacity=1`; estimate: `{"absolute_bias_pp": 0.8069129629629628, "bias_gap_ratio": 0.339361733612258, "bias_half_width_ratio": 0.678723467224516, "half_width_pp": 1.1888685185185186, "policy_gap_pp": 2.377737037037037, "signed_bias_pp": 0.010364814814814579}`.


## capacity_delta_01_k_4

At δ=0.1 and K=4, the table compares absolute ordering gap, midpoint bias, and their ratios within the primary architecture.

Source: `tables/capacity_delta_01.csv`; selector: `capacity=4`; estimate: `{"absolute_bias_pp": 0.8200314814814815, "bias_gap_ratio": 2.389755960668761, "bias_half_width_ratio": 4.779511921337522, "half_width_pp": 0.17157222222222218, "policy_gap_pp": 0.34314444444444436, "signed_bias_pp": 0.030264814814814862}`.


## capacity_delta_01_k_8

At δ=0.1 and K=8, the table compares absolute ordering gap, midpoint bias, and their ratios within the primary architecture.

Source: `tables/capacity_delta_01.csv`; selector: `capacity=8`; estimate: `{"absolute_bias_pp": 1.01685, "bias_gap_ratio": 11.065636209745675, "bias_half_width_ratio": 22.13127241949135, "half_width_pp": 0.04594629629629631, "policy_gap_pp": 0.09189259259259262, "signed_bias_pp": 0.04978333333333331}`.


## capacity_delta_01_k_16

At δ=0.1 and K=16, the table compares absolute ordering gap, midpoint bias, and their ratios within the primary architecture.

Source: `tables/capacity_delta_01.csv`; selector: `capacity=16`; estimate: `{"absolute_bias_pp": 1.1836592592592594, "bias_gap_ratio": 49.76455932731235, "bias_half_width_ratio": 99.5291186546247, "half_width_pp": 0.011892592592592597, "policy_gap_pp": 0.023785185185185194, "signed_bias_pp": 0.0833222222222221}`.


## architecture_preload_all

Insertion matching uses mutually exclusive exact-count categories from the validated focused architecture summary.

Source: `derived/insertion_architecture_summary.csv`; selector: `arrival_scheduling_mode=preload_all`; estimate: `{"af_only_percent": 93.88888888888889, "both_percent": 6.111111111111111, "df_only_percent": 0.0, "neither_percent": 0.0}`.


## architecture_schedule_next_after_transition

Insertion matching uses mutually exclusive exact-count categories from the validated focused architecture summary.

Source: `derived/insertion_architecture_summary.csv`; selector: `arrival_scheduling_mode=schedule_next_after_transition`; estimate: `{"af_only_percent": 0.0, "both_percent": 6.111111111111111, "df_only_percent": 93.88888888888889, "neither_percent": 0.0}`.
