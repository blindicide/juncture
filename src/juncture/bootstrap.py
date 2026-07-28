"""Deterministic paired bootstrap confidence intervals."""

from __future__ import annotations

import numpy as np


def paired_bootstrap_ci(
    values: np.ndarray, *, seed: int = 0, resamples: int = 10_000
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if not len(values):
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = np.mean(values[rng.integers(0, len(values), size=(resamples, len(values)))], axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)
