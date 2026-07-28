from pathlib import Path

from juncture.analysis import analyze_run
from juncture.campaign import create_run, execute_run
from juncture.config import CampaignConfig
from juncture.tables import build_tables


def test_single_delta_analysis_writes_schema_valid_empty_scaling_table(tmp_path: Path) -> None:
    config = CampaignConfig(
        name="single_delta",
        loads=[0.8],
        capacities=[1],
        deltas=[0.1],
        policies=["departure_first", "arrival_first"],
        warmup_arrivals=2,
        measured_arrivals=20,
    )
    run_dir = create_run(config, tmp_path)
    execute_run(run_dir, checkpoint_size=1)
    analyze_run(run_dir)
    build_tables(run_dir)
    assert (run_dir / "tables" / "collision_scaling_regression.csv").exists()
