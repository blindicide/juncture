# Juncture research report

## Objective

Measure how finite timestamp resolution and equal-timestamp ordering affect a finite FIFO queue.

## Model and design

Each policy shares pre-generated arrival and service workloads with its exact reference.

## Main quantitative findings

- The largest observed policy range was 0.003 at ρ=0.8, K=1, δ=0.01.
- The critical-collision predictor model had R²=0.663.

## Limitations

Relative errors are undefined when the exact reference is zero. Waiting metrics include accepted measured-arrival jobs and can have survivor bias. These experiments model timestamp representation, not physical network timing.

## Reproduction

`juncture analyze --run-dir results/smoke-20260727T085225Z`
