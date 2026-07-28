"""Small event record used by the queue simulator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    time: float | int
    raw_time: float
    event_type: str
    job_id: int
    sequence: int
    random_priority: int = 0
