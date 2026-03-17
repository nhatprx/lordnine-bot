# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\pnhat\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\customtkinter', 'customtkinter/'), ('logo.ico', '.'), ('logo.png', '.')],
    hiddenimports=['constants', 'version', 'updater', 'vision', 'chrome_manager', 'state_db', 'connection_pool', 'screencapture', 'bot_action', 'cdp_client', 'license_manager', 'node_features', 'flowchart_ui', 'tab_nodes', 'tab_macros', 'tab_loops', 'tab_accounts', 'macro_runner', 'graph_engine', 'websocket', 'websocket._abnf', 'websocket._core', 'websocket._exceptions', 'websocket._http', 'websocket._logging', 'websocket._socket', 'websocket._ssl_compat', 'websocket._url', 'cv2', 'numpy', 'PIL', 'mss', 'pyautogui', 'pynput', 'pynput.keyboard', 'pynput.keyboard._win32', 'pynput.mouse', 'pynput.mouse._win32'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'pytest', 'playwright', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LordNineBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LordNineBot',
)
