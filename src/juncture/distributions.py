"""Mean-normalized interarrival and service distributions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

DistributionName = Literal["exponential", "deterministic", "erlang", "lognormal"]


@dataclass(frozen=True)
class DistributionSpec:
    name: DistributionName = "exponential"
    shape: int = 2
    cv: float = 1.0


def sample_positive(
    rng: np.random.Generator, mean: float, size: int, spec: DistributionSpec
) -> np.ndarray:
    if mean <= 0 or size < 0:
        raise ValueError("mean must be positive and size non-negative")
    if spec.name == "exponential":
        values = rng.exponential(mean, size)
    elif spec.name == "deterministic":
        values = np.full(size, mean)
    elif spec.name == "erlang":
        if spec.shape < 1:
            raise ValueError("Erlang shape must be >= 1")
        values = rng.gamma(spec.shape, mean / spec.shape, size)
    elif spec.name == "lognormal":
        if spec.cv <= 0:
            raise ValueError("lognormal cv must be positive")
        sigma2 = np.log1p(spec.cv**2)
        values = rng.lognormal(np.log(mean) - sigma2 / 2, np.sqrt(sigma2), size)
    else:  # pragma: no cover - type system protects this
        raise ValueError(f"unsupported distribution {spec.name}")
    return np.asarray(values, dtype=float)
