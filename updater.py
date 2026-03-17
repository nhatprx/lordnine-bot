"""
Updater — Auto-update system for LordNine Bot.

Checks for new versions via Vercel API, downloads update zip from
GitHub Releases, and applies updates by swapping app directory contents.

User data (config.json, trackers/, combos.json, loops.json, multi.json,
bot_state.db, license.key) is preserved across updates.

Usage:
    from updater import check_for_update, show_update_dialog

    # In background thread:
    update_info = check_for_update()
    if update_info:
        # On GUI thread:
        show_update_dialog(root, update_info)
"""

import os
import sys
import json
import time
import hashlib
import shutil
import zipfile
import threading
import urllib.request
import urllib.error
import ssl
import logging
import subprocess

logger = logging.getLogger(__name__)

# ── SSL Context (PyInstaller .exe doesn't bundle CA certs) ─────
def _make_ssl_ctx():
    """Create SSL context that works in frozen (PyInstaller) builds."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        # Test it works
        return ctx
    except Exception:
        pass
    # Last resort: unverified (still encrypted, just no cert check)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

_SSL_CTX = _make_ssl_ctx()

# ── Configuration ──────────────────────────────────────────────

# Vercel API endpoint for checking updates
UPDATE_API_URL = "https://lordnine-update.vercel.app/api/check-update"

# Files/folders to PRESERVE during update (user data)
USER_DATA = {
    "config.json",
    "combos.json",
    "combos.json.bak",
    "loops.json",
    "loops.json.bak",
    "multi.json",
    "multi.json.bak",
    "bot_state.db",
    "bot_state.db-shm",
    "bot_state.db-wal",
    "license.key",
    "trackers",         # entire directory
    "_internal",        # PyInstaller internal (will be replaced)
}

# Directories to ALWAYS preserve
USER_DIRS = {"trackers"}

# Temp directory for downloads
UPDATE_TEMP_DIR = "_update_temp"


# ── Version Comparison ─────────────────────────────────────────

def _parse_version(version_str):
    """Parse version string to tuple. '3.15.6' → (3, 15, 6)"""
    v = version_str.strip().lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def is_newer(latest, current):
    """Check if latest version is newer than current."""
    return _parse_version(latest) > _parse_version(current)


# ── Check for Update ───────────────────────────────────────────

def check_for_update(current_version=None):
    """
    Check Vercel API for available updates.

    Args:
        current_version: Current version string (e.g. "3.15.6").
                         If None, imports from version.py.

    Returns:
        dict with {latest, download_url, changelog, size, sha256} or None
    """
    if current_version is None:
        from version import APP_VERSION
        current_version = APP_VERSION

    try:
        url = f"{UPDATE_API_URL}?v={current_version}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LordNineBot-Updater/1.0"}
        )
        resp = urllib.request.urlopen(req, timeout=10, context=_SSL_CTX)
        data = json.loads(resp.read().decode("utf-8"))

        if not data.get("update_available"):
            return None

        latest = data.get("latest_version", "")
        if not is_newer(latest, current_version):
            return None

        return {
            "latest": latest,
            "download_url": data.get("download_url", ""),
            "changelog": data.get("changelog", ""),
            "size": data.get("size", 0),
            "sha256": data.get("sha256", ""),
        }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            # API not deployed yet — silently skip
            logger.debug("[Updater] Update endpoint not found (not deployed yet)")
        else:
            logger.debug(f"[Updater] Update server returned HTTP {e.code}")
        return None
    except urllib.error.URLError as e:
        logger.debug(f"[Updater] Cannot reach update server: {e}")
        return None
    except Exception as e:
        logger.debug(f"[Updater] Update check failed: {e}")
        return None


# ── Download Update ────────────────────────────────────────────

def download_update(url, dest_path, progress_cb=None, sha256_expected=None):
    """
    Download update zip file with progress callback.

    Args:
        url: Download URL
        dest_path: Local path to save zip
        progress_cb: callable(downloaded_bytes, total_bytes)
        sha256_expected: Expected SHA-256 hash for verification

    Returns:
        (success: bool, error_msg: str or None)
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LordNineBot-Updater/1.0"}
        )
        resp = urllib.request.urlopen(req, timeout=60, context=_SSL_CTX)
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        hasher = hashlib.sha256()

        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(65536)  # 64KB chunks
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)

        # Verify SHA-256 hash
        if sha256_expected:
            actual_hash = hasher.hexdigest()
            if actual_hash != sha256_expected:
                os.remove(dest_path)
                return False, f"Hash mismatch: expected {sha256_expected[:16]}..., got {actual_hash[:16]}..."

        # Verify it's a valid zip
        if not zipfile.is_zipfile(dest_path):
            os.remove(dest_path)
            return False, "Downloaded file is not a valid ZIP"

        return True, None

    except Exception as e:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False, str(e)


