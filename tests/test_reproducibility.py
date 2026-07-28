from juncture.simulator import simulate_exact, simulate_quantized
from juncture.workload import generate_workload


def test_exact_and_quantized_reproducibility() -> None:
    workload = generate_workload(
        arrival_rate=0.9, service_rate=1, warmup_arrivals=20, measured_arrivals=100, seed=12
    )
    exact_one = simulate_exact(workload, capacity=4)
    exact_two = simulate_exact(workload, capacity=4)
    exact_one.pop("simulation_runtime_seconds")
    exact_two.pop("simulation_runtime_seconds")
    assert exact_one == exact_two
    one = simulate_quantized(workload, capacity=4, delta=0.1, policy="random_order", tie_seed=9)
    two = simulate_quantized(workload, capacity=4, delta=0.1, policy="random_order", tie_seed=9)
    one.pop("simulation_runtime_seconds")
    two.pop("simulation_runtime_seconds")
    assert one == two
