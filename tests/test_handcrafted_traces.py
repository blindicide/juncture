from juncture.events import Event
from juncture.simulator import QueueSimulator


def test_full_system_mixed_collision_is_critical() -> None:
    batch = [Event(0, 0.0, "arrival", 1, 0), Event(0, 0.0, "departure", 0, 1)]
    assert QueueSimulator._shadow_difference(1, 1, batch) == 1


def test_non_full_mixed_collision_is_not_critical() -> None:
    batch = [Event(0, 0.0, "arrival", 1, 0), Event(0, 0.0, "departure", 0, 1)]
    assert QueueSimulator._shadow_difference(0, 1, batch) == 0


def test_multiple_arrivals_one_departure() -> None:
    batch = [Event(0, 0.0, "arrival", i, i) for i in range(3)] + [Event(0, 0.0, "departure", 9, 9)]
    assert QueueSimulator._shadow_difference(1, 1, batch) == 1
