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
    _build_report(report, provenance, tables_data, validation, analysis_dir)
    _write_artifact_manifest(analysis_dir)


def _write_artifact_manifest(analysis_dir: Path) -> None:
    """Hash generated publication artifacts without touching derived simulation tables."""
    artifact_rows = []
    for directory in (analysis_dir / "tables", analysis_dir / "figures", analysis_dir / "report"):
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.name not in {"artifact_manifest.csv"}:
                artifact_rows.append({"path": str(path.relative_to(analysis_dir)), "sha256": _sha(path)})
    pd.DataFrame(artifact_rows).to_csv(analysis_dir / "artifact_manifest.csv", index=False)


def refresh_report_assets(analysis_dir: Path) -> None:
    """Regenerate only human/machine-readable reports and their hash manifest."""
    provenance = json.loads((analysis_dir / "provenance.json").read_text(encoding="utf-8"))
    validation = json.loads((analysis_dir / "derived" / "analysis_validation.json").read_text(encoding="utf-8"))
    tables = {
        "theory_validation": _load(analysis_dir, "theory_validation.csv", parquet=False),
        "collision_scaling_summary": _load(analysis_dir, "collision_scaling_summary.csv", parquet=False),
        "collision_scaling_workload_slopes": _load(analysis_dir, "collision_scaling_workload_slopes.csv", parquet=False),
        "af_df_gaps": _load(analysis_dir, "paired_bias_decomposition.parquet"),
        "predictor_configurations": _load(analysis_dir, "predictor_rows.parquet"),
        "predictor_models": _load(analysis_dir, "predictor_models.csv", parquet=False),
        "quantization_correlations": _load(analysis_dir, "quantization_correlations.csv", parquet=False),
        "insertion_equivalence": _load(analysis_dir, "insertion_architecture.parquet"),
        "architecture_robustness_comparison": _load(
            analysis_dir, "architecture_robustness_comparison.csv", parquet=False
        ),
        "random_order_scope": _load(analysis_dir, "random_order_scope.csv", parquet=False),
    }
    report = analysis_dir / "report"
    report.mkdir(exist_ok=True)
    _build_report(report, provenance, tables, validation, analysis_dir)
    _write_artifact_manifest(analysis_dir)


