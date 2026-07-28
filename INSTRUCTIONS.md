PROJECT JUNCTURE
Implementation specification for a reproducible discrete-event simulation study

You are to build a complete research codebase named “Juncture”.

The project studies how finite timestamp resolution and event tie-breaking rules affect the results of discrete-event simulations. The primary model is a finite-capacity single-server queue. The central outcome is whether quantizing event timestamps causes arrivals and service completions to collapse onto the same simulated time, allowing an arbitrary event-ordering policy to change packet-loss estimates, throughput, waiting time, and other reported metrics.

This is not a demonstration script. Build a clean, tested, reproducible experimental package capable of producing all numerical results, tables, plots, and machine-readable datasets needed for a scientific paper.

Do not fabricate results. Every number in generated reports must come from saved experiment output.

======================================================================
1. RESEARCH QUESTION
======================================================================

Investigate the following question:

“How strongly do timestamp quantization and equal-timestamp event-ordering policies influence the numerical results of finite-buffer discrete-event simulations?”

The primary hypotheses are:

H1. The frequency of event timestamp collisions initially grows approximately linearly with the timestamp quantum Δ.

H2. Total timestamp-collision frequency alone is not a sufficient predictor of simulation error.

H3. Collisions involving an arrival and a service completion while the system is at or near full capacity are much more predictive of packet-loss discrepancies.

H4. The largest sensitivity occurs near saturation, for small buffers and relatively coarse timestamp resolution.

H5. Processing arrivals before departures generally produces a higher estimated packet-loss probability than processing departures before arrivals.

H6. Random tie-breaking produces a mean result near the midpoint of the two deterministic extreme policies, but introduces additional run-to-run variance.

H7. The observed difference between deterministic ordering policies can be approximated using the frequency of critical arrival–departure collisions.

Treat all hypotheses as claims to be tested, not assumptions to be encoded into the output.

======================================================================
2. PRIMARY MODEL
======================================================================

Implement an M/M/1/K-style finite-capacity queue.

Definitions:

- λ: arrival rate.
- μ: service rate.
- ρ = λ / μ: normalized system load.
- K: maximum number of jobs in the entire system, including the job currently in service.
- An arrival is accepted only if the number of jobs currently in the system is less than K.
- An arrival is dropped if the number of jobs currently in the system equals K.
- Interarrival times are exponentially distributed with mean 1/λ.
- Service requirements are exponentially distributed with mean 1/μ.

Normalize μ = 1 by default. Therefore λ = ρ and the timestamp quantum can be expressed as:

    δ = μΔ = Δ

Keep μ configurable even though the standard experiments use μ = 1.

Each generated arrival must have:

- a unique integer job ID;
- an exact continuous arrival time;
- a pre-generated service requirement;
- acceptance or rejection status;
- service start time if accepted;
- departure time if completed.

Pre-generate the arrival times and service requirements for each replication. Reuse exactly the same workload across every ordering policy belonging to that replication.

This common-random-number design is mandatory. It reduces noise in pairwise comparisons.

Do not consume service-time random numbers only when a job is accepted. Generate one service requirement for every arrival beforehand. Otherwise policy-dependent random-number consumption will invalidate paired comparisons.

======================================================================
3. TIME REPRESENTATIONS
======================================================================

Implement two simulation modes.

3.1 Exact continuous-time reference

Use IEEE 754 double precision timestamps without explicit quantization.

Events are ordered by their exact timestamps. Exact timestamp equality should be extremely rare for continuous distributions, but deterministic secondary ordering must still exist for reproducibility.

The exact simulation is the reference result for each workload.

3.2 Quantized-time simulation

Map every event timestamp to an integer tick.

Default quantizer:

    tick(t, Δ) = floor(t / Δ)

Represent the quantized simulation clock internally as an integer tick. Do not use floating-point timestamp equality to detect ties.

The displayed time is:

    t_quantized = tick × Δ

Support these quantizers:

- floor;
- nearest;
- ceiling.

The primary experiment uses floor quantization. Nearest and ceiling are robustness checks.

When a service begins at tick q, schedule its completion from the quantized current time:

    t_completion_raw = q × Δ + service_requirement
    q_completion = quantize(t_completion_raw, Δ)

This models a simulator whose event clock itself has finite resolution.

Prevent invalid backward scheduling. A newly scheduled event must never have a tick smaller than the current tick.

Allow same-tick service completions. These are legitimate and must be processed according to the selected event-ordering policy. Protect the engine from infinite same-tick loops through explicit invariants and maximum-event guards.

