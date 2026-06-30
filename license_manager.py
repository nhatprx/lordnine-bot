"""
License Manager — Secure remote license validation via API proxy.

Uses CustomTkinter widgets matching the app's premium dark theme.
Must be called AFTER ctk.CTk() root is created.

Security features:
  - No Gist URL in client code (API proxy hides it)
  - HWID binding (each license key is bound to one machine)
  - All validation happens server-side
"""

import os
import json
import hashlib
import platform
import urllib.request
import customtkinter as ctk
from datetime import datetime
from uuid import getnode

from constants import COLOR, FONT, PAD, RADIUS

# === CONFIGURATION ===
# API endpoint — deploy api/validate-license.py to Vercel, then set this URL
API_URL = "https://lordnine-api.vercel.app/api/validate-license"
LICENSE_FILE = "license.key"
CONTACT_EMAIL = "nhatprx@gmail.com"
APP_NAME = "LordNine Bot"


def _get_hwid():
    """
    Generate a unique hardware ID (HWID) for this machine.
    Combines MAC address + hostname + OS info into a SHA-256 hash.
    Consistent across runs on the same machine.
    """
    try:
        mac = format(getnode(), '012x')       # MAC address
        hostname = platform.node()             # Computer name
        os_info = platform.platform()          # OS version string
        # Combine multiple identifiers for uniqueness
        raw = f"{mac}|{hostname}|{os_info}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    except Exception:
        # Fallback: use MAC address only
        mac = format(getnode(), '012x')
        return hashlib.sha256(mac.encode("utf-8")).hexdigest()[:32]


def _load_local_key():
    if os.path.exists(LICENSE_FILE):
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return None


def _save_local_key(key):
    try:
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(key.strip())
    except Exception:
        pass


def _validate_remote(key, hwid):
    """
    Validate license key via API proxy.
    Sends key + HWID to server; server checks against Gist data.
    Client never sees the Gist URL or other license keys.
    """
    try:
        payload = json.dumps({"key": key, "hwid": hwid}).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "LordNineBot/1.0"
            },
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("valid", False), result.get("message", "Unknown error.")
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return False, err_body.get("message", f"Server error ({e.code}).")
        except Exception:
            return False, f"Server error ({e.code})."
    except urllib.error.URLError:
        return False, "Cannot connect to license server.\nCheck your internet and try again."
    except Exception as e:
        return False, f"Connection error: {str(e)}"


def _apply_icon(dialog):
    try:
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        if os.path.exists(ico):
            dialog.after(200, lambda: dialog.iconbitmap(ico))
    except Exception:
        pass


