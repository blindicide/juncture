# Analysis schema v2

Raw schema-v2 rows carry `scenario_id`, `workload_id`, `configuration_id`, and `pair_id`, each formed with canonical JSON and SHA-256 rather than Python `hash()`. The workload identity excludes policy, tie seed, quantizer, and delta. `pair_id` joins AF/DF/reference observations for a workload and quantized setting.

Analysis provenance records the schema version, UTC timestamp, Git commit, source run ID, raw-file SHA-256 hashes, and resolved-analysis-config hash. Corrected collision fields are `measurement_processed_events`, `measurement_processed_ticks`, `measurement_collided_events`, `measurement_collided_ticks`, `measurement_mixed_collided_ticks`, `measurement_critical_collided_ticks`, and `measurement_maximum_batch_size`.