======================================================================
4. EQUAL-TIMESTAMP ORDERING POLICIES
======================================================================

Implement at least these policies:

1. departure_first

   Service completions have higher priority than arrivals at an equal tick.

2. arrival_first

   Arrivals have higher priority than service completions at an equal tick.

3. insertion_order

   Events at the same tick are processed in the order in which they were inserted into the event queue.

4. random_order

   Events at the same tick receive deterministic pseudorandom priorities derived from a dedicated tie-breaking seed.

5. exact_within_tick

   Events at the same quantized tick are ordered by their unquantized raw timestamps. This is an oracle-like diagnostic policy showing how much information was lost by quantization.

All policies must use deterministic fallback ordering by unique event sequence number.

For random_order, separate the workload seed from the tie-breaking seed. This allows repeated random tie-order simulations on one unchanged workload.

Do not assume that arrival_first must always produce greater total loss in every finite run. Report the observed direction and magnitude. Only handcrafted unit tests may enforce the expected result for specifically constructed collision cases.

======================================================================
5. SIMULATION ENGINE
======================================================================

Use an efficient event-driven engine.

A priority queue is acceptable, but do not build a needlessly generic simulation framework. The primary model only needs arrival and departure events.

Each queue event must include:

- quantized tick or exact timestamp;
- raw unquantized timestamp where applicable;
- event type;
- job ID;
- insertion sequence;
- policy priority;
- optional random tie priority.

The engine must support:

- exact simulation;
- quantized simulation;
- warm-up period;
- fixed number of measured arrivals;
- optional fixed simulation horizon;
- deterministic event logging for small diagnostic runs;
- disabled event logging for production campaigns;
- collection of time-integrated occupancy statistics;
- interruption-safe experiment execution.

Use a clear state model:

- current simulation time or tick;
- number of jobs in the system;
- waiting FIFO queue;
- currently serviced job;
- accepted arrivals;
- dropped arrivals;
- completed jobs;
- accumulated queue occupancy area;
- accumulated system occupancy area;
- per-job waiting and sojourn times.

The waiting discipline is FIFO.

For every state transition, enforce:

    0 <= jobs_in_system <= K
    completed_jobs <= accepted_jobs
    dropped_jobs + accepted_jobs = measured_arrivals
    no job may depart before it arrives
    no accepted job may be started twice
    no completed job may remain in the queue

Add explicit runtime checks in debug mode. Production mode may disable expensive checks but must retain low-cost sanity checks.

======================================================================
6. WARM-UP AND MEASUREMENT
======================================================================

Each replication must have two stages:

1. Warm-up stage.
2. Measurement stage.

Default warm-up:

    5,000 arrivals

Default measured stage:

    50,000 arrivals

Both values must be configurable.

Do not reset the queue state after warm-up. Reset only the metric accumulators.

At the exact boundary between warm-up and measurement:

- preserve current jobs and pending events;
- reset accepted, dropped, completed, collision, occupancy, waiting-time, and throughput measurement counters;
- handle jobs that arrived during warm-up but depart during measurement consistently.

For primary packet-loss calculations, count only arrivals occurring during the measurement stage.

For waiting and sojourn statistics, define and document whether a job is included based on arrival time or completion time. Prefer arrival-time inclusion: a job contributes to waiting and sojourn statistics if its arrival occurred during the measurement stage and it eventually completed.

If the simulation ends before every measured accepted job completes, either drain the system after stopping arrivals or explicitly mark censored jobs. Prefer draining after the final measured arrival while excluding the drain period from arrival-rate calculations.

======================================================================
7. COLLISION METRICS
======================================================================

Implement precise collision diagnostics.

7.1 Event collision

A timestamp collision occurs when two or more events are processed at the same quantized tick.

Record:

- number of ticks containing multiple events;
- total number of events participating in collisions;
- fraction of all events participating in collisions;
- mean number of events per collided tick;
- maximum number of events at one tick.

7.2 Mixed collision

A collided tick is mixed if it contains at least one arrival and at least one departure.

Record:

- number of mixed collided ticks;
- number of arrivals in mixed collisions;
- number of departures in mixed collisions;
- mixed-collision rate per measured arrival.

7.3 Critical collision opportunity

A critical collision opportunity is a mixed arrival–departure collision for which event ordering can affect whether at least one arrival is accepted.

At minimum, detect the canonical case:

- system occupancy immediately before processing the tied events equals K;
- at least one arrival and one departure are available at the same tick.

Also implement a shadow batch evaluator.

Before mutating the real state at a collided tick:

