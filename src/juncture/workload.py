"""Pre-generated common-random-number workloads."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .distributions import DistributionSpec, sample_positive


@dataclass(frozen=True)
class Workload:
    arrival_times: np.ndarray
    service_requirements: np.ndarray
    warmup_arrivals: int
    seed: int

    @property
    def total_arrivals(self) -> int:
        return len(self.arrival_times)

    @property
    def measured_arrivals(self) -> int:
        return self.total_arrivals - self.warmup_arrivals


def generate_workload(
    *,
    arrival_rate: float,
    service_rate: float,
    warmup_arrivals: int,
    measured_arrivals: int,
    seed: int,
    arrival_distribution: DistributionSpec | None = None,
    service_distribution: DistributionSpec | None = None,
) -> Workload:
    if arrival_rate <= 0 or service_rate <= 0:
        raise ValueError("rates must be positive")
    total = warmup_arrivals + measured_arrivals
    arrival_distribution = arrival_distribution or DistributionSpec()
    service_distribution = service_distribution or DistributionSpec()
    root = np.random.SeedSequence(seed)
    arrival_rng, service_rng = (np.random.default_rng(s) for s in root.spawn(2))
    interarrivals = sample_positive(arrival_rng, 1.0 / arrival_rate, total, arrival_distribution)
    return Workload(
        arrival_times=np.cumsum(interarrivals),
        service_requirements=sample_positive(
            service_rng, 1.0 / service_rate, total, service_distribution
        ),
        warmup_arrivals=warmup_arrivals,
        seed=seed,
    )