# ── Apply Update ───────────────────────────────────────────────

def _get_app_dir():
    """Get the application directory (where the exe lives)."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


def apply_update(zip_path):
    """
    Apply update by extracting zip and creating a swap script.

    The swap script will:
    1. Wait for app to exit
    2. Backup current app
    3. Copy new files (preserving user data)
    4. Clean up temp files
    5. Restart the app

    Args:
        zip_path: Path to downloaded update zip

    Returns:
        (success: bool, error_msg: str or None)
    """
    app_dir = _get_app_dir()
    temp_dir = os.path.join(app_dir, UPDATE_TEMP_DIR)
    extract_dir = os.path.join(temp_dir, "extracted")
    backup_dir = os.path.join(temp_dir, "backup")

    try:
        # Extract zip
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # Find the actual update content directory
        # The zip might contain a top-level folder (e.g., "LordNineBot/")
        contents = os.listdir(extract_dir)
        if len(contents) == 1 and os.path.isdir(os.path.join(extract_dir, contents[0])):
            update_source = os.path.join(extract_dir, contents[0])
        else:
            update_source = extract_dir

        # Create the update PowerShell script
        script_path = os.path.join(app_dir, "_update.ps1")
        exe_name = "LordNineBot.exe"
        exe_path = os.path.join(app_dir, exe_name)
        pid = os.getpid()

        # User data files to preserve (relative paths)
        preserve_files = [
            "config.json",
            "combos.json", "combos.json.bak",
            "loops.json", "loops.json.bak",
            "multi.json", "multi.json.bak",
            "bot_state.db", "bot_state.db-shm", "bot_state.db-wal",
            "license.key",
        ]
        preserve_dirs = ["trackers"]

        # Build PowerShell script
        ps_script = f'''# LordNine Bot Auto-Update Script
# Generated at: {time.strftime("%Y-%m-%d %H:%M:%S")}

$ErrorActionPreference = "SilentlyContinue"

$appDir = "{app_dir.replace(chr(92), chr(92)+chr(92))}"
$updateSource = "{update_source.replace(chr(92), chr(92)+chr(92))}"
$backupDir = "{backup_dir.replace(chr(92), chr(92)+chr(92))}"
$tempDir = "{temp_dir.replace(chr(92), chr(92)+chr(92))}"
$exeName = "{exe_name}"
$pid = {pid}

# Step 1: Wait for app to exit
Write-Host "Waiting for LordNine Bot to exit..."
$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {{
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if (-not $proc) {{ break }}
    Start-Sleep -Milliseconds 500
    $waited++
}}

# Force kill if still running
$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
if ($proc) {{
    Write-Host "Force stopping app..."
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}}

# Step 2: Backup current app files (excluding user data and temp)
Write-Host "Creating backup..."
New-Item -Path $backupDir -ItemType Directory -Force | Out-Null

$preserveFiles = @({", ".join(f'"{f}"' for f in preserve_files)})
$preserveDirs = @({", ".join(f'"{d}"' for d in preserve_dirs)})
$skipItems = $preserveFiles + $preserveDirs + @("{UPDATE_TEMP_DIR}", "_update.ps1")

Get-ChildItem -Path $appDir -Force | Where-Object {{
    $skipItems -notcontains $_.Name
}} | ForEach-Object {{
    try {{
        if ($_.PSIsContainer) {{
            Copy-Item -Path $_.FullName -Destination (Join-Path $backupDir $_.Name) -Recurse -Force
        }} else {{
            Copy-Item -Path $_.FullName -Destination (Join-Path $backupDir $_.Name) -Force
        }}
    }} catch {{ }}
}}

# Step 3: Remove old app files (preserving user data)
Write-Host "Removing old files..."
Get-ChildItem -Path $appDir -Force | Where-Object {{
    $skipItems -notcontains $_.Name
}} | ForEach-Object {{
    try {{
        if ($_.PSIsContainer) {{
            Remove-Item -Path $_.FullName -Recurse -Force
        }} else {{
            Remove-Item -Path $_.FullName -Force
        }}
    }} catch {{
        Write-Host "Warning: Could not remove $($_.Name): $_"
    }}
}}

# Step 4: Copy new files
Write-Host "Installing update..."
Get-ChildItem -Path $updateSource -Force | ForEach-Object {{
    $destPath = Join-Path $appDir $_.Name
    # Skip user data files that already exist
    if (($preserveFiles -contains $_.Name) -and (Test-Path $destPath)) {{
        Write-Host "  Preserved: $($_.Name)"
        return
    }}
    if (($preserveDirs -contains $_.Name) -and (Test-Path $destPath)) {{
        Write-Host "  Preserved: $($_.Name)/"
        return
    }}
    try {{
        if ($_.PSIsContainer) {{
            Copy-Item -Path $_.FullName -Destination $destPath -Recurse -Force
        }} else {{
            Copy-Item -Path $_.FullName -Destination $destPath -Force
        }}
    }} catch {{
        Write-Host "Warning: Could not copy $($_.Name): $_"
    }}
}}

# Step 5: Cleanup temp
Write-Host "Cleaning up..."
Start-Sleep -Seconds 1
Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

# Step 6: Restart app
Write-Host "Starting LordNine Bot..."
$exePath = Join-Path $appDir $exeName
if (Test-Path $exePath) {{
    Start-Process -FilePath $exePath
    Write-Host "Update complete!"
}} else {{
    Write-Host "ERROR: $exeName not found after update!"
    Write-Host "Restoring backup..."
    # Restore from backup
    Get-ChildItem -Path $backupDir -Force | ForEach-Object {{
        $destPath = Join-Path $appDir $_.Name
        Copy-Item -Path $_.FullName -Destination $destPath -Recurse -Force
    }}
    Start-Process -FilePath $exePath
}}

# Self-cleanup
Start-Sleep -Seconds 3
Remove-Item -Path (Join-Path $appDir "_update.ps1") -Force -ErrorAction SilentlyContinue
'''

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(ps_script)

        return True, None

    except Exception as e:
        return False, str(e)


def launch_update_and_exit():
    """Launch the update script and exit the application."""
    app_dir = _get_app_dir()
    script_path = os.path.join(app_dir, "_update.ps1")

    if not os.path.exists(script_path):
        return False, "Update script not found"

    try:
        # Launch PowerShell script in a new window (persists after app exit)
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Minimized", "-File", script_path],
            cwd=app_dir,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )
        return True, None
    except Exception as e:
        return False, str(e)


# ── UI Dialog ──────────────────────────────────────────────────

def show_update_dialog(root, update_info, log_fn=None):
    """
    Show a premium update dialog.

    Args:
        root: CTk root window
        update_info: dict from check_for_update()
        log_fn: callable(str) for logging

    Returns:
        None (handles update flow internally)
    """
    import customtkinter as ctk
    from constants import COLOR, FONT

    if log_fn is None:
        log_fn = print

    latest = update_info.get("latest", "?")
    changelog = update_info.get("changelog", "Bug fixes and improvements.")
    size_mb = update_info.get("size", 0) / (1024 * 1024) if update_info.get("size") else 0
    download_url = update_info.get("download_url", "")
    sha256 = update_info.get("sha256", "")

    from version import APP_VERSION

    dialog = ctk.CTkToplevel(root)
    dialog.title("Update Available")
    dialog.configure(fg_color=COLOR["bg"])
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    dialog.grab_set()

    w, h = 420, 380
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    # Set icon
    try:
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        if os.path.exists(ico):
            dialog.after(200, lambda: dialog.iconbitmap(ico))
    except Exception:
        pass

    # ── Main card ──
    card = ctk.CTkFrame(dialog, fg_color=COLOR["surface"], corner_radius=12)
    card.pack(fill="both", expand=True, padx=12, pady=12)

    # Icon + Title
    ctk.CTkLabel(card, text="\uE895",
                 font=ctk.CTkFont(family="Segoe MDL2 Assets", size=32),
                 text_color=COLOR["primary"]).pack(pady=(20, 6))
    ctk.CTkLabel(card, text="Update Available",
                 font=ctk.CTkFont(family=FONT["family"], size=16, weight="bold"),
                 text_color=COLOR["text"]).pack(pady=(0, 4))

    # Version info
    ver_frame = ctk.CTkFrame(card, fg_color=COLOR["bg"], corner_radius=8)
    ver_frame.pack(padx=24, pady=(4, 8), fill="x")

    ver_inner = ctk.CTkFrame(ver_frame, fg_color="transparent")
    ver_inner.pack(pady=8, padx=16, fill="x")

    ctk.CTkLabel(ver_inner, text=f"v{APP_VERSION}",
                 font=ctk.CTkFont(family="Consolas", size=13),
                 text_color=COLOR["text_muted"]).pack(side="left")
    ctk.CTkLabel(ver_inner, text="  →  ",
                 font=ctk.CTkFont(size=13),
                 text_color=COLOR["text_dim"]).pack(side="left")
    ctk.CTkLabel(ver_inner, text=f"v{latest}",
                 font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                 text_color=COLOR["success"]).pack(side="left")

    if size_mb > 0:
        ctk.CTkLabel(ver_inner, text=f"{size_mb:.1f} MB",
                     font=ctk.CTkFont(family="Consolas", size=11),
                     text_color=COLOR["text_muted"]).pack(side="right")

    # Changelog
    ctk.CTkLabel(card, text="What's new:",
                 font=ctk.CTkFont(family=FONT["family"], size=11, weight="bold"),
                 text_color=COLOR["text_dim"], anchor="w").pack(padx=24, fill="x")

    log_box = ctk.CTkTextbox(card, height=80,
                              fg_color=COLOR["bg"], corner_radius=8,
                              font=ctk.CTkFont(family=FONT["family"], size=11),
                              text_color=COLOR["text_dim"],
                              border_width=1, border_color=COLOR["border_subtle"],
                              wrap="word")
    log_box.pack(padx=24, pady=(4, 12), fill="x")
    log_box.insert("1.0", changelog)
    log_box.configure(state="disabled")

    # Progress bar (hidden initially)
    progress_frame = ctk.CTkFrame(card, fg_color="transparent", height=30)
    progress_label = ctk.CTkLabel(progress_frame, text="",
                                   font=ctk.CTkFont(family="Consolas", size=10),
                                   text_color=COLOR["text_dim"])
    progress_bar = ctk.CTkProgressBar(progress_frame, height=6,
                                       fg_color=COLOR["bg"],
                                       progress_color=COLOR["primary"],
                                       corner_radius=3)

    # Buttons
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(fill="x", padx=24, pady=(0, 16))

    state = {"updating": False}

    def on_update():
        if state["updating"]:
            return
        state["updating"] = True

        # Hide buttons, show progress
        btn_frame.pack_forget()
        progress_frame.pack(fill="x", padx=24, pady=(0, 12))
        progress_label.pack(fill="x")
        progress_bar.pack(fill="x", pady=(4, 0))
        progress_bar.set(0)
        progress_label.configure(text="Downloading update...")

        def _download_thread():
            app_dir = _get_app_dir()
            temp_dir = os.path.join(app_dir, UPDATE_TEMP_DIR)
            zip_path = os.path.join(temp_dir, "update.zip")

            def _progress(downloaded, total):
                if total > 0:
                    pct = downloaded / total
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    try:
                        dialog.after(0, lambda: progress_bar.set(pct))
                        dialog.after(0, lambda: progress_label.configure(
                            text=f"Downloading... {mb_done:.1f}/{mb_total:.1f} MB ({pct*100:.0f}%)"
                        ))
                    except Exception:
                        pass

            # Download
            log_fn(f"[Updater] Downloading v{latest}...")
            success, error = download_update(
                download_url, zip_path,
                progress_cb=_progress,
                sha256_expected=sha256 or None
            )

            if not success:
                log_fn(f"[Updater] Download failed: {error}")
                try:
                    dialog.after(0, lambda: progress_label.configure(
                        text=f"Download failed: {error}",
                    ))
                except Exception:
                    pass
                state["updating"] = False
                return

            # Apply update
            try:
                dialog.after(0, lambda: progress_label.configure(text="Preparing update..."))
                dialog.after(0, lambda: progress_bar.set(1.0))
            except Exception:
                pass

            log_fn("[Updater] Extracting and preparing update...")
            success, error = apply_update(zip_path)

            if not success:
                log_fn(f"[Updater] Apply failed: {error}")
                try:
                    dialog.after(0, lambda: progress_label.configure(
                        text=f"Update failed: {error}"
                    ))
                except Exception:
                    pass
                state["updating"] = False
                return

            # Launch update script and exit
            log_fn("[Updater] Launching update installer...")
            try:
                dialog.after(0, lambda: progress_label.configure(
                    text="Restarting application..."
                ))
            except Exception:
                pass

            time.sleep(1)
            success, error = launch_update_and_exit()
            if success:
                log_fn("[Updater] Update script launched. Exiting...")
                try:
                    dialog.after(500, lambda: root.destroy())
                except Exception:
                    pass
            else:
                log_fn(f"[Updater] Failed to launch update script: {error}")
                try:
                    dialog.after(0, lambda: progress_label.configure(
                        text=f"Failed to start update: {error}"
                    ))
                except Exception:
                    pass
                state["updating"] = False

        threading.Thread(target=_download_thread, daemon=True).start()

    def on_skip():
        dialog.destroy()

    ctk.CTkButton(
        btn_frame, text="⬇  Update Now", command=on_update,
        height=36, corner_radius=8,
        fg_color=COLOR["primary"], hover_color=COLOR["primary_h"],
        font=ctk.CTkFont(family=FONT["family"], size=13, weight="bold"),
        text_color="#FFFFFF"
    ).pack(fill="x", pady=(0, 6))

    ctk.CTkButton(
        btn_frame, text="Skip", command=on_skip,
        height=30, corner_radius=8,
        fg_color="transparent", hover_color=COLOR["surface2"],
        text_color=COLOR["text_muted"],
        font=ctk.CTkFont(family=FONT["family"], size=11)
    ).pack(fill="x")

    dialog.protocol("WM_DELETE_WINDOW", on_skip)
