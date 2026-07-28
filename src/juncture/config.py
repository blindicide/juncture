"""YAML campaign configuration parsing and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from .distributions import DistributionName, DistributionSpec
from .policies import OrderingPolicy


@dataclass(frozen=True)
class CampaignConfig:
    name: str
    loads: list[float]
    capacities: list[int]
    deltas: list[float]
    policies: list[OrderingPolicy]
    quantizers: list[str] = field(default_factory=lambda: ["floor"])
    replications: int = 1
    warmup_arrivals: int = 500
    measured_arrivals: int = 5_000
    service_rate: float = 1.0
    root_seed: int = 0x4A554E4354555245
    arrival_distribution: DistributionSpec = field(default_factory=DistributionSpec)
    service_distribution: DistributionSpec = field(default_factory=DistributionSpec)
    fine_delta_max: float = 0.003
    tie_repetitions: int = 1
    schema_version: int = 1
    arrival_scheduling_modes: list[str] = field(default_factory=lambda: ["preload_all"])

    def validate(self) -> None:
        if not self.name:
            raise ValueError("campaign name is required")
        if not self.loads or any(x <= 0 for x in self.loads):
            raise ValueError("loads must be non-empty and positive")
        if not self.capacities or any(x < 1 for x in self.capacities):
            raise ValueError("capacities must be positive")
        if not self.deltas or any(x <= 0 for x in self.deltas):
            raise ValueError("deltas must be non-empty and positive")
        if (
            self.replications < 1
            or self.warmup_arrivals < 0
            or self.measured_arrivals < 1
            or self.tie_repetitions < 1
        ):
            raise ValueError("invalid replication or arrival counts")
        allowed = {
            "departure_first",
            "arrival_first",
            "insertion_order",
            "random_order",
            "exact_within_tick",
        }
        if not set(self.policies) <= allowed:
            raise ValueError("unknown ordering policy")
        if not set(self.quantizers) <= {"floor", "nearest", "ceiling"}:
            raise ValueError("unknown quantizer")
        if self.schema_version not in {1, 2}:
            raise ValueError("schema_version must be 1 or 2")
        allowed_scheduling = {
            "preload_all",
            "schedule_next_after_transition",
            "schedule_next_before_transition",
        }
        if not self.arrival_scheduling_modes or not set(self.arrival_scheduling_modes) <= allowed_scheduling:
            raise ValueError("unknown arrival scheduling mode")

    def resolved(self) -> dict[str, Any]:
        return asdict(self)


def _distribution(value: Any) -> DistributionSpec:
    if value is None:
        return DistributionSpec()
    if isinstance(value, str):
        return DistributionSpec(name=cast(DistributionName, value))
    return DistributionSpec(**value)


def load_config(path: str | Path) -> CampaignConfig:
    with Path(path).open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    config = CampaignConfig(
        name=raw.get("name", Path(path).stem),
        loads=list(raw.get("loads", [])),
        capacities=list(raw.get("capacities", [])),
        deltas=list(raw.get("deltas", [])),
        policies=list(raw.get("policies", ["departure_first", "arrival_first"])),
        quantizers=list(raw.get("quantizers", ["floor"])),
        replications=int(raw.get("replications", 1)),
        warmup_arrivals=int(raw.get("warmup_arrivals", 500)),
        measured_arrivals=int(raw.get("measured_arrivals", 5_000)),
        service_rate=float(raw.get("service_rate", 1.0)),
        root_seed=int(raw.get("root_seed", 0x4A554E4354555245)),
        arrival_distribution=_distribution(raw.get("arrival_distribution")),
        service_distribution=_distribution(raw.get("service_distribution")),
        fine_delta_max=float(raw.get("fine_delta_max", 0.003)),
        tie_repetitions=int(raw.get("tie_repetitions", 1)),
        schema_version=int(raw.get("schema_version", 1)),
        arrival_scheduling_modes=list(raw.get("arrival_scheduling_modes", ["preload_all"])),
    )
    config.validate()
    return config
