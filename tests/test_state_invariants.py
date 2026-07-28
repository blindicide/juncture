from juncture.simulator import simulate_quantized
from juncture.workload import generate_workload


def test_same_tick_completion_terminates_and_accounts_arrivals() -> None:
    workload = generate_workload(
        arrival_rate=1, service_rate=1000, warmup_arrivals=2, measured_arrivals=30, seed=3
    )
    result = simulate_quantized(
        workload, capacity=1, delta=1.0, policy="departure_first", debug=True
    )
    assert result["accepted_arrivals"] + result["dropped_arrivals"] == 30
    assert result["completed_measured_jobs"] == result["accepted_arrivals"]
    assert result["maximum_batch_size"] >= 2
