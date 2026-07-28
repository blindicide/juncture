"""Exact and finite-resolution event-driven FIFO queue simulators."""

from __future__ import annotations

import heapq
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .events import Event
from .policies import OrderingPolicy, type_priority
from .quantization import Quantizer, quantize
from .workload import Workload

ENGINE_VERSION = "0.1.0"


@dataclass
class Job:
    job_id: int
    arrival_raw: float
    arrival_time: float
    service_requirement: float
    measured: bool
    accepted: bool = False
    service_start: float | None = None
    departure_time: float | None = None


@dataclass
class CollisionCounters:
    collided_ticks: int = 0
    collision_event_count: int = 0
    mixed_collided_ticks: int = 0
    mixed_arrivals: int = 0
    mixed_departures: int = 0
    critical_collided_ticks: int = 0
    critical_acceptance_difference: int = 0
    maximum_batch_size: int = 0


@dataclass
class Measurement:
    accepted: int = 0
    dropped: int = 0
    completed: int = 0
    wait_times: list[float] = field(default_factory=list)
    sojourn_times: list[float] = field(default_factory=list)
    queue_area: float = 0.0
    system_area: float = 0.0
    full_area: float = 0.0
    idle_area: float = 0.0
    max_queue_length: int = 0
    start_time: float | None = None
    end_arrival_time: float | None = None
    collisions: CollisionCounters = field(default_factory=CollisionCounters)


def _quantile(values: list[float], q: float) -> float | None:
    return float(np.quantile(values, q)) if values else None


