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
    scaling_input = _load(analysis_dir, "collision_scaling_input.parquet")
    scaling_summary = _load(analysis_dir, "collision_scaling_summary.csv", parquet=False)
    scaling_slopes = _load(analysis_dir, "collision_scaling_workload_slopes.csv", parquet=False)
    insertion = _load(analysis_dir, "insertion_architecture.parquet")
    predictor = _load(analysis_dir, "predictor_rows.parquet")
    robustness_predictor = _load(analysis_dir, "robustness_predictor_rows.parquet")
    validation = json.loads((analysis_dir / "derived" / "analysis_validation.json").read_text(encoding="utf-8"))
    tables_data: dict[str, pd.DataFrame] = {
        "parameter_grid": summary,
        "theory_validation": _load(analysis_dir, "theory_validation.csv", parquet=False),
        "collision_scaling_summary": scaling_summary,
        "collision_scaling_workload_slopes": scaling_slopes,
        "af_df_gaps": paired,
        "quantizer_bias": _load(analysis_dir, "quantization_diagnostics.csv", parquet=False),
        "decomposition": paired,
        "ranked_sensitivity_bias": paired.sort_values("absolute_packet_loss_probability_gap", ascending=False) if "absolute_packet_loss_probability_gap" in paired else paired,
        "predictor_configurations": predictor,
        "predictor_models": _load(analysis_dir, "predictor_models.csv", parquet=False),
        "insertion_equivalence": insertion,
        "random_order_scope": _load(analysis_dir, "random_order_scope.csv", parquet=False),
        "analysis_validation": pd.DataFrame([validation]),
        "legacy_limitations": pd.DataFrame([{"legacy_input": provenance["legacy_input"], "collision_denominator_consistent": provenance["collision_denominator_consistent"], "limitation": "Schema-1 collision fractions are never relabelled as corrected."}]),
        "runtime_reproducibility": pd.DataFrame([{"analysis_id": provenance["analysis_id"], "source_run_id": provenance["source_run_id"], "git_commit": provenance.get("git_commit"), "raw_hashes": json.dumps(provenance["source_raw_hashes"], sort_keys=True)}]),
        "robustness_collision_scaling_summary": _load(analysis_dir, "robustness_collision_scaling_summary.csv", parquet=False),
        "robustness_collision_scaling_workload_slopes": _load(analysis_dir, "robustness_collision_scaling_workload_slopes.csv", parquet=False),
        "robustness_predictor_configurations": robustness_predictor,
        "robustness_predictor_models": _load(analysis_dir, "robustness_predictor_models.csv", parquet=False),
        "architecture_robustness_comparison": _load(analysis_dir, "architecture_robustness_comparison.csv", parquet=False),
    }
    for name, frame in tables_data.items():
        frame.to_csv(tables / f"{name}.csv", index=False)
        (tables / f"{name}.md").write_text(_markdown(frame), encoding="utf-8")
    manifest: list[dict[str, Any]] = []
    for language in ("en", "ru"):
        text = LABELS[language]
        base = {"analysis_id": provenance["analysis_id"], "source_run_id": provenance["source_run_id"], "git_commit": provenance.get("git_commit"), "created_utc": datetime.now(UTC).isoformat(), "language": language, "units": "probability (0–1)"}
        if not scaling_input.empty:
            fig, ax = plt.subplots()
            line = scaling_input.groupby("delta", as_index=False).deterministic_mean_collision_event_fraction.mean().sort_values("delta")
            ax.plot(line.delta, line.deterministic_mean_collision_event_fraction, marker="o", color="black", label="AF/DF midpoint")
            ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel(text["delta"]); ax.set_ylabel(text["collision"]); ax.legend()
            _save(fig, figures, f"collision_scaling_{language}", {**base, "figure_id": "collision_scaling", "source_table": "collision_scaling_input.parquet", "filters": "preload_all; AF/DF midpoint within workload-design; fine-delta range", "plotting_function": "build_assets", "scope": "primary"}, manifest)
        if not paired.empty and "midpoint_signed_bias_packet_loss_probability" in paired:
            fig, ax = plt.subplots()
            ax.scatter(paired.ordering_half_width_packet_loss_probability, paired.midpoint_signed_bias_packet_loss_probability, marker="o", facecolors="none", edgecolors="black")
            ax.axhline(0, color="black", linestyle=":"); ax.set_xlabel(text["gap"]); ax.set_ylabel(text["bias"])
            _save(fig, figures, f"bias_vs_ordering_{language}", {**base, "figure_id": "bias_vs_ordering", "source_table": "paired_bias_decomposition.parquet", "filters": "preload_all paired AF/DF", "plotting_function": "build_assets", "scope": "primary"}, manifest)
        if not paired.empty and paired.rho.nunique() > 1 and paired.delta.nunique() > 1:
            matrix = paired.pivot_table(index="rho", columns="delta", values="absolute_packet_loss_probability_gap", aggfunc="mean")
            fig, ax = plt.subplots(); image = ax.imshow(matrix, cmap="Greys", aspect="auto")
            ax.set_xticks(np.arange(len(matrix.columns)), [f"{value:g}" for value in matrix.columns]); ax.set_yticks(np.arange(len(matrix.index)), [f"{value:g}" for value in matrix.index]); ax.set_xlabel(text["delta"]); ax.set_ylabel("ρ"); fig.colorbar(image, ax=ax, label=text["gap"])
            _save(fig, figures, f"sensitivity_heatmap_{language}", {**base, "figure_id": "sensitivity_heatmap", "source_table": "paired_bias_decomposition.parquet", "filters": "preload_all; mean over available capacities/quantizers", "plotting_function": "build_assets", "scope": "primary"}, manifest)
        if not predictor.empty:
            fig, ax = plt.subplots(); ax.scatter(predictor.critical_collision_rate, predictor.absolute_policy_gap, marker="x", color="black")
            limit = max(float(predictor.critical_collision_rate.max()), float(predictor.absolute_policy_gap.max()), 1e-12); ax.plot([0, limit], [0, limit], color="black", linestyle="--", label="identity")
            ax.set_xlabel(text["critical"]); ax.set_ylabel(text["gap"]); ax.legend()
            _save(fig, figures, f"critical_predictor_{language}", {**base, "figure_id": "critical_predictor", "source_table": "predictor_rows.parquet", "filters": "one preload_all row per experimental configuration", "plotting_function": "build_assets", "scope": "primary"}, manifest)
        if not insertion.empty:
            match = [column for column in insertion if column.startswith("insertion_matches_")]
            if match:
                fig, ax = plt.subplots(); ax.bar(match, [insertion[column].mean() for column in match], color="white", edgecolor="black", hatch="//"); ax.set_ylim(0, 1); ax.set_ylabel("Fraction" if language == "en" else "Доля"); ax.set_xlabel(text["architecture"])
                _save(fig, figures, f"insertion_architecture_{language}", {**base, "figure_id": "insertion_architecture", "source_table": "insertion_architecture.parquet", "filters": "preload_all; exact integer acceptance matches", "plotting_function": "build_assets", "scope": "primary"}, manifest)
        if not robustness_predictor.empty:
            fig, ax = plt.subplots(); ax.scatter(robustness_predictor.critical_collision_rate, robustness_predictor.absolute_policy_gap, marker="x", color="black")
            ax.set_xlabel(text["critical"]); ax.set_ylabel(text["gap"])
            _save(fig, figures, f"robustness_critical_predictor_{language}", {**base, "figure_id": "robustness_critical_predictor", "source_table": "robustness_predictor_rows.parquet", "filters": "schedule_next_after_transition; one row per experimental configuration", "plotting_function": "build_assets", "scope": "robustness"}, manifest)
    pd.DataFrame(manifest).to_csv(figures / "manifest.csv", index=False)
    _build_report(report, provenance, tables_data, validation)
    artifact_rows = []
    for directory in (tables, figures, report):
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.name not in {"artifact_manifest.csv"}:
                artifact_rows.append({"path": str(path.relative_to(analysis_dir)), "sha256": _sha(path)})
    pd.DataFrame(artifact_rows).to_csv(analysis_dir / "artifact_manifest.csv", index=False)


