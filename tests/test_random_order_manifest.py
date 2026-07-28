from juncture.campaign import task_manifest
from juncture.config import CampaignConfig


def test_random_order_manifest_repeats_only_tie_breaks() -> None:
    config = CampaignConfig(
        name="random",
        loads=[1.0],
        capacities=[1],
        deltas=[0.1],
        policies=["departure_first", "random_order"],
        tie_repetitions=3,
    )
    manifest = task_manifest(config)
    random = manifest[manifest.policy == "random_order"]
    deterministic = manifest[manifest.policy == "departure_first"]
    assert len(random) == 3
    assert len(deterministic) == 1
    assert random.workload_seed.nunique() == 1
    assert random.tie_seed.nunique() == 3
