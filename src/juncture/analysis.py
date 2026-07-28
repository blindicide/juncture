"""Analysis from persisted result tables only."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .bootstrap import paired_bootstrap_ci
from .regression import fit_ols
from .storage import atomic_parquet
from .theory import effective_throughput, stationary_loss_probability


def _summarize_paired(group: pd.DataFrame) -> pd.Series:
    values = group["loss_gap_AF_DF"].dropna().to_numpy(dtype=float)
    if not len(values):
        return pd.Series(dtype=float)
    low, high = paired_bootstrap_ci(values, seed=20260727, resamples=1_000)
    return pd.Series(
        {
            "n": len(values),
            "mean_loss_gap_AF_DF": values.mean(),
            "sd_loss_gap_AF_DF": values.std(ddof=1) if len(values) > 1 else 0.0,
            "median_loss_gap_AF_DF": float(np.median(values)),
            "iqr_loss_gap_AF_DF": float(np.subtract(*np.quantile(values, [0.75, 0.25]))),
            "bootstrap_ci95_low": low,
            "bootstrap_ci95_high": high,
        }
    )


def analyze_run(run_dir: Path) -> None:
    exact = pd.read_parquet(run_dir / "raw" / "exact_results.parquet")
    quantized = pd.read_parquet(run_dir / "raw" / "quantized_results.parquet")
    join_columns = ["replication", "rho", "capacity", "workload_seed"]
    ref = exact[
        join_columns + ["packet_loss_probability", "throughput", "mean_waiting_time"]
    ].rename(
        columns={
            "packet_loss_probability": "exact_packet_loss_probability",
            "throughput": "exact_throughput",
            "mean_waiting_time": "exact_mean_waiting_time",
        }
    )
    joined = quantized.merge(ref, on=join_columns, how="left", validate="many_to_one")
    for metric, ref_metric in [
        ("packet_loss_probability", "exact_packet_loss_probability"),
        ("throughput", "exact_throughput"),
        ("mean_waiting_time", "exact_mean_waiting_time"),
    ]:
        stem = metric.replace("_probability", "").replace("mean_", "mean_")
        signed = joined[metric] - joined[ref_metric]
        joined[f"signed_{stem}_error"] = signed
        joined[f"absolute_{stem}_error"] = signed.abs()
        joined[f"relative_{stem}_error"] = np.where(
            joined[ref_metric].notna() & (joined[ref_metric] != 0),
            signed.abs() / joined[ref_metric].abs(),
            np.nan,
        )
    atomic_parquet(
        joined.sort_values("task_id", kind="stable"),
        run_dir / "derived" / "quantized_with_accuracy.parquet",
    )

    key = ["replication", "rho", "capacity", "delta", "quantizer", "workload_seed"]
    pivot = joined.pivot_table(
        index=key, columns="policy", values="packet_loss_probability", aggfunc="first"
    ).reset_index()
    if {"arrival_first", "departure_first"} <= set(pivot.columns):
        pivot["loss_gap_AF_DF"] = pivot["arrival_first"] - pivot["departure_first"]
    else:
        pivot["loss_gap_AF_DF"] = np.nan
    policy_values = [p for p in joined.policy.unique() if p in pivot]
    pivot["absolute_policy_range"] = pivot[policy_values].max(axis=1) - pivot[policy_values].min(
        axis=1
    )
    metrics = joined.groupby(key, as_index=False).agg(
        total_collision_rate=("collision_event_fraction", "mean"),
        mixed_collision_rate=("mixed_collision_rate", "mean"),
        critical_acceptance_difference_rate=("critical_acceptance_difference_rate", "mean"),
    )
    paired = pivot.merge(metrics, on=key, how="left")
    atomic_parquet(
        paired.sort_values(key, kind="stable"), run_dir / "derived" / "paired_differences.parquet"
    )
    paired_summary = (
        paired.groupby(["rho", "capacity", "delta", "quantizer"], group_keys=False)
        .apply(_summarize_paired, include_groups=False)
        .reset_index()
    )
    atomic_parquet(
        paired_summary.sort_values(["rho", "capacity", "delta", "quantizer"], kind="stable"),
        run_dir / "derived" / "paired_bootstrap_summary.parquet",
    )

    summary_keys = ["rho", "capacity", "delta", "quantizer", "policy"]
    summary = joined.groupby(summary_keys, as_index=False).agg(
        n=("packet_loss_probability", "size"),
        mean_packet_loss=("packet_loss_probability", "mean"),
        sd_packet_loss=("packet_loss_probability", "std"),
        mean_throughput=("throughput", "mean"),
        mean_waiting_time=("mean_waiting_time", "mean"),
        mean_collision_rate=("collision_event_fraction", "mean"),
        mean_critical_rate=("critical_acceptance_difference_rate", "mean"),
    )
    summary["se_packet_loss"] = summary.sd_packet_loss / np.sqrt(summary.n)
    summary["ci95_low_packet_loss"] = summary.mean_packet_loss - 1.96 * summary.se_packet_loss
    summary["ci95_high_packet_loss"] = summary.mean_packet_loss + 1.96 * summary.se_packet_loss
    atomic_parquet(
        summary.sort_values(summary_keys, kind="stable"),
        run_dir / "derived" / "configuration_summary.parquet",
    )
    models = [
        fit_ols(
            paired.assign(abs_gap=paired.loss_gap_AF_DF.abs()),
            "abs_gap",
            ["total_collision_rate"],
            "A_total_collision",
        ),
        fit_ols(
            paired.assign(abs_gap=paired.loss_gap_AF_DF.abs()),
            "abs_gap",
            ["mixed_collision_rate"],
            "B_mixed_collision",
        ),
        fit_ols(
            paired.assign(abs_gap=paired.loss_gap_AF_DF.abs()),
            "abs_gap",
            ["critical_acceptance_difference_rate"],
            "C_critical_difference",
        ),
        fit_ols(
            paired.assign(
                abs_gap=paired.loss_gap_AF_DF.abs(), inverse_capacity=1 / paired.capacity
            ),
            "abs_gap",
            ["critical_acceptance_difference_rate", "rho", "inverse_capacity", "delta"],
            "D_adjusted",
        ),
    ]
    pd.DataFrame(models).to_csv(run_dir / "derived" / "regression_results.csv", index=False)

    scaling_rows: list[dict[str, float | int]] = []
    for (rho, capacity), group in joined.groupby(["rho", "capacity"]):
        scaling = (
            group.groupby("delta", as_index=False)
            .collision_event_fraction.mean()
            .query("delta > 0 and collision_event_fraction > 0")
        )
        if len(scaling) >= 2:
            from scipy.stats import linregress

            fit = linregress(np.log(scaling.delta), np.log(scaling.collision_event_fraction))
            scaling_rows.append(
                {
                    "rho": rho,
                    "capacity": capacity,
                    "n_deltas": len(scaling),
                    "intercept": fit.intercept,
                    "scaling_exponent": fit.slope,
                    "standard_error": fit.stderr,
                    "ci95_low": fit.slope - 1.96 * fit.stderr,
                    "ci95_high": fit.slope + 1.96 * fit.stderr,
                    "r_squared": fit.rvalue**2,
                }
            )
    pd.DataFrame(scaling_rows).to_csv(
        run_dir / "derived" / "collision_scaling_regression.csv", index=False
    )

    validation = exact.groupby(["rho", "capacity"], as_index=False).agg(
        n=("packet_loss_probability", "size"),
        simulated_exact_loss=("packet_loss_probability", "mean"),
        simulated_effective_throughput=("throughput", "mean"),
    )
    validation["theoretical_loss"] = validation.apply(
        lambda row: stationary_loss_probability(float(row.rho), int(row.capacity)), axis=1
    )
    validation["theoretical_effective_throughput"] = validation.apply(
        lambda row: effective_throughput(float(row.rho), float(row.rho), int(row.capacity)), axis=1
    )
    validation["absolute_loss_difference"] = (
        validation.simulated_exact_loss - validation.theoretical_loss
    ).abs()
    validation["relative_loss_difference"] = np.where(
        validation.theoretical_loss != 0,
        validation.absolute_loss_difference / validation.theoretical_loss,
        np.nan,
    )
    validation.to_csv(run_dir / "derived" / "theoretical_validation.csv", index=False)

    random = joined[joined.policy == "random_order"]
    if len(random):
        random.groupby(["rho", "capacity", "delta", "quantizer"], as_index=False).agg(
            n=("packet_loss_probability", "size"),
            mean_loss=("packet_loss_probability", "mean"),
            sd_loss=("packet_loss_probability", "std"),
            median_loss=("packet_loss_probability", "median"),
            p05_loss=("packet_loss_probability", lambda x: x.quantile(0.05)),
            p95_loss=("packet_loss_probability", lambda x: x.quantile(0.95)),
        ).to_csv(run_dir / "derived" / "random_order_variance.csv", index=False)
    thresholds = (
        joined.assign(relative_error_pct=100 * joined.relative_packet_loss_error)
        .groupby(summary_keys, as_index=False)
        .agg(
            max_absolute_error=("absolute_packet_loss_error", "max"),
            max_relative_error=("relative_packet_loss_error", "max"),
        )
    )
    thresholds["exceeds_5_percent"] = thresholds.max_relative_error > 0.05
    thresholds["exceeds_10_percent"] = thresholds.max_relative_error > 0.10
    thresholds["exceeds_25_percent"] = thresholds.max_relative_error > 0.25
    thresholds.to_csv(run_dir / "derived" / "threshold_results.csv", index=False)
