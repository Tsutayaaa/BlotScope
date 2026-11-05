"""Build a standalone native application on the target operating system."""
from pathlib import Path
import os
import plistlib
import re
import subprocess
import sys

if sys.platform != "darwin":
    raise SystemExit("Packaged app builds currently support macOS only.")

root = Path(__file__).resolve().parents[1]

# Generate a multi-resolution macOS icon from the supplied artwork.
from PIL import Image, ImageOps
icon_source = root / "docs" / "WB logo.png"
icon_path = root / "build" / "WB Marker.icns"
icon_path.parent.mkdir(parents=True, exist_ok=True)
with Image.open(icon_source) as source:
    icon = ImageOps.pad(source.convert("RGBA"), (1024, 1024),
                        method=Image.Resampling.LANCZOS, color=(0, 0, 0, 0))
    icon.save(icon_path, format="ICNS")
command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--windowed", "--onedir", "--name", "WB Marker",
           "--icon", str(icon_path),
           "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
           "--specpath", str(root / "build"), "--paths", str(root)]
if sys.platform == "darwin":
    command += ["--osx-bundle-identifier", "com.tsutayaaa.wbmarker"]
command.append(str(root / "main.py"))
env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(root / "build" / "pyinstaller-cache"))
subprocess.run(command, cwd=root, env=env, check=True)

# Keep Finder's app version aligned with the package version.
version = re.search(r'__version__ = "([^"]+)"',
                    (root / "wb_tools" / "__init__.py").read_text()).group(1)
app = root / "dist" / "WB Marker.app"
plist_path = app / "Contents" / "Info.plist"
with plist_path.open("rb") as handle:
    info = plistlib.load(handle)
info["CFBundleShortVersionString"] = version
info["CFBundleVersion"] = version
with plist_path.open("wb") as handle:
    plistlib.dump(info, handle)
# Updating Info.plist requires refreshing the local ad-hoc signature.
subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
