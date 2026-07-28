from pathlib import Path

from juncture.analysis_v2 import analyze_run_v2
from juncture.campaign import create_run, execute_run
from juncture.config import CampaignConfig
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
