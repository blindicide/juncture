"""Traceable Markdown findings report."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def build_report(run_dir: Path) -> None:
    report = run_dir / "report"
    report.mkdir(exist_ok=True)
    paired = pd.read_parquet(run_dir / "derived" / "paired_differences.parquet")
    regression = pd.read_csv(run_dir / "derived" / "regression_results.csv")
    validation = pd.read_csv(run_dir / "derived" / "theoretical_validation.csv")
    scaling = pd.read_csv(run_dir / "derived" / "collision_scaling_regression.csv")
    largest = paired.loc[paired.absolute_policy_range.idxmax()] if len(paired) else None
    lines = [
        "# Juncture research report",
        "",
        "## Objective",
        "",
        "Measure how finite timestamp resolution and equal-timestamp ordering affect a finite FIFO queue.",
        "",
        "## Model and design",
        "",
        "Each policy shares pre-generated arrival and service workloads with its exact reference.",
        "",
        "## Validation against M/M/1/K theory",
        "",
        "## Main quantitative findings",
        "",
    ]
    findings = []
    if len(validation):
        maximum_validation_error = validation.loc[validation.absolute_loss_difference.idxmax()]
        text = (
            "The largest exact-theory absolute packet-loss difference was "
            f"{maximum_validation_error.absolute_loss_difference:.6g} at "
            f"ρ={maximum_validation_error.rho}, K={int(maximum_validation_error.capacity)}."
        )
        lines.insert(lines.index("## Main quantitative findings"), f"- {text}")
        findings.append(
            {
                "finding_id": "exact_theory_validation",
                "text": text,
                "source_table": "theoretical_validation.csv",
                "source_columns": ["absolute_loss_difference", "rho", "capacity"],
                "filtering_conditions": "maximum absolute_loss_difference",
                "numeric_values": {
                    "absolute_loss_difference": float(
                        maximum_validation_error.absolute_loss_difference
                    )
                },
            }
        )
    if len(scaling):
        exponent = scaling.scaling_exponent.mean()
        text = f"The mean fitted collision-scaling exponent across available configurations was {exponent:.3g}."
        lines.append(f"- {text}")
        findings.append(
            {
                "finding_id": "collision_scaling_exponent",
                "text": text,
                "source_table": "collision_scaling_regression.csv",
                "source_columns": ["scaling_exponent"],
                "filtering_conditions": "mean across configurations",
                "numeric_values": {"mean_scaling_exponent": float(exponent)},
            }
        )
    if largest is not None:
        text = f"The largest observed policy range was {largest.absolute_policy_range:.6g} at ρ={largest.rho}, K={int(largest.capacity)}, δ={largest.delta}."
        lines.append(f"- {text}")
        findings.append(
            {
                "finding_id": "largest_policy_range",
                "text": text,
                "source_table": "paired_differences.parquet",
                "source_columns": ["absolute_policy_range", "rho", "capacity", "delta"],
                "filtering_conditions": "maximum absolute_policy_range",
                "numeric_values": {"absolute_policy_range": float(largest.absolute_policy_range)},
            }
        )
    for _, model in regression.iterrows():
        if model.get("model") == "C_critical_difference":
            text = f"The critical-collision predictor model had R²={model.r_squared:.3g}."
            lines.append(f"- {text}")
            findings.append(
                {
                    "finding_id": "critical_predictor_r2",
                    "text": text,
                    "source_table": "regression_results.csv",
                    "source_columns": ["r_squared"],
                    "filtering_conditions": "model=C_critical_difference",
                    "numeric_values": {"r_squared": float(model.r_squared)},
                }
            )
    lines += [
        "",
        "## Limitations",
        "",
        "Relative errors are undefined when the exact reference is zero. Waiting metrics include accepted measured-arrival jobs and can have survivor bias. These experiments model timestamp representation, not physical network timing.",
        "",
        "## Reproduction",
        "",
        f"`juncture analyze --run-dir {run_dir}`",
    ]
    (report / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (report / "findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
