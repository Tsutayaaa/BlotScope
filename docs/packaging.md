# Build and distribute BlotScope for macOS

Only macOS app builds are currently supported. The locally verified build uses Apple Silicon (arm64) and Python 3.12. This is not a universal binary; Intel support has not been verified.

## Prerequisites

From the repository root, use Python 3.10+ with working Tk:

```bash
python3 -m tkinter
python3 -m venv .venv-build
.venv-build/bin/python -m pip install -r requirements-build-lock.txt
```

Close the Tk demo window before building. The lock file records tested dependency versions, not the operating system or Python runtime. To intentionally update dependencies, use `requirements-build.txt` instead and repeat validation.

## Build

```bash
.venv-build/bin/python scripts/build_app.py
open "dist/BlotScope.app"
```

PyInstaller bundles the interpreter, Tk runtime, Pillow, and openpyxl into `dist/BlotScope.app`. The build uses the architecture of the Python interpreter that runs it. `build/` and `dist/` are generated and ignored by Git. Rebuilding replaces the previous same-name build output.

The English/Chinese message catalog is a Python module and is included automatically. Custom presets and language preferences are stored under `~/Library/Application Support/BlotScope/`, not inside the app bundle.

## Verify before sharing

1. Launch the app from Finder and from a location outside the source checkout.
2. Import representative marker and target images, assign kDa, fit, and analyze a lane.
3. Export CSV, XLSX, and JSON to separate folders and inspect the companion reports.
4. Save a custom preset, quit, reopen, and confirm it is retained.
5. Change language in **Language / 语言**, restart, and verify the interface.
6. Test the copy on the actual target macOS version and hardware. Build success alone does not prove compatibility.

## Package a ZIP

```bash
ditto -c -k --sequesterRsrc --keepParent   "dist/BlotScope.app" "dist/BlotScope-v1.0.1-macOS-arm64.zip"
```

Use the `arm64` filename only for an arm64 build. Share the complete app bundle; never share only `Contents/MacOS/BlotScope`. Recipients can extract the ZIP, drag the app to Applications, and launch without Python.

## Signing and distribution status

The current build has no Developer ID signature or Apple notarization. PyInstaller may apply local/ad-hoc signing, which is not equivalent to a notarized public release. Public distribution requires the maintainer’s Apple signing credentials, signing, notarization, and verification on a clean target machine. No release upload is performed by the build script.

Reference: [PyInstaller usage documentation](https://pyinstaller.org/en/stable/usage.html).
