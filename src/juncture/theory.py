"""Stationary M/M/1/K reference calculations."""

from __future__ import annotations

import math


def stationary_loss_probability(rho: float, capacity: int) -> float:
    if capacity < 0 or rho < 0:
        raise ValueError("rho and capacity must be non-negative")
    if math.isclose(rho, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return 1.0 / (capacity + 1)
    return ((1 - rho) * rho**capacity) / (1 - rho ** (capacity + 1))


def effective_throughput(arrival_rate: float, rho: float, capacity: int) -> float:
    return arrival_rate * (1 - stationary_loss_probability(rho, capacity))
