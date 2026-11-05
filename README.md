# WB Tools — WB Marker

A local desktop tool for estimating **apparent molecular weight** from Western blot images. Calibrate against marker bands, analyze target lanes, compare multiple marker groups, and export band-level results with calibration diagnostics. Images are processed on your computer and are not uploaded.

**Currently supported platform: macOS.** The current packaged app is built for Apple Silicon (arm64). Intel builds are not supplied or verified. Windows and Linux are not currently supported releases.

**Interface:** English by default, with Simplified Chinese available under **Language / 语言**. Save your results and restart the app after changing the language.

[中文使用说明](docs/wb-marker.md) · [Build and distribution guide](docs/packaging.md)

> **Screenshot placeholder — main window**
>
> Add `docs/images/main-window.png`, then uncomment the image below.
<!-- ![WB Marker main window](docs/images/main-window.png) -->

## Choose how to run it

| Option | Suitable for | Requirements |
| --- | --- | --- |
| Packaged `WB Marker.app` | Everyday image analysis | A compatible Apple Silicon Mac; no Python installation needed |
| Run from source | Development, customization, or rebuilding | macOS, Python 3.10+ with Tk, and the dependencies below |

The `.app` is a build artifact, not part of the source checkout. Cloning this repository alone does not install the packaged app. A public download is not currently documented here; obtain the app from the maintainer or build it using the instructions below.

## Use the packaged macOS app

1. Obtain `WB Marker.app` (or extract the ZIP containing it).
2. Drag the **whole app** into your **Applications** folder. Do not extract its internal executable.
3. Double-click **WB Marker** to start. You do not need Terminal, Python, or a virtual environment.
4. Choose **Language / 语言 → English** or **简体中文** if desired. The choice takes effect on the next launch; the current analysis is not reset.
5. Click **1 Import images** and follow the workflow below.

