from blotscope.core import BUILTIN_PRESETS, prepare_markers
from blotscope.presets import PRODUCT_PRESETS, band_color, BLUE, ORANGE, GREEN

PLUS, STANDARD = list(PRODUCT_PRESETS)[:2]


def test_manufacturer_nominal_values():
    assert BUILTIN_PRESETS[PLUS] == [250, 130, 100, 70, 55, 35, 25, 15, 10]
    assert BUILTIN_PRESETS[STANDARD] == [180, 130, 100, 70, 55, 40, 35, 25, 15, 10]
    for name, product in PRODUCT_PRESETS.items():
        values = BUILTIN_PRESETS[name]
        assert prepare_markers(range(len(values)), values)
        assert product["source"].startswith("https://")


def test_reference_colors_are_product_specific():
    assert band_color(PLUS, 70) == ORANGE
    assert band_color(PLUS, 25) == ORANGE
    assert band_color(STANDARD, 25) == BLUE
    for name in (PLUS, STANDARD):
        assert band_color(name, 10) == GREEN
        assert band_color(name, 130) == BLUE
    assert band_color("Custom", 25) is None
    assert band_color(PLUS, 40) is None


def test_solarbio_pr2090_values_and_colors():
    from blotscope.presets import RED
    name = "Solarbio PR2090 (20–600 kDa)"
    assert BUILTIN_PRESETS[name] == [600, 400, 250, 230, 130, 110, 75, 45, 20]
    assert band_color(name, 75) == RED
    assert band_color(name, 20) == GREEN
    assert band_color(name, 600) == BLUE
