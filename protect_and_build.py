"""
Protected Build Script — PyArmor obfuscation + PyInstaller packaging.

Usage: python protect_and_build.py

Steps:
  1. Obfuscate critical Python files with PyArmor
  2. Build with PyInstaller using obfuscated files
  3. Cleanup temporary files

Prerequisites:
  pip install pyarmor pyinstaller
"""
import subprocess
import sys
import os
import shutil
import tempfile

# Files to obfuscate (most sensitive modules)
OBFUSCATE_FILES = [
    "license_manager.py",
    "constants.py",
    "bot_action.py",
]

# All project files (for PyInstaller)
ALL_PY_FILES = [
    "main.py",
    "license_manager.py",
    "constants.py",
    "bot_action.py",
    "vision.py",
    "chrome_manager.py",
    "state_db.py",
    "connection_pool.py",
    "screencapture.py",
    "cdp_client.py",
    "node_features.py",
    "flowchart_ui.py",
    "tab_nodes.py",
    "tab_macros.py",
    "tab_loops.py",
    "tab_accounts.py",
]

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def step_obfuscate():
    """Step 1: Obfuscate critical files with PyArmor."""
    print("=" * 60)
    print("Step 1: Obfuscating critical files with PyArmor...")
    print("=" * 60)

    obf_dir = os.path.join(PROJECT_DIR, "_obfuscated")
    if os.path.exists(obf_dir):
        shutil.rmtree(obf_dir)

    # Obfuscate each critical file
    for fname in OBFUSCATE_FILES:
        fpath = os.path.join(PROJECT_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  [SKIP] {fname} not found")
            continue

        print(f"  [OBF] {fname}")
        cmd = [
            "pyarmor", "gen",
            "--output", obf_dir,
            fpath
        ]
        result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [ERROR] Failed to obfuscate {fname}:")
            print(f"    {result.stderr}")
            return False

    print(f"  [OK] Obfuscated files in: {obf_dir}")
    return True


def step_build():
    """Step 2: Build with PyInstaller using obfuscated files."""
    print()
    print("=" * 60)
    print("Step 2: Building with PyInstaller...")
    print("=" * 60)

    # Create a temporary build directory with mixed files:
    # - Obfuscated versions of critical files
    # - Original versions of non-critical files
    build_src = os.path.join(PROJECT_DIR, "_build_src")
    obf_dir = os.path.join(PROJECT_DIR, "_obfuscated")

    if os.path.exists(build_src):
        shutil.rmtree(build_src)
    os.makedirs(build_src)

    obfuscated_names = set()

    # Copy obfuscated files first
    if os.path.exists(obf_dir):
        for fname in os.listdir(obf_dir):
            src = os.path.join(obf_dir, fname)
            dst = os.path.join(build_src, fname)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                obfuscated_names.add(fname)
                print(f"  [OBF] {fname}")
            elif os.path.isdir(src):
                shutil.copytree(src, dst)
                print(f"  [OBF] {fname}/")

    # Copy remaining Python files (non-obfuscated)
    for fname in ALL_PY_FILES:
        if fname not in obfuscated_names:
            src = os.path.join(PROJECT_DIR, fname)
            dst = os.path.join(build_src, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"  [CPY] {fname}")

    # Copy assets
    for asset in ["logo.ico", "logo.png"]:
        src = os.path.join(PROJECT_DIR, asset)
        dst = os.path.join(build_src, asset)
        if os.path.exists(src):
            shutil.copy2(src, dst)

    # Get CustomTkinter path
    import customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)

    # Hidden imports
    hidden_imports = [
        "constants", "vision", "chrome_manager", "state_db",
        "connection_pool", "screencapture", "bot_action",
        "cdp_client", "license_manager", "node_features",
        "flowchart_ui", "tab_nodes", "tab_macros", "tab_loops",
        "tab_accounts",
        "websocket", "websocket._abnf", "websocket._core",
        "websocket._exceptions", "websocket._http",
        "websocket._logging", "websocket._socket",
        "websocket._ssl_compat", "websocket._url",
        "cv2", "numpy", "PIL", "mss",
        "pyautogui", "pynput", "pynput.keyboard",
        "pynput.keyboard._win32", "pynput.mouse", "pynput.mouse._win32",
    ]

    hi_args = []
    for mod in hidden_imports:
        hi_args.extend(["--hidden-import", mod])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "LordNineBot",
        "--icon", os.path.join(build_src, "logo.ico"),
        "--add-data", f"{ctk_path};customtkinter/",
        "--add-data", f"{os.path.join(build_src, 'logo.ico')};.",
        "--add-data", f"{os.path.join(build_src, 'logo.png')};.",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "pytest",
        "--exclude-module", "playwright",
        "--exclude-module", "unittest",
        *hi_args,
        os.path.join(build_src, "main.py")
    ]

    print(f"\n  Running PyInstaller...")
    result = subprocess.run(cmd, cwd=PROJECT_DIR)

    return result.returncode == 0


def step_cleanup():
    """Step 3: Clean up temporary directories."""
    print()
    print("=" * 60)
    print("Step 3: Cleaning up...")
    print("=" * 60)

    for d in ["_obfuscated", "_build_src"]:
        path = os.path.join(PROJECT_DIR, d)
        if os.path.exists(path):
            shutil.rmtree(path)
            print(f"  [DEL] {d}/")

    print("  [OK] Cleanup complete")


def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     LordNine Bot — Protected Build (PyArmor + PyInst)  ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  Obfuscating critical files, then packaging as .exe    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # Step 1: Obfuscate
    if not step_obfuscate():
        print("\n[FATAL] Obfuscation failed. Aborting build.")
        print("  Make sure PyArmor is installed: pip install pyarmor")
        sys.exit(1)

    # Step 2: Build
    if not step_build():
        print("\n[FATAL] PyInstaller build failed.")
        step_cleanup()
        sys.exit(1)

    # Step 3: Cleanup
    step_cleanup()

    print()
    print("=" * 60)
    print("BUILD SUCCESSFUL! (Protected)")
    print("Output: dist/LordNineBot/LordNineBot.exe")
    print("=" * 60)
    print()
    print("Critical files are obfuscated:")
    for f in OBFUSCATE_FILES:
        print(f"  ✓ {f}")
    print()
    print("To distribute:")
    print("  1. Copy the entire 'dist/LordNineBot/' folder")
    print("  2. User runs 'LordNineBot.exe' inside it")
    print()


if __name__ == "__main__":
    main()
