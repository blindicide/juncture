from juncture.theory import stationary_loss_probability


def test_rho_one_formula() -> None:
    assert stationary_loss_probability(1.0, 4) == 0.2


def test_known_loss() -> None:
    assert abs(stationary_loss_probability(0.5, 1) - 1 / 3) < 1e-12