- copy the occupancy-relevant batch state;
- evaluate the batch under arrival_first;
- evaluate the same batch under departure_first;
- compare how many arrivals would be accepted and dropped;
- record the absolute difference.

Define:

    critical_acceptance_difference

as the number of arrival decisions that differ between the two shadow evaluations.

This metric is policy-neutral because it is computed before applying the real policy.

Record:

- critical collided ticks;
- total critical acceptance difference;
- critical acceptance difference per measured arrival;
- fraction of mixed collisions that are critical.

The shadow evaluator must not alter the actual simulation state or random-number state.

For complex same-tick chains in which newly accepted jobs produce same-tick departures, clearly document whether the shadow evaluator includes recursively generated events. Implement both if feasible:

- static_batch_criticality: only events already pending at batch start;
- recursive_batch_criticality: include same-tick events generated while evaluating the batch.

Use static_batch_criticality as the primary metric unless testing shows recursive evaluation is necessary.

======================================================================
8. OUTPUT METRICS
======================================================================

Produce one summary row for every unique combination of:

- campaign;
- replication;
- workload seed;
- tie seed;
- ρ;
- λ;
- μ;
- K;
- Δ;
- normalized resolution δ;
- quantizer;
- ordering policy;
- warm-up arrivals;
- measured arrivals.

Required metrics:

Traffic and queue metrics:

- measured arrivals;
- accepted arrivals;
- dropped arrivals;
- completed measured jobs;
- packet-loss probability;
- acceptance probability;
- throughput;
- mean waiting time;
- median waiting time;
- 95th percentile waiting time;
- 99th percentile waiting time;
- mean sojourn time;
- median sojourn time;
- 95th percentile sojourn time;
- time-average number in queue;
- time-average number in system;
- maximum queue length;
- fraction of measured time at full capacity;
- fraction of measured time idle.

Collision metrics:

- collided ticks;
- collision-event count;
- collision-event fraction;
- mixed collided ticks;
- mixed-collision rate;
- critical collided ticks;
- critical acceptance difference;
- critical acceptance difference rate;
- maximum batch size.

Accuracy metrics relative to the exact simulation using the same workload:

- absolute packet-loss error;
- relative packet-loss error;
- signed packet-loss error;
- absolute throughput error;
- relative throughput error;
- absolute mean-waiting-time error;
- relative mean-waiting-time error;
- occupancy trajectory error if trajectory sampling is enabled.

Performance and provenance:

- simulation runtime;
- number of processed events;
- engine version;
- git commit;
- Python version;
- platform;
- root seed;
- workload seed;
- tie seed.

When the reference value is zero, relative error must be recorded as null rather than infinity.

Save all unrounded numeric values. Rounding belongs only in presentation tables.

======================================================================
9. THEORETICAL REFERENCE
======================================================================

For the exact M/M/1/K queue, calculate the stationary full-state probability:

For ρ != 1:

    π_K = ((1 - ρ) × ρ^K) / (1 - ρ^(K + 1))

For ρ = 1:

    π_K = 1 / (K + 1)

For an M/M/1/K queue, the theoretical packet-loss probability is π_K.

Also calculate theoretical effective throughput:

    λ_eff = λ × (1 - π_K)

Use these values to validate the exact simulation engine.

Generate validation tables showing:

- simulated exact packet-loss probability;
- theoretical packet-loss probability;
- absolute difference;
- relative difference;
- confidence interval;
- simulated effective throughput;
- theoretical effective throughput.

Do not compare quantized simulations directly against the stationary formula as if they remained exact M/M/1/K systems. Their event semantics have been changed.

======================================================================
10. EXPERIMENT CAMPAIGNS
======================================================================

Implement campaigns as YAML configuration files.

Provide at least:

    configs/smoke.yaml
    configs/pilot.yaml
    configs/full.yaml
    configs/validation.yaml
    configs/random_order.yaml
    configs/robustness.yaml

----------------------------------------------------------------------
E0. ENGINE VALIDATION
----------------------------------------------------------------------

Purpose:

- verify correctness of the exact queue simulation;
- verify tie-handling semantics using deterministic handcrafted traces;
- verify reproducibility.

Validation grid:

    ρ = [0.5, 0.8, 0.95, 1.0, 1.1]
    K = [1, 4, 8, 16]
    replications >= 20
    measured arrivals >= 200,000 for final validation

Compare exact simulation loss and throughput against M/M/1/K theory.

Required deterministic trace tests:

Case A:
- K = 1;
- system full;
- one departure and one arrival share the same tick.

Expected:
- departure_first accepts the arrival;
- arrival_first drops the arrival.

Case B:
- system not full;
- one departure and one arrival share the same tick.

