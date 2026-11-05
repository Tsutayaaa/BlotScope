"""Manufacturer-labelled nominal ladder values and reference colors.

Values correspond to the product's illustrated SDS-PAGE reference, not a
lot-specific calibration. Color is a visual aid, never an image classifier.
"""
BLUE = "#2563a6"
ORANGE = "#c44925"
GREEN = "#57851c"
PRODUCT_PRESETS = {
    "PageRuler™ Plus (10–250 kDa)": {
        "name": "PageRuler™ Plus Prestained Protein Ladder, 10 to 250 kDa",
        "catalog": "26619 / 26620",
        "values": [250, 130, 100, 70, 55, 35, 25, 15, 10],
        "colors": {70: ORANGE, 25: ORANGE, 10: GREEN},
        "source": "https://www.thermofisher.com/order/catalog/product/26619",
    },
    "PageRuler™ (10–180 kDa)": {
        "name": "PageRuler™ Prestained Protein Ladder, 10 to 180 kDa",
        "catalog": "26616 / 26617",
        "values": [180, 130, 100, 70, 55, 40, 35, 25, 15, 10],
        "colors": {70: ORANGE, 10: GREEN},
        "source": "https://www.thermofisher.com/order/catalog/product/26616",
    },
}


def band_color(preset_name: str, kda: float) -> str | None:
    product = PRODUCT_PRESETS.get(preset_name)
    if product is None or kda not in product["values"]:
        return None
    return product["colors"].get(kda, BLUE)
