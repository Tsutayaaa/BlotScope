"""Opt-in real Tk checks: WB_MARKER_GUI_TESTS=1 python -m pytest tests/test_gui.py."""
import os
import pytest

pytestmark = pytest.mark.skipif(os.environ.get("WB_MARKER_GUI_TESTS") != "1", reason="requires a desktop Tk session")

@pytest.fixture(params=["en", "zh"])
def app(request, tmp_path, monkeypatch):
    from wb_tools import gui, i18n
    old = i18n._language
    i18n.set_language(request.param)
    monkeypatch.setattr(gui, "config_dir", lambda: tmp_path)
    window = gui.WBMarkerApp()
    window.update()
    yield window
    window.destroy()
    i18n.set_language(old)


def test_responsive_pages_and_foldouts(app):
    assert all(not expanded.get() for _, _, expanded in app._foldouts)
    for size in ("1180x760", "820x560", "1440x900"):
        app.geometry(size)
        app.update()
        for button, body, expanded in app._foldouts:
            if not expanded.get():
                button.invoke()
        for index in (0, 1):
            app.workflow_notebook.tab(1, state="normal")
            app.workflow_notebook.select(index)
            app.update()
            content, canvas = app._scroll_pages[index]
            assert content.winfo_width() == canvas.winfo_width()
            assert not canvas.cget("xscrollcommand")
            def inspect(widget):
                for child in widget.winfo_children():
                    if child.winfo_ismapped() and child.winfo_class() in ("TButton", "TLabel"):
                        assert child.winfo_width() + 4 >= child.winfo_reqwidth(), child.cget("text")
                    inspect(child)
            inspect(content)
    assert app.result_tree.cget("displaycolumns") == ("lane", "band", "reported", "confidence")


def test_product_colors_survive_group_switches(app):
    from PIL import Image
    from wb_tools.presets import PRODUCT_PRESETS, ORANGE, BLUE
    plus, standard = PRODUCT_PRESETS
    app.images = [("synthetic.png", Image.new("RGB", (100, 200), "white"))]
    app.current_image_index = 0
    app.image_combo.configure(values=["synthetic.png"])
    for index, name in enumerate((plus, standard)):
        app.add_marker_lane((20 + index * 30, 0), (20 + index * 30, 180))
        app.preset_var.set(name)
        app.on_preset_selected()
        app.peaks = list(range(0, len(app.presets[name]) * 10, 10))
        app.apply_full_preset()
        assert app.marker_lanes[index].preset_name == name
    for index, expected in ((0, ORANGE), (1, BLUE)):
        app.load_marker_lane(index)
        peak = next(p for p, value in app.peak_kda.items() if value == "25")
        assert app._peak_color(peak) == expected
        assert app.tree.item(str(peak), "tags") == (expected,)
    app.preset_var.set(plus)
    assert app._selected_product_name([100, 70, 25, 10]) == ""
    # Full details remain available even though the table is compact.
    item = app.result_tree.insert("", "end", values=("Lane 1", 1, "Marker 2", 42, 70, "60–80", "high", "~70 kDa", "interpolation"))
    app.result_tree.selection_set(item)
    app._show_result_details()
    assert "Marker 2" in app.result_details.get("1.0", "end")
    assert "60–80" in app.result_details.get("1.0", "end")


def test_detected_target_bands_are_drawn_on_image_and_profile(app):
    from PIL import Image, ImageDraw
    from wb_tools.core import linear_fit
    image = Image.new("RGB", (100, 200), "white")
    draw = ImageDraw.Draw(image)
    for y in (40, 100, 160):
        draw.rectangle((35, y-3, 65, y+3), fill="black")
    app.images = [("synthetic.png", image)]
    app.current_image_index = 0
    app.image_combo.configure(values=["synthetic.png"])
    app.line_start, app.line_end = (10, 0), (10, 199)
    app.peaks = [10, 190]
    app.peak_kda = {10: "100", 190: "10"}
    app.fit_result = linear_fit(app.peaks, [100, 10])
    app.workflow_notebook.tab(1, state="normal")
    app.workflow_notebook.select(1)
    app.update()
    app.add_target_lane((50, 0), (50, 199))
    lane = app.target_lanes[0]
    assert len(lane.peaks) == 3
    app.on_lane_selected()
    for canvas in (app.image_canvas, app.target_plot):
        points = [item for item in canvas.find_all() if canvas.type(item) == "oval"]
        assert len(points) == len(lane.peaks)
        assert all(canvas.coords(item)[2] > canvas.coords(item)[0] for item in points)
    app.zoom_image(1.25)
    app.reanalyze_selected_lane()
    assert len([item for item in app.target_plot.find_all() if app.target_plot.type(item) == "oval"]) == 3
