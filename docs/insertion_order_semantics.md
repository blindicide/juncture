# Insertion-order semantics

`insertion_order` preserves event creation sequence and can therefore inherit a scheduler architecture's implicit priority. Schema v2 compares `preload_all` with `schedule_next_after_transition` using identical pre-generated workload arrays. `schedule_next_before_transition` is available for controlled diagnostics.

AF, DF, and exact-within-tick use explicit keys and are tested for architecture independence. Insertion comparisons report exact count matches, floating-point distances, and allegiance to AF or DF.
