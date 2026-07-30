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
from .provenance import collect_provenance
from .regression import fit_grouped_ols
from .schema import ANALYSIS_SCHEMA_VERSION
from .storage import atomic_json, atomic_parquet, save_yaml
from .theory import effective_throughput, stationary_loss_probability


@dataclass(frozen=True)
class AnalysisConfig:
    schema_version: int = 2
    fine_delta_max: float = 0.003
    sensitivity_cutoffs: list[float] | None = None
    bootstrap_resamples: int = 10_000
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


def _scaling(quantized: pd.DataFrame, config: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    use = quantized[
        quantized.policy.isin(["arrival_first", "departure_first"])
        & (quantized.delta > 0)
        & (quantized.delta <= config.fine_delta_max)
    ].copy()
    value = "collision_event_fraction"
    if value not in use:
        return _empty(["scaling_exponent"]), _empty(["delta"])
    group_keys = [key for key in ("rho", "capacity", "quantizer", "policy", "replication", "arrival_scheduling_mode") if key in use]
    rows: list[dict[str, Any]] = []
    for group_key, group in use.groupby(group_keys):
        rates = group.groupby("delta", as_index=False)[value].mean()
        rates = rates[rates[value] > 0]
        if len(rates) < 2:
            continue
        slope, intercept = np.polyfit(np.log(rates.delta), np.log(rates[value]), 1)
        row = dict(zip(group_keys, group_key if isinstance(group_key, tuple) else (group_key,)))
        row.update({"n_deltas": len(rates), "scaling_exponent": slope, "intercept": intercept})
        rows.append(row)
    replication_slopes = pd.DataFrame(rows)
    if replication_slopes.empty:
        return replication_slopes, use
    summary_keys = [key for key in ("rho", "capacity", "quantizer", "policy", "arrival_scheduling_mode") if key in replication_slopes]
    summary = replication_slopes.groupby(summary_keys, as_index=False).agg(
        n=("scaling_exponent", "size"), mean_slope=("scaling_exponent", "mean"),
        sd_slope=("scaling_exponent", "std"), median_slope=("scaling_exponent", "median"),
        q25_slope=("scaling_exponent", lambda x: x.quantile(.25)),
        q75_slope=("scaling_exponent", lambda x: x.quantile(.75)),
    )
    ci = [paired_bootstrap_ci(group.scaling_exponent.to_numpy(), seed=config.bootstrap_seed, resamples=config.bootstrap_resamples) for _, group in summary.merge(replication_slopes, on=summary_keys).groupby(summary_keys)]
    summary["bootstrap_ci95_low"] = [item[0] for item in ci]
    summary["bootstrap_ci95_high"] = [item[1] for item in ci]
    return summary, use


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
        atomic_parquet(q, target / "derived" / "legacy_quantized.parquet")
        _theory_metadata(run_dir, exact).to_csv(target / "derived" / "theory_validation.csv", index=False)
        return target
    quantized = quantized.copy()
    quantized["collision_denominator_consistent"] = True
    paired = _paired(quantized, exact)
    summary = _configuration_summary(quantized)
    scaling, scaling_input = _scaling(quantized, config)
    random, random_decomposition = _random_variance(quantized, paired, config)
    insertion = _insertion(quantized)
    atomic_parquet(quantized, target / "derived" / "quantized_v2.parquet")
    atomic_parquet(paired, target / "derived" / "paired_bias_decomposition.parquet")
    atomic_parquet(summary, target / "derived" / "configuration_summary.parquet")
    atomic_parquet(random, target / "derived" / "random_order_workload_variance.parquet")
    atomic_parquet(insertion, target / "derived" / "insertion_architecture.parquet")
    atomic_parquet(scaling_input, target / "derived" / "collision_scaling_input.parquet")
    random_decomposition.to_csv(target / "derived" / "random_variance_decomposition.csv", index=False)
    scaling.to_csv(target / "derived" / "collision_scaling_replication_slopes.csv", index=False)
    theory = _theory_metadata(run_dir, exact)
    theory.to_csv(target / "derived" / "theory_validation.csv", index=False)
    diagnostics_fields = [
        field
        for field in quantized
        if field.startswith(("arrival_quantization_error_", "service_quantization_error_"))
    ]
    diagnostic_keys = [key for key in ("quantizer", "rho", "capacity", "delta", "policy") if key in quantized]
    diagnostics = quantized.groupby(diagnostic_keys, as_index=False)[diagnostics_fields].mean()
    diagnostics.to_csv(target / "derived" / "quantization_diagnostics.csv", index=False)
    correlations: list[dict[str, Any]] = []
    for error in ("arrival_quantization_error_signed_mean", "service_quantization_error_signed_mean"):
        for outcome in ("packet_loss_probability", "throughput", "mean_waiting_time", "time_average_number_in_system"):
            usable = quantized[[error, outcome]].dropna() if error in quantized and outcome in quantized else pd.DataFrame()
            if len(usable) > 2:
                correlations.append({
                    "error_metric": error, "outcome": outcome, "n": len(usable),
                    "pearson": usable.corr(method="pearson").iloc[0, 1],
                    "spearman": usable.corr(method="spearman").iloc[0, 1],
                    "interpretation": "association only; not causal",
                })
    pd.DataFrame(correlations).to_csv(target / "derived" / "quantization_correlations.csv", index=False)
    predictor = paired.copy()
    if not predictor.empty:
        predictor["absolute_policy_gap"] = predictor.get("absolute_packet_loss_probability_gap")
        predictor["inverse_capacity"] = 1 / predictor.capacity
        collision = quantized.groupby(["pair_id", "arrival_scheduling_mode"], as_index=False).agg(
            total_collision_rate=("collision_event_fraction", "mean"),
            mixed_collision_rate=("mixed_collision_rate", "mean"),
            critical_collision_rate=("critical_acceptance_difference_rate", "mean"),
        )
        predictor = predictor.merge(collision, on=["pair_id", "arrival_scheduling_mode"], how="left")
        models = [
            fit_grouped_ols(predictor, "absolute_policy_gap", [field], name, "workload_id")
            for field, name in (
                ("total_collision_rate", "total"),
                ("mixed_collision_rate", "mixed"),
                ("critical_collision_rate", "critical"),
            )
        ]
        models.append(fit_grouped_ols(predictor, "absolute_policy_gap", ["critical_collision_rate", "rho", "inverse_capacity", "delta"], "multivariable", "workload_id"))
        pd.DataFrame(models).to_csv(target / "derived" / "predictor_models.csv", index=False)
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
        atomic_parquet(predictor, target / "derived" / "predictor_rows.parquet")
    return target
