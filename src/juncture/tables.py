"""Publication-facing tables from persisted analyses."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _markdown(frame: pd.DataFrame) -> str:
    """Render a small Markdown table without an optional tabulate dependency."""
    columns = [str(column) for column in frame.columns]
    rows = [
        [str(value).replace("|", "\\|") for value in row]
        for row in frame.fillna("").itertuples(index=False, name=None)
    ]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def build_tables(run_dir: Path) -> None:
    target = run_dir / "tables"
    target.mkdir(exist_ok=True)
    summary = pd.read_parquet(run_dir / "derived" / "configuration_summary.parquet")
    paired = pd.read_parquet(run_dir / "derived" / "paired_differences.parquet")
    frames: dict[str, pd.DataFrame] = {
        "mean_packet_loss": summary,
        "paired_policy_differences": paired,
        "largest_absolute_sensitivity": paired.reindex(
            paired.absolute_policy_range.abs().sort_values(ascending=False).index
        ).head(20),
        "predictor_models": pd.read_csv(run_dir / "derived" / "regression_results.csv"),
        "thresholds": pd.read_csv(run_dir / "derived" / "threshold_results.csv"),
        "paired_bootstrap": pd.read_parquet(
            run_dir / "derived" / "paired_bootstrap_summary.parquet"
        ),
        "theoretical_validation": pd.read_csv(run_dir / "derived" / "theoretical_validation.csv"),
        "collision_scaling_regression": pd.read_csv(
            run_dir / "derived" / "collision_scaling_regression.csv"
        ),
    }
    random_variance = run_dir / "derived" / "random_order_variance.csv"
    if random_variance.exists():
        frames["random_order_variance"] = pd.read_csv(random_variance)
    for name, frame in frames.items():
        frame.to_csv(target / f"{name}.csv", index=False)
        (target / f"{name}.md").write_text(_markdown(frame), encoding="utf-8")
