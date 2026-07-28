"""Matplotlib-only publication figures generated from saved tables."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LABELS = {
    "en": {
        "delta": "Timestamp quantum δ",
        "loss": "Packet-loss probability",
        "gap": "Arrival-first − departure-first loss",
        "collision": "Collision-event fraction",
        "error": "Signed packet-loss error",
        "critical": "Critical acceptance-difference rate",
    },
    "ru": {
        "delta": "Квант времени δ",
        "loss": "Вероятность потери",
        "gap": "Потери: arrivals-first − departures-first",
        "collision": "Доля событий в коллизиях",
        "error": "Знаковая ошибка вероятности потери",
        "critical": "Частота критической разницы принятия",
    },
}


def _save(fig: plt.Figure, directory: Path, name: str) -> list[str]:
    paths = []
    for suffix in ("png", "svg", "pdf"):
        path = directory / f"{name}.{suffix}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        paths.append(path.name)
    plt.close(fig)
    return paths


def _record(
    manifest: list[dict[str, str]],
    filenames: list[str],
    figure_id: str,
    source: str,
    language: str,
    conditions: str = "all",
) -> None:
    for filename in filenames:
        manifest.append(
            {
                "filename": filename,
                "figure_id": figure_id,
                "source_dataset": source,
                "filtering_conditions": conditions,
                "plotting_function": "plot_run",
                "language": language,
                "creation_timestamp": datetime.now(UTC).isoformat(),
            }
        )


def plot_run(run_dir: Path, language: str = "en") -> None:
    labels = LABELS[language]
    figures = run_dir / "figures"
    figures.mkdir(exist_ok=True)
    data = pd.read_parquet(run_dir / "derived" / "quantized_with_accuracy.parquet")
    manifest: list[dict[str, str]] = []
    for (rho, capacity), group in data.groupby(["rho", "capacity"]):
        fig, ax = plt.subplots()
        for policy, series in group.groupby("policy"):
            line = (
                series.groupby("delta", as_index=False)
                .packet_loss_probability.mean()
                .sort_values("delta")
            )
            ax.plot(line.delta, line.packet_loss_probability, marker="o", label=policy)
        ax.set_xscale("log")
        ax.set_xlabel(labels["delta"])
        ax.set_ylabel(labels["loss"])
        ax.set_title(f"Packet loss, ρ={rho}, K={capacity}")
        ax.legend()
        name = f"loss_rho-{rho}_K-{capacity}_{language}"
        _record(
            manifest,
            _save(fig, figures, name),
            "loss_vs_delta",
            "quantized_with_accuracy.parquet",
            language,
            f"rho={rho};capacity={capacity}",
        )
    paired = pd.read_parquet(run_dir / "derived" / "paired_differences.parquet")
    if paired.loss_gap_AF_DF.notna().any():
        fig, ax = plt.subplots()
        for capacity, series in paired.groupby("capacity"):
            line = (
                series.groupby("delta", as_index=False).loss_gap_AF_DF.mean().sort_values("delta")
            )
            ax.plot(line.delta, line.loss_gap_AF_DF, marker="o", label=f"K={capacity}")
        ax.set_xscale("log")
        ax.set_xlabel(labels["delta"])
        ax.set_ylabel(labels["gap"])
        ax.set_title("Policy loss gap")
        ax.legend()
        _record(
            manifest,
            _save(fig, figures, f"policy_gap_{language}"),
            "policy_gap",
            "paired_differences.parquet",
            language,
        )
    fig, ax = plt.subplots()
    collision = (
        data.groupby("delta", as_index=False).collision_event_fraction.mean().sort_values("delta")
    )
    ax.plot(collision.delta, collision.collision_event_fraction, marker="o")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(labels["delta"])
    ax.set_ylabel(labels["collision"])
    ax.set_title("Collision scaling")
    _record(
        manifest,
        _save(fig, figures, f"collision_scaling_{language}"),
        "collision_scaling",
        "quantized_with_accuracy.parquet",
        language,
    )
    for column, figure_id, ylabel in [
        ("signed_packet_loss_error", "signed_loss_error", labels["error"]),
        ("critical_acceptance_difference_rate", "critical_collision_rate", labels["critical"]),
    ]:
        fig, ax = plt.subplots()
        for policy, series in data.groupby("policy"):
            line = series.groupby("delta", as_index=False)[column].mean().sort_values("delta")
            ax.plot(line.delta, line[column], marker="o", label=policy)
        ax.set_xscale("log")
        ax.set_xlabel(labels["delta"])
        ax.set_ylabel(ylabel)
        ax.set_title(figure_id.replace("_", " ").title())
        ax.legend()
        _record(
            manifest,
            _save(fig, figures, f"{figure_id}_{language}"),
            figure_id,
            "quantized_with_accuracy.parquet",
            language,
        )
    for x_column, figure_id, xlabel in [
        ("total_collision_rate", "total_collision_vs_gap", labels["collision"]),
        ("critical_acceptance_difference_rate", "critical_difference_vs_gap", labels["critical"]),
    ]:
        usable = paired.dropna(subset=[x_column, "loss_gap_AF_DF"])
        if len(usable):
            fig, ax = plt.subplots()
            ax.scatter(usable[x_column], usable.loss_gap_AF_DF.abs(), marker="o")
            ax.set_xlabel(xlabel)
            ax.set_ylabel("Absolute policy loss gap")
            ax.set_title(figure_id.replace("_", " ").title())
            _record(
                manifest,
                _save(fig, figures, f"{figure_id}_{language}"),
                figure_id,
                "paired_differences.parquet",
                language,
            )
    fig, ax = plt.subplots()
    ax.scatter(data.processed_events, data.simulation_runtime_seconds, marker="o")
    ax.set_xlabel("Processed events")
    ax.set_ylabel("Simulation runtime (s)")
    ax.set_title("Runtime versus processed events")
    _record(
        manifest,
        _save(fig, figures, f"runtime_vs_events_{language}"),
        "runtime_vs_events",
        "quantized_with_accuracy.parquet",
        language,
    )
    for capacity, subset in paired.groupby("capacity"):
        heat = subset.groupby(["rho", "delta"], as_index=False).absolute_policy_range.mean()
        if heat.rho.nunique() > 1 and heat.delta.nunique() > 1:
            matrix = heat.pivot(index="rho", columns="delta", values="absolute_policy_range")
            fig, ax = plt.subplots()
            image = ax.imshow(matrix.to_numpy(), aspect="auto", cmap="Greys")
            ax.set_xticks(np.arange(len(matrix.columns)), [f"{x:g}" for x in matrix.columns])
            ax.set_yticks(np.arange(len(matrix.index)), [f"{x:g}" for x in matrix.index])
            ax.set_xlabel(labels["delta"])
            ax.set_ylabel("ρ")
            ax.set_title(f"Policy sensitivity heatmap, K={capacity}")
            fig.colorbar(image, ax=ax, label="Absolute policy range")
            _record(
                manifest,
                _save(fig, figures, f"sensitivity_heatmap_K-{capacity}_{language}"),
                "sensitivity_heatmap",
                "paired_differences.parquet",
                language,
                f"capacity={capacity}",
            )
    pd.DataFrame(manifest).to_csv(figures / "manifest.csv", index=False)
