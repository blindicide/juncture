import pytest

from juncture.quantization import quantize


def test_quantizer_boundaries() -> None:
    assert quantize(0.0, 0.1) == 0
    assert quantize(0.199999, 0.1, "floor") == 1
    assert quantize(0.15, 0.1, "nearest") == 1
    assert quantize(0.101, 0.1, "ceiling") == 2


def test_negative_time_rejected() -> None:
    with pytest.raises(ValueError):
        quantize(-0.01, 0.1)
