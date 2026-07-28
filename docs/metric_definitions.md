# Metric definitions

| Name | Type | Unit | Meaning | Missing behavior |
|---|---|---:|---|---|
| `packet_loss_probability` | float | probability | dropped measured arrivals / measured arrivals | never missing |
| `throughput` | float | jobs/time | completed measured jobs / measured arrival interval | null if zero interval |
| `mean_waiting_time` | float | time | mean service-start minus arrival time for completed measured jobs | null if none complete |
| `collision_event_fraction` | float | fraction | events in collided quantized ticks / processed events | zero in exact mode |
| `critical_acceptance_difference_rate` | float | per arrival | shadow-policy acceptance difference / measured arrivals | zero if none |
| `relative_packet_loss_error` | float | ratio | absolute quantized-exact loss / exact loss | null if exact loss is zero |
