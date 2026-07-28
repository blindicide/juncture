from juncture.cli import main


def test_validate_command(capsys) -> None:
    assert main(["validate"]) == 0
    assert "rho=0.5" in capsys.readouterr().out
