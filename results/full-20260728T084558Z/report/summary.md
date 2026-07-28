# Juncture research report

## Objective

Measure how finite timestamp resolution and equal-timestamp ordering affect a finite FIFO queue.

## Model and design

Each policy shares pre-generated arrival and service workloads with its exact reference.

## Validation against M/M/1/K theory

- The largest exact-theory absolute packet-loss difference was 0.00168197 at ρ=1.1, K=16.
## Main quantitative findings

- The mean fitted collision-scaling exponent across available configurations was 0.984.
- The largest observed policy range was 0.00578 at ρ=1.25, K=4, δ=0.1.
- The critical-collision predictor model had R²=0.628.

## Limitations

Relative errors are undefined when the exact reference is zero. Waiting metrics include accepted measured-arrival jobs and can have survivor bias. These experiments model timestamp representation, not physical network timing.

## Reproduction

`juncture analyze --run-dir results/full-20260728T084558Z`
