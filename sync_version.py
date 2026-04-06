"""
Sync Version — Single source of truth for version numbers.

Reads APP_VERSION from version.py and updates installer.iss to match.
Run before building installer.

Usage:
    python sync_version.py
"""
import re
import os


def sync():
    """Sync version from version.py → installer.iss.
    
    Returns True on success, False on error.
    """
    base = os.path.dirname(os.path.abspath(__file__))
    
    # Read version from version.py
    ver_path = os.path.join(base, "version.py")
    try:
        with open(ver_path, "r", encoding="utf-8") as f:
            m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', f.read())
    except FileNotFoundError:
        print("[sync_version] ERROR: version.py not found")
        return False
    
    if not m:
        print("[sync_version] ERROR: Can't parse APP_VERSION from version.py")
        return False
    ver = m.group(1)
    
    # Update installer.iss
    iss_path = os.path.join(base, "installer.iss")
    if not os.path.exists(iss_path):
        print(f"[sync_version] WARNING: installer.iss not found, skipping")
        return True
    
    with open(iss_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    content = re.sub(r'AppVersion=[\d.]+', f'AppVersion={ver}', content)
    content = re.sub(
        r'OutputBaseFilename=LordNineBotSetup_v[\d.]+',
        f'OutputBaseFilename=LordNineBotSetup_v{ver}',
        content
    )
    
    if content != original:
        with open(iss_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[sync_version] ✓ Synced v{ver} → installer.iss")
    else:
        print(f"[sync_version] ✓ installer.iss already at v{ver}")
    
    return True


if __name__ == "__main__":
    sync()
