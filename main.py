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
        # Set window icon
        try:
            import os as _os
            _ico = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "logo.ico")
            if _os.path.exists(_ico):
                self.iconbitmap(_ico)
        except Exception:
            pass
        self.geometry("1100x750")
        self.minsize(900, 600)
        self.configure(fg_color=COLOR["bg"])

        self.vision = Vision()
        self.debug_visual_var = ctk.BooleanVar(value=True)

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

        # Sidebar bottom spacer
        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(fill="both", expand=True)

        # Quit button at bottom of sidebar
        quit_btn = SidebarButton(
            self.sidebar, icon="\uE7E8", label="Quit",
            command=self.destroy
        )
        quit_btn.pack(fill="x", padx=4, pady=(1, 8), side="bottom")

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
        self.status_label = ctk.CTkLabel(
            self.statusbar, text="● Network OK",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR["success"]
        )
        self.status_label.pack(side="left", padx=(12, 8))

        self.cpu_label = ctk.CTkLabel(
            self.statusbar, text="CPU —",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["text_muted"]
        )
        self.cpu_label.pack(side="left", padx=(0, 8))

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

        self.status_threshold = ctk.CTkLabel(
            self.statusbar, text="Threshold: 0.85",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR["text_dim"]
        )
        self.status_threshold.pack(side="left", padx=(8, 0))

        # Right side: Port/Tab inputs + version
        self.status_version = ctk.CTkLabel(
            self.statusbar, text="v2.0",
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
        self.footer_tab_input.insert(0, "0")
        self.footer_tab_input.pack(side="right", padx=(0, 8))
        ctk.CTkLabel(
            self.statusbar, text="Tab",
            font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"]
        ).pack(side="right", padx=(0, 3))

        # Port input in footer
        self.footer_port_input = ctk.CTkEntry(
            self.statusbar, width=48, height=20,
            fg_color=COLOR["surface"], border_width=1,
            border_color=COLOR["border_subtle"], corner_radius=4,
            font=ctk.CTkFont(family="Consolas", size=10),
            justify="center"
        )
        self.footer_port_input.insert(0, "9222")
        self.footer_port_input.pack(side="right", padx=(0, 8))
        ctk.CTkLabel(
            self.statusbar, text="Port",
            font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"]
        ).pack(side="right", padx=(0, 3))

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

    # ==================== Output Tab ====================
    def _setup_output_tab(self):
        self.tab_output.grid_columnconfigure(0, weight=1)
        self.tab_output.grid_rowconfigure(0, weight=1)

        # Main Card
        card = ctk.CTkFrame(self.tab_output, fg_color=COLOR["surface"], corner_radius=12, border_width=1, border_color=COLOR["border_subtle"])
        card.grid(row=0, column=0, sticky="nsew", padx=PAD["lg"], pady=PAD["lg"])
        
        # Header Area
        header_frame = ctk.CTkFrame(card, fg_color="transparent", height=40)
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
        divider = ctk.CTkFrame(card, height=1, fg_color=COLOR["border"])
        divider.pack(fill="x", padx=PAD["lg"], pady=PAD["sm"])

        # Textbox container
        tb_container = ctk.CTkFrame(card, fg_color=COLOR["bg"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
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
        self.log_textbox.tag_config("time", foreground=COLOR["text_dim"])
        self.log_textbox.tag_config("default", foreground=COLOR["text"])
        self.log_textbox.tag_config("success", foreground=COLOR["success"])
        self.log_textbox.tag_config("warning", foreground=COLOR["warning"])
        self.log_textbox.tag_config("error", foreground=COLOR["danger"])
        self.log_textbox.tag_config("system", foreground=COLOR["primary"])

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
        self.gui_queue.put(("log", text))

    def _internal_log_gui(self, text):
        self.log_textbox.configure(state="normal")
        lines = int(self.log_textbox.index('end').split('.')[0]) - 1
        if lines > 150:
            self.log_textbox.delete("1.0", "20.0")
        current_time = time.strftime("%H:%M:%S")
        
        # Determine tag
        tag = "default"
        text_lower = text.lower()
        if "error" in text_lower or "fail" in text_lower or "exception" in text_lower:
            tag = "error"
        elif "success" in text_lower or "complet" in text_lower or "done" in text_lower or "acquir" in text_lower or "restored" in text_lower:
            tag = "success"
        elif "warning" in text_lower or "timeout" in text_lower:
            tag = "warning"
        elif "[system]" in text_lower:
            tag = "system"

        self.log_textbox.insert("end", f"[{current_time}] ", "time")
        self.log_textbox.insert("end", f"{text}\n", tag)
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    # ==================== Status Bar ====================
    def update_status(self, text):
        """Update status bar text."""
        self.status_label.configure(text=text)

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
