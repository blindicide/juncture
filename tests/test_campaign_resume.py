from pathlib import Path

from juncture.campaign import create_run, execute_run, run_status
from juncture.config import CampaignConfig


def test_campaign_resume_is_idempotent(tmp_path: Path) -> None:
    config = CampaignConfig(
        name="test",
        loads=[0.8],
        capacities=[1],
        deltas=[0.1],
        policies=["departure_first"],
        warmup_arrivals=2,
        measured_arrivals=20,
    )
    run_dir = create_run(config, tmp_path)
    execute_run(run_dir, checkpoint_size=1)
    assert run_status(run_dir) == {"complete": 2}
    execute_run(run_dir, checkpoint_size=1)
    assert run_status(run_dir) == {"complete": 2}
