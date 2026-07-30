"""Regression cases for the three Phase II.1 scientific blockers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from juncture.analysis_v2 import _paired
from juncture.campaign import task_manifest
from juncture.config import CampaignConfig
from juncture.metrics_v2 import collision_rates
from juncture.simulator import simulate_quantized
from juncture.workload import Workload


def _quantized_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pair_id": "quantized-a", "workload_id": "workload-a",
                "arrival_scheduling_mode": "preload_all", "policy": "arrival_first",
                "rho": 0.8, "capacity": 4, "delta": 0.01, "quantizer": "floor",
                "replication": 0, "packet_loss_probability": 0.30,
                "throughput": 0.7, "mean_waiting_time": 0.1,
                "mean_sojourn_time": 0.2, "time_average_number_in_system": 1.0,
            },
            {
                "pair_id": "quantized-a", "workload_id": "workload-a",
                "arrival_scheduling_mode": "preload_all", "policy": "departure_first",
                "rho": 0.8, "capacity": 4, "delta": 0.01, "quantizer": "floor",
                "replication": 0, "packet_loss_probability": 0.10,
                "throughput": 0.8, "mean_waiting_time": 0.05,
                "mean_sojourn_time": 0.15, "time_average_number_in_system": 0.9,
            },
        ]
    )


def _exact_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pair_id": "exact-not-quantized", "workload_id": "workload-a",
                "arrival_scheduling_mode": "preload_all", "policy": "exact",
                "packet_loss_probability": 0.15, "throughput": 0.75,
                "mean_waiting_time": 0.08, "mean_sojourn_time": 0.18,
                "time_average_number_in_system": 0.95,
            }
        ]
    )


def test_exact_reference_joins_by_workload_not_quantized_pair() -> None:
    paired = _paired(_quantized_rows(), _exact_rows())
    row = paired.iloc[0]
    assert row["exact_packet_loss"] == pytest.approx(0.15)
    assert row["policy_midpoint_loss"] == pytest.approx(0.20)
    assert row["midpoint_signed_bias"] == pytest.approx(0.05)
    assert row["midpoint_absolute_bias"] == pytest.approx(0.05)
    assert row["signed_policy_gap"] == pytest.approx(0.20)
    assert row["absolute_policy_gap"] == pytest.approx(0.20)
    assert row["ordering_half_width"] == pytest.approx(0.10)
    assert bool(row["exact_inside_deterministic_interval"])


def test_two_quantizers_share_one_exact_workload_reference() -> None:
    quantized = pd.concat([
        _quantized_rows(), _quantized_rows().assign(pair_id="quantized-b", delta=0.1, quantizer="nearest")
    ], ignore_index=True)
    paired = _paired(quantized, _exact_rows())
    assert len(paired) == 2
    assert paired.exact_packet_loss.notna().all()


def test_missing_or_duplicate_exact_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing exact"):
        _paired(_quantized_rows(), _exact_rows().assign(workload_id="other"))
    with pytest.raises(ValueError, match="duplicate exact"):
        _paired(_quantized_rows(), pd.concat([_exact_rows(), _exact_rows()]))


def test_manifest_shares_workload_id_but_not_exact_pair_id() -> None:
    manifest = task_manifest(CampaignConfig(
        name="identity", schema_version=2, loads=[0.8], capacities=[4], deltas=[0.01, 0.1],
        quantizers=["floor", "nearest"], policies=["arrival_first", "departure_first"],
    ))
    assert manifest.workload_id.nunique() == 1
    assert manifest[manifest.kind == "quantized"].groupby("pair_id").policy.nunique().eq(2).all()
    assert not set(manifest[manifest.kind == "exact"].pair_id) & set(manifest[manifest.kind == "quantized"].pair_id)


def test_recursive_incremental_measurement_boundary_is_started_once() -> None:
    workload = Workload(np.array([0.1, 0.2, 0.3]), np.array([0.1, 0.1, 0.1]), 1, 8)
    result = simulate_quantized(
        workload, capacity=4, delta=1.0, policy="departure_first",
        arrival_scheduling_mode="schedule_next_after_transition",
    )
    assert result["measurement_processed_ticks"] == 1
    assert result["accepted_arrivals"] + result["dropped_arrivals"] == 2


@pytest.mark.parametrize("policy", ["arrival_first", "departure_first", "insertion_order"])
@pytest.mark.parametrize("mode", ["preload_all", "schedule_next_after_transition"])
def test_measurement_accounting_holds_for_all_boundary_modes(policy: str, mode: str) -> None:
    workload = Workload(np.array([0.1, 0.2, 0.3]), np.array([0.1, 0.1, 0.1]), 1, 8)
    result = simulate_quantized(
        workload, capacity=1, delta=1.0, policy=policy, arrival_scheduling_mode=mode,
    )
    assert result["accepted_arrivals"] + result["dropped_arrivals"] == 2


def test_collision_rate_denominators_and_zero_handling() -> None:
    rates = collision_rates(
        measured_arrivals=100, measurement_processed_ticks=160, mixed_collided_ticks=5,
        critical_collided_ticks=3, critical_acceptance_difference=2,
    )
    assert rates == {
        "mixed_collision_rate_per_arrival": 0.05,
        "critical_collision_rate_per_arrival": 0.03,
        "critical_acceptance_difference_rate_per_arrival": 0.02,
        "mixed_collided_tick_fraction": 0.03125,
        "critical_collided_tick_fraction": 0.01875,
    }
    assert all(value is None for value in collision_rates(0, 0, 0, 0, 0).values())


def test_legacy_rate_reconstruction_from_counts() -> None:
    row = collision_rates(100, 160, 5, 3, 2, legacy=True)
    assert row["rate_reconstructed_from_counts"] is True