def _show_key_prompt(root):
    """Premium CTk license key prompt matching app design system."""
    result = {"key": None}

    dialog = ctk.CTkToplevel(root)
    dialog.title(APP_NAME)
    dialog.configure(fg_color=COLOR["bg"])
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    dialog.grab_set()
    _apply_icon(dialog)

    w, h = 380, 240
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    # Main card
    card = ctk.CTkFrame(dialog, fg_color=COLOR["surface"], corner_radius=12)
    card.pack(fill="both", expand=True, padx=12, pady=12)

    # Icon + Title
    ctk.CTkLabel(card, text="\uE8D7",
                 font=ctk.CTkFont(family="Segoe MDL2 Assets", size=28),
                 text_color=COLOR["primary"]).pack(pady=(20, 6))
    ctk.CTkLabel(card, text="License Activation",
                 font=ctk.CTkFont(family=FONT["family"], size=15, weight="bold"),
                 text_color=COLOR["text"]).pack(pady=(0, 2))
    ctk.CTkLabel(card, text="Enter your license key to continue",
                 font=ctk.CTkFont(family=FONT["family"], size=11),
                 text_color=COLOR["text_dim"]).pack(pady=(0, 12))

    # Key entry
    key_entry = ctk.CTkEntry(card, width=280, height=36,
                              font=ctk.CTkFont(family=FONT["mono"], size=12),
                              fg_color=COLOR["bg"],
                              border_color=COLOR["border"],
                              text_color=COLOR["text"],
                              placeholder_text="XXXX-XXXX-XXXX-XXXX",
                              placeholder_text_color=COLOR["text_muted"],
                              corner_radius=8)
    key_entry.pack(pady=(0, 14))

    key_entry.focus_set()

    key_entry.focus_set()

    def _submit():
        val = key_entry.get().strip()
        if val:
            result["key"] = val
            dialog.destroy()

    # Buttons row
    btn_frame = ctk.CTkFrame(card, fg_color="transparent")
    btn_frame.pack(fill="x", padx=40)
    ctk.CTkButton(btn_frame, text="Activate", command=_submit,
                  height=34, corner_radius=8,
                  fg_color=COLOR["primary"], hover_color=COLOR["primary_h"],
                  font=ctk.CTkFont(family=FONT["family"], size=12, weight="bold")).pack(fill="x", pady=(0, 6))
    ctk.CTkButton(btn_frame, text="Exit", command=dialog.destroy,
                  height=28, corner_radius=8,
                  fg_color="transparent", hover_color=COLOR["surface2"],
                  text_color=COLOR["text_muted"],
                  font=ctk.CTkFont(family=FONT["family"], size=11)).pack(fill="x")

    dialog.bind("<Return>", lambda e: _submit())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.wait_window()

    return result["key"]


def _show_blocked_message(message, root):
    """Premium CTk blocked dialog matching app design system."""
    dialog = ctk.CTkToplevel(root)
    dialog.title(APP_NAME)
    dialog.configure(fg_color=COLOR["bg"])
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    dialog.grab_set()
    _apply_icon(dialog)

    w, h = 380, 220
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    # Main card
    card = ctk.CTkFrame(dialog, fg_color=COLOR["surface"], corner_radius=12)
    card.pack(fill="both", expand=True, padx=12, pady=12)

    # Icon + Title
    ctk.CTkLabel(card, text="\uE711",
                 font=ctk.CTkFont(family="Segoe MDL2 Assets", size=28),
                 text_color=COLOR["danger"]).pack(pady=(20, 6))
    ctk.CTkLabel(card, text="Access Denied",
                 font=ctk.CTkFont(family=FONT["family"], size=15, weight="bold"),
                 text_color=COLOR["danger"]).pack(pady=(0, 4))
    ctk.CTkLabel(card, text=message,
                 font=ctk.CTkFont(family=FONT["family"], size=11),
                 text_color=COLOR["text_dim"]).pack(pady=(0, 4))

    # Contact row
    contact_frame = ctk.CTkFrame(card, fg_color=COLOR["bg"], corner_radius=8,
                                  height=28)
    contact_frame.pack(pady=(4, 12))
    ctk.CTkLabel(contact_frame, text=f"  Contact: {CONTACT_EMAIL}  ",
                 font=ctk.CTkFont(family=FONT["mono"], size=11),
                 text_color=COLOR["accent"]).pack(padx=8, pady=4)


    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.wait_window()


def check_license(root):
    """
    Call from BotApp.__init__ AFTER super().__init__().
    Returns True if license valid, False if blocked.

    Flow:
      1. Prompt user for license key
      2. Generate HWID from machine hardware
      3. POST (key, hwid) to API proxy
      4. API fetches Gist server-side, validates, checks HWID binding
      5. Return result to client
    """
    # Always prompt for key on startup
    key = _show_key_prompt(root)
    if not key:
        return False

    # Generate machine fingerprint
    hwid = _get_hwid()

    # Validate via API proxy (server-side, Gist URL never exposed)
    valid, message = _validate_remote(key, hwid)

    if valid:
        _save_local_key(key)
        return True
    else:
        if os.path.exists(LICENSE_FILE):
            try:
                os.remove(LICENSE_FILE)
            except Exception:
                pass
        _show_blocked_message(message, root)
        return False
