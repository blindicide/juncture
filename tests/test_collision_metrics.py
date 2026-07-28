import numpy as np

from juncture.campaign import execute_run, task_manifest
from juncture.config import CampaignConfig
from juncture.simulator import simulate_quantized
from juncture.workload import Workload


def test_collision_metrics_observe_collisions() -> None:
    workload = Workload(np.array([0.1, 0.2, 1.1]), np.array([0.1, 0.1, 0.1]), 0, 1)
    result = simulate_quantized(workload, capacity=1, delta=1.0, policy="departure_first")
    assert result["collided_ticks"] >= 1


def test_measurement_window_excludes_warmup_and_post_arrival_drain() -> None:
    # The warmup tick and the drain departure cannot enter the v2 collision denominator.
    workload = Workload(np.array([0.01, 1.01]), np.array([0.01, 1.9]), 1, 9)
    result = simulate_quantized(workload, capacity=1, delta=1.0, policy="departure_first")
    assert result["measurement_processed_ticks"] == 1
    assert result["measurement_processed_events"] == 1
    assert result["collision_event_fraction"] == 0.0


def test_first_and_final_measurement_batches_are_complete() -> None:
    workload = Workload(np.array([0.1, 0.2]), np.array([0.1, 0.1]), 0, 2)
    result = simulate_quantized(workload, capacity=1, delta=1.0, policy="departure_first")
    assert result["measurement_processed_ticks"] == 1
    # Both arrivals and recursively scheduled departures are included in the final batch.
    assert result["measurement_processed_events"] == 4
    assert result["measurement_collided_events"] == 4


def test_zero_collision_and_error_invariants() -> None:
    workload = Workload(np.array([0.1, 3.1]), np.array([1.2, 1.2]), 0, 4)
    result = simulate_quantized(workload, capacity=1, delta=1.0, policy="departure_first")
    assert result["measurement_collided_events"] == 0
    assert result["collision_event_fraction"] == 0.0
    assert result["arrival_quantization_error_signed_mean"] <= 0.0


def test_v2_manifest_ids_are_deterministic_and_worker_independent(tmp_path) -> None:
    config = CampaignConfig(
        name="ids", loads=[0.8], capacities=[1], deltas=[0.1],
        policies=["arrival_first", "departure_first"], schema_version=2,
        arrival_scheduling_modes=["preload_all"], warmup_arrivals=1, measured_arrivals=8,
    )
    first = task_manifest(config)
    assert first.scenario_id.notna().all() and first.workload_id.notna().all()
    from juncture.campaign import create_run

    one = create_run(config, tmp_path)
    two = create_run(config, tmp_path)
    execute_run(one, workers=1, checkpoint_size=1)
    execute_run(two, workers=2, checkpoint_size=1)
    import pandas as pd

    left = pd.read_parquet(one / "raw" / "quantized_results.parquet").sort_values("task_id")
    right = pd.read_parquet(two / "raw" / "quantized_results.parquet").sort_values("task_id")
    assert left.packet_loss_probability.tolist() == right.packet_loss_probability.tolist()
    assert left.quantization_seed.tolist() == right.quantization_seed.tolist()
