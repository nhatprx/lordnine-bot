"""
Build script for packaging LordNine Bot as a standalone .exe
Usage: python build_exe.py
"""
import subprocess
import sys
import os

# Get CustomTkinter path for data inclusion
import customtkinter
ctk_path = os.path.dirname(customtkinter.__file__)

# All project Python modules (entry point is main.py)
hidden_imports = [
    "constants",
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
print("Building LordNine Bot v3.15.6")
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
    print()
    print("To distribute:")
    print("  1. Copy the entire 'dist/LordNineBot/' folder")
    print("  2. User runs 'LordNineBot.exe' inside it")
    print("  3. trackers/ folder will be created automatically on first run")
else:
    print(f"\nBUILD FAILED with code {result.returncode}")
    sys.exit(1)
