from juncture.campaign import planned_task_count
from juncture.cli import main
from juncture.config import CampaignConfig


def test_validate_command(capsys) -> None:
    assert main(["validate"]) == 0
    assert "rho=0.5" in capsys.readouterr().out


def test_planned_task_count_includes_exact_and_policies() -> None:
    config = CampaignConfig(
        name="count", schema_version=2, loads=[0.8], capacities=[4], deltas=[0.1],
        quantizers=["floor"], policies=["arrival_first", "departure_first"], replications=2,
    )
    assert planned_task_count(config) == 6
