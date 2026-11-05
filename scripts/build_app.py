"""Build a standalone native application on the target operating system."""
from pathlib import Path
import os
import subprocess
import sys

if sys.platform != "darwin":
    raise SystemExit("Packaged app builds currently support macOS only.")

root = Path(__file__).resolve().parents[1]
command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--windowed", "--onedir", "--name", "WB Marker",
           "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
           "--specpath", str(root / "build"), "--paths", str(root)]
if sys.platform == "darwin":
    command += ["--osx-bundle-identifier", "com.tsutayaaa.wbmarker"]
command.append(str(root / "main.py"))
env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(root / "build" / "pyinstaller-cache"))
subprocess.run(command, cwd=root, env=env, check=True)
