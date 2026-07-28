from juncture.policies import type_priority


def test_deterministic_type_priorities() -> None:
    assert type_priority("departure_first", "departure") < type_priority(
        "departure_first", "arrival"
    )
    assert type_priority("arrival_first", "arrival") < type_priority("arrival_first", "departure")
