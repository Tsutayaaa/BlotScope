import math
import pytest
from wb_tools.core import prepare_markers, linear_fit, parse_preset_values

@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nonfinite_calibration_is_rejected(bad):
    for func in (prepare_markers, linear_fit):
        with pytest.raises(ValueError):
            func([0, bad], [100, 50])
        with pytest.raises(ValueError):
            func([0, 10], [100, bad])
    with pytest.raises(ValueError):
        parse_preset_values(f"100 {bad}")
