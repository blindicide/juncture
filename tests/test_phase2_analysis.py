from pathlib import Path

import pandas as pd

from juncture.analysis_v2 import analyze_run_v2
from juncture.campaign import create_run, execute_run
from juncture.config import CampaignConfig
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