Expected:
- both policies accept the arrival;
- no critical acceptance difference.

Case C:
- multiple arrivals and one departure at a full system.

Verify exact accepted counts for every policy.

Case D:
- same-tick zero-duration or sub-quantum service completion.

Verify that the engine terminates and preserves state invariants.

Case E:
- Δ disabled or exact mode.

Verify that ordering policy does not affect results except for true exact ties deliberately inserted into the trace.

----------------------------------------------------------------------
E1. COLLISION SCALING
----------------------------------------------------------------------

Purpose:

Test whether collision frequency grows approximately linearly with Δ for sufficiently fine resolution.

Primary grid:

    ρ = [0.8, 1.0, 1.1]
    K = [8]
    δ = [
        0.00001,
        0.00003,
        0.0001,
        0.0003,
        0.001,
        0.003,
        0.01,
        0.03,
        0.1
    ]
    quantizer = floor
    policies = [departure_first, arrival_first]
    replications = 30 or more

Fit a log-log model over the fine-resolution region:

    log(collision_rate) = a + b × log(δ)

Estimate b and its confidence interval.

Expected hypothesis:

    b approximately equals 1

Do not force the fitting range. Implement an explicit configurable maximum δ for the “fine-resolution” regression and report sensitivity to that choice.

Generate:

- collision rate versus δ;
- mixed-collision rate versus δ;
- critical-collision rate versus δ;
- fitted scaling exponent table.

----------------------------------------------------------------------
E2. POLICY-SENSITIVITY MAP
----------------------------------------------------------------------

Purpose:

Measure where tie-breaking policy materially affects reported queue metrics.

Primary grid:

    ρ = [0.5, 0.8, 0.95, 1.0, 1.1, 1.25]
    K = [4, 8, 16, 32]
    δ = [0.0001, 0.001, 0.01, 0.03, 0.1]
    quantizer = floor
    policies = [
        departure_first,
        arrival_first,
        insertion_order,
        exact_within_tick
    ]
    replications = 20 or more

Run one exact reference simulation for every workload replication.

Use paired comparisons. For each replication and parameter combination, compute:

    loss_gap_AF_DF =
        loss_probability_arrival_first
        - loss_probability_departure_first

    absolute_policy_range =
        max(loss_probability across policies)
        - min(loss_probability across policies)

    relative_policy_range =
        absolute_policy_range / exact_reference_loss

Also calculate policy ranges for throughput and waiting-time metrics.

Generate sensitivity maps over:

    (ρ, δ) for every K
    (K, δ) for selected ρ
    (ρ, K) for selected δ

Use heatmaps saved as static images. The final paper plots should remain readable in grayscale.

Identify configurations where:

- relative packet-loss error exceeds 5%;
- relative packet-loss error exceeds 10%;
- relative packet-loss error exceeds 25%;
- deterministic policy range exceeds the exact reference loss itself.

Do not conceal configurations in which relative error is undefined because the reference loss is zero or too close to zero. Report absolute errors alongside relative errors.

----------------------------------------------------------------------
E3. CRITICAL-COLLISION PREDICTOR
----------------------------------------------------------------------

Purpose:

Test whether critical collisions predict policy-induced packet-loss differences better than total collisions.

Use data from E2.

Fit and compare these models:

Model A:
    |loss_gap_AF_DF| ~ total_collision_rate

Model B:
    |loss_gap_AF_DF| ~ mixed_collision_rate

Model C:
    |loss_gap_AF_DF| ~ critical_acceptance_difference_rate

Model D:
    |loss_gap_AF_DF| ~
        critical_acceptance_difference_rate
        + ρ
        + 1/K
        + δ

Report:

- coefficient estimates;
- standard errors or bootstrap confidence intervals;
- R²;
- adjusted R²;
- RMSE;
- leave-one-configuration-out or grouped cross-validation error.

Do not randomly split individual replications across train and test if they belong to the same parameter configuration. Group by configuration to avoid leakage.

Primary expected result:

Critical acceptance difference should explain substantially more variance than total collision frequency.

Also test the simple approximation:

    |loss_gap_AF_DF|
        approximately equals
    critical_acceptance_difference_rate

Fit:

    y = a + b × x

Report whether:

    a is near zero
    b is near one

Do not describe this approximation as confirmed unless the data support it.

----------------------------------------------------------------------
E4. RANDOM TIE-BREAKING VARIANCE
----------------------------------------------------------------------

Purpose:

Separate workload randomness from randomness introduced purely by tie ordering.

Choose at least three configurations:

