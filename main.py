"""
LordNine Bot Control — Main Application Shell.

Premium UI with sidebar navigation.
  - tab_nodes.py    → NodesMixin   (Template tracking, test node, snipping)
  - tab_macros.py   → MacrosMixin  (Macro creation, editing, execution)
  - tab_loops.py    → LoopsMixin   (Flowchart automation engine)
  - tab_accounts.py → AccountsMixin(Multi-account coordinator)
  - constants.py    → COLOR palette, get_page_by_visual_index
"""

import customtkinter as ctk
import time
import os
import json
import queue
import shutil
import threading
import multiprocessing

from vision import Vision
from chrome_manager import ChromeManager
from state_db import StateDB
from constants import COLOR, FONT, PAD, RADIUS

# Tab Mixins
from tab_nodes import NodesMixin
from tab_macros import MacrosMixin
from tab_loops import LoopsMixin
from tab_accounts import AccountsMixin


# ════════════════════════════════════════════════════════════════
# Sidebar Button — Individual nav item
# ════════════════════════════════════════════════════════════════
class SidebarButton(ctk.CTkFrame):
    """Compact icon-only sidebar button with hover tooltip."""
    def __init__(self, master, icon, label, command=None, **kwargs):
        super().__init__(master, fg_color="transparent", height=36, cursor="hand2", **kwargs)
        self.pack_propagate(False)
        self.command = command
        self.is_active = False
        self._label_text = label
        self._tooltip = None
        self._tooltip_delay_id = None
        self._tooltip_hide_id = None

        # Active indicator bar (left edge, absolute positioned)
        self.indicator = ctk.CTkFrame(self, width=3, height=18, fg_color="transparent", corner_radius=2)
        self.indicator.place(x=0, rely=0.5, anchor="w")

        # Icon (centered) — uses Segoe MDL2 Assets font
        self.icon_label = ctk.CTkLabel(
            self, text=icon, font=ctk.CTkFont(family="Segoe MDL2 Assets", size=18),
            text_color=COLOR["text_dim"]
        )
        self.icon_label.pack(expand=True)

        # Bind click and hover events
        for widget in [self, self.icon_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_click(self, event=None):
        if self.command:
            self.command()

    def _on_enter(self, event=None):
        if not self.is_active:
            self.configure(fg_color=COLOR["sidebar_h"])
            self.icon_label.configure(text_color=COLOR["text_dim"])
        # Show tooltip after short delay
        self._cancel_tooltip_timers()
        self._tooltip_delay_id = self.after(300, self._show_tooltip)

    def _on_leave(self, event=None):
        if not self.is_active:
            self.configure(fg_color="transparent")
            self.icon_label.configure(text_color=COLOR["text_muted"])
        self._cancel_tooltip_timers()
        self._hide_tooltip()

    def _cancel_tooltip_timers(self):
        if self._tooltip_delay_id:
            self.after_cancel(self._tooltip_delay_id)
            self._tooltip_delay_id = None
        if self._tooltip_hide_id:
            self.after_cancel(self._tooltip_hide_id)
            self._tooltip_hide_id = None

    def _show_tooltip(self):
        if self._tooltip:
            return
        x = self.winfo_rootx() + self.winfo_width() + 4
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 12
        self._tooltip = ctk.CTkToplevel(self)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.wm_geometry(f"+{x}+{y}")
        self._tooltip.configure(fg_color=COLOR["surface3"])
        self._tooltip.attributes("-topmost", True)
        ctk.CTkLabel(
            self._tooltip, text=self._label_text,
            font=ctk.CTkFont(size=11), text_color=COLOR["text"],
            fg_color=COLOR["surface3"], corner_radius=6,
            padx=10, pady=4
        ).pack()
        # Auto-hide after 1.5s
        self._tooltip_hide_id = self.after(1500, self._hide_tooltip)

    def _hide_tooltip(self):
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    def set_active(self, active):
        self.is_active = active
        if active:
            self.indicator.configure(fg_color=COLOR["primary"])
            self.icon_label.configure(text_color=COLOR["primary"])
            self.configure(fg_color=COLOR["surface"])
        else:
            self.indicator.configure(fg_color="transparent")
            self.icon_label.configure(text_color=COLOR["text_muted"])
            self.configure(fg_color="transparent")


# ════════════════════════════════════════════════════════════════
# Main Application
# ════════════════════════════════════════════════════════════════
class BotApp(NodesMixin, MacrosMixin, LoopsMixin, AccountsMixin, ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Lordbot Control")
        self.protocol("WM_DELETE_WINDOW", self._confirm_quit)
        # Set window icon + taskbar icon
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("lordbot.control.app")
        except Exception:
            pass
        try:
            import os as _os
            self._ico_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "logo.ico")
            if _os.path.exists(self._ico_path):
                self.iconbitmap(self._ico_path)
        except Exception:
            pass
        
        # --- License Check (before UI setup) ---
        from license_manager import check_license
        if not check_license(self):
            self.destroy()
            import sys
            sys.exit(1)
        
        self.geometry("1000x650")
        self.resizable(False, False)
        self.configure(fg_color=COLOR["bg"])

        self.vision = Vision()
        
        # Load saved config for debug toggle
        _saved_debug = True
        _saved_port = "9222"
        _saved_tab = "0"
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    _cfg = json.load(f)
                _saved_debug = _cfg.get("debug_visual", True)
                _saved_port = str(_cfg.get("port", 9222))
                _saved_tab = str(_cfg.get("tab", 0))
        except: pass
        self.debug_visual_var = ctk.BooleanVar(value=_saved_debug)
        self._saved_port = _saved_port
        self._saved_tab = _saved_tab

        # Load saved data
        self.combos = {}
        self.load_combos()
        self.loops = {}
        self.load_loops()
        self.multi_accounts = []
        self.load_multi()

        # Scale infrastructure
        self.chrome_mgr = ChromeManager()
        self.state_db = StateDB()
        self.account_workers = {}
        self.account_running = {}
        self.health_monitor_active = False

        # ──── Layout: pack-based for reliable fixed sidebar width ────
        # StatusBar at bottom (pack first so it's always at bottom)
        self.statusbar = ctk.CTkFrame(self, height=28, fg_color=COLOR["sidebar"], corner_radius=0)
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.pack_propagate(False)

        # ════ SIDEBAR (compact icon-only, 48px fixed) ════
        self.sidebar = ctk.CTkFrame(self, width=48, fg_color=COLOR["sidebar"], corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo from logo.png
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=40)
        logo_frame.pack(fill="x", pady=(8, 4))
        logo_frame.pack_propagate(False)

        try:
            from PIL import Image as PILImage
            base_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(base_dir, "logo.png")
            if not os.path.exists(logo_path):
                logo_path = os.path.join(base_dir, "logo.svg")
            logo_img = PILImage.open(logo_path).convert("RGBA")
            ctk_logo = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(24, 24))
            ctk.CTkLabel(logo_frame, image=ctk_logo, text="").pack(expand=True)
        except Exception:
            ctk.CTkLabel(
                logo_frame, text="LN",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=COLOR["primary"]
            ).pack(expand=True)

        # Divider
        ctk.CTkFrame(self.sidebar, height=1, fg_color=COLOR["border_subtle"]).pack(fill="x", padx=10, pady=(0, 8))

        # Navigation buttons (icon-only)
        self.nav_buttons = []
        # Navigation buttons — uses Segoe MDL2 Assets glyphs
        nav_items = [
            ("\uE74C", "Nodes",      0),   # Page/tiles
            ("\uE945", "Macros",     1),   # Lightning bolt
            ("\uE895", "Automation", 2),   # Sync/refresh
            ("\uE77B", "Accounts",   3),   # People
            ("\uE8A1", "Output",     4),   # List/document
        ]
        self._sidebar_icons = []
        for icon, label, idx in nav_items:
            btn = SidebarButton(
                self.sidebar, icon=icon, label=label,
                command=lambda i=idx: self.switch_tab(i)
            )
            btn.pack(fill="x", padx=4, pady=1)
            self.nav_buttons.append(btn)

        # Sidebar bottom spacer + utility buttons
        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(fill="both", expand=True)

        # Bottom utility group — fixed frame, never gets squeezed
        bottom_group = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom_group.pack(fill="x", side="bottom", padx=0, pady=(0, 6))

        ctk.CTkFrame(bottom_group, height=1, fg_color=COLOR["border_subtle"]).pack(fill="x", padx=10, pady=(0, 4))

        # Lock
        self._is_locked = False
        self._lock_btn = SidebarButton(
            bottom_group, icon="\uE785", label="Lock",
            command=self._toggle_lock
        )
        self._lock_btn.pack(fill="x", padx=4, pady=1)

        # Refresh
        refresh_btn = SidebarButton(
            bottom_group, icon="\uE149", label="Refresh",
            command=self._refresh_all
        )
        refresh_btn.icon_label.configure(font=ctk.CTkFont(family="Segoe MDL2 Assets", size=14))
        refresh_btn.pack(fill="x", padx=4, pady=1)

        # Quit
        quit_btn = SidebarButton(
            bottom_group, icon="\uE7E8", label="Quit",
            command=self._confirm_quit
        )
        quit_btn.pack(fill="x", padx=4, pady=1)

        # ════ CONTENT AREA (fills remaining space) ════
        self.content_area = ctk.CTkFrame(self, fg_color=COLOR["bg"], corner_radius=0)
        self.content_area.pack(side="left", fill="both", expand=True)

        # Create tab frames (hidden by default)
        self.tab_frames = []
        self.tab_setup  = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_combo  = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_loop   = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_multi  = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_output = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)

        self.tab_frames = [self.tab_setup, self.tab_combo, self.tab_loop, self.tab_multi, self.tab_output]

        # Left side: status indicators
        ctk.CTkLabel(
            self.statusbar, text="Network",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=COLOR["success"]
        ).pack(side="left", padx=(12, 2))

        self.status_label = ctk.CTkLabel(
            self.statusbar, text="—",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["text_muted"]
        )
        self.status_label.pack(side="left", padx=(0, 8))

        self.cpu_label = ctk.CTkLabel(
            self.statusbar, text="CPU —",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["text_muted"]
        )
        self.cpu_label.pack(side="left", padx=(0, 6))

        self.ram_label = ctk.CTkLabel(
            self.statusbar, text="RAM —",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["text_muted"]
        )
        self.ram_label.pack(side="left", padx=(0, 8))

        # Account stats
        self.stat_running = ctk.CTkLabel(
            self.statusbar, text="● 0 Running",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["success"]
        )
        self.stat_running.pack(side="left", padx=(0, 6))

        self.stat_idle = ctk.CTkLabel(
            self.statusbar, text="● 0 Idle",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["text_muted"]
        )
        self.stat_idle.pack(side="left", padx=(0, 6))

        self.stat_error = ctk.CTkLabel(
            self.statusbar, text="● 0 Error",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["danger"]
        )
        self.stat_error.pack(side="left", padx=(0, 6))

        # Right side: Port/Tab inputs + version
        self.status_version = ctk.CTkLabel(
            self.statusbar, text="v3.15.6",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["text_muted"]
        )
        self.status_version.pack(side="right", padx=(0, 12))

        # Tab input in footer
        self.footer_tab_input = ctk.CTkEntry(
            self.statusbar, width=32, height=20,
            fg_color=COLOR["surface"], border_width=1,
            border_color=COLOR["border_subtle"], corner_radius=4,
            font=ctk.CTkFont(family="Consolas", size=10),
            justify="center"
        )
        self.footer_tab_input.insert(0, self._saved_tab)
        self.footer_tab_input.pack(side="right", padx=(0, 8))
        self.footer_tab_label = ctk.CTkLabel(
            self.statusbar, text="Tab",
            font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"]
        )
        self.footer_tab_label.pack(side="right", padx=(0, 3))

        # Port input in footer
        self.footer_port_input = ctk.CTkEntry(
            self.statusbar, width=48, height=20,
            fg_color=COLOR["surface"], border_width=1,
            border_color=COLOR["border_subtle"], corner_radius=4,
            font=ctk.CTkFont(family="Consolas", size=10),
            justify="center"
        )
        self.footer_port_input.insert(0, self._saved_port)
        self.footer_port_input.pack(side="right", padx=(0, 8))
        self.footer_port_label = ctk.CTkLabel(
            self.statusbar, text="Port",
            font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"]
        )
        self.footer_port_label.pack(side="right", padx=(0, 3))

        # ──── Initialize tabs ────
        self._setup_output_tab()

        self.is_looping = False
        self.is_coordinating = False
        self.gui_queue = queue.Queue()

        self.setup_tracker_tab()   # NodesMixin
        self.setup_combo_tab()     # MacrosMixin
        self.setup_loop_tab()      # LoopsMixin
        self.setup_multi_tab()     # AccountsMixin

        # Show first tab
        self.current_tab = -1
        self.switch_tab(0)

        # Start processing the thread-safe GUI queue
        self.process_gui_queue()

        # Start real-time footer stats updater
        self._start_footer_stats_updater()

    # ==================== Tab Switching ====================
    def switch_tab(self, index):
        if index == self.current_tab:
            return

        # Hide all tabs
        for frame in self.tab_frames:
            frame.pack_forget()

        # Show selected tab
        self.tab_frames[index].pack(in_=self.content_area, fill="both", expand=True)

        # Update sidebar active states
        for i, btn in enumerate(self.nav_buttons):
            btn.set_active(i == index)

        self.current_tab = index

        # Hide port/tab inputs on Accounts (3) and Output (4) tabs
        footer_widgets = [self.footer_port_label, self.footer_port_input,
                          self.footer_tab_label, self.footer_tab_input]
        if index in (3, 4):
            for w in footer_widgets:
                w.pack_forget()
        else:
            # Re-pack in correct order (right to left): Tab input, Tab label, Port input, Port label
            for w in footer_widgets:
                w.pack_forget()
            self.footer_tab_input.pack(side="right", padx=(0, 8))
            self.footer_tab_label.pack(side="right", padx=(0, 3))
            self.footer_port_input.pack(side="right", padx=(0, 8))
            self.footer_port_label.pack(side="right", padx=(0, 3))

    # ==================== Refresh All ====================
    def _refresh_all(self):
        """Reload all data from disk and refresh UI components."""
        self.load_combos()
        self.load_loops()
        self.load_multi()

        # Refresh loop dropdown in Accounts tab
        if hasattr(self, '_refresh_func_combo'):
            self._refresh_func_combo()

        # Refresh accounts list
        if hasattr(self, 'refresh_multi_acc_list'):
            self.refresh_multi_acc_list()

        # Refresh tracked list in Nodes tab
        if hasattr(self, 'refresh_tracked_list'):
            self.refresh_tracked_list()

        # Refresh loop list in Loops tab
        if hasattr(self, 'refresh_loop_list'):
            self.refresh_loop_list()

        # Refresh combo list in Macros tab
        if hasattr(self, 'refresh_combo_list'):
            self.refresh_combo_list()

        # Refresh info panel in Output tab
        if hasattr(self, '_build_info_panel'):
            self._build_info_panel()

        self.log_gui("[System] All data refreshed ✓")

    def _toggle_lock(self):
        """Toggle window lock state with confirmation dialog."""
        if self._is_locked:
            self._confirm_unlock()
        else:
            self._confirm_lock()

    def _confirm_lock(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("320x140")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 320) // 2
        y = self.winfo_y() + (self.winfo_height() - 140) // 2
        dialog.geometry(f"320x140+{x}+{y}")

        ctk.CTkLabel(dialog, text="Lock Application?", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["text"]).pack(pady=(20, 4))
        ctk.CTkLabel(dialog, text="All interaction will be disabled.", font=ctk.CTkFont(size=11), text_color=COLOR["text_muted"]).pack(pady=(0, 12))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))

        def on_lock():
            dialog.destroy()
            self._apply_lock()

        ctk.CTkButton(btn_row, text="Lock", command=on_lock, fg_color=COLOR["warning"], hover_color="#B8860B", text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"), height=30, corner_radius=6).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Cancel", command=dialog.destroy, fg_color="transparent", hover_color=COLOR["surface2"], border_width=1, border_color=COLOR["border"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"), height=30, corner_radius=6).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _confirm_unlock(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("320x140")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 320) // 2
        y = self.winfo_y() + (self.winfo_height() - 140) // 2
        dialog.geometry(f"320x140+{x}+{y}")

        ctk.CTkLabel(dialog, text="Unlock Application?", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["text"]).pack(pady=(20, 4))
        ctk.CTkLabel(dialog, text="Resume normal interaction.", font=ctk.CTkFont(size=11), text_color=COLOR["text_muted"]).pack(pady=(0, 12))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))

        def on_unlock():
            dialog.destroy()
            self._apply_unlock()

        ctk.CTkButton(btn_row, text="Unlock", command=on_unlock, fg_color=COLOR["success"], hover_color="#2E7D32", text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"), height=30, corner_radius=6).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Cancel", command=dialog.destroy, fg_color="transparent", hover_color=COLOR["surface2"], border_width=1, border_color=COLOR["border"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"), height=30, corner_radius=6).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _get_all_interactive_widgets(self):
        """Collect all interactive widgets from all tab frames."""
        widgets = []
        def _collect(parent):
            for child in parent.winfo_children():
                cls = type(child).__name__
                if cls in ("CTkButton", "CTkEntry", "CTkCheckBox", "CTkComboBox",
                           "CTkSlider", "CTkSwitch", "CTkOptionMenu",
                           "CTkSegmentedButton", "CTkTextbox"):
                    widgets.append(child)
                # Recurse into containers only (CTkFrame, CTkScrollableFrame, etc.)
                # Skip recursing into leaf interactive widgets
                if cls not in ("CTkButton", "CTkEntry", "CTkCheckBox", "CTkComboBox",
                               "CTkSlider", "CTkSwitch", "CTkOptionMenu",
                               "CTkSegmentedButton", "CTkTextbox"):
                    _collect(child)
        for frame in self.tab_frames:
            _collect(frame)
        return widgets

    def _apply_lock(self):
        self._is_locked = True
        self._lock_btn.icon_label.configure(text="\uE72E")

        for w in self._get_all_interactive_widgets():
            try:
                w.configure(state="disabled")
            except Exception:
                pass
        self.log_gui("[System] Application locked")

    def _apply_unlock(self):
        self._is_locked = False
        self._lock_btn.icon_label.configure(text="\uE785")

        for w in self._get_all_interactive_widgets():
            cls = type(w).__name__
            try:
                if cls == "CTkTextbox":
                    w.configure(state="disabled")  # Keep log read-only
                elif cls == "CTkEntry":
                    w.configure(state="normal")
                else:
                    w.configure(state="normal")
            except Exception:
                pass
        self.log_gui("[System] Application unlocked")

    def _confirm_quit(self):
        """Show a styled confirmation dialog before quitting."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("320x140")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 320) // 2
        y = self.winfo_y() + (self.winfo_height() - 140) // 2
        dialog.geometry(f"320x140+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="Quit Application?",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["text"]
        ).pack(pady=(20, 4))
        ctk.CTkLabel(
            dialog, text="All running accounts will be stopped.",
            font=ctk.CTkFont(size=11), text_color=COLOR["text_muted"]
        ).pack(pady=(0, 12))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))

        ctk.CTkButton(
            btn_row, text="Quit", command=lambda: (self._save_config_settings(), self.destroy()),
            fg_color=COLOR["danger"], hover_color="#8B2020",
            text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Cancel", command=dialog.destroy,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    # ==================== Output Tab ====================
    def _setup_output_tab(self):
        self.tab_output.grid_columnconfigure(0, weight=65, uniform="out_col")
        self.tab_output.grid_columnconfigure(1, weight=35, uniform="out_col")
        self.tab_output.grid_rowconfigure(0, weight=1)

        # ═══ LEFT: System Logs ═══
        log_card = ctk.CTkFrame(self.tab_output, fg_color=COLOR["surface"], corner_radius=12, border_width=1, border_color=COLOR["border_subtle"])
        log_card.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        # Header Area
        header_frame = ctk.CTkFrame(log_card, fg_color="transparent", height=40)
        header_frame.pack(fill="x", padx=PAD["lg"], pady=(PAD["md"], 0))
        header_frame.pack_propagate(False)

        title_lbl = ctk.CTkLabel(
            header_frame, text="System Output Logs",
            font=ctk.CTkFont(family=FONT["family"], size=13, weight="bold"),
            text_color="#FFFFFF"
        )
        title_lbl.pack(side="left", pady=10)

        def clear_log():
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.configure(state="disabled")

        def export_log():
            import tkinter.filedialog as fd
            filepath = fd.asksaveasfilename(
                title="Save Log As",
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                initialfile=f"system_log_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            )
            if filepath:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(self.log_textbox.get("1.0", "end"))

        # Buttons
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right", pady=5)

        ctk.CTkButton(
            btn_frame, text="Export", width=70, height=28,
            font=ctk.CTkFont(family=FONT["family"], size=11, weight="bold"),
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"], text_color=COLOR["text_dim"],
            command=export_log, corner_radius=6
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Clear", width=70, height=28,
            font=ctk.CTkFont(family=FONT["family"], size=11, weight="bold"),
            fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], text_color="#FFFFFF",
            command=clear_log, corner_radius=6
        ).pack(side="left")

        # Divider
        divider = ctk.CTkFrame(log_card, height=1, fg_color=COLOR["border"])
        divider.pack(fill="x", padx=PAD["lg"], pady=PAD["sm"])

        # Textbox container
        tb_container = ctk.CTkFrame(log_card, fg_color=COLOR["bg"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
        tb_container.pack(fill="both", expand=True, padx=PAD["lg"], pady=(0, PAD["lg"]))

        self.log_textbox = ctk.CTkTextbox(
            tb_container, state="disabled",
            fg_color="transparent",
            text_color=COLOR["text"],
            font=ctk.CTkFont(family=FONT["family"], size=12),
            corner_radius=0, border_width=0, wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Configure text tags for different log levels
        self.log_textbox.tag_config("time", foreground="#636e7b")
        self.log_textbox.tag_config("default", foreground="#C8CCD0")
        self.log_textbox.tag_config("success", foreground="#4ADE80")
        self.log_textbox.tag_config("warning", foreground="#FACC15")
        self.log_textbox.tag_config("error", foreground="#F87171")
        self.log_textbox.tag_config("system", foreground="#60A5FA")
        self.log_textbox.tag_config("test", foreground="#22D3EE")
        self.log_textbox.tag_config("macro", foreground="#C084FC")
        self.log_textbox.tag_config("flowchart", foreground="#FB923C")
        self.log_textbox.tag_config("loop_engine", foreground="#2DD4BF")
        self.log_textbox.tag_config("alert", foreground="#F87171")
        self.log_textbox.tag_config("matched", foreground="#4ADE80")
        self.log_textbox.tag_config("skip", foreground="#A1A1AA")
        self.log_textbox.tag_config("info", foreground="#93C5FD")
        self.log_textbox.tag_config("separator", foreground="#525866")
        self.log_textbox.tag_config("account", foreground="#A78BFA")

        # ═══ RIGHT: Software Info ═══
        info_card = ctk.CTkFrame(self.tab_output, fg_color=COLOR["surface"], corner_radius=12, border_width=1, border_color=COLOR["border_subtle"])
        info_card.grid(row=0, column=1, sticky="nsew", padx=(0, PAD["lg"]), pady=PAD["lg"])

        # Info header
        info_header = ctk.CTkFrame(info_card, fg_color="transparent", height=40)
        info_header.pack(fill="x", padx=PAD["lg"], pady=(PAD["md"], 0))
        info_header.pack_propagate(False)
        ctk.CTkLabel(
            info_header, text="Application Info",
            font=ctk.CTkFont(family=FONT["family"], size=13, weight="bold"),
            text_color="#FFFFFF"
        ).pack(side="left", pady=10)

        ctk.CTkFrame(info_card, height=1, fg_color=COLOR["border"]).pack(fill="x", padx=PAD["lg"], pady=PAD["sm"])

        # Scrollable info content
        info_scroll = ctk.CTkScrollableFrame(info_card, fg_color="transparent", scrollbar_button_color=COLOR["border"], scrollbar_button_hover_color=COLOR["text_muted"])
        info_scroll.pack(fill="both", expand=True, padx=PAD["md"], pady=(0, PAD["lg"]))

        self._info_container = info_scroll
        self._build_info_panel()

    def _build_info_panel(self):
        """Build or rebuild the software info panel content."""
        import sys
        import platform

        container = self._info_container
        for w in container.winfo_children():
            w.destroy()

        lbl_font = ctk.CTkFont(size=10, weight="bold")
        val_font = ctk.CTkFont(family="Consolas", size=10)
        dim_color = COLOR["text_muted"]
        val_color = COLOR["text_dim"]

        def _section(title):
            ctk.CTkLabel(container, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["primary"], anchor="w").pack(fill="x", pady=(12, 4))
            ctk.CTkFrame(container, height=1, fg_color=COLOR["border_subtle"]).pack(fill="x", pady=(0, 6))

        def _row(label, value, color=val_color):
            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=label, font=lbl_font, text_color=dim_color, width=100, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=str(value), font=val_font, text_color=color, anchor="w").pack(side="left", fill="x", expand=True)

        # ── Version & Environment ──
        _section("Environment")
        _row("Version", "v3.15.6")
        _row("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        _row("Platform", platform.system() + " " + platform.release())
        _row("Architecture", platform.machine())

        try:
            from screeninfo import get_monitors
            mon = get_monitors()[0]
            _row("Display", f"{mon.width}×{mon.height}")
        except Exception:
            try:
                import ctypes as _ct
                w = _ct.windll.user32.GetSystemMetrics(0)
                h = _ct.windll.user32.GetSystemMetrics(1)
                _row("Display", f"{w}×{h}")
            except Exception:
                pass

        # ── Data Counts ──
        _section("Loaded Data")
        tracker_count = len(self.trackers) if hasattr(self, 'trackers') else 0
        combo_count = len(self.combos) if hasattr(self, 'combos') else 0
        loop_count = len(self.loops) if hasattr(self, 'loops') else 0
        acc_count = len(self.multi_accounts) if hasattr(self, 'multi_accounts') else 0
        _row("Nodes", tracker_count)
        _row("Macros", combo_count)
        _row("Loops", loop_count)
        _row("Accounts", acc_count)

        # ── Chrome ──
        _section("Chrome")
        if hasattr(self, 'chrome_manager'):
            active = self.chrome_manager.get_active_ports()
            _row("Active Ports", len(active))
            if active:
                _row("Ports", ", ".join(str(p) for p in sorted(active)))
        else:
            _row("Status", "Not initialized")

        # ── File Paths ──
        _section("Paths")
        base = os.path.dirname(os.path.abspath(__file__))
        _row("App Dir", base)
        _row("Trackers", os.path.join(base, "trackers"))
        _row("Database", os.path.join(base, "bot_state.db"))
        _row("Config", os.path.join(base, "config.json"))

        # Refresh button
        ctk.CTkButton(
            container, text="↻ Refresh Info", command=self._build_info_panel,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"),
            height=28, corner_radius=6
        ).pack(fill="x", pady=(16, 4))

    # ==================== Thread-Safe GUI Queue ====================
    def process_gui_queue(self):
        try:
            while True:
                msg_type, payload = self.gui_queue.get_nowait()

                if msg_type == "log":
                    self._internal_log_gui(payload)
                elif msg_type == "dash_status":
                    acc_name, status, color = payload
                    self._internal_update_dash_status(acc_name, status, color)
                elif msg_type == "conn_status":
                    self._render_connection_status(payload)
                elif msg_type == "test_notif":
                    text, color, bg = payload
                    self._show_test_notification(text, color, bg)
                elif msg_type == "run":
                    payload()  # Execute callable

                self.gui_queue.task_done()
        except queue.Empty:
            pass

        self.after(100, self.process_gui_queue)

    # ==================== Logging ====================
    def log_gui(self, text):
        # Cap queue at 500 items to prevent OOM if GUI freezes
        if self.gui_queue.qsize() > 500:
            try: self.gui_queue.get_nowait()
            except: pass
        self.gui_queue.put(("log", text))

    def _internal_log_gui(self, text):
        self.log_textbox.configure(state="normal")
        lines = int(self.log_textbox.index('end').split('.')[0]) - 1
        if lines > 80:
            self.log_textbox.delete("1.0", "40.0")
        current_time = time.strftime("%H:%M:%S")
        
        # Determine tag — priority-based pattern matching
        tag = "default"
        text_lower = text.lower()

        # Separators (===, ---, ***)
        stripped = text.strip().replace(" ", "")
        if stripped and len(stripped) >= 6 and stripped[0] in "=-*" and stripped.count(stripped[0]) >= len(stripped) * 0.5:
            tag = "separator"
        # Specific prefixes (highest priority)
        elif "[test" in text_lower:
            tag = "test"
        elif "[macro]" in text_lower or "[test macro]" in text_lower:
            tag = "macro"
        elif "[flowchart]" in text_lower:
            tag = "flowchart"
        elif "[loop engine]" in text_lower:
            tag = "loop_engine"
        elif "[system]" in text_lower:
            tag = "system"
        elif "[alert]" in text_lower:
            tag = "alert"
        # Account worker logs (e.g. [VIP-33])
        elif text.startswith("[") and "]" in text[:20]:
            bracket_content = text[1:text.index("]")]
            if any(c.isdigit() for c in bracket_content) and not bracket_content.startswith("0"):
                tag = "account"
        # Keyword fallbacks
        if tag == "default":
            if "error" in text_lower or "fail" in text_lower or "exception" in text_lower:
                tag = "error"
            elif "matched" in text_lower or "found" in text_lower and "not" not in text_lower:
                tag = "matched"
            elif "success" in text_lower or "complet" in text_lower or "done" in text_lower or "acquir" in text_lower or "restored" in text_lower or "✓" in text:
                tag = "success"
            elif "warning" in text_lower or "timeout" in text_lower:
                tag = "warning"
            elif "skip" in text_lower or "cancel" in text_lower or "abort" in text_lower:
                tag = "skip"

        # Override: error keywords always win
        if tag not in ("error", "separator"):
            if "error" in text_lower or "fail" in text_lower or "exception" in text_lower:
                tag = "error"

        self.log_textbox.insert("end", f"[{current_time}] ", "time")
        self.log_textbox.insert("end", f"{text}\n", tag)
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    # ==================== Status Bar ====================
    def update_status(self, text):
        """Update status bar text."""
        self.status_label.configure(text=text)

    def _start_footer_stats_updater(self):
        """Background thread: collect CPU, RAM, network bandwidth, account stats."""
        import ctypes as _ct
        import subprocess as _sp

        # ── Windows kernel32 setup ──
        _kernel32 = None
        _filetime = None
        _memstatus = None
        try:
            _kernel32 = _ct.windll.kernel32

            class _FILETIME(_ct.Structure):
                _fields_ = [("dwLowDateTime", _ct.c_ulong), ("dwHighDateTime", _ct.c_ulong)]
            _filetime = _FILETIME

            class _MEMORYSTATUSEX(_ct.Structure):
                _fields_ = [
                    ("dwLength", _ct.c_ulong),
                    ("dwMemoryLoad", _ct.c_ulong),
                    ("ullTotalPhys", _ct.c_ulonglong),
                    ("ullAvailPhys", _ct.c_ulonglong),
                    ("ullTotalPageFile", _ct.c_ulonglong),
                    ("ullAvailPageFile", _ct.c_ulonglong),
                    ("ullTotalVirtual", _ct.c_ulonglong),
                    ("ullAvailVirtual", _ct.c_ulonglong),
                    ("ullAvailExtendedVirtual", _ct.c_ulonglong),
                ]
            _memstatus = _MEMORYSTATUSEX
        except Exception:
            pass

        # Previous samples
        _prev_cpu = {"idle": 0, "kernel": 0, "user": 0}
        _prev_net = {"recv": 0, "sent": 0, "time": time.time()}

        def _get_cpu_pct():
            if not _kernel32 or not _filetime:
                return None
            try:
                idle, kernel, user = _filetime(), _filetime(), _filetime()
                _kernel32.GetSystemTimes(_ct.byref(idle), _ct.byref(kernel), _ct.byref(user))
                idle_t = (idle.dwHighDateTime << 32) | idle.dwLowDateTime
                kern_t = (kernel.dwHighDateTime << 32) | kernel.dwLowDateTime
                user_t = (user.dwHighDateTime << 32) | user.dwLowDateTime
                d_idle = idle_t - _prev_cpu["idle"]
                d_kern = kern_t - _prev_cpu["kernel"]
                d_user = user_t - _prev_cpu["user"]
                _prev_cpu["idle"] = idle_t
                _prev_cpu["kernel"] = kern_t
                _prev_cpu["user"] = user_t
                total = d_kern + d_user
                if total == 0:
                    return 0.0
                return max(0.0, min(100.0, ((total - d_idle) / total) * 100))
            except Exception:
                return None

        def _get_ram():
            """Return (usage_percent, used_gb, total_gb) or None."""
            if not _kernel32 or not _memstatus:
                return None
            try:
                mem = _memstatus()
                mem.dwLength = _ct.sizeof(_memstatus)
                _kernel32.GlobalMemoryStatusEx(_ct.byref(mem))
                pct = mem.dwMemoryLoad
                used = (mem.ullTotalPhys - mem.ullAvailPhys) / (1024 ** 3)
                total = mem.ullTotalPhys / (1024 ** 3)
                return (pct, used, total)
            except Exception:
                return None

        def _get_net_bandwidth():
            """Return (recv_kbps, sent_kbps) or None using netstat -e."""
            try:
                out = _sp.check_output("netstat -e", shell=True, text=True,
                                       timeout=3, stderr=_sp.DEVNULL)
                for line in out.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("Bytes") or stripped.startswith("bytes"):
                        parts = stripped.split()
                        recv_bytes = int(parts[1])
                        sent_bytes = int(parts[2])
                        now = time.time()
                        dt = now - _prev_net["time"]
                        if dt < 0.5 or _prev_net["recv"] == 0:
                            _prev_net["recv"] = recv_bytes
                            _prev_net["sent"] = sent_bytes
                            _prev_net["time"] = now
                            return (0.0, 0.0)
                        recv_rate = (recv_bytes - _prev_net["recv"]) / dt / 1024  # KB/s
                        sent_rate = (sent_bytes - _prev_net["sent"]) / dt / 1024
                        _prev_net["recv"] = recv_bytes
                        _prev_net["sent"] = sent_bytes
                        _prev_net["time"] = now
                        return (max(0, recv_rate), max(0, sent_rate))
            except Exception:
                pass
            return None

        # Take initial CPU sample
        _get_cpu_pct()

        def _fmt_rate(kb):
            """Format KB/s to human-readable."""
            if kb >= 1024:
                return f"{kb/1024:.1f}M"
            return f"{kb:.0f}K"

        def _collect_and_push():
            while True:
                try:
                    cpu_pct = _get_cpu_pct()
                    ram = _get_ram()
                    net = _get_net_bandwidth()

                    running = sum(1 for v in self.account_running.values() if v)
                    total_acc = len(self.multi_accounts)
                    idle = total_acc - running
                    error_count = 0
                    try:
                        for acc in self.multi_accounts:
                            state = self.state_db.get_account_state(acc["name"])
                            if state and state.get("status") == "error":
                                error_count += 1
                    except Exception:
                        pass

                    def _update_ui(_cpu=cpu_pct, _ram=ram, _net=net,
                                   _run=running, _idle=idle, _err=error_count):
                        # Network bandwidth
                        if _net is not None:
                            recv_k, sent_k = _net
                            net_text = f"↓{_fmt_rate(recv_k)} ↑{_fmt_rate(sent_k)}"
                            net_color = COLOR["success"] if (recv_k + sent_k) > 0.1 else COLOR["text_muted"]
                            self.status_label.configure(text=net_text, text_color=net_color)
                        else:
                            self.status_label.configure(text="—", text_color=COLOR["danger"])

                        # CPU
                        if _cpu is not None:
                            pct = int(_cpu)
                            color = COLOR["success"] if pct < 60 else (COLOR["warning"] if pct < 85 else COLOR["danger"])
                            self.cpu_label.configure(text=f"CPU {pct}%", text_color=color)

                        # RAM
                        if _ram is not None:
                            pct, used, total = _ram
                            color = COLOR["success"] if pct < 60 else (COLOR["warning"] if pct < 85 else COLOR["danger"])
                            self.ram_label.configure(text=f"RAM {pct}%", text_color=color)

                        # Accounts
                        self.stat_running.configure(text=f"● {_run} Running")
                        self.stat_idle.configure(text=f"● {_idle} Idle")
                        self.stat_error.configure(text=f"● {_err} Error")

                    self.gui_queue.put(("run", _update_ui))
                except Exception:
                    pass
                time.sleep(3)

        t = threading.Thread(target=_collect_and_push, daemon=True)
        t.start()

    # ==================== Data Persistence ====================
    def load_combos(self):
        if os.path.exists("combos.json"):
            try:
                with open("combos.json", "r", encoding="utf-8") as f:
                    self.combos = json.load(f)
            except Exception as e:
                print("Error loading combos:", e)

    def save_combos(self):
        try:
            if os.path.exists("combos.json"):
                shutil.copy("combos.json", "combos.json.bak")
            with open("combos.json", "w", encoding="utf-8") as f:
                json.dump(self.combos, f, indent=4)
        except Exception as e:
            print("Error saving combos:", e)

    def load_loops(self):
        if os.path.exists("loops.json"):
            try:
                with open("loops.json", "r", encoding="utf-8") as f:
                    self.loops = json.load(f)
            except Exception as e:
                print("Error loading loops:", e)

    def save_loops(self):
        try:
            if os.path.exists("loops.json"):
                shutil.copy("loops.json", "loops.json.bak")
            with open("loops.json", "w", encoding="utf-8") as f:
                json.dump(self.loops, f, indent=4)
        except Exception as e:
            print("Error saving loops:", e)

    def load_multi(self):
        if os.path.exists("multi.json"):
            try:
                with open("multi.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.multi_accounts = data.get("accounts", [])
            except Exception as e:
                print("Error loading multi:", e)

    def save_multi(self):
        try:
            if os.path.exists("multi.json"):
                shutil.copy("multi.json", "multi.json.bak")
            with open("multi.json", "w", encoding="utf-8") as f:
                json.dump({"accounts": self.multi_accounts}, f, indent=4)
        except Exception as e:
            print("Error saving multi:", e)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = BotApp()
    try:
        app.mainloop()
    finally:
        app.vision.shutdown_pool()

