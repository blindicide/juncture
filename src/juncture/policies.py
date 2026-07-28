"""Equal-timestamp event ordering policies."""

from __future__ import annotations

from typing import Literal

OrderingPolicy = Literal[
    "departure_first", "arrival_first", "insertion_order", "random_order", "exact_within_tick"
]

POLICIES: tuple[OrderingPolicy, ...] = (
    "departure_first",
    "arrival_first",
    "insertion_order",
    "random_order",
    "exact_within_tick",
)


def type_priority(policy: OrderingPolicy, event_type: str) -> int:
    if policy == "departure_first":
        return 0 if event_type == "departure" else 1
    if policy == "arrival_first":
        return 0 if event_type == "arrival" else 1
    return 0
