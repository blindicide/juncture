"""Phase II.2.1 publication repairs using immutable Phase II.2 outputs only."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .storage import atomic_json, save_yaml

SOURCE_ID = "v2.2-20260801T081533769838Z-fbfe1698"
PRIMARY = "preload_all"
FORBIDDEN_RUSSIAN = (
    "arrival_first", "departure_first", "insertion_order", "preload_all",
    "schedule_next_after_transition", "AF–DF gap", "collision scaling", "critical rate",
)
PREDICTOR_TERMS = {
    "total": "total_collision_rate",
    "mixed": "mixed_collision_rate",
    "critical": "critical_collision_rate",
    "multivariable": "critical_collision_rate",
}
ARCHITECTURE_LABELS = {
    PRIMARY: {"en": "Preload arrivals", "ru": "Предварительное добавление поступлений"},
    "schedule_next_after_transition": {
        "en": "Sequential arrival scheduling", "ru": "Последовательное планирование поступлений",
    },
}
ARCHITECTURE_CATEGORIES = (
    ("matches_af_only", "AF only", "Только AF"),
    ("matches_df_only", "DF only", "Только DF"),
    ("matches_both", "Both", "Оба"),
    ("matches_neither", "Neither", "Ни один"),
)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _md(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows.\n"
    columns = [str(column) for column in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in frame.fillna("").itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines) + "\n"


def _predictor_coefficient(models: pd.DataFrame, model_id: str, term: str) -> dict[str, Any]:
    """Select a saved predictor coefficient by canonical non-intercept term."""
    if term == "const":
        raise ValueError("intercept cannot be exported as a predictor coefficient")
    rows = models.loc[models.model.eq(model_id)]
    if len(rows) != 1:
        raise ValueError(f"expected one model row for {model_id}, found {len(rows)}")
    row = rows.iloc[0]
    coefficient_column = f"coefficient_{term}"
    se_column = f"hc3_standard_error_{term}"
    low_column = f"bootstrap_ci95_low_coefficient_{term}"
    high_column = f"bootstrap_ci95_high_coefficient_{term}"
    needed = (coefficient_column, se_column, low_column, high_column)
    if any(column not in models.columns or pd.isna(row[column]) for column in needed):
        raise ValueError(f"missing unique saved coefficient for {model_id}/{term}")
    return {
        "model_id": model_id,
        "predictor_term": term,
        "coefficient": float(row[coefficient_column]),
        "hc3_standard_error": float(row[se_column]),
        "ci95_low": float(row[low_column]),
        "ci95_high": float(row[high_column]),
        "r_squared": float(row.r_squared),
        "cv_rmse": float(row.cv_rmse),
        "cv_mae": np.nan,
        "cv_mae_reason": "not retained in Phase II.2 predictor_models_retained.csv",
        "n": int(row.n),
        "source_table": "derived/predictor_models_retained.csv",
        "selector": f"model={model_id}; coefficient_{term}; term != const",
    }


def _architecture_rows(summary: pd.DataFrame) -> pd.DataFrame:
    expected = [PRIMARY, "schedule_next_after_transition"]
    rows = summary.set_index("arrival_scheduling_mode").reindex(expected)
    if rows.index.hasnans or rows.isna().all(axis=1).any() or len(rows) != 2:
        raise ValueError("architecture summary must have one row for each required architecture")
    if summary.arrival_scheduling_mode.duplicated().any():
        raise ValueError("architecture summary contains duplicate architecture rows")
    for category, _, _ in ARCHITECTURE_CATEGORIES:
        if not np.allclose(rows[category], rows[f"{category}_percent"] * rows.paired_count / 100):
            raise ValueError("architecture counts and percentages disagree")
    count_total = rows[[item[0] for item in ARCHITECTURE_CATEGORIES]].sum(axis=1)
    percent_total = rows[[f"{item[0]}_percent" for item in ARCHITECTURE_CATEGORIES]].sum(axis=1)
    if not count_total.eq(rows.paired_count).all() or not np.allclose(percent_total, 100):
        raise ValueError("architecture categories must be mutually exclusive and exhaustive")
    return rows.reset_index()


def _capacity_table(timing: pd.DataFrame) -> pd.DataFrame:
    primary = timing[(timing.arrival_scheduling_mode == PRIMARY) & np.isclose(timing.delta, 0.1)].copy()
    primary["absolute_policy_gap"] = primary.af_df_loss_gap.abs()
    table = primary.groupby("capacity", as_index=False).agg(
        configuration_count=("configuration_id_v22", "size"),
        mean_absolute_policy_gap=("absolute_policy_gap", "mean"),
        mean_midpoint_absolute_bias=("absolute_midpoint_loss_bias", "mean"),
        mean_midpoint_signed_bias=("midpoint_signed_loss_bias", "mean"),
    )
    table["mean_ordering_half_width"] = table.mean_absolute_policy_gap / 2
    table["bias_to_policy_gap_ratio"] = table.mean_midpoint_absolute_bias.div(
        table.mean_absolute_policy_gap.where(table.mean_absolute_policy_gap.ne(0))
    )
    table["bias_to_half_width_ratio"] = table.mean_midpoint_absolute_bias.div(
        table.mean_ordering_half_width.where(table.mean_ordering_half_width.ne(0))
    )
    return table


def _quantizer_table(timing: pd.DataFrame, pearson: float) -> pd.DataFrame:
    primary = timing[timing.arrival_scheduling_mode == PRIMARY].copy()
    primary["absolute_policy_gap"] = primary.af_df_loss_gap.abs()
    table = primary.groupby("quantizer", as_index=False).agg(
        configuration_count=("configuration_id_v22", "size"),
        mean_signed_midpoint_bias=("midpoint_signed_loss_bias", "mean"),
        mean_absolute_midpoint_bias=("absolute_midpoint_loss_bias", "mean"),
        mean_absolute_policy_gap=("absolute_policy_gap", "mean"),
        mean_signed_service_duration_error=("mean_signed_service_duration_error_pair", "mean"),
        mean_absolute_service_duration_error=("mean_absolute_service_duration_error_pair", "mean"),
        mean_service_zero_tick_fraction=("service_zero_tick_fraction_pair", "mean"),
    )
    table["service_error_bias_pearson"] = pearson
    return table.set_index("quantizer").reindex(["floor", "nearest", "ceiling"]).reset_index()


def _save_figure(fig: plt.Figure, directory: Path, name: str, metadata: dict[str, Any], manifest: list[dict[str, Any]]) -> None:
    for extension in ("png", "svg", "pdf"):
        path = directory / f"{name}.{extension}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        manifest.append({**metadata, "file": path.name, "sha256": _sha(path)})
    plt.close(fig)


def _critical_figure(configs: pd.DataFrame, coefficient: dict[str, Any], figures: Path, manifest: list[dict[str, Any]]) -> None:
    use = configs.loc[configs.arrival_scheduling_mode.eq(PRIMARY)].copy()
    if len(use) != 648 or not use.analysis_configuration_id.is_unique:
        raise ValueError("critical figure requires exactly 648 unique primary configurations")
    x = use.critical_collision_rate * 100
    y = use.absolute_policy_gap * 100
    line_x = np.linspace(0, max(float(x.max()), float(y.max())), 200)
    line_y = coefficient["intercept"] * 100 + coefficient["slope"] * line_x
    figure_data = {
        "figure_id": "critical_predictor", "source_file": "derived/predictor_configurations_retained.csv",
        "source_analysis": SOURCE_ID, "scope": "primary preload_all only", "n": len(use),
        "x": "critical_acceptance_difference_rate_per_arrival", "y": "mean_absolute_policy_gap",
        "slope": coefficient["slope"], "intercept": coefficient["intercept"],
        "r_squared": coefficient["r_squared"], "cv_rmse": coefficient["cv_rmse"], "units": "percentage points",
    }
    labels = {
        "en": ("Critical acceptance-difference rate per arrival (pp)", "Mean absolute AF–DF loss gap (pp)", "Fitted relationship", "Identity reference"),
        "ru": ("Частота критических различий приёма на поступление (п.п.)", "Средний абсолютный разрыв потерь AF–DF (п.п.)", "Аппроксимированная зависимость", "Эталон тождества"),
    }
    for language, (x_label, y_label, fit_label, identity_label) in labels.items():
        fig, axis = plt.subplots(figsize=(6.5, 4.5))
        axis.scatter(x, y, s=14, facecolors="none", edgecolors="black", linewidths=.55, label="Observations" if language == "en" else "Наблюдения")
        axis.plot(line_x, line_y, color="black", linewidth=1.4, label=fit_label)
        axis.plot(line_x, line_x, color="0.45", linestyle="--", linewidth=1.0, label=identity_label)
        axis.set_xlabel(x_label); axis.set_ylabel(y_label); axis.legend(frameon=False, fontsize=8)
        axis.grid(color="0.9", linewidth=.6)
        _save_figure(fig, figures, f"critical_predictor_{language}", {**figure_data, "language": language}, manifest)


def _architecture_figure(summary: pd.DataFrame, figures: Path, manifest: list[dict[str, Any]]) -> None:
    rows = _architecture_rows(summary)
    metadata = {"figure_id": "architecture_match", "source_file": "derived/insertion_architecture_summary.csv", "source_analysis": SOURCE_ID, "scope": "focused architecture source; exact integer count equality", "chart": "100 percent stacked categories"}
    colors = ["#4a4a4a", "#8a8a8a", "#c4c4c4", "#eeeeee"]
    for language in ("en", "ru"):
        fig, axis = plt.subplots(figsize=(7, 4.2)); bottom = np.zeros(len(rows))
        names = [ARCHITECTURE_LABELS[value][language] for value in rows.arrival_scheduling_mode]
        for (key, english, russian), color in zip(ARCHITECTURE_CATEGORIES, colors, strict=True):
            values = rows[f"{key}_percent"].to_numpy()
            axis.bar(names, values, bottom=bottom, color=color, edgecolor="black", linewidth=.5, label=english if language == "en" else russian)
            bottom += values
        axis.set_ylim(0, 100); axis.set_ylabel("Paired configurations (%)" if language == "en" else "Парные конфигурации (%)")
        axis.legend(frameon=False, fontsize=8, ncols=2); axis.grid(axis="y", color="0.9", linewidth=.6)
        _save_figure(fig, figures, f"architecture_match_{language}", {**metadata, "language": language}, manifest)


def _scaling_figures(pairs: pd.DataFrame, exponents: pd.DataFrame, figures: Path, manifest: list[dict[str, Any]]) -> None:
    selected_rho, selected_capacity = 1.0, 8
    use = pairs[(pairs.arrival_scheduling_mode == PRIMARY) & pairs.rho.eq(selected_rho) & pairs.capacity.eq(selected_capacity) & pairs.delta.gt(0) & pairs.delta.le(.003)]
    curve = use.groupby("delta", as_index=False).policy_neutral_collision_rate.mean()
    curve = curve[curve.policy_neutral_collision_rate.gt(0)]
    source = exponents[(exponents.rho.eq(selected_rho)) & exponents.capacity.eq(selected_capacity)]
    if len(source) != 1 or len(curve) < 2:
        raise ValueError("selected primary scaling curve is unavailable")
    row = source.iloc[0]; fitted = np.exp(row.intercept) * curve.delta.to_numpy() ** row.exponent
    metadata = {"source_file": "derived/timing_bias_workload_pairs.parquet; derived/collision_condition_exponents.csv", "source_analysis": SOURCE_ID, "scope": "primary preload_all; policy-neutral AF/DF average; positive condition means only", "selected_rule": "central configured condition rho=1.0, K=8", "fit_range": "0 < delta <= 0.003", "rho": selected_rho, "capacity": selected_capacity, "n_deltas": len(curve), "exponent": float(row.exponent), "r_squared": float(row.r_squared)}
    for language in ("en", "ru"):
        fig, axis = plt.subplots(figsize=(6.5, 4.5))
        axis.loglog(curve.delta, curve.policy_neutral_collision_rate, marker="o", color="black", label="Condition mean" if language == "en" else "Среднее по условию")
        axis.loglog(curve.delta, fitted, color="0.4", linestyle="--", label="Log-log fit" if language == "en" else "Лог-лог аппроксимация")
        axis.set_xlabel("Timestamp quantum δ" if language == "en" else "Квант времени δ")
        axis.set_ylabel("Policy-neutral collision frequency" if language == "en" else "Политически-нейтральная частота коллизий")
        axis.legend(frameon=False, fontsize=8); axis.grid(which="both", color="0.9", linewidth=.5)
        _save_figure(fig, figures, f"collision_frequency_delta_{language}", {**metadata, "figure_id": "collision_frequency_delta", "language": language}, manifest)
        fig, axis = plt.subplots(figsize=(6.5, 4.5))
        for rho, group in exponents.groupby("rho", sort=True):
            axis.plot(group.capacity, group.exponent, marker="o", linewidth=1, label=f"ρ={rho:g}")
        axis.set_xlabel("K" if language == "en" else "Ёмкость K")
        axis.set_ylabel("Condition exponent" if language == "en" else "Показатель условия")
        axis.legend(frameon=False, fontsize=8, ncols=2); axis.grid(color="0.9", linewidth=.5)
        _save_figure(fig, figures, f"collision_exponent_capacity_supplement_{language}", {"figure_id": "collision_exponent_capacity_supplement", "language": language, "source_file": "derived/collision_condition_exponents.csv", "source_analysis": SOURCE_ID, "scope": "supplemental; primary preload_all condition exponents"}, manifest)


def _localized_tables(capacity: pd.DataFrame, quantizer: pd.DataFrame, architecture: pd.DataFrame, tables: Path) -> None:
    cap = capacity.copy()
    cap.columns = ["K", "Число конфигураций", "Средний абсолютный разрыв потерь (п.п.)", "Средняя полу-ширина порядка (п.п.)", "Среднее абсолютное смещение середины (п.п.)", "Среднее знаковое смещение середины (п.п.)", "Отношение смещения к разрыву", "Отношение смещения к полу-ширине"]
    for column in cap.columns[2:6]: cap[column] *= 100
    (tables / "capacity_delta_01_ru.md").write_text(_md(cap), encoding="utf-8")
    q = quantizer.copy()
    q.columns = ["Квантизатор", "Число конфигураций", "Знаковое смещение середины (п.п.)", "Абсолютное смещение середины (п.п.)", "Средний абсолютный разрыв потерь (п.п.)", "Знаковая ошибка длительности обслуживания", "Абсолютная ошибка длительности обслуживания", "Доля нулевых тактов", "Корреляция Пирсона ошибки и смещения"]
    for column in q.columns[2:5]: q[column] *= 100
    (tables / "quantizer_summary_ru.md").write_text(_md(q), encoding="utf-8")
    rows = _architecture_rows(architecture).copy()
    rows["Архитектура"] = [ARCHITECTURE_LABELS[value]["ru"] for value in rows.arrival_scheduling_mode]
    out = rows[["Архитектура", "paired_count", "matches_af_only_percent", "matches_df_only_percent", "matches_both_percent", "matches_neither_percent"]]
    out.columns = ["Архитектура", "Парные конфигурации", "Только AF (%)", "Только DF (%)", "Оба (%)", "Ни один (%)"]
    (tables / "architecture_comparison_ru.md").write_text(_md(out), encoding="utf-8")


def _manifest(target: Path) -> None:
    rows = [
        {"path": str(path.relative_to(target)), "sha256": _sha(path)}
        for path in target.rglob("*")
        if path.is_file() and path != target / "manifests" / "artifacts.csv"
    ]
    pd.DataFrame(rows).sort_values("path").to_csv(target / "manifests" / "artifacts.csv", index=False)


def _finding(**item: Any) -> dict[str, Any]:
    required = {"finding_id", "publication_text", "source_run", "source_analysis", "source_file", "row_selector", "filters", "grouping_keys", "aggregation", "units", "estimate", "ci", "sample_size", "commit"}
    missing = required.difference(item)
    if missing: raise ValueError(f"incomplete Phase II.2.1 finding: {sorted(missing)}")
    return item


def _findings(source_runs: dict[str, Any], predictors: pd.DataFrame, capacity: pd.DataFrame, quantizer: pd.DataFrame, exponents: pd.DataFrame, censor: pd.DataFrame, service: pd.Series, architecture: pd.DataFrame, commit: str) -> list[dict[str, Any]]:
    principal = Path(source_runs["principal"]["path"]).name
    output: list[dict[str, Any]] = []
    for row in predictors.itertuples(index=False):
        output.append(_finding(finding_id=f"predictor_{row.model_id}_coefficient", publication_text=f"The retained {row.model_id} predictor coefficient is selected by the canonical term `{row.predictor_term}`, not by row position or intercept.", source_run=principal, source_analysis=SOURCE_ID, source_file=row.source_table, row_selector=row.selector, filters="primary architecture; saved retained predictor model", grouping_keys="analysis_configuration_id", aggregation="saved workload-paired configuration model", units="packet-loss-probability gap per predictor unit", estimate={"coefficient": row.coefficient, "hc3_standard_error": row.hc3_standard_error, "r_squared": row.r_squared, "cv_rmse": row.cv_rmse, "cv_mae": None}, ci={"low": row.ci95_low, "high": row.ci95_high, "method": "saved replication-level bootstrap"}, sample_size={"n": int(row.n)}, commit=commit))
    condition = exponents[(exponents.rho.eq(1.0)) & (exponents.capacity.eq(8))].iloc[0]
    output.append(_finding(finding_id="condition_scaling_rho_1_k_8", publication_text="The primary collision-frequency figure shows the selected central rho=1.0, K=8 condition on logarithmic delta and frequency axes.", source_run=principal, source_analysis=SOURCE_ID, source_file="derived/collision_condition_exponents.csv", row_selector="rho=1.0; capacity=8", filters="preload_all; positive condition means; 0 < delta <= 0.003", grouping_keys="rho, capacity", aggregation="one saved condition-level log-log fit", units="log-log exponent", estimate={"exponent": float(condition.exponent), "r_squared": float(condition.r_squared)}, ci={"available": False, "reason": "condition exponent table has no saved interval"}, sample_size={"fine_deltas": int(condition.positive_fine_deltas)}, commit=commit))
    for row in censor.itertuples(index=False):
        output.append(_finding(finding_id=f"censor_{row.status}", publication_text=f"The zero-censoring audit retains the `{row.status}` category separately.", source_run=principal, source_analysis=SOURCE_ID, source_file="derived/collision_zero_censoring_summary.csv", row_selector=f"status={row.status}", filters="primary fine-delta workload fits", grouping_keys="workload_id, rho, capacity, quantizer", aggregation="saved category summary", units="percent and log-log exponent", estimate={"count": int(row.n), "percent": float(row.percent), "mean_exponent": float(row.mean_exponent)}, ci={"low": float(row.bootstrap_ci95_low), "high": float(row.bootstrap_ci95_high), "method": "saved bootstrap"}, sample_size={"workload_design_rows": int(row.n)}, commit=commit))
    output.append(_finding(finding_id="service_error_bias_relationship", publication_text="Signed service-duration error has a saved descriptive relationship with midpoint bias; no causal interpretation is made.", source_run=principal, source_analysis=SOURCE_ID, source_file="derived/timing_relationships.csv", row_selector="model=service_signed", filters="primary configuration means", grouping_keys="rho, capacity, delta, quantizer", aggregation="saved HC3 OLS and grouped validation", units="bias per normalized service-time error", estimate={"pearson": float(service.pearson), "slope": float(service.slope), "r_squared": float(service.r_squared), "cv_rmse": float(service.cv_rmse)}, ci={"low": float(service.hc3_ci95_low), "high": float(service.hc3_ci95_high), "method": "saved HC3 interval"}, sample_size={"configurations": int(service.n)}, commit=commit))
    for row in quantizer.itertuples(index=False):
        output.append(_finding(finding_id=f"quantizer_{row.quantizer}", publication_text=f"The {row.quantizer} quantizer row reports configuration-level midpoint bias, ordering gap, service-time error, and zero-tick fraction.", source_run=principal, source_analysis=SOURCE_ID, source_file="tables/quantizer_summary.csv", row_selector=f"quantizer={row.quantizer}", filters="primary configuration means", grouping_keys="quantizer", aggregation="mean over configurations", units="packet-loss percentage points; normalized service time", estimate={"signed_midpoint_bias": row.mean_signed_midpoint_bias * 100, "absolute_midpoint_bias": row.mean_absolute_midpoint_bias * 100, "absolute_policy_gap": row.mean_absolute_policy_gap * 100, "signed_service_error": row.mean_signed_service_duration_error, "absolute_service_error": row.mean_absolute_service_duration_error, "zero_tick_fraction": row.mean_service_zero_tick_fraction, "pearson": row.service_error_bias_pearson}, ci={"available": False, "reason": "publication table is a saved configuration-level mean"}, sample_size={"configurations": int(row.configuration_count)}, commit=commit))
    for row in capacity.itertuples(index=False):
        output.append(_finding(finding_id=f"capacity_delta_01_k_{row.capacity}", publication_text=f"At δ=0.1 and K={row.capacity}, the table compares absolute ordering gap, midpoint bias, and their ratios within the primary architecture.", source_run=principal, source_analysis=SOURCE_ID, source_file="tables/capacity_delta_01.csv", row_selector=f"capacity={row.capacity}", filters="delta=0.1; primary architecture", grouping_keys="capacity", aggregation="mean of configuration-level quantities; ratios of means", units="packet-loss percentage points and dimensionless ratios", estimate={"policy_gap_pp": row.mean_absolute_policy_gap * 100, "half_width_pp": row.mean_ordering_half_width * 100, "absolute_bias_pp": row.mean_midpoint_absolute_bias * 100, "signed_bias_pp": row.mean_midpoint_signed_bias * 100, "bias_gap_ratio": row.bias_to_policy_gap_ratio, "bias_half_width_ratio": row.bias_to_half_width_ratio}, ci={"available": False, "reason": "compact publication comparison uses saved means"}, sample_size={"configurations": int(row.configuration_count)}, commit=commit))
    for row in _architecture_rows(architecture).itertuples(index=False):
        output.append(_finding(finding_id=f"architecture_{row.arrival_scheduling_mode}", publication_text="Insertion matching uses mutually exclusive exact-count categories from the validated focused architecture summary.", source_run=Path(source_runs["focused_insertion"]["path"]).name, source_analysis=SOURCE_ID, source_file="derived/insertion_architecture_summary.csv", row_selector=f"arrival_scheduling_mode={row.arrival_scheduling_mode}", filters="AF, DF, insertion policy; focused architecture run", grouping_keys="workload_id, rho, capacity, delta, quantizer", aggregation="exact integer equality category percentages", units="percent of paired configurations", estimate={"af_only_percent": float(row.matches_af_only_percent), "df_only_percent": float(row.matches_df_only_percent), "both_percent": float(row.matches_both_percent), "neither_percent": float(row.matches_neither_percent)}, ci={"available": False, "reason": "complete focused paired count audit"}, sample_size={"pairs": int(row.paired_count)}, commit=commit))
    return output


def _reports(target: Path, findings: list[dict[str, Any]], predictor: pd.DataFrame, capacity: pd.DataFrame, architecture: pd.DataFrame) -> None:
    report = target / "report"
    report.joinpath("findings.json").write_text(json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.joinpath("summary.md").write_text("# Phase II.2.1 corrected publication bundle\n\nThis version corrects export selection and publication presentation only. It reuses immutable Phase II.2 inputs, retains the primary preload architecture scope, and does not rerun simulation or alter scientific tables. The critical predictor coefficient is 0.454996 for the canonical critical-collision term, not the saved intercept.\n\nThe main collision figure now shows frequency versus timestamp quantum on log axes; exponent versus capacity is supplemental. The architecture chart is derived from the validated summary and has mutually exclusive 100% categories.\n", encoding="utf-8")
    report.joinpath("methodology.md").write_text("# Export methodology\n\nAll values are loaded from the immutable source analysis. Predictor terms are selected by `model` plus a canonical non-constant term. The critical figure uses 648 unique saved primary configuration rows, plots the saved fit and identity reference, and expresses both axes in percentage points. Capacity and quantizer tables use configuration-level primary values; zero denominators yield null ratios.\n", encoding="utf-8")
    report.joinpath("findings.md").write_text("# Traceable corrected findings\n\n" + "\n\n".join(f"## {item['finding_id']}\n\n{item['publication_text']}\n\nSource: `{item['source_file']}`; selector: `{item['row_selector']}`; estimate: `{json.dumps(item['estimate'], sort_keys=True)}`.\n" for item in findings) + "\n", encoding="utf-8")
    report.joinpath("limitations.md").write_text("# Limitations\n\nThe bundle repairs only exports. Predictor associations remain non-causal, saved condition exponents do not have intervals, CV MAE was not retained in the source predictor table, and random-order observations remain unavailable. The online architecture is a separately labelled robustness result, not a primary observation.\n", encoding="utf-8")
    report.joinpath("validation.md").write_text(f"# Validation\n\nPredictor export rows: {len(predictor)}. Capacity table rows: {len(capacity)}. Architecture rows: {len(architecture)}. Artifact and localization validators must pass before publication.\n", encoding="utf-8")


def build_phase221(source: Path) -> Path:
    """Create one Phase II.2.1 publication-only directory from immutable v2.2 assets."""
    source = Path(source)
    if source.name != SOURCE_ID:
        raise ValueError(f"Phase II.2.1 requires source analysis {SOURCE_ID}")
    commit = __import__("subprocess").check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    target = source.parent / f"v2.2.1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{commit}"
    for name in ("figures", "tables", "report", "manifests"):
        (target / name).mkdir(parents=True, exist_ok=False)
    timing = pd.read_parquet(source / "derived" / "timing_bias_configuration.parquet")
    pairs = pd.read_parquet(source / "derived" / "timing_bias_workload_pairs.parquet")
    models = pd.read_csv(source / "derived" / "predictor_models_retained.csv")
    configs = pd.read_csv(source / "derived" / "predictor_configurations_retained.csv")
    relationships = pd.read_csv(source / "derived" / "timing_relationships.csv")
    exponents = pd.read_csv(source / "derived" / "collision_condition_exponents.csv")
    censor = pd.read_csv(source / "derived" / "collision_zero_censoring_summary.csv")
    architecture = pd.read_csv(source / "derived" / "insertion_architecture_summary.csv")
    predictor = pd.DataFrame([_predictor_coefficient(models, model, term) for model, term in PREDICTOR_TERMS.items()])
    critical = predictor.loc[predictor.model_id.eq("critical")].iloc[0]
    fit = {"slope": float(critical.coefficient), "intercept": float(models.loc[models.model.eq("critical"), "coefficient_const"].iloc[0]), "r_squared": float(critical.r_squared), "cv_rmse": float(critical.cv_rmse)}
    capacity = _capacity_table(timing)
    service = relationships.loc[relationships.model.eq("service_signed")].iloc[0]
    quantizer = _quantizer_table(timing, float(service.pearson))
    for frame, name in ((predictor, "predictor_coefficients"), (capacity, "capacity_delta_01"), (quantizer, "quantizer_summary"), (architecture, "architecture_comparison")):
        frame.to_csv(target / "tables" / f"{name}.csv", index=False)
        (target / "tables" / f"{name}.md").write_text(_md(frame), encoding="utf-8")
    _localized_tables(capacity, quantizer, architecture, target / "tables")
    figure_manifest: list[dict[str, Any]] = []
    _critical_figure(configs, fit, target / "figures", figure_manifest)
    _architecture_figure(architecture, target / "figures", figure_manifest)
    _scaling_figures(pairs, exponents, target / "figures", figure_manifest)
    pd.DataFrame(figure_manifest).sort_values(["figure_id", "language", "file"]).to_csv(target / "manifests" / "figures.csv", index=False)
    source_runs = json.loads((source / "source_runs.json").read_text(encoding="utf-8"))
    source_hashes = {str(path.relative_to(source)): _sha(path) for path in sorted((source / "derived").glob("*")) if path.is_file()}
    atomic_json({"source_analysis": str(source), "source_analysis_provenance_sha256": _sha(source / "provenance.json"), "source_derived_sha256": source_hashes, "source_runs": source_runs}, target / "source_runs.json")
    config = {"schema": "phase_ii_2_1", "source_analysis": SOURCE_ID, "primary_architecture": PRIMARY, "critical_figure": {"x": "critical_acceptance_difference_rate_per_arrival", "y": "mean_absolute_policy_gap", "n": 648}, "scaling_selection_rule": "rho=1.0, K=8 central configured condition"}
    save_yaml(config, target / "config.resolved.yaml")
    atomic_json({"analysis_id": target.name, "created_utc": datetime.now(UTC).isoformat(), "git_commit": commit, "source_analysis": SOURCE_ID, "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()}, target / "provenance.json")
    findings = _findings(source_runs, predictor, capacity, quantizer, exponents, censor, service, architecture, commit)
    _reports(target, findings, predictor, capacity, architecture)
    _manifest(target)
    validate_phase221(target)
    return target


def validate_phase221(target: Path) -> None:
    """Validate corrected publication assets and their immutable-source traceability."""
    target = Path(target)
    findings = json.loads((target / "report" / "findings.json").read_text(encoding="utf-8"))
    expected = {"finding_id", "publication_text", "source_run", "source_analysis", "source_file", "row_selector", "filters", "grouping_keys", "aggregation", "units", "estimate", "ci", "sample_size", "commit"}
    if not findings or any(expected.difference(row) for row in findings): raise ValueError("incomplete publication finding")
    predictor = pd.read_csv(target / "tables" / "predictor_coefficients.csv")
    if set(predictor.predictor_term) != {"total_collision_rate", "mixed_collision_rate", "critical_collision_rate"} or predictor.predictor_term.eq("const").any(): raise ValueError("invalid predictor export terms")
    if not np.isclose(float(predictor.loc[predictor.model_id.eq("critical"), "coefficient"].iloc[0]), .454996, atol=1e-6): raise ValueError("critical coefficient mismatch")
    architecture = pd.read_csv(target / "tables" / "architecture_comparison.csv") if (target / "tables" / "architecture_comparison.csv").exists() else None
    if architecture is not None: _architecture_rows(architecture)
    for path in list((target / "figures").glob("*_ru.svg")) + list((target / "tables").glob("*_ru.md")):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in FORBIDDEN_RUSSIAN): raise ValueError(f"unlocalized identifier in {path}")
    manifest = pd.read_csv(target / "manifests" / "artifacts.csv")
    for row in manifest.itertuples(index=False):
        if _sha(target / row.path) != row.sha256: raise ValueError(f"artifact hash mismatch: {row.path}")
    figures = pd.read_csv(target / "manifests" / "figures.csv")
    if len(figures) != 24 or figures.file.duplicated().any(): raise ValueError("incorrect corrected figure manifest")
    source = json.loads((target / "source_runs.json").read_text(encoding="utf-8"))
    source_root = Path(source["source_analysis"])
    for relative, digest in source["source_derived_sha256"].items():
        if _sha(source_root / relative) != digest: raise ValueError(f"source derived hash changed: {relative}")
    for details in source["source_runs"].values():
        for filename, digest in details.get("raw_hashes", {}).items():
            raw = Path(details["path"]) / "raw" / filename
            if _sha(raw) != digest: raise ValueError(f"source raw hash changed: {raw}")
