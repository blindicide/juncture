import numpy as np

from juncture.events import Event
from juncture.simulator import QueueSimulator, simulate_quantized
from juncture.workload import Workload


def test_full_system_mixed_collision_is_critical() -> None:
    batch = [Event(0, 0.0, "arrival", 1, 0), Event(0, 0.0, "departure", 0, 1)]
    assert QueueSimulator._shadow_difference(1, 1, batch) == 1


def test_non_full_mixed_collision_is_not_critical() -> None:
    batch = [Event(0, 0.0, "arrival", 1, 0), Event(0, 0.0, "departure", 0, 1)]
    assert QueueSimulator._shadow_difference(0, 1, batch) == 0


def test_multiple_arrivals_one_departure() -> None:
    batch = [Event(0, 0.0, "arrival", i, i) for i in range(3)] + [Event(0, 0.0, "departure", 9, 9)]
    assert QueueSimulator._shadow_difference(1, 1, batch) == 1


def test_explicit_policies_are_scheduler_architecture_independent() -> None:
    workload = Workload(np.array([0.1, 0.2, 1.1]), np.array([0.1, 0.7, 0.1]), 0, 7)
    for policy in ("arrival_first", "departure_first", "exact_within_tick"):
        preload = simulate_quantized(workload, capacity=1, delta=1.0, policy=policy)
        incremental = simulate_quantized(
            workload, capacity=1, delta=1.0, policy=policy,
            arrival_scheduling_mode="schedule_next_after_transition",
        )
        assert preload["accepted_arrivals"] == incremental["accepted_arrivals"]