1. Low-sensitivity case.
2. Medium-sensitivity case.
3. High-sensitivity case selected from E2.

For each selected workload:

- hold arrival times and service requirements fixed;
- perform at least 100 random_order runs;
- vary only the tie-breaking seed.

Compare the random-order distribution with:

- arrival_first result;
- departure_first result;
- arithmetic midpoint of the two deterministic policies;
- exact reference result.

Measure:

- mean;
- standard deviation;
- median;
- 5th and 95th percentiles;
- bias relative to the deterministic midpoint;
- bias relative to the exact reference;
- variance attributable solely to tie ordering.

Generate:

- histogram or empirical cumulative distribution of packet loss;
- box plots for selected configurations;
- table of random-order variance.

----------------------------------------------------------------------
E5. QUANTIZER ROBUSTNESS
----------------------------------------------------------------------

Purpose:

Determine whether conclusions depend on the exact quantization rule.

Reduced grid:

    ρ = [0.8, 1.0, 1.1]
    K = [4, 8, 16]
    δ = [0.001, 0.01, 0.1]
    quantizers = [floor, nearest, ceiling]
    policies = [departure_first, arrival_first]
    replications >= 20

Compare:

- collision rates;
- critical-collision rates;
- packet-loss policy gap;
- signed bias relative to exact simulation.

Check whether floor and ceiling produce systematic biases in opposite directions.

----------------------------------------------------------------------
E6. DISTRIBUTIONAL ROBUSTNESS
----------------------------------------------------------------------

Make the engine support additional arrival and service distributions.

At minimum:

Arrival distributions:
- exponential;
- Erlang with configurable shape;
- deterministic;
- lognormal interarrival times with configurable coefficient of variation.

Service distributions:
- exponential;
- deterministic;
- Erlang;
- lognormal with configurable coefficient of variation.

All distributions must be normalized to the requested mean.

Use a small robustness campaign with equal mean arrival and service rates but different variability.

Suggested cases:

A. M/M/1/K:
   exponential arrivals, exponential service.

B. M/D/1/K:
   exponential arrivals, deterministic service.

C. D/M/1/K:
   deterministic arrivals, exponential service.

D. Bursty case:
   lognormal arrivals and lognormal service.

Purpose:

Determine whether collision sensitivity is primarily driven by mean load or is strongly changed by variability and synchronization.

This experiment is secondary. Do not let it delay implementation of E0–E4.

======================================================================
11. STATISTICAL ANALYSIS
======================================================================

Use paired analysis wherever policies share a workload.

For each configuration, report:

- sample mean;
- sample standard deviation;
- standard error;
- 95% confidence interval;
- median;
- interquartile range.

Use paired bootstrap confidence intervals for policy differences.

Bootstrap requirements:

- deterministic seed;
- at least 10,000 resamples for final reports;
- resample replication pairs, not individual event observations;
- save bootstrap configuration in metadata.

Avoid excessive null-hypothesis testing. Prioritize:

- effect sizes;
- confidence intervals;
- regression quality;
- practical thresholds.

When conducting hypothesis tests, correct for multiple comparisons or clearly label exploratory results.

For random-order analysis, use nested variance decomposition if practical:

- between-workload variance;
- within-workload tie-order variance.

======================================================================
12. FIGURES
======================================================================

Use matplotlib only.

Do not use seaborn.

Every chart must be generated from saved result tables, not directly from transient in-memory simulation objects.

Produce each chart as a separate figure. Do not use subplot grids unless a figure is explicitly designed as a multi-panel publication figure.

Save figures as:

- PNG at 300 dpi;
- SVG;
- PDF where practical.

Do not hard-code decorative colors. Use default matplotlib styling unless grayscale-safe differentiation requires markers, line styles, or hatching.

All labels must be available in both English and Russian through a plotting-language configuration.

Required plots:

1. Packet-loss probability versus δ by policy.
2. Signed packet-loss error versus δ.
3. Policy gap arrival_first minus departure_first versus δ.
4. Collision rate versus δ on log-log axes.
5. Critical-collision rate versus δ.
6. Policy sensitivity heatmap over ρ and δ.
7. Policy sensitivity heatmap over K and δ.
8. Scatter plot:
       total collision rate
       versus policy loss gap.
9. Scatter plot:
       critical acceptance difference rate
       versus policy loss gap.
10. Regression prediction versus observed policy gap.
11. Random-order loss distribution for selected workloads.
12. Exact simulation versus M/M/1/K theoretical loss.
13. Runtime versus number of processed events.
14. Relative error threshold map.

Every figure must have:

