"""Versioned, persisted-table analysis for Phase II.

This module deliberately never writes to a historical run's ``derived``,
``figures``, ``tables``, or ``report`` directories.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .bootstrap import paired_bootstrap_ci
from .metrics_v2 import collision_rates
from .provenance import collect_provenance
from .regression import fit_grouped_ols
from .schema import ANALYSIS_SCHEMA_VERSION
from .storage import atomic_json, atomic_parquet, save_yaml
from .theory import effective_throughput, stationary_loss_probability

PRIMARY_ARCHITECTURE = "preload_all"
ROBUSTNESS_ARCHITECTURE = "schedule_next_after_transition"


@dataclass(frozen=True)
class AnalysisConfig:
    schema_version: int = 2
    fine_delta_max: float = 0.003
    sensitivity_cutoffs: list[float] | None = None
    bootstrap_resamples: int = 10_000
    predictor_bootstrap_resamples: int = 1_000
    bootstrap_seed: int = 20260729
    deterministic_policy_scope: str = "mean(arrival_first,departure_first)"
    confidence_level: float = 0.95
    include_legacy: bool = False
    bilingual_output: bool = True
    percentage_point_presentation: bool = True

    def validate(self) -> None:
        if self.schema_version != ANALYSIS_SCHEMA_VERSION:
            raise ValueError("analysis schema_version must be 2")
        if self.fine_delta_max <= 0 or self.bootstrap_resamples < 1:
            raise ValueError("fine_delta_max and bootstrap_resamples must be positive")
        if self.predictor_bootstrap_resamples < 1:
            raise ValueError("predictor_bootstrap_resamples must be positive")
        if self.deterministic_policy_scope != "mean(arrival_first,departure_first)":
            raise ValueError("only the paired AF/DF deterministic scope is supported")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be between zero and one")
        cutoffs = self.sensitivity_cutoffs or []
        if any(value <= 0 for value in cutoffs):
            raise ValueError("sensitivity cutoffs must be positive")


def load_analysis_config(path: Path | None) -> AnalysisConfig:
    raw: dict[str, Any] = {}
    if path is not None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = AnalysisConfig(
        schema_version=int(raw.get("schema_version", 2)),
        fine_delta_max=float(raw.get("fine_delta_max", 0.003)),
        sensitivity_cutoffs=list(raw.get("sensitivity_cutoffs", [0.001, 0.003, 0.01])),
        bootstrap_resamples=int(raw.get("bootstrap_resamples", 10_000)),
        predictor_bootstrap_resamples=int(raw.get("predictor_bootstrap_resamples", 1_000)),
        bootstrap_seed=int(raw.get("bootstrap_seed", 20260729)),
        deterministic_policy_scope=str(
            raw.get("deterministic_policy_scope", "mean(arrival_first,departure_first)")
        ),
        confidence_level=float(raw.get("confidence_level", 0.95)),
        include_legacy=bool(raw.get("include_legacy", False)),
        bilingual_output=bool(raw.get("bilingual_output", True)),
        percentage_point_presentation=bool(raw.get("percentage_point_presentation", True)),
    )
    config.validate()
    return config


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _read_raw(run_dir: Path, name: str) -> pd.DataFrame:
    path = run_dir / "raw" / name
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def _theory_metadata(run_dir: Path, exact: pd.DataFrame) -> pd.DataFrame:
    resolved = yaml.safe_load((run_dir / "config.resolved.yaml").read_text(encoding="utf-8"))
    applicable = (
        resolved.get("arrival_distribution", {}).get("name", "exponential") == "exponential"
        and resolved.get("service_distribution", {}).get("name", "exponential") == "exponential"
    )
    reason = None if applicable else "M/M/1/K requires exponential arrivals and services"
    rows: list[dict[str, Any]] = []
    for (rho, capacity), group in exact.groupby(["rho", "capacity"]):
        row: dict[str, Any] = {
            "rho": rho,
            "capacity": capacity,
            "n": len(group),
            "theory_model": "M/M/1/K" if applicable else None,
            "theory_applicable": applicable,
            "theory_inapplicability_reason": reason,
            "simulated_exact_loss": group.packet_loss_probability.mean(),
            "simulated_effective_throughput": group.throughput.mean(),
            "theoretical_loss": None,
            "theoretical_effective_throughput": None,
            "absolute_loss_difference": None,
        }
        if applicable:
            row["theoretical_loss"] = stationary_loss_probability(float(rho), int(capacity))
            row["theoretical_effective_throughput"] = effective_throughput(
                float(rho), float(rho), int(capacity)
            )
            row["absolute_loss_difference"] = abs(
                row["simulated_exact_loss"] - row["theoretical_loss"]
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _paired(quantized: pd.DataFrame, exact: pd.DataFrame) -> pd.DataFrame:
    required = {"pair_id", "workload_id", "arrival_scheduling_mode"}
    if not required <= set(quantized.columns):
        return _empty(["legacy_analysis", "legacy_collision_event_fraction"])
    pair_key = ["pair_id", "arrival_scheduling_mode"]
    reference_key = ["workload_id", "arrival_scheduling_mode"]
    metrics = [
        "packet_loss_probability",
        "throughput",
        "mean_waiting_time",
        "mean_sojourn_time",
        "time_average_number_in_system",
    ]
    if not set(reference_key).issubset(exact.columns):
        raise ValueError("exact reference rows lack workload identity")
    if exact.duplicated(reference_key).any():
        raise ValueError("duplicate exact references for workload identity")
    references = exact[reference_key + [metric for metric in metrics if metric in exact]].rename(
        columns={metric: f"exact_{metric}" for metric in metrics if metric in exact}
    )
    deterministic = quantized[quantized.policy.isin(["arrival_first", "departure_first"])]
    values = deterministic.pivot_table(
        index=pair_key, columns="policy", values=metrics, aggfunc="first"
    )
    if values.empty or "arrival_first" not in values.columns.get_level_values(1):
        return _empty(pair_key)
    values.columns = [f"{policy}_{metric}" for metric, policy in values.columns]
    detail = deterministic.groupby(pair_key, as_index=False).first()
    keep = [
        column
        for column in ("rho", "capacity", "delta", "quantizer", "workload_id", "replication")
        if column in detail
    ]
    result = values.reset_index().merge(detail[pair_key + keep], on=pair_key, how="left")
    result = result.merge(references, on=reference_key, how="left", validate="many_to_one")
    if result[[f"exact_{metric}" for metric in metrics if f"exact_{metric}" in result]].isna().any(axis=None):
        raise ValueError("missing exact reference for completed quantized pair")
    for metric in metrics:
        af = f"arrival_first_{metric}"
        df = f"departure_first_{metric}"
        if af not in result or df not in result:
            continue
        gap = result[af] - result[df]
        midpoint = (result[af] + result[df]) / 2
        result[f"signed_{metric}_gap"] = gap
        result[f"absolute_{metric}_gap"] = gap.abs()
        result[f"deterministic_midpoint_{metric}"] = midpoint
        exact_metric = f"exact_{metric}"
        if exact_metric in result:
            bias = midpoint - result[exact_metric]
            result[f"midpoint_signed_bias_{metric}"] = bias
            result[f"midpoint_absolute_bias_{metric}"] = bias.abs()
            half_width = gap.abs() / 2
            result[f"ordering_half_width_{metric}"] = half_width
            result[f"bias_to_ordering_ratio_{metric}"] = np.where(
                half_width != 0, bias.abs() / half_width, np.nan
            )
            result[f"full_bias_to_gap_ratio_{metric}"] = np.where(
                gap.abs() != 0, bias.abs() / gap.abs(), np.nan
            )
            result[f"exact_inside_deterministic_interval_{metric}"] = (
                (result[exact_metric] >= result[[af, df]].min(axis=1))
                & (result[exact_metric] <= result[[af, df]].max(axis=1))
            )
    # Compact loss aliases are the public Phase II.1 contract.
    result["exact_packet_loss"] = result["exact_packet_loss_probability"]
    result["policy_midpoint_loss"] = result["deterministic_midpoint_packet_loss_probability"]
    result["midpoint_signed_bias"] = result["midpoint_signed_bias_packet_loss_probability"]
    result["midpoint_absolute_bias"] = result["midpoint_absolute_bias_packet_loss_probability"]
    result["signed_policy_gap"] = result["signed_packet_loss_probability_gap"]
    result["absolute_policy_gap"] = result["absolute_packet_loss_probability_gap"]
    result["ordering_half_width"] = result["ordering_half_width_packet_loss_probability"]
    result["exact_inside_deterministic_interval"] = result[
        "exact_inside_deterministic_interval_packet_loss_probability"
    ]
    return result


def _configuration_summary(quantized: pd.DataFrame) -> pd.DataFrame:
    keys = [
        column
        for column in ("configuration_id", "rho", "capacity", "delta", "quantizer", "policy", "arrival_scheduling_mode")
        if column in quantized
    ]
    aggregations: dict[str, tuple[str, str]] = {
        "n": ("packet_loss_probability", "size"),
        "mean_packet_loss": ("packet_loss_probability", "mean"),
        "sd_packet_loss": ("packet_loss_probability", "std"),
        "mean_throughput": ("throughput", "mean"),
        "mean_waiting_time": ("mean_waiting_time", "mean"),
        "mean_sojourn_time": ("mean_sojourn_time", "mean"),
        "mean_occupancy": ("time_average_number_in_system", "mean"),
    }
    for field in ("collision_event_fraction", "collided_tick_fraction", "mixed_collision_rate", "critical_acceptance_difference_rate"):
        if field in quantized:
            aggregations[f"mean_{field}"] = (field, "mean")
    summary = quantized.groupby(keys, as_index=False).agg(**aggregations)
    summary["se_packet_loss"] = summary.sd_packet_loss.fillna(0) / np.sqrt(summary.n)
    summary["ci95_low_packet_loss"] = summary.mean_packet_loss - 1.96 * summary.se_packet_loss
    summary["ci95_high_packet_loss"] = summary.mean_packet_loss + 1.96 * summary.se_packet_loss
    return summary


def _scaling(
    quantized: pd.DataFrame, config: AnalysisConfig
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit one deterministic midpoint slope per workload-design unit.

    A workload is reused across quantizers, so ``workload_id`` alone is not a
    collision-scaling observation.  The analysis unit is therefore a workload
    under one quantizer (with rho and capacity already embedded in the workload
    identity).  AF and DF are averaged *before* the log-log fit.
    """
    use = quantized[
        quantized.policy.isin(["arrival_first", "departure_first"])
        & (quantized.delta > 0)
        & (quantized.delta <= config.fine_delta_max)
    ].copy()
    value = "collision_event_fraction"
    if use.empty or value not in use:
        return _empty(["scaling_exponent"]), _empty(["mean_slope"]), _empty(["delta"])
    unit_keys = [
        key
        for key in ("workload_id", "rho", "capacity", "quantizer", "arrival_scheduling_mode")
        if key in use
    ]
    policy_rates = (
        use.groupby(unit_keys + ["delta", "policy"], as_index=False)[value]
        .mean()
        .pivot(index=unit_keys + ["delta"], columns="policy", values=value)
        .reset_index()
    )
    required = {"arrival_first", "departure_first"}
    if not required <= set(policy_rates):
        return _empty(["scaling_exponent"]), _empty(["mean_slope"]), _empty(["delta"])
    midpoint = policy_rates[list(required)].mean(axis=1)
    scaling_input = policy_rates[unit_keys + ["delta"]].copy()
    scaling_input["deterministic_mean_collision_event_fraction"] = midpoint
    scaling_input["af_df_policy_rows_averaged"] = 2
    scaling_input["aggregation"] = "mean(arrival_first,departure_first) within workload-design and delta"
    rows: list[dict[str, Any]] = []
    for group_key, group in scaling_input.groupby(unit_keys, sort=True):
        valid = group[group.deterministic_mean_collision_event_fraction > 0].sort_values("delta")
        if len(valid) < 2:
            continue
        slope, intercept = np.polyfit(
            np.log(valid.delta), np.log(valid.deterministic_mean_collision_event_fraction), 1
        )
        row = dict(zip(unit_keys, group_key if isinstance(group_key, tuple) else (group_key,)))
        row.update(
            {
                "n_valid_deltas": len(valid),
                "scaling_exponent": slope,
                "intercept": intercept,
                "aggregation": "AF/DF midpoint before one log-log slope per workload-design",
            }
        )
        rows.append(row)
    slopes = pd.DataFrame(rows)
    if slopes.empty:
        return slopes, _empty(["mean_slope"]), scaling_input
    summary_keys = [key for key in ("rho", "capacity", "quantizer", "arrival_scheduling_mode") if key in slopes]
    summary = slopes.groupby(summary_keys, as_index=False).agg(
        n_workloads=("scaling_exponent", "size"),
        mean_slope=("scaling_exponent", "mean"),
        sd_slope=("scaling_exponent", "std"),
        median_slope=("scaling_exponent", "median"),
        q25_slope=("scaling_exponent", lambda values: values.quantile(0.25)),
        q75_slope=("scaling_exponent", lambda values: values.quantile(0.75)),
    )
    summary["iqr_slope"] = summary.q75_slope - summary.q25_slope
    intervals: list[tuple[float, float]] = []
    for index, (_, group) in enumerate(slopes.groupby(summary_keys, sort=True)):
        intervals.append(
            paired_bootstrap_ci(
                group.scaling_exponent.to_numpy(),
                seed=config.bootstrap_seed + index,
                resamples=config.bootstrap_resamples,
            )
        )
    summary["bootstrap_ci95_low"] = [interval[0] for interval in intervals]
    summary["bootstrap_ci95_high"] = [interval[1] for interval in intervals]
    summary["bootstrap_unit"] = "workload-design replication"
    summary["aggregation"] = "AF/DF midpoint, then one slope per workload-design"
    return slopes, summary, scaling_input