The current local build is not Developer ID signed or Apple notarized. macOS may ask for approval before opening an app received from another computer. Only approve a copy you trust, using macOS Privacy & Security settings if necessary. See [Apple’s opening-app guidance](https://support.apple.com/en-us/102445). Formal public distribution requires a signed and notarized build.

To update, quit WB Marker and replace the old `.app` with the newer one. Language preferences and custom presets are stored separately in:

```text
~/Library/Application Support/WB Marker/
├── settings.json
└── marker_presets.json
```

These settings survive replacement of the app. Exported results stay wherever you save them. Analysis sessions are **not automatically restored**: save results before quitting or restarting to change language.

## Run from source on macOS

### 1. Get the repository

```bash
git clone https://github.com/Tsutayaaa/wb_tool.git
cd wb_tool
```

If you already have a checkout, open Terminal in that directory instead.

### 2. Check Python and Tk

Use Python **3.10 or newer** with working Tkinter:

```bash
python3 --version
python3 -m tkinter
```

The second command should open a small Tk demonstration window; close it before continuing. If `_tkinter` is missing, install a Python distribution with Tk support, then create the virtual environment using that interpreter. The `python.org` macOS installer is one option. Tkinter is not installed with `pip install tkinter`.

### 3. Create an isolated environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Runtime dependencies are Pillow for image processing and openpyxl for Excel exports. First-time installation needs an internet connection; normal image analysis runs locally.

### 4. Launch

```bash
python -m wb_tools
```

Choose a language for a single launch:

```bash
python -m wb_tools --language en
python -m wb_tools --language zh
```

The optional `WB_MARKER_LANGUAGE=en` or `WB_MARKER_LANGUAGE=zh` environment variable overrides the saved preference; `--language` takes precedence over both. CLI overrides do not change the saved preference.

The existing entry points also work:

```bash
python main.py
python wb_marker_tool.py
```

Alternatively, double-click `run_wb_tool.command` in Finder, or run:

```bash
zsh run_wb_tool.command
```

The launcher creates `.venv` if needed, installs missing runtime dependencies, and starts the app. It needs a Python installation with Tk support and may access the network on first launch. It is a source launcher, not the standalone packaged app.

For later sessions, activate the environment again before launching:

```bash
cd /path/to/wb_tool
source .venv/bin/activate
python -m wb_tools
```

## Interface in v0.4.0

Analysis panels fit the window width without horizontal scrolling. Long product names and instructions wrap. Advanced peak detection, marker group management, custom preset/anchor assignment, and calibration diagnostics are collapsed by default; click their disclosure buttons to expand them.

The target result table shows lane, band, recommended report, and confidence. Select a row and expand **Selected band details** for marker group, pixel position, local kDa, uncertainty range, and range status. Full exported columns are unchanged.

### Named marker presets

| Product | Nominal bands (kDa, descending) | Reference colors |
| --- | --- | --- |
| PageRuler™ Plus Prestained Protein Ladder, 10 to 250 kDa (#26619 / #26620) | 250, 130, 100, 70, 55, 35, 25, 15, 10 | 70 and 25: orange/red; 10: green; others: blue |
| PageRuler™ Prestained Protein Ladder, 10 to 180 kDa (#26616 / #26617) | 180, 130, 100, 70, 55, 40, 35, 25, 15, 10 | 70: orange/red; 10: green; others, including 25: blue |

The selector uses short product names; the full product name, catalog numbers, and colored kDa preview appear below it. After applying a product preset, the peak table, profile annotations, and active marker image annotations use its reference colors. Each marker group retains its own product association. Browsing another preset does not change existing assignments.

Colors are orientation aids, not automatic band identification. These are nominal manufacturer reference values; check your ladder documentation and gel system before assignment. Existing generic and custom presets remain available.

Sources: [Thermo Fisher PageRuler Plus](https://www.thermofisher.com/order/catalog/product/26619), [Thermo Fisher PageRuler](https://www.thermofisher.com/order/catalog/product/26616).

## Analyze a Western blot

### 1. Prepare and import images

- Supported images: PNG, JPEG, TIFF, and BMP.
- Use images with dark bands on a light background: peak detection samples inverted grayscale intensity.
- Import the marker and target channels together with **1 Import images**. A single image containing both is also usable.
- Multiple channels must already be aligned in pixel coordinates and should have the same dimensions. The app does not register or align channels automatically.
- Select the active image with **Channel**. Use **+**, **−**, **Fit to window**, scrollbars, or Command + mouse wheel to navigate.

### 2. Draw and calibrate marker lanes

1. Select the marker image channel and **Draw marker lane**.
2. Drag along the center of the marker lane, from the loading-well/top direction toward the bottom. Each new line creates a separate marker group.
3. Review the intensity profile and detected peaks. Expand **Advanced peak detection** to adjust smoothing radius, prominence, minimum peak spacing, and lane half-width, then click **Detect peaks again** if needed. The sampling width is `2 × half-width + 1` pixels.
4. Click the profile to add or remove peaks manually.
5. Double-click a peak's **kDa** cell to enter its known marker value. Leave unidentified peaks blank. Assign at least two known peaks, with kDa decreasing along migration.
6. Alternatively, choose a built-in preset, or expand **Custom preset & anchor assignment** and enter a descending list such as `170, 130, 100, 70, 55, 40, 35, 25, 15, 10`. Use **Apply full preset**, or select a known peak and use **Assign downward from selected peak**. Verify the mapping when marker bands are missing or faint.
7. Under **Custom preset & anchor assignment**, use **Save new preset** to retain a custom ladder for later sessions.
8. Repeat for additional marker lanes if useful. Each group has its own peak assignments and calibration. Expand **Manage marker groups** to select or remove a group.
9. Click **Fit markers & continue →**. Review calibration messages; invalid groups may be excluded. Return to the marker tab and expand **Calibration diagnostics** for the detailed fit.

> **Screenshot placeholder — marker calibration**
>
> Add `docs/images/marker-calibration.png`, then uncomment the image below.
<!-- ![Marker peaks, kDa assignments, and calibration](docs/images/marker-calibration.png) -->

### 3. Analyze target lanes

1. Switch to the target image channel.
2. Select **Add target lane** and drag from the top to the bottom along its center, in the same migration direction as the marker lanes.
3. Select the lane in the list to review its detected bands and intensity profile.
4. Expand **Advanced peak detection** to adjust target detection parameters and use **Re-detect selected lane**, or click the profile to add/remove band peaks manually.
5. Repeat for the remaining target lanes.
6. Review the compact band table, then select a row and expand **Selected band details** to inspect its selected marker group, local estimate, uncertainty range, and range status.

Coordinates must be comparable across channels and lanes. Slanted lanes, distorted gels, or misaligned channels can compromise calibration even when the fit statistics look good.

> **Screenshot placeholder — target analysis and results**
>
> Add `docs/images/target-results.png`, then uncomment the image below.
<!-- ![Target lane analysis and band results](docs/images/target-results.png) -->

### 4. Export results

Click **Save results**, choose CSV, XLSX, or JSON, and select an output location. XLSX puts **Lane summary** first and detailed **Band results** in a separate sheet.

The export also writes companion reports to the same directory:

| Output | Contents |
| --- | --- |
| Your selected CSV/XLSX/JSON file | Band estimates, selected marker group, uncertainty, confidence, warnings, and reporting text |
| `lane_summary.csv` | One row per lane, with its band estimates |
| `calibration_report.csv` | Marker back-calculation and local leave-one-out errors |
| `fit_summary.csv` | Global fit and local cross-validation summary |
| `calibration_diagnostic*.svg` | Marker points, global fit, local interpolation, and residuals |
| `calibration_error_vs_mw*.svg` | Calibration errors versus marker molecular weight |

**Use a separate output folder for each analysis.** Companion reports use fixed filenames and may overwrite earlier reports in the same folder. Exports are analysis outputs, not reloadable project/session files. Column names and scientific status codes remain English in either interface language for consistent downstream processing.

## How molecular weight is estimated

The recommended estimate uses the two neighboring markers and interpolates linearly in `log10(MW)`:

```text
log10(MW) = log10(MW1)
          + (position - position1) / (position2 - position1)
          × (log10(MW2) - log10(MW1))
```

A global linear fit is also calculated as a diagnostic, not as the default reported estimate. With multiple marker groups, selection prioritizes coverage of the target band, then estimated uncertainty and other quality criteria. Local leave-one-out calibration errors and peak widths contribute to the uncertainty estimate.

Results are **apparent molecular weights**, not exact protein masses. The uncertainty range is a heuristic diagnostic, not a validated statistical confidence interval. Out-of-range bands are flagged as extrapolations with very low confidence and preferentially reported as above/below the calibrated range. A high R² cannot remove systematic effects from gel composition, transfer, glycosylation, aggregation, or unusual migration.

## Use the calculation API

The numerical core does not require a graphical display:

```python
from wb_tools.core import prepare_markers, linear_fit, estimate_band

positions = [25, 94, 124, 141, 215, 307, 362, 422, 478]
weights_kda = [600, 400, 250, 230, 130, 110, 75, 45, 20]
markers = prepare_markers(positions, weights_kda)
fit = linear_fit(positions, weights_kda)
result = estimate_band(markers, fit, position_px=94.3, peak_width_px=8)

print(result.apparent_mw_local_kda)  # approximately 398 kDa
print(result.reported_mw_text)
print(result.confidence)
```

Run from the repository root with its virtual environment active, or install the package into that environment with `python -m pip install -e .`. Use consistent pixel coordinates for markers and target positions.

## Build a standalone macOS app

```bash
python3 -m venv .venv-build
.venv-build/bin/python -m pip install -r requirements-build-lock.txt
.venv-build/bin/python scripts/build_app.py
open "dist/WB Marker.app"
```

The lock file records the dependency versions from the tested build; `requirements-build.txt` provides version ranges if you intentionally want to update them. The build bundles Python, Tk, Pillow, and openpyxl. It must be run on macOS with a working Tk-enabled Python; architecture follows that Python interpreter.

Output: **`dist/WB Marker.app`**. See [the build guide](docs/packaging.md) for packaging a ZIP, verification, and distribution limitations. Build artifacts are ignored by Git.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `_tkinter` is missing or no window opens from source | Run `python3 -m tkinter`; recreate the environment with a Tk-enabled interpreter. |
| `PIL` or `openpyxl` is missing | Activate `.venv` and run `python -m pip install -r requirements.txt`. |
| The app cannot open on this Mac | Confirm the app architecture matches the Mac. Current packaged builds target Apple Silicon. |
| Few peaks, too many peaks, or incorrect bands | Check image polarity, lane placement, half-width, smoothing, prominence, and peak spacing; edit peaks manually. |
| Calibration fails | Assign at least two finite, positive kDa values at distinct positions, descending along migration. |
| Results differ between channels | Confirm identical pixel alignment and dimensions; the app does not align images. |
| Language has not changed | Save results, quit, and reopen. Check CLI/environment overrides if running from source. |
| Custom presets cannot be saved | Check write access to `~/Library/Application Support/WB Marker/`. |
| Older exports disappear | Save each analysis in a different directory to avoid overwriting companion reports. |

## Development and repository layout

```text
wb_tools/
  core.py             # Numerical calibration, peak detection, and result organization
  imaging.py          # Lane intensity sampling
  gui.py              # Tk interface and export workflow
  i18n.py             # English/Chinese messages and language preferences
  presets.py          # Named ladder products, nominal values, and reference colors
scripts/build_app.py  # macOS standalone build
tests/                # Regression and language tests
docs/                 # Guides and screenshot locations
main.py               # Compatible source entry point
wb_marker_tool.py     # Legacy import/launch compatibility
```

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
# Optional: real-window layout and interaction tests on a desktop session
WB_MARKER_GUI_TESTS=1 python -m pytest -q
```

The current checkout contains the WB Marker implementation. The SprB sequence builder mentioned in an earlier README is **not present**; its historical instructions are retained in [docs/sprb-legacy.md](docs/sprb-legacy.md) for reference, not as working commands.