- title;
- axis labels;
- units;
- legend when needed;
- parameter values in title or caption metadata;
- deterministic output filename.

Write a manifest:

    results/<run_id>/figures/manifest.csv

with:

- filename;
- figure ID;
- source dataset;
- filtering conditions;
- plotting function;
- language;
- creation timestamp.

======================================================================
13. TABLES
======================================================================

Generate machine-readable CSV files and publication-ready Markdown tables.

Required tables:

1. Simulation parameter grid.
2. Exact-engine theoretical validation.
3. Collision scaling regression.
4. Mean packet loss by policy, ρ, K, and δ.
5. Paired arrival-first versus departure-first differences.
6. Configurations with largest absolute policy sensitivity.
7. Configurations with largest relative policy sensitivity.
8. Predictor-model comparison.
9. Random-order variance.
10. Quantizer robustness.
11. Distributional robustness.
12. Runtime and resource summary.

Do not manually copy values into report templates. Generate tables programmatically.

======================================================================
14. REPOSITORY STRUCTURE
======================================================================

Use this general structure:

juncture/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── configs/
│   ├── smoke.yaml
│   ├── pilot.yaml
│   ├── full.yaml
│   ├── validation.yaml
│   ├── random_order.yaml
│   └── robustness.yaml
├── src/
│   └── juncture/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── seeds.py
│       ├── distributions.py
│       ├── workload.py
│       ├── events.py
│       ├── policies.py
│       ├── quantization.py
│       ├── state.py
│       ├── simulator.py
│       ├── exact_simulator.py
│       ├── metrics.py
│       ├── collisions.py
│       ├── theory.py
│       ├── campaign.py
│       ├── storage.py
│       ├── analysis.py
│       ├── regression.py
│       ├── bootstrap.py
│       ├── plots.py
│       ├── tables.py
│       ├── report.py
│       └── provenance.py
├── tests/
│   ├── test_quantization.py
│   ├── test_policies.py
│   ├── test_handcrafted_traces.py
│   ├── test_exact_theory.py
│   ├── test_state_invariants.py
│   ├── test_reproducibility.py
│   ├── test_collision_metrics.py
│   ├── test_campaign_resume.py
│   └── test_cli.py
├── scripts/
│   ├── run_smoke.py
│   ├── run_full.py
│   └── build_report.py
├── docs/
│   ├── methodology.md
│   ├── metric_definitions.md
│   ├── experiment_plan.md
│   └── result_interpretation.md
└── results/
    └── .gitkeep

Do not commit generated production results unless explicitly requested.

======================================================================
15. DEPENDENCIES
======================================================================

Prefer a compact dependency set:

- Python 3.11 or newer;
- numpy;
- pandas;
- scipy;
- matplotlib;
- pyarrow;
- pyyaml;
- statsmodels;
- tqdm;
- pytest;
- ruff;
- mypy.

Optional:

- numba, but only if profiling proves the simulation engine is too slow.

The codebase must work without numba.

Do not introduce a database, web interface, notebook dependency, distributed framework, or workflow engine unless clearly necessary.

Notebooks may be added for exploration but must not be the only way to reproduce analyses.

======================================================================
16. COMMAND-LINE INTERFACE
======================================================================

Provide a console command named:

    juncture

Required commands:

    juncture validate
    juncture run --config configs/smoke.yaml
    juncture run --config configs/full.yaml
    juncture resume --run-dir results/<run_id>
    juncture status --run-dir results/<run_id>
    juncture analyze --run-dir results/<run_id>
    juncture plot --run-dir results/<run_id> --language en
    juncture plot --run-dir results/<run_id> --language ru
    juncture tables --run-dir results/<run_id>
    juncture report --run-dir results/<run_id>
    juncture inspect-trace --trace <path>

The run command must:

- validate the configuration;
- create a unique run directory;
- save the resolved configuration;
- save environment and provenance metadata;
- generate a deterministic task manifest;
- execute unfinished tasks;
- write results atomically;
- support safe interruption;
- allow later resume.

Provide:

    --workers N

for process-level parallelism.

Parallel execution must not alter numerical results.

Each task must have a deterministic task ID derived from its complete parameter set.

======================================================================
17. RANDOM SEEDS
======================================================================

Use the project root seed:

    0x4A554E4354555245

This hexadecimal value encodes “JUNCTURE”.

Use numpy.random.SeedSequence or an equivalent stable mechanism.

Derive child seeds from:

- campaign name;
- replication index;
- ρ;
- K;
- Δ;
- quantizer;
- distribution configuration;
- workload role;
- tie-order role.

Do not use Python’s built-in hash() because it is not stable across interpreter processes.

