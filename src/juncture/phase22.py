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
    return frame.to_markdown(index=False) + "\n"


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
    values["insertion_matches_neither"]=~values.insertion_matches_arrival_first & ~values.insertion_matches_departure_first
    summary=values.groupby("arrival_scheduling_mode",as_index=False).agg(paired_count=("workload_id","size"),matches_af=("insertion_matches_arrival_first","sum"),matches_df=("insertion_matches_departure_first","sum"),matches_neither=("insertion_matches_neither","sum"),mean_distance_af=("insertion_loss_distance_arrival_first","mean"),max_distance_af=("insertion_loss_distance_arrival_first","max"),mean_distance_df=("insertion_loss_distance_departure_first","mean"),max_distance_df=("insertion_loss_distance_departure_first","max"))
    for c in ["matches_af","matches_df","matches_neither"]:summary[f"{c}_percent"]=100*summary[c]/summary.paired_count
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
    service=relationships[relationships.model=="service_signed"].iloc[0];critical=models[models.model=="critical"].iloc[0];complete=audit[audit.status=="complete"].exponent;complete_ci=_ci(complete)
    findings=[{"id":"service_bias_relationship","publication_text":"Signed service-duration error is descriptively associated with midpoint loss bias.","source_run":principal.name,"source_analysis":baseline.name,"table":"derived/timing_relationships.csv","filters":"preload_all, AF/DF paired","grouping":"configuration","aggregation":"mean of 30 workload pairs","units":"loss probability per time error","estimate":float(service.slope),"ci":[float(service.hc3_ci95_low),float(service.hc3_ci95_high)],"n":int(service.n),"commit":commit},{"id":"complete_case_scaling","publication_text":"Complete-case fine-delta workload exponents are reported with zero-censoring disclosed.","source_run":principal.name,"source_analysis":baseline.name,"table":"derived/collision_zero_censoring_audit.csv","filters":"preload_all; positive collision rates only","grouping":"workload-design","aggregation":"complete-case mean","units":"log-log exponent","estimate":float(complete.mean()),"ci":list(complete_ci),"n":len(complete),"commit":commit},{"id":"critical_predictor","publication_text":"Critical rate remains an association rather than a direct estimator.","source_run":principal.name,"source_analysis":baseline.name,"table":"derived/predictor_models_retained.csv","filters":"preload_all configurations","grouping":"configuration","aggregation":"retained model","units":"loss probability per critical rate","estimate":float(critical.coefficient_critical_collision_rate),"ci":[float(critical.bootstrap_ci95_low_coefficient_critical_collision_rate),float(critical.bootstrap_ci95_high_coefficient_critical_collision_rate)],"n":int(critical.n),"commit":commit}]
    (target/"report"/"summary.md").write_text(f"# Phase II.2 summary\n\nPrimary scope is `{PRIMARY}` only. Timing analysis has {len(timing)} configuration rows from {len(paired)} paired workloads. Zero-censoring audit has {len(audit)} workload-design fits. The selected architecture run is `{focused.name}`.\n",encoding="utf-8")
    (target/"report"/"methodology.md").write_text("# Methodology\n\nAF/DF are paired within workload replication before configuration aggregation. Collision fits exclude zero rates without epsilon replacement and disclose censoring. Architecture results use a separately selected verified focused run.\n",encoding="utf-8")
    (target/"report"/"findings.md").write_text("# Findings\n\n"+"\n\n".join(f"- {x['publication_text']} Estimate={x['estimate']:.6g}; n={x['n']}; source `{x['table']}`." for x in findings)+"\n",encoding="utf-8")
    (target/"report"/"limitations.md").write_text("# Limitations\n\nNo causal claims are made. Zero collision rates are censored for log fitting and reported explicitly. Theory validation has no confidence interval. Random-order results are unavailable in the principal run.\n",encoding="utf-8")
    (target/"report"/"validation.md").write_text(f"# Validation\n\nPrimary configuration IDs unique: {timing.configuration_id_v22.is_unique}. Predictor configurations retained: {len(predictor)}. Explicit architecture equality is reported rather than assumed.\n",encoding="utf-8")
    (target/"report"/"findings.json").write_text(json.dumps(findings,indent=2),encoding="utf-8")
    artifact: list[dict[str, str]]=[]
    for directory in (target/"derived",target/"figures",target/"tables",target/"report"):
        artifact.extend({"path":str(p.relative_to(target)),"sha256":_sha(p)} for p in directory.glob("*") if p.is_file())
    pd.DataFrame(artifact).to_csv(target/"manifests"/"artifacts.csv",index=False)
    return target
