from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from juncture.phase221 import (
    FORBIDDEN_RUSSIAN,
    _architecture_rows,
    _capacity_table,
    _critical_figure,
    _finding,
    _predictor_coefficient,
    _quantizer_table,
    _scaling_figures,
)


def _models() -> pd.DataFrame:
    return pd.DataFrame([{
        "model": "critical", "coefficient_const": -0.2, "hc3_standard_error_const": .1,
        "bootstrap_ci95_low_coefficient_const": -.3, "bootstrap_ci95_high_coefficient_const": -.1,
        "coefficient_critical_collision_rate": .454996, "hc3_standard_error_critical_collision_rate": .02,
        "bootstrap_ci95_low_coefficient_critical_collision_rate": .45,
        "bootstrap_ci95_high_coefficient_critical_collision_rate": .46,
        "r_squared": .84, "cv_rmse": .0016, "n": 648,
    }])


def test_predictor_export_selects_explicit_non_intercept_term() -> None:
    selected = _predictor_coefficient(_models(), "critical", "critical_collision_rate")
    assert selected["coefficient"] == pytest.approx(.454996)
    assert selected["predictor_term"] != "const"
    with pytest.raises(ValueError, match="intercept"):
        _predictor_coefficient(_models(), "critical", "const")


def test_critical_figure_uses_648_configs_fit_and_identity(tmp_path: Path) -> None:
    configs = pd.DataFrame({
        "analysis_configuration_id": [f"c{i}" for i in range(648)],
        "arrival_scheduling_mode": ["preload_all"] * 648,
        "critical_collision_rate": np.linspace(0, .01, 648),
        "absolute_policy_gap": np.linspace(0, .004, 648),
    })
    manifest: list[dict[str, object]] = []
    _critical_figure(configs, {"slope": .454996, "intercept": -.0002218, "r_squared": .84, "cv_rmse": .0016}, tmp_path, manifest)
    assert len(manifest) == 6
    assert {row["x"] for row in manifest} == {"critical_acceptance_difference_rate_per_arrival"}
    assert {row["y"] for row in manifest} == {"mean_absolute_policy_gap"}
    assert (tmp_path / "critical_predictor_en.svg").exists()


def _architecture() -> pd.DataFrame:
    return pd.DataFrame([
        {"arrival_scheduling_mode": "preload_all", "paired_count": 540, "matches_af_only": 507, "matches_df_only": 0, "matches_both": 33, "matches_neither": 0, "matches_af_only_percent": 93.8888889, "matches_df_only_percent": 0., "matches_both_percent": 6.1111111, "matches_neither_percent": 0.},
        {"arrival_scheduling_mode": "schedule_next_after_transition", "paired_count": 540, "matches_af_only": 0, "matches_df_only": 507, "matches_both": 33, "matches_neither": 0, "matches_af_only_percent": 0., "matches_df_only_percent": 93.8888889, "matches_both_percent": 6.1111111, "matches_neither_percent": 0.},
    ])


def test_architecture_categories_are_exclusive_and_validated() -> None:
    rows = _architecture_rows(_architecture())
    assert rows.loc[0, "matches_af_only_percent"] == pytest.approx(93.8888889)
    assert rows.loc[1, "matches_df_only_percent"] == pytest.approx(93.8888889)


def _timing() -> pd.DataFrame:
    return pd.DataFrame({
        "arrival_scheduling_mode": ["preload_all"] * 6,
        "delta": [.1] * 3 + [.03] * 3,
        "capacity": [1, 4, 8, 1, 4, 8],
        "configuration_id_v22": [f"c{i}" for i in range(6)],
        "af_df_loss_gap": [.02, -.04, .06, .01, .02, .03],
        "absolute_midpoint_loss_bias": [.01, .02, .03, .01, .02, .03],
        "midpoint_signed_loss_bias": [-.01, .02, -.03, .01, .02, .03],
        "quantizer": ["floor", "nearest", "ceiling", "floor", "nearest", "ceiling"],
        "mean_signed_service_duration_error_pair": [-.1, 0, .1, -.1, 0, .1],
        "mean_absolute_service_duration_error_pair": [.1] * 6,
        "service_zero_tick_fraction_pair": [0] * 6,
    })


def test_capacity_table_has_delta_point_one_gap_bias_and_ratios() -> None:
    table = _capacity_table(_timing())
    assert set(table.columns) >= {"mean_ordering_half_width", "bias_to_policy_gap_ratio", "bias_to_half_width_ratio"}
    assert len(table) == 3
    assert table.mean_absolute_policy_gap.notna().all()


def test_quantizer_table_contains_service_error_and_pearson() -> None:
    table = _quantizer_table(_timing(), .852)
    assert table.quantizer.tolist() == ["floor", "nearest", "ceiling"]
    assert table.mean_signed_service_duration_error.notna().all()
    assert table.service_error_bias_pearson.eq(.852).all()


def test_primary_scaling_figure_uses_delta_log_curve(tmp_path: Path) -> None:
    deltas = np.array([.00001, .00003, .0001, .0003, .001, .003])
    pairs = pd.DataFrame({"arrival_scheduling_mode": ["preload_all"] * 6, "rho": [1.] * 6, "capacity": [8] * 6, "delta": deltas, "policy_neutral_collision_rate": deltas * 2})
    exponents = pd.DataFrame({"rho": [1.], "capacity": [8], "exponent": [1.], "intercept": [np.log(2)], "r_squared": [.99]})
    manifest: list[dict[str, object]] = []
    _scaling_figures(pairs, exponents, tmp_path, manifest)
    primary = [row for row in manifest if row["figure_id"] == "collision_frequency_delta"]
    assert len(primary) == 6
    assert {row["fit_range"] for row in primary} == {"0 < delta <= 0.003"}


def test_russian_localization_forbidden_identifiers_are_detectable() -> None:
    localized = "Предварительное добавление поступлений; только AF"
    assert not any(token in localized for token in FORBIDDEN_RUSSIAN)
    assert "preload_all" in FORBIDDEN_RUSSIAN


def test_finding_requires_source_resolution_fields() -> None:
    fields = {"finding_id", "publication_text", "source_run", "source_analysis", "source_file", "row_selector", "filters", "grouping_keys", "aggregation", "units", "estimate", "ci", "sample_size", "commit"}
    item = {field: "x" for field in fields}
    assert _finding(**item) == item
    item.pop("source_file")
    with pytest.raises(ValueError, match="source_file"):
        _finding(**item)