Save every derived seed in the result rows.

Workload generation and tie-order generation must use separate random-number generators.

Running with one worker and multiple workers must produce byte-for-byte equivalent summary tables after deterministic sorting.

======================================================================
18. RESULT STORAGE
======================================================================

Each run directory must contain:

results/<run_id>/
├── config.resolved.yaml
├── provenance.json
├── environment.txt
├── task_manifest.parquet
├── task_status.parquet
├── raw/
│   ├── exact_results.parquet
│   └── quantized_results.parquet
├── derived/
│   ├── paired_differences.parquet
│   ├── configuration_summary.parquet
│   ├── regression_results.csv
│   └── threshold_results.csv
├── figures/
├── tables/
├── logs/
└── report/
    ├── summary.md
    ├── validation.md
    ├── findings.md
    └── limitations.md

Write task results atomically:

1. Write to a temporary file.
2. Flush and close.
3. Rename to the final path.

Do not leave partially written result rows marked as complete.

Use Parquet for primary numeric data and CSV for final exchange tables.

======================================================================
19. PERFORMANCE
======================================================================

Correctness comes first, but the full campaign must remain practical.

Profile the simulator using the pilot campaign.

Targets:

- no storage of full event traces during production runs;
- O(number of events) simulation time;
- bounded memory use independent of total event count, except for pre-generated workload arrays;
- optional chunked workload generation if arrays become too large;
- efficient percentile calculation without storing unnecessary warm-up observations.

If full waiting-time arrays are retained, store only measured jobs.

Add a benchmark command or script reporting:

- events processed per second;
- memory usage;
- runtime by policy;
- runtime by configuration.

Do not optimize by changing scientific semantics.

======================================================================
20. TESTING
======================================================================

Use pytest.

Minimum required test coverage:

- quantizer boundary behavior;
- no negative ticks;
- deterministic event priority;
- handcrafted arrival/departure collision cases;
- multiple-event same-tick batches;
- same-tick recursively scheduled departures;
- exact reference reproducibility;
- random-order reproducibility for a fixed tie seed;
- different random-order results for different tie seeds in a collision-rich trace;
- queue-capacity invariants;
- no duplicate job completion;
- theoretical M/M/1/K convergence;
- warm-up metric reset;
- drain-stage handling;
- critical-collision shadow evaluation;
- result serialization;
- campaign resume after simulated interruption;
- deterministic output across worker counts.

Use small deterministic traces for semantic tests and stochastic tests with loose but meaningful tolerances for theory validation.

Do not make stochastic tests flaky. Fix seeds and use sufficiently large samples.

======================================================================
21. DOCUMENTATION
======================================================================

README.md must explain:

- the research question;
- why equal-timestamp event ordering matters;
- the queue model;
- how timestamp quantization works;
- ordering policies;
- installation;
- smoke run;
- full campaign;
- resuming interrupted runs;
- analysis and plot generation;
- result directory structure;
- reproducibility guarantees.

docs/methodology.md must formally define:

- M/M/1/K model;
- capacity convention;
- timestamp quantizer;
- ordering policies;
- warm-up procedure;
- measurement procedure;
- collision metrics;
- critical collision opportunity;
- exact reference;
- theoretical stationary loss;
- paired experimental design.

docs/metric_definitions.md must provide every output column with:

- name;
- type;
- unit;
- formula;
- interpretation;
- missing-value behavior.

docs/result_interpretation.md must explicitly warn about:

- high relative error when exact packet loss is near zero;
- survivor bias in waiting-time measurements;
- random-order variance;
- dependence on capacity convention;
- distinction between process-level timestamp quantization and physical network timing;
- limitations of one queueing model;
- the difference between process crashes and power-loss durability, which is unrelated to this project.

======================================================================
22. AUTOMATIC REPORT
======================================================================

Generate a concise Markdown research report from the completed run.

The report must contain:

1. Objective.
2. Model and experimental design.
3. Validation against M/M/1/K theory.
4. Collision-scaling results.
5. Policy-sensitivity results.
6. Critical-collision predictor results.
7. Random-order variance.
8. Robustness checks.
9. Main quantitative findings.
10. Limitations.
11. Reproduction command.

The report must insert actual measured values.

Examples of acceptable generated statements:

- “At ρ = ..., K = ..., and δ = ..., the mean packet-loss estimates differed by ... percentage points.”
- “The critical-collision metric explained ...% of the variance in the paired policy difference.”
- “The fitted fine-resolution collision-scaling exponent was ... with a 95% confidence interval of [..., ...].”

Examples of forbidden generated statements:

