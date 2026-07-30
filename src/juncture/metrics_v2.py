"""Schema-v2 collision-rate definitions with explicit denominators and units."""

from __future__ import annotations

from typing import Any


def _ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def collision_rates(
    measured_arrivals: int,
    measurement_processed_ticks: int,
    mixed_collided_ticks: int,
    critical_collided_ticks: int,
    critical_acceptance_difference: int,
    *,
    legacy: bool = False,
) -> dict[str, Any]:
    """Return per-arrival rates and independent observation-window tick fractions."""
    values: dict[str, Any] = {
        "mixed_collision_rate_per_arrival": _ratio(mixed_collided_ticks, measured_arrivals),
        "critical_collision_rate_per_arrival": _ratio(
            critical_collided_ticks, measured_arrivals
        ),
        "critical_acceptance_difference_rate_per_arrival": _ratio(
            critical_acceptance_difference, measured_arrivals
        ),
        "mixed_collided_tick_fraction": _ratio(
            mixed_collided_ticks, measurement_processed_ticks
        ),
        "critical_collided_tick_fraction": _ratio(
            critical_collided_ticks, measurement_processed_ticks
        ),
    }
    if legacy:
        values["rate_reconstructed_from_counts"] = bool(measured_arrivals)
    return values
