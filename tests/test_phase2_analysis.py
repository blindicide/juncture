from pathlib import Path

import pandas as pd

from juncture.analysis_v2 import AnalysisConfig, _predictor_rows, _scaling, analyze_run_v2
from juncture.campaign import create_run, execute_run
from juncture.config import CampaignConfig
from juncture.phase22 import _FINDING_FIELDS, _censoring, _report_entry
from juncture.regression import fit_grouped_ols
from juncture.verification import verify_run


def test_versioned_analysis_preserves_historical_output_locations(tmp_path: Path) -> None:
    config = CampaignConfig(
        name="v2-analysis", schema_version=2, loads=[0.8], capacities=[1], deltas=[0.1],
        policies=["departure_first", "arrival_first"], warmup_arrivals=1, measured_arrivals=8,
    )
    run_dir = create_run(config, tmp_path)
    execute_run(run_dir, checkpoint_size=1)
    assert verify_run(run_dir)["ok"]
    analysis = analyze_run_v2(run_dir)
    assert (analysis / "provenance.json").exists()
    assert (analysis / "derived" / "paired_bias_decomposition.parquet").exists()
    assert not (run_dir / "derived" / "paired_bias_decomposition.parquet").exists()


def test_grouped_regression_handles_constant_predictor() -> None:
    frame = pd.DataFrame({
        "y": [0.1, 0.2, 0.3, 0.4], "x": [1.0, 2.0, 3.0, 4.0],
        "constant": [1.0, 1.0, 1.0, 1.0], "group": ["a", "a", "b", "b"],
    })
    result = fit_grouped_ols(frame, "y", ["x", "constant"], "test", "group")
    assert result["n"] == 4
    assert result["validation_group"] == "group"
    assert result["n_folds"] == 2
    assert result["train_test_groups_disjoint"] is True


def test_scaling_averages_af_df_before_one_primary_workload_slope() -> None:
    rows = []
    for mode in ("preload_all", "schedule_next_after_transition"):
        for delta, af, df in ((0.001, 0.08, 0.12), (0.002, 0.02, 0.03)):
            rows.extend(
                [
                    {"workload_id": "w", "rho": 0.8, "capacity": 4, "quantizer": "floor", "arrival_scheduling_mode": mode, "delta": delta, "policy": "arrival_first", "collision_event_fraction": af},
                    {"workload_id": "w", "rho": 0.8, "capacity": 4, "quantizer": "floor", "arrival_scheduling_mode": mode, "delta": delta, "policy": "departure_first", "collision_event_fraction": df},
                ]
            )
    slopes, summary, input_rows = _scaling(
        pd.DataFrame(rows).query("arrival_scheduling_mode == 'preload_all'"),
        AnalysisConfig(bootstrap_resamples=20),
    )
    assert len(input_rows) == 2
    assert len(slopes) == 1
    assert len(summary) == 1
    assert "policy" not in summary
    assert input_rows.deterministic_mean_collision_event_fraction.tolist() == [0.1, 0.025]


def test_predictors_aggregate_paired_workloads_to_one_configuration_row() -> None:
    paired = pd.DataFrame(
        [
            {"pair_id": f"p-{rep}", "workload_id": f"w-{rep}", "rho": 0.8, "capacity": 4, "delta": 0.001, "quantizer": "floor", "arrival_scheduling_mode": "preload_all", "absolute_packet_loss_probability_gap": gap}
            for rep, gap in enumerate((0.1, 0.2, 0.3, 0.4))
        ]
    )
    quantized = pd.DataFrame(
        [
            {"pair_id": f"p-{rep}", "workload_id": f"w-{rep}", "rho": 0.8, "capacity": 4, "delta": 0.001, "quantizer": "floor", "arrival_scheduling_mode": "preload_all", "policy": policy, "collision_event_fraction": collision, "mixed_collision_rate": collision / 2, "critical_acceptance_difference_rate": collision / 4}
            for rep, collision in enumerate((0.1, 0.2, 0.3, 0.4))
            for policy in ("arrival_first", "departure_first")
        ]
    )
    config = AnalysisConfig(bootstrap_resamples=20, predictor_bootstrap_resamples=10)
    workloads, configurations = _predictor_rows(paired, quantized, config)
    assert len(workloads) == 4
    assert len(configurations) == 1
    assert configurations.n_workloads.item() == 4
    assert configurations.analysis_configuration_id.is_unique


def test_phase22_zero_audit_keeps_zeros_out_of_log_fit_without_epsilon() -> None:
    rows = pd.DataFrame(
        {
            "workload_id": ["w"] * 3,
            "rho": [0.8] * 3,
            "capacity": [4] * 3,
            "quantizer": ["floor"] * 3,
            "arrival_scheduling_mode": ["preload_all"] * 3,
            "delta": [0.001, 0.002, 0.003],
            "policy_neutral_collision_rate": [0.0, 0.02, 0.01],
        }
    )
    audit, summary, condition = _censoring(rows)
    assert audit.iloc[0].status == "one_missing"
    assert audit.iloc[0].positive_fine_deltas == 2
    assert audit.iloc[0].min_included_delta == 0.002
    assert summary.n.sum() == 1
    assert condition.iloc[0].positive_fine_deltas == 2


def test_phase22_report_findings_require_traceability_fields() -> None:
    entry = {field: "present" for field in _FINDING_FIELDS}
    assert _report_entry(**entry) == entry
    entry.pop("commit")
    try:
        _report_entry(**entry)
    except ValueError as error:
        assert "commit" in str(error)
    else:
        raise AssertionError("report entry without a commit was accepted")
