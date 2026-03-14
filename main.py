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
    """A sidebar navigation button with icon, label, and active indicator."""
    def __init__(self, master, icon, label, command=None, **kwargs):
        super().__init__(master, fg_color="transparent", height=56, cursor="hand2", **kwargs)
        self.pack_propagate(False)
        self.command = command
        self.is_active = False
        self._label_text = label

        # Active indicator bar (left edge)
        self.indicator = ctk.CTkFrame(self, width=3, height=28, fg_color="transparent", corner_radius=2)
        self.indicator.pack(side="left", padx=(0, 0), pady=14)

        # Content frame
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=(4, 8))

        self.icon_label = ctk.CTkLabel(
            content, text=icon, font=ctk.CTkFont(size=18),
            text_color=COLOR["text_dim"], width=30
        )
        self.icon_label.pack(side="left", padx=(8, 4))

        self.text_label = ctk.CTkLabel(
            content, text=label, font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR["text_dim"], anchor="w"
        )
        self.text_label.pack(side="left", fill="x", expand=True)

        # Bind click events to all children
        for widget in [self, content, self.icon_label, self.text_label]:
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_click(self, event=None):
        if self.command:
            self.command()

    def _on_enter(self, event=None):
        if not self.is_active:
            self.configure(fg_color=COLOR["sidebar_h"])

    def _on_leave(self, event=None):
        if not self.is_active:
            self.configure(fg_color="transparent")

    def set_active(self, active):
        self.is_active = active
        if active:
            self.indicator.configure(fg_color=COLOR["primary"])
            self.icon_label.configure(text_color=COLOR["primary"])
            self.text_label.configure(text_color=COLOR["text"])
            self.configure(fg_color=COLOR["surface"])
        else:
            self.indicator.configure(fg_color="transparent")
            self.icon_label.configure(text_color=COLOR["text_dim"])
            self.text_label.configure(text_color=COLOR["text_dim"])
            self.configure(fg_color="transparent")


# ════════════════════════════════════════════════════════════════
# Main Application
# ════════════════════════════════════════════════════════════════
class BotApp(NodesMixin, MacrosMixin, LoopsMixin, AccountsMixin, ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LordNine Bot Control")
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

        # ──── Layout: Sidebar + Content + StatusBar ────
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ════ SIDEBAR ════
        self.sidebar = ctk.CTkFrame(self, width=180, fg_color=COLOR["sidebar"], corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # App logo/title in sidebar
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=60)
        logo_frame.pack(fill="x", pady=(12, 4))
        logo_frame.pack_propagate(False)

        ctk.CTkLabel(
            logo_frame, text="⚡ LordNine",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=COLOR["primary"]
        ).pack(side="left", padx=16)

        # Divider
        ctk.CTkFrame(self.sidebar, height=1, fg_color=COLOR["border"]).pack(fill="x", padx=12, pady=(0, 8))

        # Navigation buttons
        self.nav_buttons = []
        nav_items = [
            ("🎯", "Nodes",      0),
            ("⚡", "Macros",     1),
            ("🔄", "Automation", 2),
            ("👥", "Accounts",   3),
            ("📋", "Output",     4),
        ]

        for icon, label, idx in nav_items:
            btn = SidebarButton(
                self.sidebar, icon=icon, label=label,
                command=lambda i=idx: self.switch_tab(i)
            )
            btn.pack(fill="x", padx=6, pady=1)
            self.nav_buttons.append(btn)

        # Sidebar bottom spacer
        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(fill="both", expand=True)

        # Version label at bottom of sidebar
        ctk.CTkLabel(
            self.sidebar, text="v2.0",
            font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"]
        ).pack(side="bottom", pady=10)

        # ════ CONTENT AREA ════
        self.content_area = ctk.CTkFrame(self, fg_color=COLOR["bg"], corner_radius=0)
        self.content_area.grid(row=0, column=1, sticky="nsew")

        # Create tab frames (hidden by default)
        self.tab_frames = []
        self.tab_setup  = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_combo  = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_loop   = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_multi  = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)
        self.tab_output = ctk.CTkFrame(self.content_area, fg_color=COLOR["bg"], corner_radius=0)

        self.tab_frames = [self.tab_setup, self.tab_combo, self.tab_loop, self.tab_multi, self.tab_output]

        # ════ STATUS BAR ════
        self.statusbar = ctk.CTkFrame(self, height=28, fg_color=COLOR["sidebar"], corner_radius=0)
        self.statusbar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.statusbar.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.statusbar, text="Ready",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR["text_dim"]
        )
        self.status_label.pack(side="left", padx=12)

        self.status_threshold = ctk.CTkLabel(
            self.statusbar, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR["text_muted"]
        )
        self.status_threshold.pack(side="right", padx=12)

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
        # Header
        log_header = ctk.CTkFrame(self.tab_output, fg_color="transparent")
        log_header.pack(fill="x", padx=PAD["xl"], pady=(PAD["lg"], PAD["sm"]))

        ctk.CTkLabel(
            log_header, text="SYSTEM LOG",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR["accent"]
        ).pack(side="left")

        def clear_log():
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.configure(state="disabled")

        ctk.CTkButton(
            log_header, text="Clear", width=70, height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR["danger"], hover_color=COLOR["danger_h"],
            command=clear_log, corner_radius=RADIUS
        ).pack(side="right")

        # Textbox
        self.log_textbox = ctk.CTkTextbox(
            self.tab_output, state="disabled",
            fg_color=COLOR["surface"],
            text_color=COLOR["accent"],
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=RADIUS,
            border_width=1,
            border_color=COLOR["border"]
        )
        self.log_textbox.pack(fill="both", expand=True, padx=PAD["xl"], pady=(0, PAD["xl"]))

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
        self.log_textbox.insert("end", f"[{current_time}] {text}\n")
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