def _build_report(
    report: Path, provenance: dict[str, Any], tables: dict[str, pd.DataFrame], validation: dict[str, Any]
) -> None:
    source = f"analysis={provenance['analysis_id']}; run={provenance['source_run_id']}; commit={provenance.get('git_commit')}"
    counts = provenance["row_counts"]
    (report / "summary.md").write_text(
        f"# Juncture Phase II summary\n\n{source}\n\n"
        f"Primary analysis uses only `{provenance['primary_architecture']}`: "
        f"{counts['primary_paired_workload_rows']} paired workload rows and "
        f"{counts['primary_predictor_configuration_rows']} experimental-configuration predictor rows. "
        f"`{provenance['robustness_architecture']}` is reported only as separately labelled robustness output.\n",
        encoding="utf-8",
    )
    (report / "methodology.md").write_text(
        f"# Methodology\n\n{source}\n\n"
        "Collision denominators are complete batches from the first through final measured arrival; post-final drain is excluded. "
        "For scaling, AF and DF collision-event fractions are averaged within each workload-design and delta before one log-log slope is fitted over positive fine-delta values. "
        "Predictor outcomes and collision predictors are AF/DF-paired at workload level, then averaged to exactly one experimental-configuration row before fitting. "
        "Bootstrap intervals resample workload replications within configurations; grouped validation leaves out complete experimental configurations.\n",
        encoding="utf-8",
    )
    theory = tables["theory_validation"]
    (report / "validation.md").write_text(
        f"# Validation\n\n{source}\n\nTheory is applied only when the scenario is M/M/1/K eligible. Rows: {len(theory)}. "
        f"Primary architecture only: {validation['primary_architecture_only']}. "
        f"Primary predictor rows unique: {validation['primary_predictor_rows_unique']}; "
        f"folds: {validation['predictor_validation_folds']} by {validation['predictor_validation_group']}.\n",
        encoding="utf-8",
    )
    scaling = tables["collision_scaling_summary"]
    estimate = float(scaling.mean_slope.mean()) if not scaling.empty else None
    findings = [{"finding_id": "primary_collision_scaling_mean_slope", "source_analysis_id": provenance["analysis_id"], "source_table": "collision_scaling_summary.csv", "columns": ["mean_slope", "bootstrap_ci95_low", "bootstrap_ci95_high"], "filters": "preload_all; configured fine-delta range", "aggregation": "AF/DF midpoint within workload-design, then workload-slope summary", "units": "log-log exponent", "estimate": estimate, "interval": None, "run_ids": [provenance["source_run_id"]], "commit": provenance.get("git_commit"), "text": "Primary collision scaling is summarized from one AF/DF-midpoint log-log slope per workload-design."}]
    (report / "findings.md").write_text(
        f"# Findings\n\n{source}\n\nPrimary collision scaling uses {counts['primary_scaling_workload_slopes']} workload-design slopes and {counts['primary_scaling_summary_rows']} summary rows. "
        "No AF/DF-separated scheduler observations are presented as primary results.\n",
        encoding="utf-8",
    )
    (report / "limitations.md").write_text(
        f"# Limitations\n\n{source}\n\n"
        "`random_order` is absent from this full-v2 run, so no random-order result is estimated or inferred. "
        "`schedule_next_after_transition` is a robustness architecture only and is not pooled with primary observations. "
        "Associations and regressions are non-causal.\n",
        encoding="utf-8",
    )
    (report / "findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
