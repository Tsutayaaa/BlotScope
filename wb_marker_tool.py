"""Compatibility entry point. New code should import wb_tools.core or wb_tools.gui."""
from wb_tools.core import *

def main():
    from wb_tools.gui import main as launch
    launch()

def __getattr__(name):
    if name == "WBMarkerApp":
        from wb_tools.gui import WBMarkerApp
        return WBMarkerApp
    if name == "sample_line_intensity":
        from wb_tools.imaging import sample_line_intensity
        return sample_line_intensity
    raise AttributeError(name)

if __name__ == "__main__":
    main()