def _analysis_configuration_id(row: pd.Series) -> str:
    fields = {
        key: row[key]
        for key in ("rho", "capacity", "delta", "quantizer", "arrival_scheduling_mode")
    }
    encoded = json.dumps(fields, sort_keys=True, default=str).encode("utf-8")
    return f"analysis_configuration_{hashlib.sha256(encoded).hexdigest()[:24]}"


def _predictor_rows(
    paired: pd.DataFrame, quantized: pd.DataFrame, config: AnalysisConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return workload-paired and one-row-per-configuration predictor inputs."""
    if paired.empty:
        return _empty(["analysis_configuration_id"]), _empty(["analysis_configuration_id"])
    keys = [
        key
        for key in ("pair_id", "workload_id", "rho", "capacity", "delta", "quantizer", "arrival_scheduling_mode")
        if key in paired and key in quantized
    ]
    deterministic = quantized[quantized.policy.isin(["arrival_first", "departure_first"])]
    collision = deterministic.groupby(keys, as_index=False).agg(
        total_collision_rate=("collision_event_fraction", "mean"),
        mixed_collision_rate=("mixed_collision_rate", "mean"),
        critical_collision_rate=("critical_acceptance_difference_rate", "mean"),
    )
    workload = paired.merge(collision, on=keys, how="left", validate="one_to_one")
    workload["absolute_policy_gap"] = workload["absolute_packet_loss_probability_gap"]
    workload["inverse_capacity"] = 1 / workload.capacity
    workload["analysis_configuration_id"] = workload.apply(_analysis_configuration_id, axis=1)
    configuration_keys = [
        "analysis_configuration_id",
        "rho",
        "capacity",
        "delta",
        "quantizer",
        "arrival_scheduling_mode",
    ]
    value_columns = [
        "absolute_policy_gap",
        "total_collision_rate",
        "mixed_collision_rate",
        "critical_collision_rate",
        "inverse_capacity",
    ]
    rows = workload.groupby(configuration_keys, as_index=False).agg(
        n_workloads=("workload_id", "nunique"),
        **{column: (column, "mean") for column in value_columns},
    )
    intervals = [
        paired_bootstrap_ci(
            group.absolute_policy_gap.to_numpy(),
            seed=config.bootstrap_seed + index,
            resamples=config.bootstrap_resamples,
        )
        for index, (_, group) in enumerate(workload.groupby(configuration_keys, sort=True))
    ]
    rows["policy_gap_bootstrap_ci95_low"] = [interval[0] for interval in intervals]
    rows["policy_gap_bootstrap_ci95_high"] = [interval[1] for interval in intervals]
    rows["aggregation"] = "mean of workload-paired AF/DF estimates"
    rows["bootstrap_unit"] = "workload replication"
    if rows.analysis_configuration_id.duplicated().any():
        raise ValueError("predictor aggregation did not produce one row per configuration")
    return workload, rows


def _ols_coefficients(data: pd.DataFrame, outcome: str, predictors: list[str]) -> dict[str, float]:
    usable = data.dropna(subset=[outcome, *predictors])
    if len(usable) <= len(predictors) + 1:
        return {}
    design = np.column_stack([np.ones(len(usable)), *(usable[field].to_numpy() for field in predictors)])
    values = np.linalg.lstsq(design, usable[outcome].to_numpy(), rcond=None)[0]
    return dict(zip(["const", *predictors], values, strict=True))


def _bootstrap_predictor_models(
    workload: pd.DataFrame,
    models: list[dict[str, Any]],
    config: AnalysisConfig,
) -> None:
    """Attach CIs from resampling paired workload replications within configurations."""
    specifications = {
        "total": ["total_collision_rate"],
        "mixed": ["mixed_collision_rate"],
        "critical": ["critical_collision_rate"],
        "multivariable": ["critical_collision_rate", "rho", "inverse_capacity", "delta"],
    }
    configuration_keys = [
        "analysis_configuration_id",
        "rho",
        "capacity",
        "delta",
        "quantizer",
        "arrival_scheduling_mode",
    ]
    fields = [
        "absolute_policy_gap",
        "total_collision_rate",
        "mixed_collision_rate",
        "critical_collision_rate",
        "rho",
        "inverse_capacity",
        "delta",
    ]
    groups = [
        group[fields].to_numpy(dtype=float)
        for _, group in workload.groupby(configuration_keys, sort=True)
    ]
    if not groups:
        return
    rng = np.random.default_rng(config.bootstrap_seed)
    sampled: dict[str, dict[str, list[float]]] = {
        name: {field: [] for field in ["const", *predictors]}
        for name, predictors in specifications.items()
    }
    for _ in range(config.predictor_bootstrap_resamples):
        means = np.asarray(
            [
                values[rng.integers(0, len(values), size=len(values))].mean(axis=0)
                for values in groups
            ]
        )
        sample = pd.DataFrame(means, columns=fields)
        for name, predictors in specifications.items():
            for field, value in _ols_coefficients(sample, "absolute_policy_gap", predictors).items():
                sampled[name][field].append(value)
    for model in models:
        name = str(model["model"])
        for field, values in sampled.get(name, {}).items():
            if values:
                low, high = np.quantile(values, [0.025, 0.975])
                model[f"bootstrap_ci95_low_coefficient_{field}"] = float(low)
                model[f"bootstrap_ci95_high_coefficient_{field}"] = float(high)
        model["bootstrap_unit"] = "workload-paired replication within configuration"
        model["bootstrap_resamples"] = config.predictor_bootstrap_resamples


def _predictor_models(
    configuration_rows: pd.DataFrame, workload_rows: pd.DataFrame, config: AnalysisConfig
) -> pd.DataFrame:
    if configuration_rows.empty:
        return pd.DataFrame()
    models = [
        fit_grouped_ols(configuration_rows, "absolute_policy_gap", [field], name, "analysis_configuration_id")
        for field, name in (
            ("total_collision_rate", "total"),
            ("mixed_collision_rate", "mixed"),
            ("critical_collision_rate", "critical"),
        )
    ]
    models.append(
        fit_grouped_ols(
            configuration_rows,
            "absolute_policy_gap",
            ["critical_collision_rate", "rho", "inverse_capacity", "delta"],
            "multivariable",
            "analysis_configuration_id",
        )
    )
    _bootstrap_predictor_models(workload_rows, models, config)
    return pd.DataFrame(models)


def _random_variance(quantized: pd.DataFrame, paired: pd.DataFrame, config: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    random = quantized[quantized.policy == "random_order"].copy()
    keys = [key for key in ("pair_id", "arrival_scheduling_mode") if key in random]
    if random.empty or not keys:
        return _empty(keys), _empty(["component", "variance"])
    workload = random.groupby(keys, as_index=False).agg(
        tie_repetitions=("packet_loss_probability", "size"), tie_mean=("packet_loss_probability", "mean"),
        tie_variance=("packet_loss_probability", "var"), tie_sd=("packet_loss_probability", "std"),
        tie_min=("packet_loss_probability", "min"), tie_max=("packet_loss_probability", "max"),
        tie_p05=("packet_loss_probability", lambda x: x.quantile(.05)),
        tie_p95=("packet_loss_probability", lambda x: x.quantile(.95)),
    )
    references = paired[keys + [column for column in paired if column.startswith(("arrival_first_packet", "departure_first_packet", "deterministic_midpoint_packet", "packet_loss_probability"))]]
    workload = workload.merge(references, on=keys, how="left")
    midpoint = "deterministic_midpoint_packet_loss_probability"
    if midpoint in workload:
        diff = workload.tie_mean - workload[midpoint]
        low, high = paired_bootstrap_ci(diff.dropna().to_numpy(), seed=config.bootstrap_seed, resamples=config.bootstrap_resamples)
    else:
        low = high = np.nan
    within = float(workload.tie_variance.fillna(0).mean())
    between = float(workload.tie_mean.var(ddof=1)) if len(workload) > 1 else 0.0
    total = float(random.packet_loss_probability.var(ddof=1)) if len(random) > 1 else 0.0
    decomposition = pd.DataFrame([
        {"component": "within_workload_tie_variance", "variance": within},
        {"component": "between_workload_variance", "variance": between},
        {"component": "total_variance", "variance": total},
        {"component": "midpoint_hypothesis_ci95_low", "variance": low},
        {"component": "midpoint_hypothesis_ci95_high", "variance": high},
        {"component": "total_minus_weighted_components", "variance": total - within - between},
    ])
    return workload, decomposition


def _insertion(quantized: pd.DataFrame) -> pd.DataFrame:
    keys = [key for key in ("pair_id", "arrival_scheduling_mode") if key in quantized]
    if not keys:
        return _empty(keys)
    values = quantized[quantized.policy.isin(["arrival_first", "departure_first", "insertion_order"])]
    pivot = values.pivot_table(index=keys, columns="policy", values=["accepted_arrivals", "packet_loss_probability", "throughput"], aggfunc="first")
    if pivot.empty or "insertion_order" not in pivot.columns.get_level_values(1):
        return _empty(keys)
    pivot.columns = [f"{policy}_{metric}" for metric, policy in pivot.columns]
    output = pivot.reset_index()
    for policy in ("arrival_first", "departure_first"):
        accepted = f"{policy}_accepted_arrivals"
        insertion = "insertion_order_accepted_arrivals"
        if accepted in output:
            output[f"insertion_matches_{policy}_counts"] = output[insertion] == output[accepted]
            output[f"insertion_loss_distance_{policy}"] = (
                output["insertion_order_packet_loss_probability"] - output[f"{policy}_packet_loss_probability"]
            ).abs()
    return output


def _architecture_comparison(primary: pd.DataFrame, robustness: pd.DataFrame) -> pd.DataFrame:
    keys = [key for key in ("rho", "capacity", "delta", "quantizer") if key in primary and key in robustness]
    if primary.empty or robustness.empty or not keys:
        return _empty(keys)
    fields = [
        field
        for field in ("absolute_policy_gap", "critical_collision_rate", "total_collision_rate")
        if field in primary and field in robustness
    ]
    left = primary[keys + fields].rename(columns={field: f"preload_all_{field}" for field in fields})
    right = robustness[keys + fields].rename(
        columns={field: f"schedule_next_after_transition_{field}" for field in fields}
    )
    comparison = left.merge(right, on=keys, validate="one_to_one")
    for field in fields:
        comparison[f"robustness_difference_{field}"] = (
            comparison[f"schedule_next_after_transition_{field}"]
            - comparison[f"preload_all_{field}"]
        )
    comparison["comparison_label"] = "robustness only; not primary observations"
    return comparison


def analyze_run_v2(run_dir: Path, analysis_config: Path | None = None) -> Path:
    """Create a new immutable analysis directory from persisted raw files."""
    config = load_analysis_config(analysis_config)
    raw_paths = [path for path in (run_dir / "raw").glob("*.parquet")]
    exact = _read_raw(run_dir, "exact_results.parquet")
    quantized = _read_raw(run_dir, "quantized_results.parquet")
    if exact.empty or quantized.empty:
        raise ValueError("analysis requires completed exact and quantized raw tables")
    schema2 = "raw_schema_version" in exact and "raw_schema_version" in quantized and (
        exact.raw_schema_version.eq(2).all() and quantized.raw_schema_version.eq(2).all()
    )
    if not schema2 and not config.include_legacy:
        raise ValueError("legacy schema-1 input requires include_legacy: true")
    config_hash = hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()
    analysis_id = f"v2-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{config_hash[:10]}"
    target = run_dir / "analysis" / analysis_id
    for name in ("derived", "figures", "tables", "report"):
        (target / name).mkdir(parents=True, exist_ok=name != "derived")
    provenance = {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "source_run_id": run_dir.name,
        "source_raw_hashes": {path.name: _sha256(path) for path in raw_paths},
        "config_hash": config_hash,
        **collect_provenance(run_dir.parent.parent),
        "legacy_input": not schema2,
        "collision_denominator_consistent": schema2,
    }
    save_yaml(asdict(config), target / "analysis_config.resolved.yaml")
    atomic_json(provenance, target / "provenance.json")
    if not schema2:
        q = quantized.copy()
        q["legacy_collision_event_fraction"] = q.get("collision_event_fraction")
        q["collision_denominator_consistent"] = False
        counts = {
            "measured_arrivals",
            "mixed_collided_ticks",
            "critical_collided_ticks",
            "critical_acceptance_difference",
        }
        if counts.issubset(q.columns):
            reconstructed = q.apply(
                lambda row: collision_rates(
                    int(row.measured_arrivals),
                    int(row.get("measurement_processed_ticks", 0)),
                    int(row.mixed_collided_ticks),
                    int(row.critical_collided_ticks),
                    int(row.critical_acceptance_difference),
                    legacy=True,
                ),
                axis=1,
            )
            q = pd.concat([q, pd.DataFrame(reconstructed.tolist())], axis=1)
        else:
            q["rate_reconstructed_from_counts"] = False
        atomic_parquet(q, target / "derived" / "legacy_quantized.parquet")
        _theory_metadata(run_dir, exact).to_csv(target / "derived" / "theory_validation.csv", index=False)
        return target
    quantized = quantized.copy()
    quantized["collision_denominator_consistent"] = True
    primary_quantized = quantized[
        quantized.arrival_scheduling_mode.eq(PRIMARY_ARCHITECTURE)
    ].copy()
    robustness_quantized = quantized[
        quantized.arrival_scheduling_mode.eq(ROBUSTNESS_ARCHITECTURE)
    ].copy()
    primary_exact = exact[exact.arrival_scheduling_mode.eq(PRIMARY_ARCHITECTURE)].copy()
    robustness_exact = exact[
        exact.arrival_scheduling_mode.eq(ROBUSTNESS_ARCHITECTURE)
    ].copy()
    paired = _paired(primary_quantized, primary_exact)
    robustness_paired = _paired(robustness_quantized, robustness_exact)
    summary = _configuration_summary(primary_quantized)
    robustness_summary = _configuration_summary(robustness_quantized)
    slopes, scaling, scaling_input = _scaling(primary_quantized, config)
    robustness_slopes, robustness_scaling, robustness_scaling_input = _scaling(
        robustness_quantized, config
    )
    predictor_workloads, predictor = _predictor_rows(paired, primary_quantized, config)
    robustness_predictor_workloads, robustness_predictor = _predictor_rows(
        robustness_paired, robustness_quantized, config
    )
    models = _predictor_models(predictor, predictor_workloads, config)
    robustness_models = _predictor_models(
        robustness_predictor, robustness_predictor_workloads, config
    )
    random, random_decomposition = _random_variance(primary_quantized, paired, config)
    insertion = _insertion(primary_quantized)
    robustness_insertion = _insertion(robustness_quantized)
    architecture_comparison = _architecture_comparison(predictor, robustness_predictor)
    atomic_parquet(quantized, target / "derived" / "quantized_v2.parquet")
    atomic_parquet(paired, target / "derived" / "paired_bias_decomposition.parquet")
    atomic_parquet(
        robustness_paired, target / "derived" / "robustness_paired_bias_decomposition.parquet"
    )
    atomic_parquet(summary, target / "derived" / "configuration_summary.parquet")
    atomic_parquet(
        robustness_summary, target / "derived" / "robustness_configuration_summary.parquet"
    )
    atomic_parquet(random, target / "derived" / "random_order_workload_variance.parquet")
    atomic_parquet(insertion, target / "derived" / "insertion_architecture.parquet")
    atomic_parquet(
        robustness_insertion, target / "derived" / "robustness_insertion_architecture.parquet"
    )
    atomic_parquet(scaling_input, target / "derived" / "collision_scaling_input.parquet")
    atomic_parquet(
        robustness_scaling_input, target / "derived" / "robustness_collision_scaling_input.parquet"
    )
    atomic_parquet(predictor_workloads, target / "derived" / "predictor_workload_rows.parquet")
    atomic_parquet(predictor, target / "derived" / "predictor_rows.parquet")
    atomic_parquet(
        robustness_predictor_workloads, target / "derived" / "robustness_predictor_workload_rows.parquet"
    )
    atomic_parquet(
        robustness_predictor, target / "derived" / "robustness_predictor_rows.parquet"
    )
    random_decomposition.to_csv(target / "derived" / "random_variance_decomposition.csv", index=False)
    slopes.to_csv(target / "derived" / "collision_scaling_workload_slopes.csv", index=False)
    scaling.to_csv(target / "derived" / "collision_scaling_summary.csv", index=False)
    robustness_slopes.to_csv(
        target / "derived" / "robustness_collision_scaling_workload_slopes.csv", index=False
    )
    robustness_scaling.to_csv(target / "derived" / "robustness_collision_scaling_summary.csv", index=False)
    models.to_csv(target / "derived" / "predictor_models.csv", index=False)
    robustness_models.to_csv(target / "derived" / "robustness_predictor_models.csv", index=False)
    architecture_comparison.to_csv(
        target / "derived" / "architecture_robustness_comparison.csv", index=False
    )
    pd.DataFrame([
        {
            "random_order_available": not random.empty,
            "policy": "random_order",
            "scope_note": "No random_order tasks are present in this full-v2 run; no random-order finding is estimated.",
        }
    ]).to_csv(target / "derived" / "random_order_scope.csv", index=False)
    theory = _theory_metadata(run_dir, primary_exact)
    theory.to_csv(target / "derived" / "theory_validation.csv", index=False)
    robustness_theory = _theory_metadata(run_dir, robustness_exact)
    robustness_theory.to_csv(target / "derived" / "robustness_theory_validation.csv", index=False)
    diagnostics_fields = [
        field
        for field in quantized
        if field.startswith(("arrival_quantization_error_", "service_quantization_error_"))
    ]
    diagnostic_keys = [key for key in ("quantizer", "rho", "capacity", "delta", "policy") if key in primary_quantized]
    diagnostics = primary_quantized.groupby(diagnostic_keys, as_index=False)[diagnostics_fields].mean()
    diagnostics.to_csv(target / "derived" / "quantization_diagnostics.csv", index=False)
    robustness_diagnostics = robustness_quantized.groupby(diagnostic_keys, as_index=False)[diagnostics_fields].mean()
    robustness_diagnostics.to_csv(
        target / "derived" / "robustness_quantization_diagnostics.csv", index=False
    )
    correlations: list[dict[str, Any]] = []
    for error in ("arrival_quantization_error_signed_mean", "service_quantization_error_signed_mean"):
        for outcome in ("packet_loss_probability", "throughput", "mean_waiting_time", "time_average_number_in_system"):
            usable = primary_quantized[[error, outcome]].dropna() if error in primary_quantized and outcome in primary_quantized else pd.DataFrame()
            if len(usable) > 2:
                correlations.append({
                    "error_metric": error, "outcome": outcome, "n": len(usable),
                    "pearson": usable.corr(method="pearson").iloc[0, 1],
                    "spearman": usable.corr(method="spearman").iloc[0, 1],
                    "interpretation": "association only; not causal",
                })
    pd.DataFrame(correlations).to_csv(target / "derived" / "quantization_correlations.csv", index=False)
    if not predictor.empty:
        identity = predictor.dropna(subset=["absolute_policy_gap", "critical_collision_rate"])
        identity_rows = []
        if len(identity) > 1:
            import statsmodels.api as sm

            for intercept in (True, False):
                design = identity[["critical_collision_rate"]]
                if intercept:
                    design = sm.add_constant(design)
                fit = sm.OLS(identity.absolute_policy_gap, design).fit(cov_type="HC3")
                identity_rows.append({
                    "model": "with_intercept" if intercept else "through_origin",
                    "n": len(identity), "r_squared": fit.rsquared,
                    "slope": fit.params["critical_collision_rate"],
                    "slope_hc3_se": fit.bse["critical_collision_rate"],
                    "intercept": fit.params.get("const", 0.0),
                    "interpretation": "identity test, not an estimator",
                })
        pd.DataFrame(identity_rows).to_csv(target / "derived" / "critical_identity_tests.csv", index=False)
    provenance["primary_architecture"] = PRIMARY_ARCHITECTURE
    provenance["robustness_architecture"] = ROBUSTNESS_ARCHITECTURE
    provenance["aggregation"] = {
        "collision_scaling": "Within workload-design and delta, mean arrival_first and departure_first; fit one log-log slope per workload-design over positive fine-delta values.",
        "predictor_models": "Within workload-paired AF/DF observations, aggregate to exactly one row per experimental configuration before fitting; bootstrap resamples workload replications within each configuration.",
        "validation_folds": "leave-analysis_configuration_id-out; configurations are disjoint between train and test.",
    }
    provenance["row_counts"] = {
        "primary_quantized_rows": len(primary_quantized),
        "robustness_quantized_rows": len(robustness_quantized),
        "primary_paired_workload_rows": len(paired),
        "primary_scaling_workload_slopes": len(slopes),
        "primary_scaling_summary_rows": len(scaling),
        "primary_predictor_workload_rows": len(predictor_workloads),
        "primary_predictor_configuration_rows": len(predictor),
        "robustness_predictor_configuration_rows": len(robustness_predictor),
        "random_order_rows": int((quantized.policy == "random_order").sum()),
    }
    provenance["random_order_scope"] = "absent from full-v2; no random-order result is estimated"
    validation = {
        "primary_architecture_only": bool(
            primary_quantized.arrival_scheduling_mode.eq(PRIMARY_ARCHITECTURE).all()
        ),
        "primary_scaling_has_no_policy_column": "policy" not in scaling.columns,
        "primary_scaling_workload_slope_rows": len(slopes),
        "primary_predictor_rows_unique": not predictor.analysis_configuration_id.duplicated().any(),
        "primary_predictor_rows": len(predictor),
        "primary_predictor_workload_rows": len(predictor_workloads),
        "predictor_validation_group": "analysis_configuration_id",
        "predictor_validation_folds": int(models.n_folds.max()) if not models.empty else 0,
        "robustness_rows_separate": bool(
            robustness_predictor.empty
            or robustness_predictor.arrival_scheduling_mode.eq(ROBUSTNESS_ARCHITECTURE).all()
        ),
        "random_order_available": not random.empty,
        "raw_hashes": provenance["source_raw_hashes"],
    }
    atomic_json(validation, target / "derived" / "analysis_validation.json")
    atomic_json(provenance, target / "provenance.json")
    return target