class QueueSimulator:
    """A bounded single-server FIFO queue driven by a pre-generated workload."""

    def __init__(
        self,
        workload: Workload,
        *,
        capacity: int,
        service_rate: float,
        exact: bool,
        delta: float | None = None,
        quantizer: Quantizer = "floor",
        policy: OrderingPolicy = "departure_first",
        tie_seed: int = 0,
        debug: bool = False,
        max_events: int | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if service_rate <= 0:
            raise ValueError("service_rate must be positive")
        if not exact and (delta is None or delta <= 0):
            raise ValueError("quantized simulation requires positive delta")
        self.workload = workload
        self.capacity = capacity
        self.service_rate = service_rate
        self.exact = exact
        self.delta = delta
        self.quantizer = quantizer
        self.policy = policy
        self.debug = debug
        self.max_events = max_events or max(1000, 20 * workload.total_arrivals + 1000)
        self.rng = np.random.default_rng(tie_seed)
        self.tie_seed = tie_seed
        self.queue: list[tuple[tuple[Any, ...], Event]] = []
        self.sequence = 0
        self.jobs: dict[int, Job] = {}
        self.waiting: deque[int] = deque()
        self.in_service: int | None = None
        self.jobs_in_system = 0
        self.measurement = Measurement()
        self.measurement_started = False
        self.collecting_time = False
        self.last_clock: float | None = None
        self.processed_events = 0
        self._active_tick: float | int | None = None
        self._same_tick_heap: list[tuple[tuple[Any, ...], Event]] | None = None

    def _clock(self, value: float) -> float:
        if self.exact:
            return float(value)
        assert self.delta is not None
        return float(value) * self.delta

    def _event_key(self, event: Event) -> tuple[Any, ...]:
        if self.exact:
            return (event.time, type_priority("departure_first", event.event_type), event.sequence)
        if self.policy == "insertion_order":
            policy_key: Any = event.sequence
        elif self.policy == "random_order":
            policy_key = event.random_priority
        elif self.policy == "exact_within_tick":
            policy_key = event.raw_time
        else:
            policy_key = type_priority(self.policy, event.event_type)
        return (event.time, policy_key, event.sequence)

    def _push(self, time_value: float, raw_time: float, event_type: str, job_id: int) -> None:
        event = Event(
            time_value,
            raw_time,
            event_type,
            job_id,
            self.sequence,
            int(self.rng.integers(0, 2**63)),
        )
        self.sequence += 1
        item = (self._event_key(event), event)
        if self._same_tick_heap is not None and time_value == self._active_tick:
            heapq.heappush(self._same_tick_heap, item)
        else:
            heapq.heappush(self.queue, item)

    def _schedule_initial_arrivals(self) -> None:
        delta = self.delta
        for job_id, arrival in enumerate(self.workload.arrival_times):
            if self.exact:
                moment = arrival
            else:
                assert delta is not None
                moment = float(quantize(arrival, delta, self.quantizer))
            self._push(moment, float(arrival), "arrival", job_id)

    def _update_integrals(self, clock: float) -> None:
        if not self.collecting_time:
            self.last_clock = clock
            return
        assert self.last_clock is not None
        elapsed = clock - self.last_clock
        if elapsed < -1e-12:
            raise RuntimeError("simulation clock moved backwards")
        if elapsed > 0:
            m = self.measurement
            queue_length = len(self.waiting)
            m.queue_area += queue_length * elapsed
            m.system_area += self.jobs_in_system * elapsed
            m.full_area += (self.jobs_in_system == self.capacity) * elapsed
            m.idle_area += (self.jobs_in_system == 0) * elapsed
        self.last_clock = clock

    def _reset_measurement(self, clock: float) -> None:
        self.measurement = Measurement(start_time=clock)
        self.measurement_started = True
        self.collecting_time = True
        self.last_clock = clock

    def _assert_invariants(self) -> None:
        if not (0 <= self.jobs_in_system <= self.capacity):
            raise RuntimeError("queue capacity invariant violated")
        if self.in_service is not None and self.in_service in self.waiting:
            raise RuntimeError("job is both waiting and in service")
        if self.jobs_in_system != len(self.waiting) + (self.in_service is not None):
            raise RuntimeError("system occupancy does not match state")

    @staticmethod
    def _shadow_difference(occupancy: int, capacity: int, batch: list[Event]) -> int:
        arrivals = sum(e.event_type == "arrival" for e in batch)
        departures = sum(e.event_type == "departure" for e in batch)
        if not arrivals or not departures:
            return 0

        def accepted(arrival_first: bool) -> int:
            n = occupancy
            accepted_count = 0
            sequence = (
                ["arrival"] * arrivals + ["departure"] * departures
                if arrival_first
                else ["departure"] * departures + ["arrival"] * arrivals
            )
            for event_type in sequence:
                if event_type == "departure":
                    n = max(0, n - 1)
                elif n < capacity:
                    n += 1
                    accepted_count += 1
            return accepted_count

        return abs(accepted(True) - accepted(False))

    def _record_static_criticality(self, batch: list[Event]) -> None:
        """Evaluate policy-neutral static batch criticality before state mutation."""
        if self.exact or not self.measurement_started or len(batch) < 2:
            return
        counters = self.measurement.collisions
        arrivals = [e for e in batch if e.event_type == "arrival"]
        departures = [e for e in batch if e.event_type == "departure"]
        if arrivals and departures:
            difference = self._shadow_difference(self.jobs_in_system, self.capacity, batch)
            if difference:
                counters.critical_collided_ticks += 1
                counters.critical_acceptance_difference += difference

    def _record_event_collision(self, batch: list[Event]) -> None:
        """Record all events processed at a tick, including recursive completions."""
        if self.exact or not self.measurement_started or len(batch) < 2:
            return
        counters = self.measurement.collisions
        counters.collided_ticks += 1
        counters.collision_event_count += len(batch)
        counters.maximum_batch_size = max(counters.maximum_batch_size, len(batch))
        arrivals = [e for e in batch if e.event_type == "arrival"]
        departures = [e for e in batch if e.event_type == "departure"]
        if arrivals and departures:
            counters.mixed_collided_ticks += 1
            counters.mixed_arrivals += len(arrivals)
            counters.mixed_departures += len(departures)

    def _start_service(self, job_id: int, clock: float) -> None:
        job = self.jobs[job_id]
        if job.service_start is not None:
            raise RuntimeError("job started twice")
        job.service_start = clock
        self.in_service = job_id
        if self.exact:
            completion_raw = clock + job.service_requirement
            scheduled: float | int = completion_raw
        else:
            completion_raw = clock + job.service_requirement
            assert self.delta is not None
            scheduled = float(
                max(int(self._current_time), quantize(completion_raw, self.delta, self.quantizer))
            )
        self._push(scheduled, completion_raw, "departure", job_id)

    def _arrival(self, event: Event, clock: float) -> None:
        job_id = event.job_id
        measured = job_id >= self.workload.warmup_arrivals
        job = Job(
            job_id,
            event.raw_time,
            clock,
            float(self.workload.service_requirements[job_id]),
            measured,
        )
        self.jobs[job_id] = job
        if self.jobs_in_system < self.capacity:
            job.accepted = True
            self.jobs_in_system += 1
            if measured:
                self.measurement.accepted += 1
            if self.in_service is None:
                self._start_service(job_id, clock)
            else:
                self.waiting.append(job_id)
        elif measured:
            self.measurement.dropped += 1
        if measured and job_id == self.workload.total_arrivals - 1:
            self.measurement.end_arrival_time = clock
            self.collecting_time = False
        self.measurement.max_queue_length = max(
            self.measurement.max_queue_length, len(self.waiting)
        )

    def _departure(self, event: Event, clock: float) -> None:
        job = self.jobs[event.job_id]
        if self.in_service != event.job_id:
            raise RuntimeError("departure for a job not in service")
        job.departure_time = clock
        self.in_service = None
        self.jobs_in_system -= 1
        if job.measured:
            self.measurement.completed += 1
            assert job.service_start is not None
            self.measurement.wait_times.append(job.service_start - job.arrival_time)
            self.measurement.sojourn_times.append(clock - job.arrival_time)
        if self.waiting:
            self._start_service(self.waiting.popleft(), clock)

    def run(self) -> dict[str, Any]:
        started = time.perf_counter()
        self._schedule_initial_arrivals()
        while self.queue:
            _, first = heapq.heappop(self.queue)
            current = first.time
            self._current_time = current
            batch = [first]
            while self.queue and self.queue[0][1].time == current:
                batch.append(heapq.heappop(self.queue)[1])
            clock = self._clock(current)
            if not self.measurement_started and any(
                e.event_type == "arrival" and e.job_id >= self.workload.warmup_arrivals
                for e in batch
            ):
                self._reset_measurement(clock)
            self._update_integrals(clock)
            self._record_static_criticality(batch)
            # Newly scheduled events at this tick join the active local heap, so a sub-quantum
            # service completion is ordered under the same policy as the events that caused it.
            self._active_tick = current
            self._same_tick_heap = [(self._event_key(event), event) for event in batch]
            heapq.heapify(self._same_tick_heap)
            processed_at_tick: list[Event] = []
            while self._same_tick_heap:
                _, event = heapq.heappop(self._same_tick_heap)
                if event.event_type == "arrival":
                    self._arrival(event, clock)
                else:
                    self._departure(event, clock)
                self.processed_events += 1
                if self.processed_events > self.max_events:
                    raise RuntimeError("maximum event guard exceeded")
                if self.debug:
                    self._assert_invariants()
                processed_at_tick.append(event)
            self._record_event_collision(processed_at_tick)
            self._same_tick_heap = None
            self._active_tick = None
        if self.jobs_in_system != 0 or self.in_service is not None:
            raise RuntimeError("simulation ended without draining")
        return self._result(time.perf_counter() - started)

    def _result(self, runtime: float) -> dict[str, Any]:
        m = self.measurement
        measured = self.workload.measured_arrivals
        duration = (
            (m.end_arrival_time - m.start_time)
            if m.start_time is not None and m.end_arrival_time is not None
            else 0.0
        )
        collision = m.collisions
        events_seen = max(1, self.processed_events)
        result: dict[str, Any] = {
            "mode": "exact" if self.exact else "quantized",
            "capacity": self.capacity,
            "delta": None if self.exact else self.delta,
            "quantizer": None if self.exact else self.quantizer,
            "ordering_policy": "exact" if self.exact else self.policy,
            "tie_seed": self.tie_seed,
            "workload_seed": self.workload.seed,
            "warmup_arrivals": self.workload.warmup_arrivals,
            "measured_arrivals": measured,
            "accepted_arrivals": m.accepted,
            "dropped_arrivals": m.dropped,
            "completed_measured_jobs": m.completed,
            "packet_loss_probability": m.dropped / measured,
            "acceptance_probability": m.accepted / measured,
            "throughput": m.completed / duration if duration > 0 else None,
            "mean_waiting_time": float(np.mean(m.wait_times)) if m.wait_times else None,
            "median_waiting_time": _quantile(m.wait_times, 0.5),
            "p95_waiting_time": _quantile(m.wait_times, 0.95),
            "p99_waiting_time": _quantile(m.wait_times, 0.99),
            "mean_sojourn_time": float(np.mean(m.sojourn_times)) if m.sojourn_times else None,
            "median_sojourn_time": _quantile(m.sojourn_times, 0.5),
            "p95_sojourn_time": _quantile(m.sojourn_times, 0.95),
            "time_average_number_in_queue": m.queue_area / duration if duration > 0 else None,
            "time_average_number_in_system": m.system_area / duration if duration > 0 else None,
            "maximum_queue_length": m.max_queue_length,
            "fraction_time_full": m.full_area / duration if duration > 0 else None,
            "fraction_time_idle": m.idle_area / duration if duration > 0 else None,
            "collided_ticks": collision.collided_ticks,
            "collision_event_count": collision.collision_event_count,
            "collision_event_fraction": collision.collision_event_count / events_seen,
            "mixed_collided_ticks": collision.mixed_collided_ticks,
            "mixed_collision_rate": collision.mixed_collided_ticks / measured,
            "critical_collided_ticks": collision.critical_collided_ticks,
            "critical_acceptance_difference": collision.critical_acceptance_difference,
            "critical_acceptance_difference_rate": collision.critical_acceptance_difference
            / measured,
            "maximum_batch_size": collision.maximum_batch_size,
            "processed_events": self.processed_events,
            "simulation_runtime_seconds": runtime,
            "engine_version": ENGINE_VERSION,
        }
        if m.accepted + m.dropped != measured:
            raise RuntimeError("measurement arrival accounting invariant violated")
        return result


def simulate_exact(
    workload: Workload, *, capacity: int, service_rate: float = 1.0, debug: bool = False
) -> dict[str, Any]:
    return QueueSimulator(
        workload, capacity=capacity, service_rate=service_rate, exact=True, debug=debug
    ).run()


def simulate_quantized(
    workload: Workload,
    *,
    capacity: int,
    delta: float,
    service_rate: float = 1.0,
    quantizer: Quantizer = "floor",
    policy: OrderingPolicy = "departure_first",
    tie_seed: int = 0,
    debug: bool = False,
) -> dict[str, Any]:
    return QueueSimulator(
        workload,
        capacity=capacity,
        service_rate=service_rate,
        exact=False,
        delta=delta,
        quantizer=quantizer,
        policy=policy,
        tie_seed=tie_seed,
        debug=debug,
    ).run()
