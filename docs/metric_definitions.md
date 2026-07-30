# Metric definitions

| Name | Type | Unit | Meaning | Missing behavior |
|---|---|---:|---|---|
| `packet_loss_probability` | float | probability | dropped measured arrivals / measured arrivals | never missing |
| `throughput` | float | jobs/time | completed measured jobs / measured arrival interval | null if zero interval |
| `mean_waiting_time` | float | time | mean service-start minus arrival time for completed measured jobs | null if none complete |
| `collision_event_fraction` | float | fraction | events in collided quantized ticks / processed events | zero in exact mode |
| `critical_acceptance_difference_rate` | float | per arrival | shadow-policy acceptance difference / measured arrivals | zero if none |
| `relative_packet_loss_error` | float | ratio | absolute quantized-exact loss / exact loss | null if exact loss is zero |
# Phase II metric update

Schema-v2 reports collision-event fraction as `measurement_collided_events / measurement_processed_events` and collided-tick fraction as `measurement_collided_ticks / measurement_processed_ticks`; a zero denominator is null, while a nonempty collision-free window is zero. Legacy collision fractions are not denominator-consistent.

Mixed and critical `_per_arrival` rates use `measured_arrivals` as their denominator: mixed ticks, critical ticks, and critical acceptance difference respectively. `mixed_collided_tick_fraction` and `critical_collided_tick_fraction` instead use `measurement_processed_ticks`. The schema-v2 compatibility aliases `mixed_collision_rate` and `critical_acceptance_difference_rate` are per-arrival rates; schema-1 values are never silently reinterpreted.
