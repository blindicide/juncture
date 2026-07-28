import numpy as np

from juncture.simulator import simulate_quantized
from juncture.workload import Workload


def test_collision_metrics_observe_collisions() -> None:
    workload = Workload(np.array([0.1, 0.2, 1.1]), np.array([0.1, 0.1, 0.1]), 0, 1)
    result = simulate_quantized(workload, capacity=1, delta=1.0, policy="departure_first")
    assert result["collided_ticks"] >= 1
