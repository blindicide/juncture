# Phase II corrections

Phase I raw and presentation directories are immutable historical artifacts. Their collision-event fraction used an all-run event denominator and must not be described as corrected. Schema-v2 counts only complete timestamp batches beginning with the first measured arrival and ending with the final measured-arrival batch, including recursive events and excluding post-final drain.

Schema-v2 analysis is written under `analysis/<analysis_id>` with input hashes, configuration hash, commit, timestamp, and source run ID. A schema-1 reanalysis needs `include_legacy: true`; it retains `legacy_collision_event_fraction` and `collision_denominator_consistent=false`.

All Phase I campaigns require reruns for corrected collision scaling, timing diagnostics, paired bias decomposition, architecture comparisons, and hierarchical random-order variance.
