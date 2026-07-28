# Juncture research report

## Objective

Measure how finite timestamp resolution and equal-timestamp ordering affect a finite FIFO queue.

## Model and design

Each policy shares pre-generated arrival and service workloads with its exact reference.

## Validation against M/M/1/K theory

- The largest exact-theory absolute packet-loss difference was 0.00149253 at ρ=1.0, K=16.
## Main quantitative findings

- The mean fitted collision-scaling exponent across available configurations was 0.978.
- The largest observed policy range was 0.00688 at ρ=1.1, K=4, δ=0.1.
- The critical-collision predictor model had R²=0.721.

## Limitations

Relative errors are undefined when the exact reference is zero. Waiting metrics include accepted measured-arrival jobs and can have survivor bias. These experiments model timestamp representation, not physical network timing.

## Reproduction

`juncture analyze --run-dir results/robustness-20260728T104156Z`
