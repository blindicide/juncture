"""Traceable publication tables, bilingual figures, and compact reports."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LABELS = {
    "en": {
        "delta": "Timestamp quantum δ", "collision": "Collision-event fraction",
        "gap": "AF–DF packet-loss gap", "bias": "Midpoint packet-loss bias",
        "critical": "Critical acceptance-difference rate", "density": "Density",
        "architecture": "Arrival scheduling architecture", "value": "Packet-loss probability",
    },
    "ru": {
        "delta": "Квант времени δ", "collision": "Доля событий в коллизиях",
        "gap": "Разность потерь AF–DF", "bias": "Смещение середины по вероятности потерь",
        "critical": "Частота критического различия принятия", "density": "Плотность",
        "architecture": "Архитектура планирования поступлений", "value": "Вероятность потерь",
    },
}


def _markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows.\n"
    columns = [str(column) for column in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in frame.fillna("").itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines) + "\n"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(fig: plt.Figure, target: Path, stem: str, metadata: dict[str, Any], manifest: list[dict[str, Any]]) -> None:
    for suffix in ("png", "svg", "pdf"):
        path = target / f"{stem}.{suffix}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        manifest.append({**metadata, "filename": path.name, "sha256": _sha(path)})
    plt.close(fig)


def _load(analysis_dir: Path, name: str, parquet: bool = True) -> pd.DataFrame:
    path = analysis_dir / "derived" / name
    if not path.exists():
        return pd.DataFrame()
    if parquet:
        return pd.read_parquet(path)
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def build_assets(analysis_dir: Path) -> None:
    """Build all assets from persisted v2 tables, never from raw simulation state."""
    provenance = json.loads((analysis_dir / "provenance.json").read_text(encoding="utf-8"))
    figures = analysis_dir / "figures"
    tables = analysis_dir / "tables"
    report = analysis_dir / "report"
    figures.mkdir(exist_ok=True); tables.mkdir(exist_ok=True); report.mkdir(exist_ok=True)
    summary = _load(analysis_dir, "configuration_summary.parquet")
    paired = _load(analysis_dir, "paired_bias_decomposition.parquet")
    scaling = _load(analysis_dir, "collision_scaling_input.parquet")
    insertion = _load(analysis_dir, "insertion_architecture.parquet")
    random = _load(analysis_dir, "random_order_workload_variance.parquet")
    predictor = _load(analysis_dir, "predictor_rows.parquet")
    tables_data: dict[str, pd.DataFrame] = {
        "parameter_grid": summary,
        "theory_validation": _load(analysis_dir, "theory_validation.csv", parquet=False),
        "corrected_scaling": _load(analysis_dir, "collision_scaling_replication_slopes.csv", parquet=False),
        "af_df_gaps": paired,
        "quantizer_bias": _load(analysis_dir, "quantization_diagnostics.csv", parquet=False),
        "decomposition": paired,
        "ranked_sensitivity_bias": paired.sort_values("absolute_packet_loss_probability_gap", ascending=False) if "absolute_packet_loss_probability_gap" in paired else paired,
        "predictor_models": _load(analysis_dir, "predictor_models.csv", parquet=False),
        "insertion_equivalence": insertion,
        "random_variance": random,
        "distribution_robustness": _load(analysis_dir, "theory_validation.csv", parquet=False),
        "legacy_limitations": pd.DataFrame([{"legacy_input": provenance["legacy_input"], "collision_denominator_consistent": provenance["collision_denominator_consistent"], "limitation": "Schema-1 collision fractions are never relabelled as corrected."}]),
        "runtime_reproducibility": pd.DataFrame([{"analysis_id": provenance["analysis_id"], "source_run_id": provenance["source_run_id"], "git_commit": provenance.get("git_commit"), "raw_hashes": json.dumps(provenance["source_raw_hashes"], sort_keys=True)}]),
    }
    for name, frame in tables_data.items():
        frame.to_csv(tables / f"{name}.csv", index=False)
        (tables / f"{name}.md").write_text(_markdown(frame), encoding="utf-8")
    manifest: list[dict[str, Any]] = []
    for language in ("en", "ru"):
        text = LABELS[language]
        base = {"analysis_id": provenance["analysis_id"], "source_run_id": provenance["source_run_id"], "git_commit": provenance.get("git_commit"), "created_utc": datetime.now(UTC).isoformat(), "language": language, "units": "probability (0–1)"}
        if not scaling.empty:
            fig, ax = plt.subplots()
            for policy, group in scaling.groupby("policy"):
                line = group.groupby("delta", as_index=False).collision_event_fraction.mean().sort_values("delta")
                ax.plot(line.delta, line.collision_event_fraction, marker="o", linestyle="-" if policy == "departure_first" else "--", label=policy)
            ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel(text["delta"]); ax.set_ylabel(text["collision"]); ax.legend()
            _save(fig, figures, f"collision_scaling_{language}", {**base, "figure_id": "collision_scaling", "source_table": "collision_scaling_input.parquet", "filters": "AF/DF; configured fine-delta range", "plotting_function": "build_assets"}, manifest)
        if not paired.empty and "midpoint_signed_bias_packet_loss_probability" in paired:
            fig, ax = plt.subplots()
            ax.scatter(paired.ordering_half_width_packet_loss_probability, paired.midpoint_signed_bias_packet_loss_probability, marker="o", facecolors="none", edgecolors="black")
            ax.axhline(0, color="black", linestyle=":"); ax.set_xlabel(text["gap"]); ax.set_ylabel(text["bias"])
            _save(fig, figures, f"bias_vs_ordering_{language}", {**base, "figure_id": "bias_vs_ordering", "source_table": "paired_bias_decomposition.parquet", "filters": "paired AF/DF", "plotting_function": "build_assets"}, manifest)
        if not paired.empty and paired.rho.nunique() > 1 and paired.delta.nunique() > 1:
            matrix = paired.pivot_table(index="rho", columns="delta", values="absolute_packet_loss_probability_gap", aggfunc="mean")
            fig, ax = plt.subplots(); image = ax.imshow(matrix, cmap="Greys", aspect="auto")
            ax.set_xticks(np.arange(len(matrix.columns)), [f"{value:g}" for value in matrix.columns]); ax.set_yticks(np.arange(len(matrix.index)), [f"{value:g}" for value in matrix.index]); ax.set_xlabel(text["delta"]); ax.set_ylabel("ρ"); fig.colorbar(image, ax=ax, label=text["gap"])
            _save(fig, figures, f"sensitivity_heatmap_{language}", {**base, "figure_id": "sensitivity_heatmap", "source_table": "paired_bias_decomposition.parquet", "filters": "mean over available capacities/quantizers", "plotting_function": "build_assets"}, manifest)
        if not predictor.empty:
            fig, ax = plt.subplots(); ax.scatter(predictor.critical_collision_rate, predictor.absolute_policy_gap, marker="x", color="black")
            limit = max(float(predictor.critical_collision_rate.max()), float(predictor.absolute_policy_gap.max()), 1e-12); ax.plot([0, limit], [0, limit], color="black", linestyle="--", label="identity")
            ax.set_xlabel(text["critical"]); ax.set_ylabel(text["gap"]); ax.legend()
            _save(fig, figures, f"critical_predictor_{language}", {**base, "figure_id": "critical_predictor", "source_table": "predictor_rows.parquet", "filters": "paired AF/DF", "plotting_function": "build_assets"}, manifest)
        if not insertion.empty:
            match = [column for column in insertion if column.startswith("insertion_matches_")]
            if match:
                fig, ax = plt.subplots(); ax.bar(match, [insertion[column].mean() for column in match], color="white", edgecolor="black", hatch="//"); ax.set_ylim(0, 1); ax.set_ylabel("Fraction" if language == "en" else "Доля"); ax.set_xlabel(text["architecture"])
                _save(fig, figures, f"insertion_architecture_{language}", {**base, "figure_id": "insertion_architecture", "source_table": "insertion_architecture.parquet", "filters": "exact integer acceptance matches", "plotting_function": "build_assets"}, manifest)
        if not random.empty:
            fig, ax = plt.subplots(); ax.hist(random.tie_variance.dropna(), bins=min(20, max(1, len(random))), color="white", edgecolor="black", hatch="..")
            ax.set_xlabel("Tie variance" if language == "en" else "Дисперсия при жребии"); ax.set_ylabel(text["density"])
            _save(fig, figures, f"random_order_distribution_{language}", {**base, "figure_id": "random_order_distribution", "source_table": "random_order_workload_variance.parquet", "filters": "workload-level hierarchy", "plotting_function": "build_assets"}, manifest)
    pd.DataFrame(manifest).to_csv(figures / "manifest.csv", index=False)
    _build_report(report, provenance, tables_data)


def _build_report(report: Path, provenance: dict[str, Any], tables: dict[str, pd.DataFrame]) -> None:
    source = f"analysis={provenance['analysis_id']}; run={provenance['source_run_id']}; commit={provenance.get('git_commit')}"
    (report / "summary.md").write_text(f"# Juncture Phase II summary\n\n{source}\n\nThis analysis is traceable to persisted raw hashes. Smoke-sized output is validation only and supports no scientific conclusion.\n", encoding="utf-8")
    (report / "methodology.md").write_text(f"# Methodology\n\n{source}\n\nCollision denominators are complete batches from the first through final measured arrival; post-final drain is excluded. AF/DF midpoint bias is separated from ordering half-width.\n", encoding="utf-8")
    theory = tables["theory_validation"]
    (report / "validation.md").write_text(f"# Validation\n\n{source}\n\nTheory is applied only when the scenario is M/M/1/K eligible. Rows: {len(theory)}.\n", encoding="utf-8")
    findings = [{"finding_id": "smoke_scope", "source_analysis_id": provenance["analysis_id"], "source_table": "runtime_reproducibility.csv", "columns": ["analysis_id", "source_run_id"], "filters": "all", "aggregation": "none", "units": "n/a", "estimate": None, "interval": None, "run_ids": [provenance["source_run_id"]], "commit": provenance.get("git_commit"), "text": "Smoke output validates pipeline execution only; it is not a scientific finding."}]
    (report / "findings.md").write_text(f"# Findings\n\n{source}\n\nNo scientific conclusions are drawn from smoke-sized data.\n", encoding="utf-8")
    (report / "limitations.md").write_text(f"# Limitations\n\n{source}\n\nLegacy schema-1 collision fractions remain inconsistent and are labelled legacy. Associations and regressions are non-causal; full campaigns are required for inference.\n", encoding="utf-8")
    (report / "findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
