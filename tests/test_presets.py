from wb_tools.core import BUILTIN_PRESETS, prepare_markers
from wb_tools.presets import PRODUCT_PRESETS, band_color, BLUE, ORANGE, GREEN

PLUS, STANDARD = PRODUCT_PRESETS


def test_manufacturer_nominal_values():
    assert BUILTIN_PRESETS[PLUS] == [250, 130, 100, 70, 55, 35, 25, 15, 10]
    assert BUILTIN_PRESETS[STANDARD] == [180, 130, 100, 70, 55, 40, 35, 25, 15, 10]
    for name, product in PRODUCT_PRESETS.items():
        values = BUILTIN_PRESETS[name]
        assert prepare_markers(range(len(values)), values)
        assert product["source"].startswith("https://www.thermofisher.com/")


def test_reference_colors_are_product_specific():
    assert band_color(PLUS, 70) == ORANGE
    assert band_color(PLUS, 25) == ORANGE
    assert band_color(STANDARD, 25) == BLUE
    for name in (PLUS, STANDARD):
        assert band_color(name, 10) == GREEN
        assert band_color(name, 130) == BLUE
    assert band_color("Custom", 25) is None
    assert band_color(PLUS, 40) is None