- “The hypothesis was confirmed” without a defined criterion.
- “The effect was significant” without a reported effect size or statistical procedure.
- Any number not traceable to a saved dataset.

Add a machine-readable findings file:

    report/findings.json

Each finding must include:

- finding ID;
- text;
- source table;
- source columns;
- filtering conditions;
- numeric values;
- uncertainty interval where applicable.

======================================================================
23. IMPLEMENTATION ORDER
======================================================================

Work in the following stages.

Stage 1: Skeleton

- Create repository structure.
- Configure pyproject.toml.
- Add CLI skeleton.
- Add linting, typing, and test configuration.
- Write initial README.

Stage 2: Core semantics

- Implement quantizers.
- Implement events and policies.
- Implement workload generation.
- Implement exact queue simulator.
- Implement quantized queue simulator.
- Implement handcrafted trace mode.
- Add state-invariant tests.

Stage 3: Metrics and validation

- Implement all queue metrics.
- Implement collision diagnostics.
- Implement shadow criticality evaluation.
- Implement theoretical M/M/1/K calculations.
- Complete E0 validation.

Do not continue to large campaigns until E0 passes.

Stage 4: Campaign system

- Implement YAML configuration.
- Implement task manifests.
- Implement deterministic seeds.
- Implement parallel execution.
- Implement atomic result writing.
- Implement resume and status commands.

Stage 5: Pilot campaign

- Run smoke campaign.
- Run pilot campaign.
- Profile runtime.
- Inspect event traces for selected collision cases.
- Verify paired result joins.
- Verify that exact references are reused rather than redundantly rerun.

Stage 6: Analysis

- Implement summaries.
- Implement paired bootstrap.
- Implement scaling regression.
- Implement predictor regressions.
- Implement threshold analysis.
- Implement random-order variance analysis.

Stage 7: Presentation

- Generate all figures.
- Generate tables.
- Generate English and Russian labels.
- Generate automatic report.
- Add figure and table manifests.

Stage 8: Full verification

- Run complete test suite.
- Run linting.
- Run type checking.
- Run deterministic single-worker versus multi-worker comparison.
- Run full validation campaign.
- Document any deviations from the original plan.

======================================================================
24. ACCEPTANCE CRITERIA
======================================================================

The project is complete only when all of the following are true:

- Exact simulation agrees with M/M/1/K theory within documented Monte Carlo uncertainty.
- Handcrafted tie cases produce the expected policy-dependent outcomes.
- Every production result is reproducible from saved configuration and seeds.
- Workload randomness is separated from tie-order randomness.
- Parallel execution does not change results.
- Interrupted campaigns can resume without duplicating completed tasks.
- Collision and critical-collision metrics are independently tested.
- Exact and quantized results are joined using workload identity, not approximate floating-point keys.
- All requested campaigns have valid configuration files.
- All tables and plots are generated from saved results.
- The automatic report contains no fabricated placeholder numbers.
- The smoke campaign completes successfully on an ordinary desktop computer.
- The codebase passes pytest, ruff, and mypy.
- The README contains a complete reproduction procedure.

======================================================================
25. SCIENTIFIC CAUTION
======================================================================

Do not design the software to force the expected narrative.

In particular:

- Do not clamp negative or unexpected policy gaps to zero.
- Do not silently remove outliers.
- Do not select only parameter combinations supporting the hypotheses.
- Do not choose regression ranges after looking at the result without reporting the selection rule.
- Do not treat relative error as meaningful when the denominator is effectively zero.
- Do not conflate timestamp collision frequency with critical collision frequency.
- Do not interpret lower waiting time as automatically better if it results from dropping more jobs.
- Do not claim generality beyond finite-capacity queue simulations without evidence.
- Do not hide null or contradictory results.

Unexpected results should be preserved, investigated, and documented.

======================================================================
26. FINAL DELIVERABLE
======================================================================

Return a complete repository containing:

- working simulation engine;
- exact and quantized queue models;
- deterministic workload generation;
- five event-ordering policies;
- all collision diagnostics;
- theory validation;
- campaign runner;
- resumable multiprocessing;
- statistical analysis;
- plots;
- tables;
- automatic reports;
- tests;
- documentation;
- smoke, pilot, and full experiment configurations.

At the end, provide a concise completion summary containing:

- repository tree;
- implemented commands;
- tests executed;
- validation results;
- smoke-campaign runtime;
- known limitations;
- exact command required to launch the full experiment campaign.

Do not run the full campaign unless explicitly instructed. Run only unit tests, validation-scale checks, and the smoke campaign during implementation.