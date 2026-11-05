"""Compatibility entry point. New code should import blotscope.core or blotscope.gui."""
from blotscope.core import *

def main():
    from blotscope.gui import main as launch
    launch()

def __getattr__(name):
    if name == "WBMarkerApp":
        from blotscope.gui import WBMarkerApp
        return WBMarkerApp
    if name == "sample_line_intensity":
        from blotscope.imaging import sample_line_intensity
        return sample_line_intensity
    raise AttributeError(name)

if __name__ == "__main__":
    main()
