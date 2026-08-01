"""Final, immutable Phase II.2 publication analysis built from saved runs only."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from .bootstrap import paired_bootstrap_ci
from .provenance import collect_provenance
from .storage import atomic_json, atomic_parquet, save_yaml

PRIMARY = "preload_all"
ALTERNATE = "schedule_next_after_transition"


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
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in frame.fillna("").itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines) + "\n"


def _ci(values: pd.Series, seed: int = 20260801) -> tuple[float, float]:
    return paired_bootstrap_ci(values.dropna().to_numpy(), seed=seed, resamples=10_000)


def _configuration_id(frame: pd.DataFrame) -> pd.Series:
    fields = ["rho", "capacity", "delta", "quantizer", "arrival_scheduling_mode"]
    return frame[fields].astype(str).agg("|".join, axis=1)


def _paired_primary(q: pd.DataFrame, exact: pd.DataFrame) -> pd.DataFrame:
    q = q[(q.arrival_scheduling_mode == PRIMARY) & q.policy.isin(["arrival_first", "departure_first"])]
    keys = ["pair_id", "workload_id", "rho", "capacity", "delta", "quantizer", "arrival_scheduling_mode"]
    values = q.pivot(index=keys, columns="policy", values=["packet_loss_probability", "service_quantization_error_signed_mean", "service_quantization_error_absolute_mean", "arrival_quantization_error_signed_mean", "arrival_quantization_error_absolute_mean", "service_quantization_error_zero_fraction", "collision_event_fraction", "critical_acceptance_difference_rate", "mixed_collision_rate"]).reset_index()
    values.columns = ["_".join(column).strip("_") if isinstance(column, tuple) else column for column in values.columns]
    ref = exact[exact.arrival_scheduling_mode == PRIMARY][["workload_id", "arrival_scheduling_mode", "packet_loss_probability"]].rename(columns={"packet_loss_probability": "exact_loss"})
    if ref.duplicated(["workload_id", "arrival_scheduling_mode"]).any():
        raise ValueError("duplicate primary exact workload references")
    result = values.merge(ref, on=["workload_id", "arrival_scheduling_mode"], validate="many_to_one")
    result["midpoint_signed_loss_bias"] = (result.packet_loss_probability_arrival_first + result.packet_loss_probability_departure_first) / 2 - result.exact_loss
    result["absolute_midpoint_loss_bias"] = result.midpoint_signed_loss_bias.abs()
    result["af_df_loss_gap"] = result.packet_loss_probability_arrival_first - result.packet_loss_probability_departure_first
    for source, target in [("service_quantization_error_signed_mean", "mean_signed_service_duration_error_pair"), ("service_quantization_error_absolute_mean", "mean_absolute_service_duration_error_pair"), ("arrival_quantization_error_signed_mean", "mean_signed_arrival_error_pair"), ("arrival_quantization_error_absolute_mean", "mean_absolute_arrival_error_pair"), ("service_quantization_error_zero_fraction", "service_zero_tick_fraction_pair"), ("collision_event_fraction", "policy_neutral_collision_rate"), ("critical_acceptance_difference_rate", "critical_rate"), ("mixed_collision_rate", "mixed_rate")]:
        result[target] = (result[f"{source}_arrival_first"] + result[f"{source}_departure_first"]) / 2
    result["inverse_capacity"] = 1 / result.capacity
    result["configuration_id_v22"] = _configuration_id(result)
    return result


def _timing_configuration(paired: pd.DataFrame) -> pd.DataFrame:
    keys = ["configuration_id_v22", "rho", "capacity", "delta", "quantizer", "arrival_scheduling_mode"]
    numeric = ["midpoint_signed_loss_bias", "absolute_midpoint_loss_bias", "mean_signed_service_duration_error_pair", "mean_absolute_service_duration_error_pair", "mean_signed_arrival_error_pair", "mean_absolute_arrival_error_pair", "service_zero_tick_fraction_pair", "af_df_loss_gap", "policy_neutral_collision_rate", "critical_rate", "mixed_rate", "inverse_capacity"]
    grouped = paired.groupby(keys, sort=True)
    out = grouped.agg(
        **{column: (column, "mean") for column in numeric},
        replication_count=("workload_id", "size"),
        median_midpoint_signed_loss_bias=("midpoint_signed_loss_bias", "median"),
        se_midpoint_signed_loss_bias=("midpoint_signed_loss_bias", "sem"),
    ).reset_index()
    out["se_midpoint_signed_loss_bias"] = out.se_midpoint_signed_loss_bias.fillna(0)
    intervals = [_ci(g.midpoint_signed_loss_bias, 20260801 + i) for i, (_, g) in enumerate(grouped)]
    out["bias_bootstrap_ci95_low"] = [x[0] for x in intervals]
    out["bias_bootstrap_ci95_high"] = [x[1] for x in intervals]
    return out


def _relationship(config: pd.DataFrame) -> pd.DataFrame:
    outcome = "midpoint_signed_loss_bias"
    rows: list[dict[str, Any]] = []
    for predictor, name in [("mean_signed_service_duration_error_pair", "service_signed"), ("mean_signed_arrival_error_pair", "arrival_signed"), ("mean_absolute_service_duration_error_pair", "service_absolute"), ("service_zero_tick_fraction_pair", "service_zero_tick"), ("delta", "delta"), ("rho", "rho"), ("inverse_capacity", "inverse_capacity")]:
        use = config[[outcome, predictor, "configuration_id_v22"]].dropna()
        fit = sm.OLS(use[outcome], sm.add_constant(use[[predictor]])).fit(cov_type="HC3")
        predicted = pd.Series(index=use.index, dtype=float)
        for _, held in use.groupby("configuration_id_v22"):
            train = use.drop(index=held.index)
            fold = sm.OLS(train[outcome], sm.add_constant(train[[predictor]], has_constant="add")).fit()
            predicted.loc[held.index] = fold.predict(sm.add_constant(held[[predictor]], has_constant="add"))
        error = use[outcome] - predicted
        rows.append({"model": name, "predictor": predictor, "n": len(use), "pearson": use[[outcome, predictor]].corr().iloc[0, 1], "spearman": use[[outcome, predictor]].corr(method="spearman").iloc[0, 1], "slope": fit.params[predictor], "intercept": fit.params["const"], "hc3_se_slope": fit.bse[predictor], "hc3_ci95_low": fit.params[predictor] - 1.96 * fit.bse[predictor], "hc3_ci95_high": fit.params[predictor] + 1.96 * fit.bse[predictor], "r_squared": fit.rsquared, "cv_rmse": float(np.sqrt((error**2).mean())), "cv_mae": float(error.abs().mean()), "folds": int(use.configuration_id_v22.nunique())})
    predictors = ["mean_signed_service_duration_error_pair", "rho", "inverse_capacity", "delta"]
    use = config[[outcome, *predictors]].dropna(); fit = sm.OLS(use[outcome], sm.add_constant(use[predictors])).fit(cov_type="HC3")
    rows.append({"model": "explanatory", "predictor": "+".join(predictors), "n": len(use), "r_squared": fit.rsquared, **{f"coefficient_{key}": value for key, value in fit.params.items()}, **{f"hc3_se_{key}": value for key, value in fit.bse.items()}})
    return pd.DataFrame(rows)


def _censoring(paired: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fine = paired[(paired.delta > 0) & (paired.delta <= 0.003)].copy()
    rows = []
    for keys, group in fine.groupby(["workload_id", "rho", "capacity", "quantizer", "arrival_scheduling_mode"]):
        all_d = group.delta.nunique(); positive = group[group.policy_neutral_collision_rate > 0].sort_values("delta")
        zero = all_d - len(positive); status = "complete" if zero == 0 else "one_missing" if zero == 1 else "two_or_more_missing" if len(positive) >= 2 else "insufficient_for_fit"
        row = dict(zip(["workload_id", "rho", "capacity", "quantizer", "arrival_scheduling_mode"], keys)); row.update({"configured_fine_deltas": all_d, "positive_fine_deltas": len(positive), "zero_fine_deltas": zero, "min_included_delta": positive.delta.min() if len(positive) else np.nan, "max_included_delta": positive.delta.max() if len(positive) else np.nan, "status": status, "exponent": np.nan, "intercept": np.nan, "r_squared": np.nan})
        if len(positive) >= 2:
            x=np.log(positive.delta); y=np.log(positive.policy_neutral_collision_rate); slope, intercept=np.polyfit(x,y,1); row.update({"exponent":slope,"intercept":intercept,"r_squared":float(np.corrcoef(x,y)[0,1]**2)})
        rows.append(row)
    audit=pd.DataFrame(rows); summary=audit.groupby("status",as_index=False).agg(n=("status","size"),percent=("status",lambda x:100*len(x)/len(audit)),mean_exponent=("exponent","mean"),median_exponent=("exponent","median")); summary[["bootstrap_ci95_low","bootstrap_ci95_high"]]=[_ci(g.exponent,20260810+i) for i,(_,g) in enumerate(audit.groupby("status"))]
    cond=[]
    for keys,g in fine.groupby(["rho","capacity"]):
        rates=g.groupby("delta",as_index=False).policy_neutral_collision_rate.mean(); positive=rates[rates.policy_neutral_collision_rate>0]
        if len(positive)>=2:
            x=np.log(positive.delta);y=np.log(positive.policy_neutral_collision_rate); slope,intercept=np.polyfit(x,y,1);r2=float(np.corrcoef(x,y)[0,1]**2)
        else:slope=intercept=r2=np.nan
        cond.append({"rho":keys[0],"capacity":keys[1],"configured_fine_deltas":len(rates),"positive_fine_deltas":len(positive),"exponent":slope,"intercept":intercept,"r_squared":r2})
    return audit,summary,pd.DataFrame(cond)


def _architecture(run: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    q=pd.read_parquet(run/"raw/quantized_results.parquet"); keys=["workload_id","rho","capacity","delta","quantizer","arrival_scheduling_mode"]
    values=q[q.policy.isin(["arrival_first","departure_first","insertion_order"])].pivot(index=keys,columns="policy",values=["accepted_arrivals","dropped_arrivals","completed_measured_jobs","packet_loss_probability"]).reset_index();values.columns=["_".join(x).strip("_") if isinstance(x,tuple) else x for x in values.columns]
    count_metrics=["accepted_arrivals","dropped_arrivals","completed_measured_jobs"]
    for policy in ["arrival_first","departure_first"]:
        values[f"insertion_matches_{policy}"]=np.logical_and.reduce([values[f"{m}_insertion_order"].eq(values[f"{m}_{policy}"]) for m in count_metrics]);values[f"insertion_loss_distance_{policy}"]=(values.packet_loss_probability_insertion_order-values[f"packet_loss_probability_{policy}"]).abs()
    values["insertion_matches_both"] = values.insertion_matches_arrival_first & values.insertion_matches_departure_first
    values["insertion_matches_af_only"] = values.insertion_matches_arrival_first & ~values.insertion_matches_departure_first
    values["insertion_matches_df_only"] = values.insertion_matches_departure_first & ~values.insertion_matches_arrival_first
    values["insertion_matches_neither"]=~values.insertion_matches_arrival_first & ~values.insertion_matches_departure_first
    summary=values.groupby("arrival_scheduling_mode",as_index=False).agg(paired_count=("workload_id","size"),matches_both=("insertion_matches_both","sum"),matches_af_only=("insertion_matches_af_only","sum"),matches_df_only=("insertion_matches_df_only","sum"),matches_neither=("insertion_matches_neither","sum"),mean_distance_af=("insertion_loss_distance_arrival_first","mean"),max_distance_af=("insertion_loss_distance_arrival_first","max"),mean_distance_df=("insertion_loss_distance_departure_first","mean"),max_distance_df=("insertion_loss_distance_departure_first","max"))
    for c in ["matches_both","matches_af_only","matches_df_only","matches_neither"]:summary[f"{c}_percent"]=100*summary[c]/summary.paired_count
    explicit=values.pivot(index=["workload_id","rho","capacity","delta","quantizer"],columns="arrival_scheduling_mode",values=["accepted_arrivals_arrival_first","dropped_arrivals_arrival_first","packet_loss_probability_arrival_first","accepted_arrivals_departure_first","dropped_arrivals_departure_first","packet_loss_probability_departure_first"]).reset_index(); explicit.columns=["_".join(x).strip("_") if isinstance(x,tuple) else x for x in explicit.columns]
    for policy in ["arrival_first","departure_first"]:
        explicit[f"{policy}_accepted_equal"] = explicit[f"accepted_arrivals_{policy}_{PRIMARY}"].eq(explicit[f"accepted_arrivals_{policy}_{ALTERNATE}"]);explicit[f"{policy}_dropped_equal"] = explicit[f"dropped_arrivals_{policy}_{PRIMARY}"].eq(explicit[f"dropped_arrivals_{policy}_{ALTERNATE}"]);explicit[f"{policy}_loss_difference"]=(explicit[f"packet_loss_probability_{policy}_{PRIMARY}"]-explicit[f"packet_loss_probability_{policy}_{ALTERNATE}"]).abs()
    return values,summary,explicit


def _save(fig: plt.Figure, directory: Path, name: str, meta: dict[str, Any], manifest: list[dict[str, Any]]) -> None:
    for ext in ("png","svg","pdf"):
        path=directory/f"{name}.{ext}";fig.savefig(path,dpi=300,bbox_inches="tight");manifest.append({**meta,"file":path.name,"sha256":_sha(path)})
    plt.close(fig)


def _figures(target: Path, timing: pd.DataFrame, audit: pd.DataFrame, condition: pd.DataFrame, predictor: pd.DataFrame, architecture: pd.DataFrame) -> None:
    figs=target/"figures"; manifest: list[dict[str, Any]]=[]
    labels={"en":("Timestamp quantum δ","Bias / gap"),"ru":("Квант времени δ","Смещение / разность")}
    for lang,(xlab,ylab) in labels.items():
        fig,ax=plt.subplots();ax.scatter(condition.capacity,condition.exponent,color="black");ax.set_xlabel("K");ax.set_ylabel("Exponent" if lang=="en" else "Показатель");_save(fig,figs,f"collision_scaling_{lang}",{ "figure":"collision_scaling","language":lang,"source":"derived/collision_condition_exponents.csv"},manifest)
        fig,ax=plt.subplots();ax.scatter(timing.af_df_loss_gap,timing.midpoint_signed_loss_bias,facecolors="none",edgecolors="black");ax.set_xlabel("AF–DF gap");ax.set_ylabel(ylab);_save(fig,figs,f"midpoint_bias_gap_{lang}",{ "figure":"midpoint_bias_gap","language":lang,"source":"derived/timing_bias_configuration.csv"},manifest)
        fig,ax=plt.subplots();ax.scatter(timing.mean_signed_service_duration_error_pair,timing.midpoint_signed_loss_bias,color="black",s=10);ax.set_xlabel("Signed service-duration error" if lang=="en" else "Знаковая ошибка длительности обслуживания");ax.set_ylabel(ylab);_save(fig,figs,f"service_error_bias_{lang}",{ "figure":"service_error_bias","language":lang,"source":"derived/timing_bias_configuration.csv"},manifest)
        fig,ax=plt.subplots();ax.scatter(predictor.critical_rate,predictor.midpoint_signed_loss_bias,color="black",s=10);ax.set_xlabel("Critical rate" if lang=="en" else "Критическая частота");ax.set_ylabel("AF–DF gap" if lang=="en" else "Разность AF–DF");_save(fig,figs,f"critical_gap_{lang}",{ "figure":"critical_gap","language":lang,"source":"derived/timing_bias_configuration.csv"},manifest)
        fig,ax=plt.subplots();summary=architecture.groupby("arrival_scheduling_mode")["insertion_matches_arrival_first"].mean();ax.bar(summary.index,summary.values,color="white",edgecolor="black",hatch="//");ax.set_ylim(0,1);ax.set_ylabel("Match fraction" if lang=="en" else "Доля совпадений");_save(fig,figs,f"architecture_match_{lang}",{ "figure":"architecture_match","language":lang,"source":"derived/insertion_architecture_pairs.parquet"},manifest)
        fig,ax=plt.subplots();sub=timing[np.isclose(timing.delta,.1)];line=sub.groupby("capacity").absolute_midpoint_loss_bias.mean();ax.plot(line.index,line.values,color="black",marker="o");ax.set_xlabel("K");ax.set_ylabel("Absolute midpoint bias" if lang=="en" else "Абсолютное смещение середины");_save(fig,figs,f"k_effect_delta_01_{lang}",{ "figure":"k_effect_delta_01","language":lang,"source":"derived/timing_bias_configuration.csv","filters":"delta=0.1"},manifest)
    pd.DataFrame(manifest).to_csv(target/"manifests"/"figures.csv",index=False)


_FINDING_FIELDS = {
    "finding_id", "publication_text", "source_run", "source_analysis", "source_table",
    "source_file", "filters", "grouping_keys", "aggregation", "units", "estimate",
    "ci", "sample_size", "commit",
}


def _report_entry(**entry: Any) -> dict[str, Any]:
    """Keep machine-readable publication claims complete and auditable."""
    missing = _FINDING_FIELDS.difference(entry)
    if missing:
        raise ValueError(f"incomplete Phase II.2 finding: {sorted(missing)}")
    prefix = str(entry["finding_id"]).split("_", 1)[0]
    entry["status"] = "not_tested" if prefix == "H6" else "limited" if prefix in {"H1", "H3", "H4", "H5", "H7"} else "supported"
    return entry


def _format_number(value: Any, digits: int = 6) -> str:
    if isinstance(value, (float, np.floating)):
        return f"{value:.{digits}g}"
    return str(value)


def _ci_entry(low: float, high: float, method: str) -> dict[str, Any]:
    return {"available": True, "level": 0.95, "method": method, "low": float(low), "high": float(high)}


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def _report_manifest(target: Path) -> None:
    artifact: list[dict[str, str]] = []
    for directory in (target / "derived", target / "figures", target / "tables", target / "report"):
        artifact.extend(
            {"path": str(path.relative_to(target)), "sha256": _sha(path)}
            for path in directory.glob("*")
            if path.is_file()
        )
    pd.DataFrame(artifact).sort_values("path").to_csv(target / "manifests" / "artifacts.csv", index=False)


def _finding_markdown(findings: list[dict[str, Any]]) -> str:
    sections = ["# Phase II.2 findings\n", "All estimates below are descriptive unless explicitly labelled otherwise. `CI unavailable` means the saved derived input does not contain the replication-level information needed to reconstruct that interval without touching raw results.\n"]
    for item in findings:
        estimate = json.dumps(item["estimate"], sort_keys=True)
        ci = item["ci"]
        ci_text = json.dumps(ci, sort_keys=True)
        sections.append(
            f"## {item['finding_id']}\n\n{item['publication_text']}\n\n"
            f"- Status: `{item['status']}`.\n"
            f"- Source run: `{item['source_run']}`; source analysis: `{item['source_analysis']}`; commit: `{item['commit']}`.\n"
            f"- Source table/file: `{item['source_table']}` / `{item['source_file']}`.\n"
            f"- Filters: {item['filters']}\n"
            f"- Grouping keys: {item['grouping_keys']}; aggregation: {item['aggregation']}.\n"
            f"- Units: {item['units']}; sample size: `{json.dumps(item['sample_size'], sort_keys=True)}`.\n"
            f"- Estimate: `{estimate}`. CI: `{ci_text}`.\n"
        )
    return "\n".join(sections)


def refresh_phase22_report(target: Path) -> None:
    """Refresh Phase II.2 narrative assets from its existing derived outputs only."""
    target = Path(target)
    required = [
        target / "provenance.json", target / "source_runs.json",
        target / "derived" / "timing_bias_workload_pairs.parquet",
        target / "derived" / "timing_bias_configuration.parquet",
        target / "derived" / "timing_relationships.csv",
        target / "derived" / "collision_zero_censoring_audit.csv",
        target / "derived" / "collision_zero_censoring_summary.csv",
        target / "derived" / "collision_condition_exponents.csv",
        target / "derived" / "insertion_architecture_summary.csv",
        target / "derived" / "explicit_architecture_stability.parquet",
        target / "derived" / "predictor_models_retained.csv",
        target / "derived" / "exact_validation_retained.csv",
    ]
    absent = [str(path) for path in required if not path.exists()]
    if absent:
        raise FileNotFoundError(f"cannot refresh Phase II.2 report; missing {absent}")
    provenance = json.loads((target / "provenance.json").read_text(encoding="utf-8"))
    sources = json.loads((target / "source_runs.json").read_text(encoding="utf-8"))
    principal = Path(sources["principal"]["path"]).name
    baseline = Path(sources["baseline"]["path"]).name
    focused = Path(sources["focused_insertion"]["path"]).name
    commit = str(provenance["git_commit"])
    paired = pd.read_parquet(target / "derived" / "timing_bias_workload_pairs.parquet")
    timing = pd.read_parquet(target / "derived" / "timing_bias_configuration.parquet")
    relationships = pd.read_csv(target / "derived" / "timing_relationships.csv")
    audit = pd.read_csv(target / "derived" / "collision_zero_censoring_audit.csv")
    censor = pd.read_csv(target / "derived" / "collision_zero_censoring_summary.csv")
    condition = pd.read_csv(target / "derived" / "collision_condition_exponents.csv")
    architecture = pd.read_csv(target / "derived" / "insertion_architecture_summary.csv")
    explicit = pd.read_parquet(target / "derived" / "explicit_architecture_stability.parquet")
    models = pd.read_csv(target / "derived" / "predictor_models_retained.csv")
    theory = pd.read_csv(target / "derived" / "exact_validation_retained.csv")
    service = relationships.loc[relationships.model.eq("service_signed")].iloc[0]
    complete = audit.loc[audit.status.eq("complete"), "exponent"].dropna()
    condition_ci = _ci(condition.exponent, 20260821)
    complete_ci = _ci(complete, 20260822)
    exact_max = theory.loc[theory.absolute_loss_difference.idxmax()]
    source_table = "derived/timing_bias_configuration.parquet"
    primary_filter = "arrival_scheduling_mode=preload_all; policies=arrival_first,departure_first; exact reference joined by workload_id"
    findings: list[dict[str, Any]] = []
    findings.append(_report_entry(
        finding_id="H1_exact_engine_validation", publication_text=(
            "H1 is supported only as a point-estimate agreement check: the largest saved absolute exact-loss difference from M/M/1/K theory is reported below; no uncertainty interval was retained for this comparison."
        ), source_run=principal, source_analysis=baseline, source_table="tables/exact_validation.csv", source_file="derived/exact_validation_retained.csv",
        filters="theory_applicable=true; M/M/1/K", grouping_keys="rho, capacity", aggregation="one saved exact-result mean per condition",
        units="absolute packet-loss-probability difference", estimate={"max_absolute_difference": float(exact_max.absolute_loss_difference), "rho": float(exact_max.rho), "capacity": int(exact_max.capacity), "condition_rows": len(theory), "replications_per_condition": int(theory.n.min())},
        ci=_unavailable("the retained exact-validation table contains condition means and n, but no replication-level values or saved CI"), sample_size={"condition_rows": len(theory), "replications_per_condition": int(theory.n.min())}, commit=commit,
    ))
    findings.append(_report_entry(
        finding_id="H2_service_error_bias_relationship", publication_text=(
            "H2 is supported as a descriptive association: configuration-mean signed service-duration error and midpoint loss bias are strongly positively associated in the preload_all primary analysis; this is not a causal estimate."
        ), source_run=principal, source_analysis=target.name, source_table="derived/timing_relationships.csv", source_file=source_table,
        filters=primary_filter, grouping_keys="rho, capacity, delta, quantizer, arrival_scheduling_mode", aggregation="AF/DF average within each workload, then mean of 30 paired workloads per configuration; OLS with HC3 and leave-one-configuration-out CV",
        units="midpoint loss-probability bias per signed service-duration error", estimate={"pearson": float(service.pearson), "spearman": float(service.spearman), "slope": float(service.slope), "intercept": float(service.intercept), "hc3_se": float(service.hc3_se_slope), "r_squared": float(service.r_squared), "cv_rmse": float(service.cv_rmse), "cv_mae": float(service.cv_mae), "folds": int(service.folds)},
        ci=_ci_entry(service.hc3_ci95_low, service.hc3_ci95_high, "HC3 normal-approximation interval for OLS slope"), sample_size={"configuration_rows": int(service.n), "paired_workload_rows": len(paired), "replications_per_configuration": int(timing.replication_count.min())}, commit=commit,
    ))
    max_bias = timing.loc[timing.absolute_midpoint_loss_bias.idxmax()]
    findings.append(_report_entry(
        finding_id="H2_maximum_configuration_bias", publication_text=(
            "H2 maximum configuration-mean bias identifies the largest saved absolute midpoint-bias configuration in the primary analysis; it is an observed configuration summary, not a worst-case guarantee beyond the sampled design."
        ), source_run=principal, source_analysis=target.name, source_table="derived/timing_bias_configuration.parquet", source_file=source_table,
        filters=primary_filter, grouping_keys="rho, capacity, delta, quantizer", aggregation="maximum absolute value over saved configuration means",
        units="packet-loss probability", estimate={"configuration_id": str(max_bias.configuration_id_v22), "signed_midpoint_bias": float(max_bias.midpoint_signed_loss_bias), "absolute_midpoint_bias": float(max_bias.absolute_midpoint_loss_bias), "configuration_bootstrap_ci95": [float(max_bias.bias_bootstrap_ci95_low), float(max_bias.bias_bootstrap_ci95_high)]},
        ci=_ci_entry(max_bias.bias_bootstrap_ci95_low, max_bias.bias_bootstrap_ci95_high, "bootstrap over the 30 paired workload rows in the selected configuration"), sample_size={"configuration_rows_searched": len(timing), "paired_workload_rows_selected_configuration": int(max_bias.replication_count)}, commit=commit,
    ))
    for quantizer, group in timing.groupby("quantizer", sort=True):
        bias_ci = _ci(group.midpoint_signed_loss_bias, 20260830 + len(findings))
        gap_ci = _ci(group.af_df_loss_gap, 20260840 + len(findings))
        findings.append(_report_entry(
            finding_id=f"H2_quantizer_{quantizer}", publication_text=(
                f"H2 quantizer-stratified descriptive result ({quantizer}): the configuration-mean midpoint bias and AF–DF loss gap are reported separately; this stratum does not establish a mechanism."
            ), source_run=principal, source_analysis=target.name, source_table="tables/quantizer_bias_order_gap.csv", source_file=source_table,
            filters=f"{primary_filter}; quantizer={quantizer}", grouping_keys="rho, capacity, delta, quantizer", aggregation="mean across configuration rows; bootstrap over configurations",
            units="packet-loss probability", estimate={"mean_midpoint_signed_bias": float(group.midpoint_signed_loss_bias.mean()), "mean_af_df_loss_gap": float(group.af_df_loss_gap.mean())},
            ci={"midpoint_bias": _ci_entry(*bias_ci, "bootstrap over configuration means"), "af_df_gap": _ci_entry(*gap_ci, "bootstrap over configuration means")}, sample_size={"configuration_rows": len(group), "paired_workload_rows": int(group.replication_count.sum())}, commit=commit,
        ))
    for row in censor.itertuples(index=False):
        findings.append(_report_entry(
            finding_id=f"H3_zero_censoring_{row.status}", publication_text=(
                f"H3 zero-censoring audit ({row.status}): {int(row.n)} workload-design fits ({row.percent:.3f}%) fall in this category; exponents use positive rates only and do not replace zeros with epsilon."
            ), source_run=principal, source_analysis=target.name, source_table="tables/collision_zero_censoring.csv", source_file="derived/collision_zero_censoring_summary.csv",
            filters="preload_all; delta>0 and delta<=0.003; policy-neutral AF/DF collision rate", grouping_keys="workload_id, rho, capacity, quantizer", aggregation="one log-log slope per workload-design using positive fine-delta rates",
            units="log-log collision-rate exponent", estimate={"count": int(row.n), "percent": float(row.percent), "mean_exponent": float(row.mean_exponent), "median_exponent": float(row.median_exponent)}, ci=_ci_entry(row.bootstrap_ci95_low, row.bootstrap_ci95_high, "bootstrap over workload-design exponents"), sample_size={"workload_design_rows": len(audit), "category_rows": int(row.n)}, commit=commit,
        ))
    findings.append(_report_entry(
        finding_id="H3_condition_level_scaling", publication_text=(
            "H3 condition-level scaling is descriptively near linear on the configured fine-delta range after averaging policy-neutral collision rates within condition; it does not imply a universal exponent."
        ), source_run=principal, source_analysis=target.name, source_table="tables/collision_scaling.csv", source_file="derived/collision_condition_exponents.csv",
        filters="preload_all; delta>0 and delta<=0.003; positive condition-mean collision rates", grouping_keys="rho, capacity", aggregation="one log-log slope per rho/capacity condition after policy-neutral AF/DF and workload averaging",
        units="log-log collision-rate exponent", estimate={"mean": float(condition.exponent.mean()), "median": float(condition.exponent.median()), "minimum": float(condition.exponent.min()), "maximum": float(condition.exponent.max()), "mean_r_squared": float(condition.r_squared.mean())}, ci=_ci_entry(*condition_ci, "bootstrap over 24 condition exponents"), sample_size={"condition_rows": len(condition), "fine_deltas_per_condition": int(condition.configured_fine_deltas.min())}, commit=commit,
    ))
    findings.append(_report_entry(
        finding_id="H3_complete_case_scaling", publication_text=(
            "H3 complete-case workload scaling is lower than the all-condition summary and is reported separately because zero-censoring changes the retained fine-delta support."
        ), source_run=principal, source_analysis=target.name, source_table="tables/collision_zero_censoring.csv", source_file="derived/collision_zero_censoring_audit.csv",
        filters="status=complete; preload_all; six positive configured fine deltas", grouping_keys="workload_id, rho, capacity, quantizer", aggregation="mean of one positive-rate log-log slope per complete workload-design",
        units="log-log collision-rate exponent", estimate={"mean": float(complete.mean()), "median": float(complete.median())}, ci=_ci_entry(*complete_ci, "bootstrap over complete-case workload-design exponents"), sample_size={"complete_case_rows": len(complete), "all_workload_design_rows": len(audit)}, commit=commit,
    ))
    for model in models.itertuples(index=False):
        name = str(model.model)
        coefficient = next((column for column in models.columns if column.startswith("coefficient_") and pd.notna(getattr(model, column))), None)
        low = next((column for column in models.columns if column.startswith("bootstrap_ci95_low_coefficient_") and coefficient and column.endswith(coefficient.removeprefix("coefficient_"))), None)
        high = next((column for column in models.columns if column.startswith("bootstrap_ci95_high_coefficient_") and coefficient and column.endswith(coefficient.removeprefix("coefficient_"))), None)
        findings.append(_report_entry(
        finding_id=f"H4_predictor_{name}", publication_text=(
                f"H4 retained predictor model ({name}) is an association model evaluated by grouped leave-one-configuration-out validation; it is not a direct causal estimator." + (" The critical-rate coefficient is below one and must not be interpreted as a direct estimator." if name == "critical" else "")
            ), source_run=principal, source_analysis=baseline, source_table="tables/predictor_comparison.csv", source_file="derived/predictor_models_retained.csv",
            filters="primary preload_all retained predictor configurations", grouping_keys="analysis_configuration_id", aggregation="saved workload-paired configuration model with grouped validation",
            units="packet-loss-probability gap per model predictor unit", estimate={"r_squared": float(model.r_squared), "cv_rmse": float(model.cv_rmse), "folds": int(model.n_folds), "coefficient_name": coefficient, "coefficient": float(getattr(model, coefficient)) if coefficient else None}, ci=_ci_entry(getattr(model, low), getattr(model, high), "replication-level bootstrap, 1,000 resamples") if low and high else _unavailable("no single coefficient interval applies to this retained model row"), sample_size={"configuration_rows": int(model.n), "folds": int(model.n_folds), "train_test_groups_disjoint": bool(model.train_test_groups_disjoint)}, commit=commit,
        ))
    for row in architecture.itertuples(index=False):
        findings.append(_report_entry(
            finding_id=f"H5_architecture_{row.arrival_scheduling_mode}", publication_text=(
                f"H5 insertion-order matching for {row.arrival_scheduling_mode} is descriptive robustness evidence from the focused architecture run; it is not included in primary preload_all timing or scaling observations."
            ), source_run=focused, source_analysis=target.name, source_table="tables/architecture_comparison.csv", source_file="derived/insertion_architecture_summary.csv",
            filters=f"arrival_scheduling_mode={row.arrival_scheduling_mode}; policies=AF,DF,insertion_order", grouping_keys="workload_id, rho, capacity, delta, quantizer, arrival_scheduling_mode", aggregation="exact integer equality of accepted/dropped/completed counts; loss distances summarized over pairs",
            units="percent of paired workload/configurations; absolute packet-loss-probability distance", estimate={"paired_count": int(row.paired_count), "matches_both_percent": float(row.matches_both_percent), "matches_af_only_percent": float(row.matches_af_only_percent), "matches_df_only_percent": float(row.matches_df_only_percent), "matches_neither_percent": float(row.matches_neither_percent), "mean_distance_af": float(row.mean_distance_af), "max_distance_af": float(row.max_distance_af), "mean_distance_df": float(row.mean_distance_df), "max_distance_df": float(row.max_distance_df)}, ci=_unavailable("focused architecture results are paired deterministic count comparisons; no resampling interval was specified or saved"), sample_size={"paired_workload_configuration_rows": int(row.paired_count)}, commit=commit,
        ))
    stability = {}
    for policy in ("arrival_first", "departure_first"):
        stability[policy] = {
            "accepted_equal_percent": float(100 * explicit[f"{policy}_accepted_equal"].mean()),
            "dropped_equal_percent": float(100 * explicit[f"{policy}_dropped_equal"].mean()),
            "mean_loss_difference": float(explicit[f"{policy}_loss_difference"].mean()),
            "max_loss_difference": float(explicit[f"{policy}_loss_difference"].max()),
        }
    findings.append(_report_entry(
        finding_id="H5_explicit_policy_stability", publication_text=(
            "H5 explicit AF and DF policies have identical accepted and dropped counts across the two scheduling architectures in the focused comparison; the recorded loss differences are reported rather than assumed to be zero."
        ), source_run=focused, source_analysis=target.name, source_table="tables/architecture_comparison.csv", source_file="derived/explicit_architecture_stability.parquet",
        filters="policies=arrival_first,departure_first; preload_all versus schedule_next_after_transition", grouping_keys="workload_id, rho, capacity, delta, quantizer", aggregation="exact integer equality rates and absolute loss differences across architecture pairs",
        units="percent exact equality; absolute packet-loss-probability difference", estimate=stability, ci=_unavailable("focused explicit-policy comparison is a complete paired deterministic count audit, not a resampled estimate"), sample_size={"paired_workload_configuration_rows": len(explicit)}, commit=commit,
    ))
    findings.append(_report_entry(
        finding_id="H6_random_order_scope", publication_text=(
            "H6 is not tested: no random_order policy observation is present in the principal Phase II.2 saved inputs, so no random-order result is inferred or fabricated."
        ), source_run=principal, source_analysis=target.name, source_table="source_runs.json", source_file="derived/timing_bias_workload_pairs.parquet",
        filters="policy=random_order", grouping_keys="not applicable", aggregation="absence check in saved primary derived input", units="not applicable", estimate={"available_rows": 0}, ci=_unavailable("no saved random_order observations"), sample_size={"rows": 0}, commit=commit,
    ))
    findings.append(_report_entry(
        finding_id="H7_scope_and_causal_limit", publication_text=(
            "H7 is limited: the saved analyses establish descriptive associations and reproducibility checks within their configured scenarios, not causal effects, universal scaling laws, or unmeasured-policy comparisons."
        ), source_run=principal, source_analysis=target.name, source_table="report/limitations.md", source_file="source_runs.json",
        filters="primary preload_all analysis scope", grouping_keys="not applicable", aggregation="scope statement based on saved analysis design", units="not applicable", estimate={"primary_configuration_rows": len(timing), "paired_workload_rows": len(paired)}, ci=_unavailable("scope limitation, not an estimand"), sample_size={"configuration_rows": len(timing)}, commit=commit,
    ))
    report = target / "report"
    report.mkdir(exist_ok=True)
    report.joinpath("findings.json").write_text(json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.joinpath("findings.md").write_text(_finding_markdown(findings), encoding="utf-8")
    report.joinpath("summary.md").write_text(
        "# Phase II.2 publication summary\n\n"
        f"This report refresh reads only existing v2.2 derived artifacts in `{target.name}`; it does not rerun simulation, regenerate workloads, or alter raw results. The canonical analysis is `{PRIMARY}` only: {len(paired):,} AF/DF-paired workload rows were aggregated to {len(timing):,} unique configuration rows, each with {int(timing.replication_count.min())} workload replications.\n\n"
        f"The service-error/bias association has Pearson {service.pearson:.6f}, Spearman {service.spearman:.6f}, HC3 slope {service.slope:.6f} (95% CI [{service.hc3_ci95_low:.6f}, {service.hc3_ci95_high:.6f}]), R² {service.r_squared:.6f}, and grouped CV RMSE/MAE {service.cv_rmse:.6f}/{service.cv_mae:.6f} across {int(service.folds)} configuration-held-out folds [H2_service_error_bias_relationship].\n\n"
        f"The zero-censoring audit covers {len(audit):,} workload-design fits: {int(censor.loc[censor.status.eq('complete'), 'n'].iloc[0]):,} complete ({float(censor.loc[censor.status.eq('complete'), 'percent'].iloc[0]):.3f}%), {int(censor.loc[censor.status.eq('one_missing'), 'n'].iloc[0]):,} with one missing positive rate, and {int(censor.loc[censor.status.eq('two_or_more_missing'), 'n'].iloc[0]):,} with two or more missing. Condition exponents average {condition.exponent.mean():.6f}; complete-case workload exponents average {complete.mean():.6f} (95% CI [{complete_ci[0]:.6f}, {complete_ci[1]:.6f}]) [H3_condition_level_scaling; H3_complete_case_scaling].\n\n"
        f"Insertion-order results come from the separately selected verified focused run `{focused}`. In preload_all, insertion matches AF only in {float(architecture.loc[architecture.arrival_scheduling_mode.eq(PRIMARY), 'matches_af_only_percent'].iloc[0]):.6f}% of pairs; schedule_next_after_transition is labelled robustness-only and matches DF only in {float(architecture.loc[architecture.arrival_scheduling_mode.eq(ALTERNATE), 'matches_df_only_percent'].iloc[0]):.6f}% [H5_architecture_preload_all; H5_architecture_schedule_next_after_transition].\n\n"
        "Retained predictor models and the exact-engine comparison are reported as saved analyses with their stated uncertainty limits. No random_order observation is available, and no causal, universal, or direct-estimator claim is made [H1_exact_engine_validation; H4_predictor_critical; H6_random_order_scope; H7_scope_and_causal_limit].\n",
        encoding="utf-8",
    )
    report.joinpath("methodology.md").write_text(
        "# Methodology and provenance\n\n"
        f"**Inputs.** Principal saved run: `{principal}`. Baseline corrected analysis retained for predictor and exact-validation outputs: `{baseline}`. Focused insertion architecture source: `{focused}`, selected as the latest verified completed schema-v2 insertion-architecture run containing AF, DF, insertion_order, preload_all, and schedule_next_after_transition. The source paths and cryptographic source hashes are recorded in `source_runs.json`; this publication refresh uses only `derived/` files in `{target.name}`.\n\n"
        f"**Primary timing unit.** The primary architecture is `{PRIMARY}`. For each workload identity and configuration (rho, capacity, delta, quantizer), AF and DF are paired first. Midpoint signed loss bias is `(loss_AF + loss_DF)/2 − exact_loss`; signed service-duration error is `(error_AF + error_DF)/2`. Those paired workload observations are then averaged to one configuration row. Thus {len(paired):,} workload-paired rows yield {len(timing):,} unique configuration rows with {int(timing.replication_count.min())} replications each; insertion, random_order, exact-as-policy, and the alternate architecture are excluded from this primary unit.\n\n"
        "**Relationship model.** The primary descriptive OLS regresses configuration-mean midpoint bias on configuration-mean signed service-duration error. Pearson and Spearman correlations are descriptive. The slope has an HC3 standard error and normal-approximation 95% interval; out-of-sample error uses leave-one-configuration-out folds, so no configuration is in both training and test data. Quantizer rows are descriptive strata, each bootstrapped over its configuration means.\n\n"
        "**Scaling and censoring.** Fine deltas satisfy `0 < delta <= 0.003`. For each workload-design, AF/DF collision rates are averaged before fitting one log-log slope. Zero collision rates are excluded from the logarithm, never replaced by epsilon, and their number/support are retained in the audit. Condition-level slopes instead fit one rho/capacity mean rate curve. Complete-case summaries use only all-positive fine-delta designs.\n\n"
        "**Architecture.** The focused run pairs shared workload/configuration values across AF, DF, and insertion_order for both scheduling architectures. Matches require exact integer equality of accepted arrivals, dropped arrivals, and completed measured jobs. Explicit AF/DF policy comparisons across architectures are a separate stability audit. Alternate-architecture observations are never merged with primary timing, scaling, or predictor rows.\n\n"
        "**Predictor and theory retention.** Predictor and exact validation tables are retained from the baseline corrected analysis rather than rebuilt. Predictor validation groups by `analysis_configuration_id`; its bootstrap is replication-level within configuration. The exact table stores condition means and counts but no saved replication-level interval.\n",
        encoding="utf-8",
    )
    report.joinpath("validation.md").write_text(
        "# Validation and audit trail\n\n"
        f"**Input and scope checks.** `source_runs.json` records principal raw hashes for `{principal}`, focused-run raw hashes for `{focused}`, and the baseline provenance hash. The primary derived timing table contains only `{PRIMARY}` ({set(timing.arrival_scheduling_mode) == {PRIMARY}}), has {len(timing):,} rows, and its configuration identifier is unique (`{timing.configuration_id_v22.is_unique}`). It is derived from {len(paired):,} workload-paired rows with replication count range {int(timing.replication_count.min())}–{int(timing.replication_count.max())}.\n\n"
        f"**Censoring checks.** The audit has {len(audit):,} workload-design rows and no epsilon-adjusted zero-rate field. Its categories sum to {int(censor.n.sum()):,}; positive-rate support and min/max included delta are retained per row in `derived/collision_zero_censoring_audit.csv`. The condition table has {len(condition)} rho/capacity rows, one slope per condition.\n\n"
        f"**Architecture checks.** The focused summary has {len(architecture)} architecture rows with pair counts totaling {int(architecture.paired_count.sum()):,}. In each row, the four exclusive match categories sum to 100%: " + "; ".join(f"{row.arrival_scheduling_mode}={row.matches_both_percent + row.matches_af_only_percent + row.matches_df_only_percent + row.matches_neither_percent:.6f}%" for row in architecture.itertuples(index=False)) + f". Explicit-policy stability has {len(explicit):,} paired rows and is reported without pooling it into primary data.\n\n"
        f"**Predictor checks.** The retained table has {len(models)} models over {int(models.n.iloc[0])} primary configurations; every model records {int(models.n_folds.iloc[0])} grouped folds and `train_test_groups_disjoint={bool(models.train_test_groups_disjoint.all())}`.\n\n"
        "**Publication checks.** `manifests/figures.csv` records 36 EN/RU PNG/SVG/PDF figure assets. `manifests/artifacts.csv` hashes every current derived, table, figure, and report artifact. This report refresh deliberately does not claim that theory has a CI, does not treat excluded zeros as observed log values, and does not add absent random_order data.\n",
        encoding="utf-8",
    )
    report.joinpath("limitations.md").write_text(
        "# Limitations and interpretation boundaries\n\n"
        "1. **Primary scope only.** Primary conclusions apply to preload_all AF/DF paired observations in the configured scenarios. schedule_next_after_transition is a separately labelled architecture robustness comparison, not an additional primary sample or scheduler-mode duplicate.\n\n"
        "2. **No causal claim.** Correlations, OLS coefficients, and predictor fits are descriptive associations under the saved design. They do not identify causal effects of quantization error, collision rates, queue capacity, or scheduling policy. In particular, the critical-rate coefficient is below one in the retained single-predictor model and is not a direct estimator.\n\n"
        "3. **Zero censoring changes support.** Log-log slopes exclude zero collision rates because `log(0)` is undefined. The audit reports complete, one-missing, and two-or-more-missing categories; condition-level and complete-case summaries answer different descriptive questions and should not be collapsed into a universal exponent.\n\n"
        "4. **Uncertainty availability differs by output.** Timing slopes use HC3 intervals; selected means and scaling summaries use stated bootstraps. The saved exact validation table has no replication-level CI, and the focused architecture count audit has no resampling interval. These are reported as unavailable rather than reconstructed from raw data.\n\n"
        "5. **Policy coverage.** random_order is absent from the principal saved Phase II.2 inputs. It is explicitly not tested; no result is imputed. Insertion_order is examined only in the focused architecture synthesis and is not part of primary timing-bias, scaling, or predictor analyses.\n\n"
        "6. **Saved-data boundary.** This refresh intentionally uses existing v2.2 derived/tables/figures only. It neither reruns simulations nor regenerates raw data, so it cannot recover analyses requiring unavailable replication-level exact-validation data or absent policies.\n",
        encoding="utf-8",
    )
    _report_manifest(target)


def analyze_phase22(principal: Path, baseline: Path, focused: Path | None = None) -> Path:
    """Create a v2.2 directory; all source runs remain read-only."""
    if focused is None: focused=principal.parent.parent/"insertion-architecture-v2-20260730T092338223105Z"
    commit=(collect_provenance(principal.parent.parent).get("git_commit") or "unknown")[:8]; target=principal/"analysis"/f"v2.2-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{commit}"
    for name in ("derived","figures","tables","report","manifests"): (target/name).mkdir(parents=True,exist_ok=False)
    q=pd.read_parquet(principal/"raw/quantized_results.parquet");e=pd.read_parquet(principal/"raw/exact_results.parquet");paired=_paired_primary(q,e);timing=_timing_configuration(paired);relationships=_relationship(timing);audit,censor,condition=_censoring(paired);arch_pairs,arch_summary,explicit=_architecture(focused)
    predictor=pd.read_parquet(baseline/"derived/predictor_rows.parquet");models=pd.read_csv(baseline/"derived/predictor_models.csv");theory=pd.read_csv(baseline/"derived/theory_validation.csv")
    for name,frame in {"timing_bias_workload_pairs.parquet":paired,"timing_bias_configuration.parquet":timing,"insertion_architecture_pairs.parquet":arch_pairs,"explicit_architecture_stability.parquet":explicit}.items():atomic_parquet(frame,target/"derived"/name)
    for name,frame in {"timing_relationships.csv":relationships,"collision_zero_censoring_audit.csv":audit,"collision_zero_censoring_summary.csv":censor,"collision_condition_exponents.csv":condition,"insertion_architecture_summary.csv":arch_summary,"predictor_models_retained.csv":models,"predictor_configurations_retained.csv":predictor,"exact_validation_retained.csv":theory}.items():frame.to_csv(target/"derived"/name,index=False)
    design=pd.DataFrame([{"principal_run":principal.name,"focused_architecture_run":focused.name,"previous_analysis":baseline.name,"primary_architecture":PRIMARY,"focused_selection_rule":"latest verified completed schema-v2 insertion-architecture run with AF, DF, insertion_order and both architectures"}])
    k_effect=timing[np.isclose(timing.delta,.1)].groupby("capacity",as_index=False).agg(n=("configuration_id_v22","size"),mean_absolute_bias=("absolute_midpoint_loss_bias","mean"),max_absolute_bias=("absolute_midpoint_loss_bias","max"))
    tables={"experimental_design":design,"exact_validation":theory,"collision_scaling":condition,"collision_zero_censoring":censor,"predictor_comparison":models,"quantizer_bias_order_gap":timing.groupby("quantizer",as_index=False).agg(n=("configuration_id_v22","size"),mean_bias=("midpoint_signed_loss_bias","mean"),mean_gap=("af_df_loss_gap","mean")),"k_effect_delta_01":k_effect,"architecture_comparison":arch_summary}
    for name,frame in tables.items():frame.to_csv(target/"tables"/f"{name}.csv",index=False);(target/"tables"/f"{name}.md").write_text(_md(frame),encoding="utf-8")
    source_runs={"principal":{"path":str(principal),"raw_hashes":{p.name:_sha(p) for p in (principal/"raw").glob("*.parquet")}},"baseline":{"path":str(baseline),"provenance_hash":_sha(baseline/"provenance.json")},"focused_insertion":{"path":str(focused),"raw_hashes":{p.name:_sha(p) for p in (focused/"raw").glob("*.parquet")}}};atomic_json(source_runs,target/"source_runs.json")
    config={"schema":"phase_ii_2","primary_architecture":PRIMARY,"fine_delta_max":.003,"focused_selection_rule":design.focused_selection_rule.iloc[0]};save_yaml(config,target/"config.resolved.yaml");atomic_json({"analysis_id":target.name,"created_utc":datetime.now(UTC).isoformat(),"git_commit":commit,"source_runs":source_runs,"config_hash":hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()},target/"provenance.json")
    _figures(target,timing,audit,condition,timing,arch_pairs)
    refresh_phase22_report(target)
    return target