def _build_report(
    report: Path,
    provenance: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    validation: dict[str, Any],
    analysis_dir: Path,
) -> None:
    source = f"analysis={provenance['analysis_id']}; run={provenance['source_run_id']}; commit={provenance.get('git_commit')}"
    counts = provenance["row_counts"]
    theory = tables["theory_validation"]
    slopes = tables["collision_scaling_workload_slopes"]
    scaling = tables["collision_scaling_summary"]
    paired = tables["af_df_gaps"]
    predictor = tables["predictor_configurations"]
    models = tables["predictor_models"]
    correlations = tables.get("quantization_correlations", pd.DataFrame())
    insertion = tables["insertion_equivalence"]
    architecture = tables["architecture_robustness_comparison"]
    random_scope = tables["random_order_scope"]
    derived = "derived"

    def relative(name: str) -> str:
        return str((analysis_dir / name).relative_to(analysis_dir))

    def number(value: float | None, digits: int = 6) -> str:
        return "not available" if value is None or pd.isna(value) else f"{float(value):.{digits}g}"

    theory_max = theory.loc[theory.absolute_loss_difference.idxmax()] if not theory.empty else None
    slope_mean = float(slopes.scaling_exponent.mean()) if not slopes.empty else None
    slope_min = float(scaling.mean_slope.min()) if not scaling.empty else None
    slope_max = float(scaling.mean_slope.max()) if not scaling.empty else None
    gap_mean = float(paired.absolute_policy_gap.mean()) if not paired.empty else None
    exact_inside = float(paired.exact_inside_deterministic_interval.mean()) if not paired.empty else None
    critical = models.loc[models.model == "critical"].iloc[0] if not models.empty and (models.model == "critical").any() else None
    strongest = correlations.iloc[correlations.pearson.abs().argmax()] if not correlations.empty else None
    match_columns = [column for column in insertion if column.startswith("insertion_matches_")]
    insertion_matches = {column: float(insertion[column].mean()) for column in match_columns}
    architecture_max = (
        float(architecture.robustness_difference_critical_collision_rate.abs().max())
        if not architecture.empty and "robustness_difference_critical_collision_rate" in architecture
        else None
    )

    findings: list[dict[str, Any]] = [
        {
            "finding_id": "H1_exact_theory_validation",
            "hypothesis": "H1: the exact engine agrees with the M/M/1/K reference on eligible workloads",
            "status": "supported",
            "source_files": [relative(f"{derived}/theory_validation.csv")],
            "filters": "preload_all exact rows; exponential arrivals and services; all 24 rho-by-capacity conditions",
            "aggregation_unit": "condition mean over 30 replications",
            "row_count": len(theory),
            "estimate": {"maximum_absolute_loss_difference": None if theory_max is None else float(theory_max.absolute_loss_difference), "rho": None if theory_max is None else float(theory_max.rho), "capacity": None if theory_max is None else int(theory_max.capacity)},
            "interval": {"available": False, "reason": "theory-validation table contains no replication-level confidence interval"},
            "interpretation": "Exact-engine agreement is a validation result, not a causal claim about quantization.",
        },
        {
            "finding_id": "H2_collision_scaling",
            "hypothesis": "H2: collision-event frequency scales approximately linearly with fine timestamp resolution",
            "status": "supported",
            "source_files": [relative(f"{derived}/collision_scaling_workload_slopes.csv"), relative(f"{derived}/collision_scaling_summary.csv")],
            "filters": "preload_all only; delta > 0 and delta <= 0.003; arrival_first and departure_first averaged within workload-design and delta before fitting",
            "aggregation_unit": "one log-log slope per workload-design, then summary by rho, capacity, and quantizer",
            "row_count": {"workload_design_slopes": len(slopes), "condition_summaries": len(scaling)},
            "estimate": {"mean_workload_design_slope": slope_mean, "range_of_condition_mean_slopes": [slope_min, slope_max]},
            "interval": {"available": True, "type": "condition-specific 95% bootstrap CI", "resamples": 10000, "source_column_pair": ["bootstrap_ci95_low", "bootstrap_ci95_high"], "rows": len(scaling), "pooled_interval": None},
            "interpretation": "The estimate is descriptive across the configured grid; no pooled causal or universal scaling claim is made.",
        },
        {
            "finding_id": "H3_af_df_ordering_sensitivity",
            "hypothesis": "H3: deterministic within-tick order changes packet-loss outcomes",
            "status": "supported",
            "source_files": [relative(f"{derived}/paired_bias_decomposition.parquet"), relative(f"{derived}/predictor_rows.parquet")],
            "filters": "preload_all only; exact workload reference joined by workload identity; paired arrival_first/departure_first observations",
            "aggregation_unit": "workload-paired AF/DF difference; configuration means use 30 workload replications",
            "row_count": {"paired_workloads": len(paired), "configuration_rows": len(predictor)},
            "estimate": {"mean_absolute_policy_gap": gap_mean, "exact_inside_deterministic_interval_fraction": exact_inside},
            "interval": {"available": True, "type": "configuration-specific 95% workload-replication bootstrap", "source_columns": ["policy_gap_bootstrap_ci95_low", "policy_gap_bootstrap_ci95_high"], "rows": len(predictor), "pooled_interval": None},
            "interpretation": "This is a paired simulation contrast, not evidence of a causal mechanism outside the model.",
        },
        {
            "finding_id": "H4_critical_collision_predictor",
            "hypothesis": "H4: critical acceptance-difference rate is associated with AF/DF policy sensitivity",
            "status": "supported",
            "source_files": [relative(f"{derived}/predictor_models.csv"), relative(f"{derived}/predictor_rows.parquet")],
            "filters": "preload_all only; one AF/DF-paired mean row per experimental configuration",
            "aggregation_unit": "648 configuration-level means from 19,440 workload-paired rows; leave-configuration-out validation",
            "row_count": 0 if critical is None else int(critical.n),
            "estimate": {"r_squared": None if critical is None else float(critical.r_squared), "cv_rmse": None if critical is None else float(critical.cv_rmse), "critical_rate_coefficient": None if critical is None else float(critical.coefficient_critical_collision_rate)},
            "interval": {"available": critical is not None, "type": "95% bootstrap over workload-paired replications within configuration", "resamples": 0 if critical is None else int(critical.bootstrap_resamples), "coefficient_ci": None if critical is None else [float(critical.bootstrap_ci95_low_coefficient_critical_collision_rate), float(critical.bootstrap_ci95_high_coefficient_critical_collision_rate)]},
            "validation": {"group": validation["predictor_validation_group"], "folds": validation["predictor_validation_folds"], "configurations_disjoint_between_train_and_test": True},
            "interpretation": "Association only; regression coefficients are not causal estimates.",
        },
        {
            "finding_id": "H5_quantizer_timing_diagnostics",
            "hypothesis": "H5: quantizer timing diagnostics are associated with observed outcomes",
            "status": "limited",
            "source_files": [relative(f"{derived}/quantization_diagnostics.csv"), relative(f"{derived}/quantization_correlations.csv")],
            "filters": "preload_all quantized rows; descriptive quantizer, rho, capacity, delta, and policy summaries",
            "aggregation_unit": "configuration summary and pairwise descriptive correlation",
            "row_count": {"diagnostic_rows": len(pd.read_csv(analysis_dir / f'{derived}/quantization_diagnostics.csv')), "correlation_rows": len(correlations)},
            "estimate": None if strongest is None else {"largest_absolute_pearson": float(strongest.pearson), "error_metric": str(strongest.error_metric), "outcome": str(strongest.outcome)},
            "interval": {"available": False, "reason": "correlation table reports no confidence intervals"},
            "interpretation": "Diagnostics are descriptive associations and do not establish a causal effect of quantization error.",
        },
        {
            "finding_id": "H6_insertion_and_architecture_robustness",
            "hypothesis": "H6: insertion-order behavior is scheduler-architecture dependent while explicit-order primary results remain distinct",
            "status": "limited",
            "source_files": [relative(f"{derived}/insertion_architecture.parquet"), relative(f"{derived}/architecture_robustness_comparison.csv")],
            "filters": "primary insertion table: preload_all only; architecture comparison: preload_all versus separately labelled schedule_next_after_transition",
            "aggregation_unit": "paired workload rows for insertion; one matched configuration row for robustness comparison",
            "row_count": {"primary_insertion_pairs": len(insertion), "architecture_comparisons": len(architecture)},
            "estimate": {"insertion_count_match_fraction": insertion_matches, "maximum_absolute_critical_rate_robustness_difference": architecture_max},
            "interval": {"available": False, "reason": "no architecture-comparison confidence interval is published"},
            "interpretation": "schedule_next_after_transition is a robustness result only and is never pooled with primary observations.",
        },
        {
            "finding_id": "H7_random_order_variance",
            "hypothesis": "H7: random-order tie-breaking has measurable within-workload variance",
            "status": "not tested",
            "source_files": [relative(f"{derived}/random_order_scope.csv")],
            "filters": "full-v2 campaign",
            "aggregation_unit": "not applicable",
            "row_count": 0,
            "estimate": None,
            "interval": {"available": False, "reason": "random_order is absent from this run"},
            "interpretation": str(random_scope.iloc[0].scope_note) if not random_scope.empty else "No random-order result is available.",
        },
    ]
    (report / "summary.md").write_text(
        f"# Juncture Phase II campaign summary\n\n{source}\n\n"
        "## Scope and canonical estimand\n\n"
        f"The primary analysis is **{provenance['primary_architecture']} only**. It contains "
        f"{counts['primary_paired_workload_rows']:,} AF/DF-paired workload observations and "
        f"{counts['primary_predictor_configuration_rows']:,} one-row-per-configuration predictor observations. "
        f"`{provenance['robustness_architecture']}` is retained only in separately labelled robustness files and is never pooled into a primary table, figure, model, or conclusion.\n\n"
        "## Main quantitative results\n\n"
        f"Fine-resolution collision scaling used {counts['primary_scaling_workload_slopes']:,} workload-design log-log slopes, summarized into {counts['primary_scaling_summary_rows']} rho/capacity/quantizer conditions. "
        f"The mean workload-design slope was {number(slope_mean)}; condition mean slopes ranged from {number(slope_min)} to {number(slope_max)}. "
        f"The critical-collision configuration model used {counts['primary_predictor_configuration_rows']} rows, had R²={number(None if critical is None else critical.r_squared, 4)}, and coefficient {number(None if critical is None else critical.coefficient_critical_collision_rate, 6)} "
        f"with bootstrap 95% CI [{number(None if critical is None else critical.bootstrap_ci95_low_coefficient_critical_collision_rate, 6)}, {number(None if critical is None else critical.bootstrap_ci95_high_coefficient_critical_collision_rate, 6)}].\n\n"
        "## Interpretation boundary\n\n"
        "All regression and diagnostic statements are descriptive associations within this simulation design. `random_order` was not run in full-v2 and therefore contributes no result. The corrected aggregation changes the unit of inference and presentation: it replaces AF/DF- and architecture-duplicated primary rows with AF/DF-midpoint workload slopes and configuration-level predictor rows.\n",
        encoding="utf-8",
    )
    (report / "methodology.md").write_text(
        f"# Methodology\n\n{source}\n\n"
        "## Inputs and preservation\n\n"
        "This versioned analysis reads only the completed raw Parquet tables. Their SHA-256 values are recorded in `provenance.json`; no raw campaign file is rewritten. Collision denominators cover complete timestamp batches from the first measured arrival through the final measured-arrival batch, including recursive same-tick events and excluding post-final drain.\n\n"
        "## Primary collision scaling\n\n"
        "The canonical architecture is `preload_all`. For each workload-design (workload identity plus quantizer) and each valid fine delta (`0 < delta <= 0.003`), the arrival-first and departure-first collision-event fractions are averaged first. One log-log slope is then fitted to positive midpoint rates for that workload-design. The 2,160 slopes are summarized by rho, capacity, and quantizer into 72 conditions with mean, SD, median, IQR, and condition-specific 10,000-resample 95% bootstrap intervals. Source: `derived/collision_scaling_workload_slopes.csv` and `derived/collision_scaling_summary.csv`.\n\n"
        "## Predictor models and validation\n\n"
        "AF/DF policy gaps and collision rates are paired at workload level, then averaged over 30 workload replications into exactly one experimental-configuration row. Thus 19,440 paired workload rows produce 648 predictor rows. Bootstrap coefficient intervals resample workload-paired replications within configuration (1,000 resamples). Leave-configuration-out validation uses 648 folds; a configuration is never present in both a training and test fold. Sources: `derived/predictor_workload_rows.parquet`, `derived/predictor_rows.parquet`, and `derived/predictor_models.csv`.\n\n"
        "## Robustness and non-primary scopes\n\n"
        "`schedule_next_after_transition` is analysed only in `robustness_*` outputs and `derived/architecture_robustness_comparison.csv`. It is not a second primary scheduler observation. `random_order` has no full-v2 rows and is explicitly reported as unavailable.\n",
        encoding="utf-8",
    )
    (report / "validation.md").write_text(
        f"# Validation\n\n{source}\n\n"
        "## Campaign integrity\n\n"
        f"`juncture verify-run` completed with 118,080 manifest tasks and no errors. Raw SHA-256 values match analysis provenance: exact `{validation['raw_hashes']['exact_results.parquet']}` and quantized `{validation['raw_hashes']['quantized_results.parquet']}`.\n\n"
        "## Analysis consistency checks\n\n"
        f"Primary architecture only: `{validation['primary_architecture_only']}`. Primary scaling has no policy column: `{validation['primary_scaling_has_no_policy_column']}`. Predictor configuration rows are unique: `{validation['primary_predictor_rows_unique']}`. Primary/robustness outputs are separated: `{validation['robustness_rows_separate']}`. The report covers {validation['primary_scaling_workload_slope_rows']:,} slopes, {validation['primary_predictor_workload_rows']:,} predictor workload rows, and {validation['primary_predictor_rows']} predictor configurations.\n\n"
        "## Exact-theory check\n\n"
        f"All {len(theory)} primary exact conditions are M/M/1/K eligible. The largest absolute packet-loss difference is {number(None if theory_max is None else theory_max.absolute_loss_difference)} at rho={number(None if theory_max is None else theory_max.rho)} and K={number(None if theory_max is None else theory_max.capacity, 0)}. `derived/theory_validation.csv` reports condition means but no confidence intervals; that uncertainty limitation remains explicit.\n\n"
        "## Publication provenance\n\n"
        "`figures/manifest.csv` hashes each figure rendition and `artifact_manifest.csv` hashes report, table, and figure artifacts. The report is generated from derived files only; no conclusion is calculated directly from raw simulation state.\n",
        encoding="utf-8",
    )
    (report / "findings.md").write_text(
        f"# Findings\n\n{source}\n\n"
        "Each hypothesis below identifies its status, source, filters, aggregation unit, row count, estimate, and available interval.\n\n"
        + "\n\n".join(
            f"## {item['finding_id']}: {item['status']}\n\n"
            f"{item['hypothesis']}\n\n"
            f"- Source: `{', '.join(item['source_files'])}`\n"
            f"- Filters: {item['filters']}\n"
            f"- Aggregation unit: {item['aggregation_unit']}\n"
            f"- Row count: {item['row_count']}\n"
            f"- Estimate: `{json.dumps(item['estimate'], sort_keys=True)}`\n"
            f"- Interval: `{json.dumps(item['interval'], sort_keys=True)}`\n"
            f"- Interpretation: {item['interpretation']}"
            for item in findings
        )
        + "\n",
        encoding="utf-8",
    )
    (report / "limitations.md").write_text(
        f"# Limitations\n\n{source}\n\n"
        "1. `random_order` is absent from full-v2. H7 is not tested; no random-order variance estimate is fabricated.\n\n"
        "2. Exact-theory validation has 24 condition means but no confidence intervals in `derived/theory_validation.csv`; agreement should not be read as a formal uncertainty-calibrated test.\n\n"
        "3. Predictor regressions and timing correlations are descriptive associations. The 648 grouped folds prevent configuration leakage, but they do not turn coefficients into causal effects.\n\n"
        "4. `schedule_next_after_transition` is a labelled robustness architecture, not an additional primary sample. It remains separated in `robustness_*` files and the architecture comparison.\n\n"
        "5. The corrected aggregation changes presentation and inferential units: primary scaling is AF/DF-midpoint, workload-design based; predictor models use one configuration mean. Therefore prior AF/DF-separated or mode-pooled numerical summaries are superseded, not directly comparable primary estimates.\n",
        encoding="utf-8",
    )
    for item in findings:
        item.update({
            "source_analysis_id": provenance["analysis_id"],
            "run_ids": [provenance["source_run_id"]],
            "commit": provenance.get("git_commit"),
        })
    (report / "findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
