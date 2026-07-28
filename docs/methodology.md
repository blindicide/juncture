# Methodology

Juncture simulates a FIFO finite-capacity single-server queue. `K` counts all jobs in the system. Arrivals and service requirements are pre-generated for each replication. Exact mode orders raw double-precision timestamps; quantized mode stores integer ticks using floor, nearest, or ceiling quantization and schedules a completion from the quantized current clock.

At equal ticks, policies can prioritize departures, arrivals, insertion order, seeded random priorities, or raw timestamps within a tick. Measurement begins at the first measured arrival without resetting queue state; measured accepted jobs contribute waiting and sojourn metrics when they depart. Collision diagnostics use static pending batches and compare shadow arrival-first and departure-first acceptance counts.
# Phase II update

For schema-v2 runs, collision observations use complete timestamp batches from the first measured arrival through the final measured-arrival batch. They include recursive events created on that tick and exclude warmup and post-final drain. See `analysis_schema_v2.md` for fields and `insertion_order_semantics.md` for scheduler controls.
