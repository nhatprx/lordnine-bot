"""
Build script for packaging LordNine Bot as a standalone .exe
Usage: python build_exe.py

After build, creates dist/LordNineBot_v{version}_update.zip for auto-update.
"""
import subprocess
import sys
import os
import zipfile
import hashlib

from version import APP_VERSION

# Get CustomTkinter path for data inclusion
import customtkinter
ctk_path = os.path.dirname(customtkinter.__file__)

# All project Python modules (entry point is main.py)
hidden_imports = [
    "constants",
    "version",
    "updater",
    "vision",
    "chrome_manager",
    "state_db",
    "connection_pool",
    "screencapture",
    "bot_action",
    "cdp_client",
    "license_manager",
    "node_features",
    "flowchart_ui",
    "tab_nodes",
    "tab_macros",
    "tab_loops",
    "tab_accounts",
    "macro_runner",
    "graph_engine",
    "websocket",
    "websocket._abnf",
    "websocket._core",
    "websocket._exceptions",
    "websocket._http",
    "websocket._logging",
    "websocket._socket",
    "websocket._ssl_compat",
    "websocket._url",
    "cv2",
    "numpy",
    "PIL",
    "mss",
    "pyautogui",
    "pynput",
    "pynput.keyboard",
    "pynput.keyboard._win32",
    "pynput.mouse",
    "pynput.mouse._win32",
]

# Build hidden imports args
hi_args = []
for mod in hidden_imports:
    hi_args.extend(["--hidden-import", mod])

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onedir",             # onedir is faster to build and start than onefile
    "--windowed",           # No console window
    "--name", "LordNineBot",
    "--icon", "logo.ico",
    # Include CustomTkinter data files (themes, assets)
    "--add-data", f"{ctk_path};customtkinter/",
    # Include app assets
    "--add-data", "logo.ico;.",
    "--add-data", "logo.png;.",
    # Exclude unnecessary modules to reduce size
    "--exclude-module", "matplotlib",
    "--exclude-module", "scipy",
    "--exclude-module", "pandas",
    "--exclude-module", "pytest",
    "--exclude-module", "playwright",
    "--exclude-module", "unittest",
    *hi_args,
    "main.py"
]

print("=" * 60)
print(f"Building LordNine Bot v{APP_VERSION}")
print("=" * 60)
print(f"Command: {' '.join(cmd[:10])}...")
print()

result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

if result.returncode == 0:
    print()
    print("=" * 60)
    print("BUILD SUCCESSFUL!")
    print("Output: dist/LordNineBot/LordNineBot.exe")
    print("=" * 60)

    # ── Create update.zip for auto-update ──
    dist_dir = os.path.join("dist", "LordNineBot")
    zip_name = f"LordNineBot_v{APP_VERSION}_update.zip"
    zip_path = os.path.join("dist", zip_name)

    print()
    print(f"Creating update package: dist/{zip_name}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root_dir, dirs, files in os.walk(dist_dir):
            for f in files:
                full_path = os.path.join(root_dir, f)
                arc_name = os.path.relpath(full_path, os.path.dirname(dist_dir))
                zf.write(full_path, arc_name)

    # Calculate SHA-256 hash
    sha256 = hashlib.sha256()
    with open(zip_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    sha256_hash = sha256.hexdigest()
    zip_size = os.path.getsize(zip_path)

    print(f"  Size:   {zip_size / (1024*1024):.1f} MB")
    print(f"  SHA256: {sha256_hash}")
    print()
    print("=" * 60)
    print("RELEASE CHECKLIST:")
    print("=" * 60)
    print(f"  1. Upload dist/{zip_name} to GitHub Releases")
    print(f"  2. Set Vercel env vars:")
    print(f"     LATEST_VERSION = {APP_VERSION}")
    print(f"     DOWNLOAD_URL   = https://github.com/<user>/<repo>/releases/download/v{APP_VERSION}/{zip_name}")
    print(f"     UPDATE_SIZE    = {zip_size}")
    print(f"     UPDATE_SHA256  = {sha256_hash}")
    print(f"     CHANGELOG      = <your changelog here>")
    print()
else:
    print(f"\nBUILD FAILED with code {result.returncode}")
    sys.exit(1)

