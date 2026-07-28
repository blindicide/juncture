"""Deterministic task manifests and resumable experiment execution."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any, cast

import pandas as pd

from .config import CampaignConfig
from .identities import stable_id
from .policies import OrderingPolicy
from .provenance import collect_provenance
from .quantization import Quantizer
from .schema import RAW_SCHEMA_VERSION
from .seeds import derive_seed
from .simulator import simulate_exact, simulate_quantized
from .storage import atomic_json, atomic_parquet, save_yaml
from .workload import generate_workload


def task_manifest(config: CampaignConfig) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for rho in config.loads:
        for capacity in config.capacities:
            for replication in range(config.replications):
                workload_seed = derive_seed(
                    config.name, replication, rho, capacity, "workload", root_seed=config.root_seed
                )
                scenario = {
                    "arrival_distribution": config.arrival_distribution,
                    "service_distribution": config.service_distribution,
                    "service_rate": config.service_rate,
                    "timestamp_semantics": "continuous" if config.schema_version == 1 else "quantized_tick_v2",
                }
                workload_identity = {
                    "scenario": scenario,
                    "campaign": config.name,
                    "replication": replication,
                    "rho": rho,
                    "capacity": capacity,
                    "warmup_arrivals": config.warmup_arrivals,
                    "measured_arrivals": config.measured_arrivals,
                    "workload_seed": workload_seed,
                }
                for scheduling_mode in config.arrival_scheduling_modes:
                    exact_id = f"exact-{derive_seed(config.name, rho, capacity, replication, scheduling_mode, 'exact', root_seed=config.root_seed):016x}"
                    exact_row = {
                        "task_id": exact_id,
                        "kind": "exact",
                        "replication": replication,
                        "rho": rho,
                        "capacity": capacity,
                        "delta": None,
                        "quantizer": None,
                        "policy": "exact",
                        "workload_seed": workload_seed,
                        "tie_seed": 0,
                        "quantization_seed": derive_seed(config.name, rho, capacity, replication, "quantization", root_seed=config.root_seed),
                        "arrival_scheduling_mode": scheduling_mode,
                    }
                    if config.schema_version >= 2:
                        exact_row.update(
                            {
                                "raw_schema_version": RAW_SCHEMA_VERSION,
                                "scenario_id": stable_id("scenario", {**scenario, "arrival_scheduling_mode": scheduling_mode}),
                                "workload_id": stable_id("workload", workload_identity),
                                "configuration_id": stable_id("configuration", {**scenario, "rho": rho, "capacity": capacity, "delta": None, "quantizer": None, "policy": "exact", "arrival_scheduling_mode": scheduling_mode}),
                                "pair_id": stable_id("pair", {**workload_identity, "delta": None, "quantizer": None, "arrival_scheduling_mode": scheduling_mode}),
                            }
                        )
                    records.append(exact_row)
                    for delta in config.deltas:
                        for quantizer in config.quantizers:
                            for policy in config.policies:
                                repetitions = config.tie_repetitions if policy == "random_order" else 1
                                for tie_repeat in range(repetitions):
                                    repeated_tie_seed = derive_seed(
                                        config.name,
                                        replication,
                                        rho,
                                        capacity,
                                        delta,
                                        quantizer,
                                        policy,
                                        tie_repeat,
                                        "tie",
                                        root_seed=config.root_seed,
                                    )
                                    task_id = f"quantized-{derive_seed(config.name, rho, capacity, replication, scheduling_mode, delta, quantizer, policy, tie_repeat, root_seed=config.root_seed):016x}"
                                    row = {
                                        "task_id": task_id,
                                        "kind": "quantized",
                                        "replication": replication,
                                        "rho": rho,
                                        "capacity": capacity,
                                        "delta": delta,
                                        "quantizer": quantizer,
                                        "policy": policy,
                                        "tie_repeat": tie_repeat,
                                        "workload_seed": workload_seed,
                                        "tie_seed": repeated_tie_seed,
                                        "quantization_seed": derive_seed(config.name, rho, capacity, replication, delta, quantizer, "quantization", root_seed=config.root_seed),
                                        "arrival_scheduling_mode": scheduling_mode,
                                    }
                                    if config.schema_version >= 2:
                                        row.update(
                                            {
                                            "raw_schema_version": RAW_SCHEMA_VERSION,
                                            "scenario_id": stable_id("scenario", {**scenario, "arrival_scheduling_mode": scheduling_mode}),
                                            "workload_id": stable_id("workload", workload_identity),
                                            "configuration_id": stable_id("configuration", {**scenario, "rho": rho, "capacity": capacity, "delta": delta, "quantizer": quantizer, "policy": policy, "arrival_scheduling_mode": scheduling_mode}),
                                            "pair_id": stable_id("pair", {**workload_identity, "delta": delta, "quantizer": quantizer, "arrival_scheduling_mode": scheduling_mode}),
                                            }
                                        )
                                    records.append(row)
    return pd.DataFrame(records).sort_values("task_id", kind="stable").reset_index(drop=True)


def create_run(config: CampaignConfig, root: Path) -> Path:
    run_id = f"{config.name}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    run_dir = root / "results" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    for part in ("raw", "derived", "figures", "tables", "logs", "report"):
        (run_dir / part).mkdir()
    save_yaml(config.resolved(), run_dir / "config.resolved.yaml")
    atomic_json(collect_provenance(root), run_dir / "provenance.json")
    (run_dir / "environment.txt").write_text(
        collect_provenance(root)["python_version"] or "", encoding="utf-8"
    )
    manifest = task_manifest(config)
    atomic_parquet(manifest, run_dir / "task_manifest.parquet")
    status = manifest[["task_id"]].copy()
    status["status"] = "pending"
    atomic_parquet(status, run_dir / "task_status.parquet")
    return run_dir


def _run_one(task: dict[str, Any], config_data: dict[str, Any]) -> dict[str, Any]:
    config = CampaignConfig(**config_data)
    workload = generate_workload(
        arrival_rate=float(task["rho"]) * config.service_rate,
        service_rate=config.service_rate,
        warmup_arrivals=config.warmup_arrivals,
        measured_arrivals=config.measured_arrivals,
        seed=int(task["workload_seed"]),
        arrival_distribution=config.arrival_distribution,
        service_distribution=config.service_distribution,
    )
    if task["kind"] == "exact":
        result = simulate_exact(
            workload,
            capacity=int(task["capacity"]),
            service_rate=config.service_rate,
            quantization_seed=int(task.get("quantization_seed", 0)),
            arrival_scheduling_mode=str(task.get("arrival_scheduling_mode", "preload_all")),
        )
    else:
        result = simulate_quantized(
            workload,
            capacity=int(task["capacity"]),
            delta=float(task["delta"]),
            service_rate=config.service_rate,
            quantizer=cast(Quantizer, task["quantizer"]),
            policy=cast(OrderingPolicy, task["policy"]),
            tie_seed=int(task["tie_seed"]),
            quantization_seed=int(task.get("quantization_seed", 0)),
            arrival_scheduling_mode=str(task.get("arrival_scheduling_mode", "preload_all")),
        )
    return {
        **task,
        **result,
        "lambda": float(task["rho"]) * config.service_rate,
        "mu": config.service_rate,
        "normalized_resolution": task["delta"],
        "root_seed": config.root_seed,
        "raw_schema_version": int(task.get("raw_schema_version", 1)),
    }


def execute_run(run_dir: Path, *, workers: int = 1, checkpoint_size: int = 32) -> None:
    """Execute pending tasks and atomically checkpoint each bounded result batch.

    A task is marked complete only after its row is included in a replacement Parquet
    file.  If interrupted between checkpoints, resuming recomputes at most one batch.
    """
    if workers < 1 or checkpoint_size < 1:
        raise ValueError("workers and checkpoint_size must be positive")
    import yaml

    config_data = yaml.safe_load((run_dir / "config.resolved.yaml").read_text(encoding="utf-8"))
    config_data["arrival_distribution"] = config_data.get("arrival_distribution", {})
    config_data["service_distribution"] = config_data.get("service_distribution", {})
    # Rehydrate nested dataclasses after YAML serialization.
    from .distributions import DistributionSpec

    config_data["arrival_distribution"] = DistributionSpec(**config_data["arrival_distribution"])
    config_data["service_distribution"] = DistributionSpec(**config_data["service_distribution"])
    manifest = pd.read_parquet(run_dir / "task_manifest.parquet")
    status = pd.read_parquet(run_dir / "task_status.parquet")
    pending_ids = set(status.loc[status.status != "complete", "task_id"])
    tasks = manifest[manifest.task_id.isin(pending_ids)].to_dict("records")
    old_exact = _read_or_empty(run_dir / "raw" / "exact_results.parquet")
    old_quantized = _read_or_empty(run_dir / "raw" / "quantized_results.parquet")
    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = executor.map(_run_task_args, ((task, config_data) for task in tasks))
            _checkpoint_results(
                results,
                checkpoint_size,
                run_dir,
                status,
                old_exact,
                old_quantized,
            )
    else:
        _checkpoint_results(
            (_run_one(task, config_data) for task in tasks),
            checkpoint_size,
            run_dir,
            status,
            old_exact,
            old_quantized,
        )


def _checkpoint_results(
    results: Any,
    checkpoint_size: int,
    run_dir: Path,
    status: pd.DataFrame,
    exact: pd.DataFrame,
    quantized: pd.DataFrame,
) -> None:
    iterator = iter(results)
    while batch := list(islice(iterator, checkpoint_size)):
        exact_rows = [row for row in batch if row["kind"] == "exact"]
        quantized_rows = [row for row in batch if row["kind"] == "quantized"]
        if exact_rows:
            exact = _append_unique(exact, pd.DataFrame(exact_rows))
            atomic_parquet(exact, run_dir / "raw" / "exact_results.parquet")
        if quantized_rows:
            quantized = _append_unique(quantized, pd.DataFrame(quantized_rows))
            atomic_parquet(quantized, run_dir / "raw" / "quantized_results.parquet")
        status.loc[status.task_id.isin([row["task_id"] for row in batch]), "status"] = "complete"
        atomic_parquet(status, run_dir / "task_status.parquet")


def _append_unique(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([existing, new], ignore_index=True)
    return combined.drop_duplicates(subset="task_id", keep="last").sort_values(
        "task_id", kind="stable"
    )


def _run_task_args(args: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    return _run_one(*args)


def _read_or_empty(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def run_status(run_dir: Path) -> dict[str, int]:
    status = pd.read_parquet(run_dir / "task_status.parquet")
    return {str(k): int(v) for k, v in status.status.value_counts().items()}
