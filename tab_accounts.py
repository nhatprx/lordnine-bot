"""Accounts tab mixin — Multi-account coordinator, Chrome management, workers."""
import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import os

from constants import COLOR, FONT, PAD, RADIUS
from bot_action import BotAction
from cdp_client import CDPClient
from chrome_manager import ChromeManager
from macro_runner import run_macro
from state_db import StateDB

class AccountsMixin:
    """Mixin for the Accounts/Coordinator tab. Mixed into BotApp."""

    # ---- Thread-safe account_running helpers ----
    _running_lock = threading.Lock()

    def _is_running(self, acc_name):
        """Thread-safe check if account is running."""
        with self._running_lock:
            return self.account_running.get(acc_name, False)

    def _set_running(self, acc_name, val):
        """Thread-safe set account running state."""
        with self._running_lock:
            self.account_running[acc_name] = val

    def setup_multi_tab(self):
        # Sort state
        self._acc_sort_key = None    # "port", "tab", "name", "status", "function" or None
        self._acc_sort_reverse = False

        # Full-width single column layout (no 2-column split)
        self.tab_multi.grid_columnconfigure(0, weight=1)
        self.tab_multi.grid_rowconfigure(0, weight=1)

        # Main container
        main_frame = ctk.CTkFrame(self.tab_multi, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=PAD["lg"], pady=(PAD["md"], PAD["lg"]))
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(4, weight=1)  # table rows expand

        # ═══ ROW 0: Launch + Chrome (side by side) ═══
        top_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew", pady=(0, PAD["sm"]))
        top_row.grid_columnconfigure(0, weight=65, uniform="col")  # Launch (65%)
        top_row.grid_columnconfigure(1, weight=35, uniform="col")  # Chrome (35%)

        # -- Quick Launch pill --
        ql_pill = ctk.CTkFrame(top_row, fg_color=COLOR["bg_subtle"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
        ql_pill.grid(row=0, column=0, sticky="ew", padx=(0, PAD["sm"]))

        ql_inner = ctk.CTkFrame(ql_pill, fg_color="transparent")
        ql_inner.pack(fill="x", padx=PAD["sm"], pady=6)

        ctk.CTkLabel(ql_inner, text="LAUNCH", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold")).pack(side="left", padx=(0, 8))

        self.quick_url_entry = ctk.CTkEntry(ql_inner, placeholder_text="URL...", fg_color=COLOR["surface"], corner_radius=4, height=24, border_width=1, border_color=COLOR["border_subtle"], font=ctk.CTkFont(size=10))
        self.quick_url_entry.insert(0, "https://www.cloudemulator.net/app/phone?channelCode=web")
        self.quick_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkLabel(ql_inner, text="x", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10)).pack(side="left")
        self.quick_count_entry = ctk.CTkEntry(ql_inner, width=40, fg_color=COLOR["surface"], corner_radius=4, height=24, border_width=1, border_color=COLOR["border_subtle"], font=ctk.CTkFont(size=10), justify="center")
        self.quick_count_entry.pack(side="left", padx=(2, 8))

        ctk.CTkLabel(ql_inner, text="Max", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10)).pack(side="left")
        self.quick_max_tabs_entry = ctk.CTkEntry(ql_inner, width=40, fg_color=COLOR["surface"], corner_radius=4, height=24, border_width=1, border_color=COLOR["border_subtle"], font=ctk.CTkFont(size=10), justify="center")
        self.quick_max_tabs_entry.insert(0, "10")
        self.quick_max_tabs_entry.pack(side="left", padx=(2, 8))

        ctk.CTkLabel(ql_inner, text="Phone", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10)).pack(side="left")
        self.quick_start_phone_entry = ctk.CTkEntry(ql_inner, width=40, fg_color=COLOR["surface"], corner_radius=4, height=24, border_width=1, border_color=COLOR["border_subtle"], font=ctk.CTkFont(size=10), justify="center")
        self.quick_start_phone_entry.insert(0, "1")
        self.quick_start_phone_entry.pack(side="left", padx=(2, 8))

        self.quick_launch_btn = ctk.CTkButton(ql_inner, text="Launch", command=self._quick_launch, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(size=10, weight="bold"), corner_radius=4, height=24, width=55)
        self.quick_launch_btn.pack(side="left")

        self.quick_status_label = ctk.CTkLabel(ql_inner, text="", font=ctk.CTkFont(size=9), text_color=COLOR["text_muted"])
        self.quick_status_label.pack(side="left", padx=4)

        # -- Chrome Instances pill (same row, right) --
        chrome_pill = ctk.CTkFrame(top_row, fg_color=COLOR["bg_subtle"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
        chrome_pill.grid(row=0, column=1, sticky="nsew")

        chrome_inner = ctk.CTkFrame(chrome_pill, fg_color="transparent")
        chrome_inner.pack(fill="both", expand=True, padx=PAD["sm"], pady=6)

        chrome_top = ctk.CTkFrame(chrome_inner, fg_color="transparent")
        chrome_top.pack(fill="x")

        ctk.CTkLabel(chrome_top, text="CHROME", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold")).pack(side="left", padx=(0, 8))

        self.chrome_instances_container = ctk.CTkFrame(chrome_top, fg_color="transparent")
        self.chrome_instances_container.pack(side="left", fill="x", expand=True)
        self.conn_status_label = ctk.CTkLabel(self.chrome_instances_container, text="Not checked", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10))
        self.conn_status_label.pack(side="left")

        ctk.CTkButton(chrome_top, text="+ Add", command=self._launch_new_chrome, fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["primary"], font=ctk.CTkFont(size=10, weight="bold"), width=40, height=24, corner_radius=4).pack(side="right")

        # ═══ ROW 1: Toolbar (full width) ═══
        toolbar = ctk.CTkFrame(main_frame, fg_color=COLOR["bg_subtle"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, PAD["sm"]))

        toolbar_inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        toolbar_inner.pack(fill="x", padx=PAD["sm"], pady=5)

        # Left group: Start | Stop | Delete
        left_grp = ctk.CTkFrame(toolbar_inner, fg_color="transparent")
        left_grp.pack(side="left")
        self._btn_start = ctk.CTkButton(left_grp, text="Start All", command=self._batch_start_all, fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["success"], font=ctk.CTkFont(size=10, weight="bold"), width=75, height=24, corner_radius=4)
        self._btn_start.pack(side="left", padx=(0, 1))
        self._btn_stop = ctk.CTkButton(left_grp, text="Stop All", command=self._batch_stop_all, fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["danger"], font=ctk.CTkFont(size=10, weight="bold"), width=65, height=24, corner_radius=4)
        self._btn_stop.pack(side="left")
        ctk.CTkButton(left_grp, text="Delete", command=self._delete_selected_accounts, fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"), width=45, height=24, corner_radius=4).pack(side="left", padx=(1, 0))
        ctk.CTkButton(left_grp, text="⟳ Refresh", command=self._refresh_accounts, fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["accent"], font=ctk.CTkFont(size=10, weight="bold"), width=60, height=24, corner_radius=4).pack(side="left", padx=(1, 0))

        # Right group: Function assignment (type selector + name)
        right_grp = ctk.CTkFrame(toolbar_inner, fg_color="transparent")
        right_grp.pack(side="right")
        self.func_type_combo = ctk.CTkComboBox(right_grp, values=["Loop", "Macro"], width=70, font=ctk.CTkFont(size=10), height=24, corner_radius=4, fg_color=COLOR["surface"], border_color=COLOR["border_subtle"], command=self._on_func_type_changed)
        self.func_type_combo.pack(side="left", padx=(0, 4))
        self.func_type_combo.set("Loop")
        self.func_assign_combo = ctk.CTkComboBox(right_grp, values=[], width=130, font=ctk.CTkFont(size=10), height=24, corner_radius=4, fg_color=COLOR["surface"], border_color=COLOR["border_subtle"])
        self.func_assign_combo.pack(side="left", padx=(0, 4))
        self.func_assign_combo.set("")
        ctk.CTkButton(right_grp, text="Assign", command=self._assign_function_to_selected, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(size=10, weight="bold"), corner_radius=4, height=24, width=50).pack(side="left")

        # Center group: Stats + Search (expands to fill middle, content centered)
        center_grp = ctk.CTkFrame(toolbar_inner, fg_color="transparent")
        center_grp.pack(side="left", fill="x", expand=True)
        self.acc_stats_label = ctk.CTkLabel(center_grp, text="", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10))
        self.acc_stats_label.pack(side="left", padx=(8, 4))

        self._acc_search_debounce_id = None
        def _debounced_acc_search(*a):
            if self._acc_search_debounce_id:
                self.after_cancel(self._acc_search_debounce_id)
            self._acc_search_debounce_id = self.after(150, self.refresh_multi_acc_list)
        self.acc_search_entry = ctk.CTkEntry(
            center_grp, placeholder_text="Search...",
            fg_color=COLOR["surface"], border_color=COLOR["border_subtle"],
            border_width=1, corner_radius=4, height=24, width=140,
            font=ctk.CTkFont(size=10)
        )
        self.acc_search_entry.pack(side="left")
        self.acc_search_entry._entry.bind("<KeyRelease>", _debounced_acc_search)

        # Blur searchbox when clicking anywhere outside any entry
        def _blur_acc_search(event=None):
            if not hasattr(self, 'acc_search_entry'):
                return
            try:
                import tkinter
                clicked = event.widget
                # Don't steal focus if clicking on ANY entry widget
                if isinstance(clicked, (tkinter.Entry, ctk.CTkEntry)):
                    return
                search_inner = self.acc_search_entry._entry
                if clicked is not search_inner and clicked is not self.acc_search_entry:
                    self.focus_set()
            except Exception:
                pass
        self._blur_acc_search = _blur_acc_search
        self.bind_all("<Button-1>", _blur_acc_search, add="+")

        # ═══ TABLE HEADER ═══
        # Column config grouped into 40%, 40%, 20% width pools
        header_row = ctk.CTkFrame(main_frame, fg_color="transparent", height=28)
        header_row.grid(row=2, column=0, sticky="ew", pady=(0, 2), padx=(7, 23)) # 7px left padding, 23px right (padding + scrollbar)
        header_row.grid_propagate(False)
        header_row.grid_columnconfigure(0, weight=1)

        # Matched simulated container
        header_bg = ctk.CTkFrame(header_row, fg_color="transparent", corner_radius=6)
        header_bg.grid(row=0, column=0, sticky="ew")

        # Matched inner layout
        header_inner = ctk.CTkFrame(header_bg, fg_color="transparent")
        header_inner.pack(fill="x", expand=True, padx=4, pady=5)
        
        # 40% - 40% - 20% System
        header_inner.grid_columnconfigure(0, weight=4, uniform="base_col")
        header_inner.grid_columnconfigure(1, weight=4, uniform="base_col")
        header_inner.grid_columnconfigure(2, weight=2, uniform="base_col")

        # Group 1 (40%): Checkbox, Port, Tab, Name — clickable sort headers
        h_grp1 = ctk.CTkFrame(header_inner, fg_color="transparent")
        h_grp1.grid(row=0, column=0, sticky="ew")
        self.select_all_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(h_grp1, text="", variable=self.select_all_var, command=self._toggle_select_all, checkbox_width=14, checkbox_height=14, corner_radius=3, border_width=1, border_color=COLOR["border"]).pack(side="left", padx=(4, 15))

        self._sort_header_btns = {}
        self._sort_header_btns["port"] = ctk.CTkButton(h_grp1, text="PORT", command=lambda: self._sort_by("port"), fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"), width=35, height=20, corner_radius=3, cursor="hand2")
        self._sort_header_btns["port"].pack(side="left", padx=4)
        self._sort_header_btns["tab"] = ctk.CTkButton(h_grp1, text="TAB", command=lambda: self._sort_by("tab"), fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"), width=30, height=20, corner_radius=3, cursor="hand2")
        self._sort_header_btns["tab"].pack(side="left", padx=4)
        self._sort_header_btns["name"] = ctk.CTkButton(h_grp1, text="NAME", command=lambda: self._sort_by("name"), fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"), height=20, corner_radius=3, cursor="hand2")
        self._sort_header_btns["name"].pack(side="left", padx=4, fill="x", expand=True)

        # Group 2 (40%): Status
        h_grp2 = ctk.CTkFrame(header_inner, fg_color="transparent")
        h_grp2.grid(row=0, column=1, sticky="ew")
        self._sort_header_btns["status"] = ctk.CTkButton(h_grp2, text="STATUS", command=lambda: self._sort_by("status"), fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"), height=20, corner_radius=3, cursor="hand2")
        self._sort_header_btns["status"].pack(fill="x", expand=True)

        # Group 3 (20%): Loop, Action
        h_grp3 = ctk.CTkFrame(header_inner, fg_color="transparent")
        h_grp3.grid(row=0, column=2, sticky="ew")
        h_grp3.grid_columnconfigure(0, weight=1)
        h_grp3.grid_columnconfigure(1, weight=1)
        self._sort_header_btns["function"] = ctk.CTkButton(h_grp3, text="FUNCTION", command=lambda: self._sort_by("function"), fg_color="transparent", hover_color=COLOR["surface2"], text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"), width=55, height=20, corner_radius=3, cursor="hand2")
        self._sort_header_btns["function"].grid(row=0, column=0, sticky="ew", padx=4)
        ctk.CTkLabel(h_grp3, text="ACTION", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10, weight="bold"), anchor="center").grid(row=0, column=1, sticky="ew", padx=4)

        # Header bottom border
        ctk.CTkFrame(main_frame, fg_color=COLOR["border_subtle"], height=1).grid(row=3, column=0, sticky="ew", padx=(7, 23))

        # ═══ TABLE ROWS (scrollable) ═══
        self.dash_grid = ctk.CTkScrollableFrame(main_frame, fg_color="transparent", scrollbar_button_color=COLOR["border"], scrollbar_button_hover_color=COLOR["text_muted"])
        self.dash_grid.grid(row=4, column=0, sticky="nsew", pady=(2, 0))

        self.dash_labels = {}
        self.dash_conn_labels = {}
        self.dash_checkboxes = {}
        self._row_widgets = {}  # acc_name → {row, btn, lbl_func, lbl_conn}
        self.refresh_multi_acc_list()

        # Auto-check connection on startup (delayed)
        self.after(2000, self._refresh_connection_status)
        self._start_health_monitor()

    # ---- Chrome Management ----
    def _launch_new_chrome(self):
        port = self.chrome_mgr.get_next_available_port()
        if port is None:
            self.log_gui("[Chrome] All ports in use (9222-9241)")
            return
            
        def _launch():
            success, msg = self.chrome_mgr.launch(port=port)
            self.gui_queue.put(("log", f"[Chrome] {msg}"))
            if success:
                self.state_db.save_chrome_instance(port, status="running")
            self.after(500, self._refresh_connection_status)
        
        threading.Thread(target=_launch, daemon=True).start()
        self.log_gui(f"[Chrome] Launching on port {port}...")

    def _kill_chrome_port(self, port):
        success, msg = self.chrome_mgr.kill(port)
        self.log_gui(f"[Chrome] {msg}")
        self.state_db.remove_chrome_instance(port)
        self.after(500, self._refresh_connection_status)

    def _quick_launch(self):
        """Quick Launch: Auto-open Chrome instances with balanced tabs."""
        url = self.quick_url_entry.get().strip()
        count_str = self.quick_count_entry.get().strip()
        max_tabs_str = self.quick_max_tabs_entry.get().strip()
        
        if not url:
            self._acc_styled_info("Missing URL", "Enter a URL to launch")
            return
        if not count_str.isdigit() or int(count_str) < 1:
            self._acc_styled_info("Invalid count", "Account count must be a positive number")
            return
        if not max_tabs_str.isdigit() or int(max_tabs_str) < 1:
            self._acc_styled_info("Invalid max tabs", "Max tabs must be a positive number")
            return

        
        total_accounts = int(count_str)
        max_tabs = int(max_tabs_str)
        
        # Get start phone index
        start_str = self.quick_start_phone_entry.get().strip()
        start_phone = int(start_str) if start_str.isdigit() and int(start_str) >= 1 else 1
        
        # Calculate distribution
        import math
        num_chrome = math.ceil(total_accounts / max_tabs)
        distribution = []
        remaining = total_accounts
        for i in range(num_chrome):
            tabs = min(max_tabs, remaining)
            distribution.append(tabs)
            remaining -= tabs
        
        # Preview
        dist_str = " + ".join(str(d) for d in distribution)
        self.log_gui(f"[Quick Launch] {total_accounts} accounts → {num_chrome} Chrome instances ({dist_str})")
        
        self.quick_launch_btn.configure(state="disabled", text="Launching...")
        self.quick_status_label.configure(text=f"Opening {num_chrome} Chrome ({dist_str})...", text_color=COLOR["warning"])
        
        def _do_launch():
            base_port = 9222
            ports_needed = [base_port + i for i in range(num_chrome)]
            
            # Kill only the ports we need (not all managed)
            for p in ports_needed:
                if p in self.chrome_mgr.processes:
                    self.chrome_mgr.kill(p)
            
            # Launch all Chrome instances in PARALLEL
            results = {}  # port -> (success, msg, actual)
            
            def _launch_one(port, tab_count):
                success, msg, actual = self.chrome_mgr.launch_with_tabs(port, url, tab_count)
                results[port] = (success, msg, actual)
                self.gui_queue.put(("log", f"[Quick Launch] {msg}"))
            
            self.gui_queue.put(("log", f"[Quick Launch] Launching {num_chrome} Chrome(s) in parallel..."))
            threads = []
            for idx, tab_count in enumerate(distribution):
                port = ports_needed[idx]
                t = threading.Thread(target=_launch_one, args=(port, tab_count), daemon=True)
                threads.append(t)
                t.start()
            
            # Wait for all to finish
            for t in threads:
                t.join(timeout=15)
            
            # Auto-open cloud phones FIRST (to get phone names)
            self.gui_queue.put(("log", f"[Quick Launch] Waiting for pages to load..."))
            time.sleep(5)  # 5s for Redfinger page to fully load with multiple tabs
            
            all_phone_names = {}  # (port, tab_idx) -> phone_name
            global_phone_counter = start_phone  # 1-based, for fallback naming
            for port_idx, port in enumerate(ports_needed):
                if port not in results:
                    continue
                success, msg, actual = results[port]
                if not success:
                    continue
                
                # Each Chrome tab's page shows ALL phone cards.
                # phone_indices tells each tab which card to click (0-based).
                # CRITICAL: offset by global_phone_counter so each Chrome profile
                # opens DIFFERENT phones. Without offset, every profile clicks
                # cards [0,1,2...] = same phones!
                start_idx = global_phone_counter - start_phone  # convert to 0-based offset
                indices = list(range(start_idx, start_idx + actual))
                
                # Wave-based: wait between ports so pages have time to stabilize
                if port_idx > 0:
                    time.sleep(2)
                
                self.gui_queue.put(("log", f"[Quick Launch] Scanning phones {global_phone_counter}-{global_phone_counter+actual-1} on port {port}..."))
                try:
                    opened, errors, phone_names = self.chrome_mgr.auto_open_cloud_phones(port, indices)
                    
                    for tab_idx, name in phone_names.items():
                        all_phone_names[(port, tab_idx)] = name
                    
                    if errors:
                        for err in errors:
                            self.gui_queue.put(("log", f"[Quick Launch] ⚠ {err}"))
                    self.gui_queue.put(("log", f"[Quick Launch] Port {port}: opened {opened}/{actual} cloud phones"))
                except Exception as e:
                    self.gui_queue.put(("log", f"[Quick Launch] ❌ Port {port} scan failed: {e}"))
                
                global_phone_counter += actual
            
            # Create accounts with phone names
            created_accounts = []
            for idx, port in enumerate(ports_needed):
                if port not in results:
                    continue
                success, msg, actual = results[port]
                if not success:
                    continue
                self.state_db.save_chrome_instance(port, status="running")
                for tab_idx in range(actual):
                    phone_name = all_phone_names.get((port, tab_idx), f"Phone-{len(created_accounts)+1}")
                    acc_entry = {
                        "name": phone_name,
                        "target": str(tab_idx),
                        "port": port,
                        "loop": "",
                        "proxy": "",
                        "enabled": True,
                        "group": "default",
                    }
                    created_accounts.append(acc_entry)
            
            # Save accounts
            # Merge new accounts with existing (preserve other ports)
            if created_accounts:
                # Deduplicate names: if a name already exists on a DIFFERENT port, add suffix
                existing_names = {}  # name → port
                for a in self.multi_accounts:
                    existing_names[a['name']] = a.get('port', 9222)
                
                for acc in created_accounts:
                    base_name = acc['name']
                    if base_name in existing_names and existing_names[base_name] != acc['port']:
                        # Name exists on different port → make unique
                        acc['name'] = f"{base_name} ({acc['port']})"
                    # Also check for duplicates within created_accounts itself
                    used_names = {a['name'] for a in created_accounts if a is not acc}
                    while acc['name'] in used_names:
                        acc['name'] = f"{acc['name']} ({acc['port']})"
                
                # Also rename OLD accounts that conflict with new ones
                new_base_names = {all_phone_names.get((a['port'], int(a['target'])), a['name']): a['port'] 
                                  for a in created_accounts}
                for a in self.multi_accounts:
                    if a['name'] in new_base_names and new_base_names[a['name']] != a.get('port', 9222):
                        a['name'] = f"{a['name']} ({a.get('port', 9222)})"
                
                new_names = {a['name'] for a in created_accounts}
                merged = [a for a in self.multi_accounts if a['name'] not in new_names]
                merged.extend(created_accounts)
                self.multi_accounts = merged
                self.save_multi()
            
            self.gui_queue.put(("log", f"[Quick Launch] All done! {len(created_accounts)} accounts ready."))
            
            # Update UI on main thread
            def _update_ui():
                self.quick_launch_btn.configure(state="normal", text="Launch")
                self.quick_status_label.configure(
                    text=f"Done: {len(created_accounts)} accounts, {num_chrome} Chrome",
                    text_color=COLOR["success"]
                )
                self.refresh_multi_acc_list()
                self._refresh_connection_status()
            
            self.after(100, _update_ui)
        
        threading.Thread(target=_do_launch, daemon=True).start()

    def _refresh_connection_status(self):
        def _check():
            ports_info = self.chrome_mgr.get_all_ports_info()
            self.gui_queue.put(("conn_status", ports_info))
        
        try:
            if self.conn_status_label.winfo_exists():
                self.conn_status_label.configure(text="Checking...", text_color=COLOR["warning"])
        except:
            pass
        threading.Thread(target=_check, daemon=True).start()

    def _render_connection_status(self, ports_info):
        for w in self.chrome_instances_container.winfo_children():
            w.destroy()
        
        if not ports_info:
            ctk.CTkLabel(self.chrome_instances_container, text="No Chrome instances", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10)).pack(side="left")
            if hasattr(self, 'dash_conn_labels'):
                for lbl in self.dash_conn_labels.values():
                    lbl.configure(text_color=COLOR["danger"])
            return
        
        total_tabs = sum(p["tab_count"] for p in ports_info)
        num_instances = len(ports_info)
        
        # Compact summary: green dot + count
        ctk.CTkLabel(self.chrome_instances_container, text="●", text_color=COLOR["success"], font=ctk.CTkFont(size=8)).pack(side="left")
        ctk.CTkLabel(
            self.chrome_instances_container,
            text=f" {num_instances} instance{'s' if num_instances > 1 else ''}, {total_tabs} tabs",
            text_color=COLOR["text"], font=ctk.CTkFont(size=10, weight="bold")
        ).pack(side="left", padx=(2, 6))

        # Details button → opens popup
        def _show_details():
            dlg = ctk.CTkToplevel(self)
            dlg.title("Lordbot Control")
            h = min(60 + num_instances * 40, 320)
            dlg.geometry(f"300x{h}")
            dlg.resizable(False, False)
            dlg.configure(fg_color=COLOR["surface"])
            dlg.transient(self)
            dlg.grab_set()
            dlg.after(200, lambda: dlg.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
            dlg.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - 300) // 2
            y = self.winfo_y() + (self.winfo_height() - h) // 2
            dlg.geometry(f"300x{h}+{x}+{y}")

            ctk.CTkLabel(dlg, text="Chrome Instances", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["text"]).pack(pady=(12, 8))

            for pinfo in ports_info:
                row = ctk.CTkFrame(dlg, fg_color=COLOR["bg"], corner_radius=6)
                row.pack(fill="x", padx=16, pady=2)
                row_inner = ctk.CTkFrame(row, fg_color="transparent")
                row_inner.pack(fill="x", padx=8, pady=4)
                ctk.CTkLabel(row_inner, text="●", text_color=COLOR["success"], font=ctk.CTkFont(size=8)).pack(side="left")
                ctk.CTkLabel(row_inner, text=f":{pinfo['port']}", text_color=COLOR["text"], font=ctk.CTkFont(family="Consolas", size=11, weight="bold")).pack(side="left", padx=(4, 8))
                ctk.CTkLabel(row_inner, text=f"{pinfo['tab_count']} tabs", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10)).pack(side="left")
                ctk.CTkButton(row_inner, text="Kill", width=40, height=20, fg_color=COLOR["danger_dim"], hover_color=COLOR["danger"], text_color=COLOR["danger"], font=ctk.CTkFont(size=9, weight="bold"), corner_radius=4, command=lambda p=pinfo['port']: (self._kill_chrome_port(p), dlg.destroy())).pack(side="right")

        ctk.CTkButton(
            self.chrome_instances_container, text="Details", width=50, height=20,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["primary"], font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=4, command=_show_details
        ).pack(side="left")
        
        if hasattr(self, 'dash_conn_labels'):
            all_ports_tabs = {}
            for pinfo in ports_info:
                all_ports_tabs[pinfo['port']] = pinfo['tab_count']
            
            for acc in self.multi_accounts:
                name = acc.get('name', '')
                port = acc.get('port', 9222)
                tab_idx = int(acc.get('target', '0')) if acc.get('target', '').isdigit() else 0
                
                if name in self.dash_conn_labels:
                    if port in all_ports_tabs and tab_idx < all_ports_tabs[port]:
                        self.dash_conn_labels[name].configure(text_color=COLOR["success"])
                    else:
                        self.dash_conn_labels[name].configure(text_color=COLOR["danger"])

    # ---- Account Management ----
    def add_multi_account(self):
        if not self.tracked_icons or not self.loops:
            self._acc_styled_info("Setup required", "Create Tracking Nodes and Loops first")
            return
            
        top = ctk.CTkToplevel(self)
        top.title("Lordbot Control")
        top.geometry("400x430")
        top.resizable(False, False)
        top.configure(fg_color=COLOR["surface"])
        top.transient(self)
        top.grab_set()
        top.after(200, lambda: top.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        top.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 430) // 2
        top.geometry(f"400x430+{x}+{y}")

        ctk.CTkLabel(
            top, text="Add Account",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR["primary"]
        ).pack(pady=(16, 8))

        form = ctk.CTkFrame(top, fg_color="transparent")
        form.pack(fill="x", padx=20)

        # Display Name
        ctk.CTkLabel(form, text="Display Name:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        ent_name = ctk.CTkEntry(form, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=30, font=ctk.CTkFont(size=11), placeholder_text="Account name...")
        ent_name.pack(fill="x", pady=(0, 8))

        # Port + Tab row
        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(row1, text="Port:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(side="left")
        ent_port = ctk.CTkEntry(row1, width=70, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=28, font=ctk.CTkFont(size=11), placeholder_text="9222")
        ent_port.insert(0, "9222")
        ent_port.pack(side="left", padx=(4, 12))
        
        ctk.CTkLabel(row1, text="Tab Index:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(side="left")
        ent_target = ctk.CTkEntry(row1, width=50, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=28, font=ctk.CTkFont(size=11), placeholder_text="0")
        ent_target.pack(side="left", padx=4)

        # Loop assignment
        ctk.CTkLabel(form, text="Assigned Loop:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        combo_loop = ctk.CTkComboBox(form, values=list(self.loops.keys()), fg_color=COLOR["bg"], border_color=COLOR["border"], corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        combo_loop.pack(fill="x", pady=(0, 8))

        # Proxy
        ctk.CTkLabel(form, text="Proxy (optional):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        ent_proxy = ctk.CTkEntry(form, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=30, font=ctk.CTkFont(size=11), placeholder_text="socks5://1.2.3.4:1080")
        ent_proxy.pack(fill="x", pady=(0, 8))
        
        # Group
        ctk.CTkLabel(form, text="Group:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        ent_group = ctk.CTkEntry(form, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=30, font=ctk.CTkFont(size=11), placeholder_text="default")
        ent_group.insert(0, "default")
        ent_group.pack(fill="x", pady=(0, 12))

        # Buttons
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        def on_save():
            name = ent_name.get().strip()
            target = ent_target.get().strip()
            port_str = ent_port.get().strip()
            
            if not name or not target:
                self._acc_styled_info("Missing fields", "Name and Tab Index are required")
                return
            if not target.isdigit():
                self._acc_styled_info("Invalid input", "Tab Index must be a number")
                return
            if not port_str.isdigit():
                self._acc_styled_info("Invalid input", "Port must be a number")
                return
                
            self.multi_accounts.append({
                "name": name,
                "target": target,
                "port": int(port_str),
                "loop": combo_loop.get(),
                "proxy": ent_proxy.get().strip(),
                "enabled": True,
                "group": ent_group.get().strip() or "default",
            })
            self.save_multi()
            self.refresh_multi_acc_list()
            top.destroy()

        ctk.CTkButton(
            btn_row, text="Save Account", command=on_save,
            fg_color=COLOR["primary"], hover_color=COLOR["surface2"],
            text_color="#FFFFFF", font=ctk.CTkFont(size=12, weight="bold"),
            height=34, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Cancel", command=top.destroy,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=12, weight="bold"),
            height=34, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def refresh_multi_acc_list(self):
        for widget in self.dash_grid.winfo_children():
            widget.destroy()
        self.dash_labels.clear()
        self.dash_conn_labels = {}
        self.dash_checkboxes = {}
        self._row_widgets = {}

        # Update sort header arrows
        self._update_sort_headers()

        running_count = 0
        idle_count = 0
        error_count = 0

        # Search filter
        search_q = ""
        if hasattr(self, 'acc_search_entry'):
            search_q = self.acc_search_entry.get().strip().lower()

        # Build sorted + filtered display list
        display_list = list(self.multi_accounts)
        if search_q:
            def _matches(a):
                fields = [
                    a.get('name', ''),
                    str(a.get('port', '')),
                    str(a.get('target', '')),
                    a.get('loop', '') or '',
                    'running' if self.account_running.get(a['name'], False) else 'idle',
                ]
                return any(search_q in f.lower() for f in fields)
            display_list = [a for a in display_list if _matches(a)]

        if self._acc_sort_key:
            try:
                key_map = {
                    "port": lambda a: a.get('port', 9222),
                    "tab": lambda a: int(a.get('target', '0')) if str(a.get('target', '0')).isdigit() else 0,
                    "name": lambda a: a['name'].lower(),
                    "status": lambda a: 0 if self.account_running.get(a['name'], False) else 1,
                    "function": lambda a: (a.get('loop', '') or '').lower(),
                }
                if self._acc_sort_key in key_map:
                    display_list.sort(key=key_map[self._acc_sort_key], reverse=self._acc_sort_reverse)
            except Exception:
                pass

        for idx, acc in enumerate(display_list):
            name = acc['name']
            port = acc.get('port', 9222)
            is_running = self._is_running(name)
            
            # Count stats
            if is_running:
                running_count += 1
            else:
                idle_count += 1

            row = ctk.CTkFrame(self.dash_grid, fg_color=COLOR["bg_subtle"], corner_radius=6)
            row.pack(fill="x", pady=1, expand=True)

            row_inner = ctk.CTkFrame(row, fg_color="transparent")
            row_inner.pack(fill="x", expand=True, padx=4, pady=5)
            row_inner.grid_columnconfigure(0, weight=4, uniform="base_col")
            row_inner.grid_columnconfigure(1, weight=4, uniform="base_col")
            row_inner.grid_columnconfigure(2, weight=2, uniform="base_col")

            # Group 1 (40%)
            r_grp1 = ctk.CTkFrame(row_inner, fg_color="transparent")
            r_grp1.grid(row=0, column=0, sticky="ew")
            
            chk_var = ctk.BooleanVar(value=False)
            self.dash_checkboxes[name] = chk_var
            def _on_chk_change(*a, n=name): self._update_toolbar_buttons()
            chk_var.trace_add("write", _on_chk_change)
            ctk.CTkCheckBox(r_grp1, text="", variable=chk_var, checkbox_width=14, checkbox_height=14, corner_radius=3, border_width=1, border_color=COLOR["border"]).pack(side="left", padx=(4, 15))

            conn_color = COLOR["success"] if is_running else COLOR["text_muted"]
            lbl_conn = ctk.CTkLabel(r_grp1, text=str(port), font=ctk.CTkFont(family="Consolas", size=10), text_color=conn_color, width=35, anchor="center")
            lbl_conn.pack(side="left", padx=4)
            self.dash_conn_labels[name] = lbl_conn

            ctk.CTkLabel(r_grp1, text=str(acc.get('target', '0')), font=ctk.CTkFont(family="Consolas", size=10), text_color=COLOR["text_dim"], width=30, anchor="center").pack(side="left", padx=4)
            ctk.CTkLabel(r_grp1, text=name, font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR["text"], anchor="center").pack(side="left", padx=4, fill="x", expand=True)

            # Group 2 (40%)
            r_grp2 = ctk.CTkFrame(row_inner, fg_color="transparent")
            r_grp2.grid(row=0, column=1, sticky="ew")
            status_text = "Running..." if is_running else "Idle"
            status_color = COLOR["success"] if is_running else COLOR["text_muted"]
            lbl_status = ctk.CTkLabel(r_grp2, text=status_text, text_color=status_color, font=ctk.CTkFont(size=11), anchor="center")
            lbl_status.pack(fill="x", expand=True)
            self.dash_labels[name] = lbl_status

            # Group 3 (20%)
            r_grp3 = ctk.CTkFrame(row_inner, fg_color="transparent")
            r_grp3.grid(row=0, column=2, sticky="ew")
            r_grp3.grid_columnconfigure(0, weight=1)
            r_grp3.grid_columnconfigure(1, weight=1)

            loop_name = acc.get('loop', '—') or "—"
            ctk.CTkLabel(r_grp3, text=loop_name, text_color=COLOR["text_muted"], font=ctk.CTkFont(size=10), anchor="center").grid(row=0, column=0, sticky="ew", padx=4)

            btn_text = "Stop" if is_running else "Start"
            btn_fg = COLOR["danger_dim"] if is_running else COLOR["success_dim"]
            btn_color = COLOR["danger"] if is_running else COLOR["success"]
            
            def toggle_single(n=name):
                if self._is_running(n):
                    self._stop_account(n)
                else:
                    self._start_account(n)
            
            # Action button container
            action_frame = ctk.CTkFrame(r_grp3, fg_color="transparent")
            action_frame.grid(row=0, column=1, sticky="nsew")
            ctk.CTkButton(action_frame, text=btn_text, width=50, height=22, fg_color=btn_fg, hover_color=COLOR["surface2"], text_color=btn_color, corner_radius=4, font=ctk.CTkFont(size=10, weight="bold"), command=toggle_single).pack(expand=True)

            # Cache widget references for in-place updates
            self._row_widgets[name] = {
                "row": row,
                "btn_frame": action_frame,
                "lbl_conn": lbl_conn,
                "lbl_func": r_grp3.winfo_children()[0] if r_grp3.winfo_children() else None,
            }

        # Update stats label
        if hasattr(self, 'acc_stats_label'):
            parts = []
            if running_count: parts.append(f"● {running_count} running")
            if idle_count: parts.append(f"● {idle_count} idle")
            if error_count: parts.append(f"● {error_count} error")
            self.acc_stats_label.configure(text=" · ".join(parts) if parts else "")

        # Refresh loop dropdown values
        self._refresh_func_combo()

    def update_dash_status(self, acc_name, status, color="white"):
        self.gui_queue.put(("dash_status", (acc_name, status, color)))
        
    def _internal_update_dash_status(self, acc_name, status, color):
        if acc_name in self.dash_labels:
            self.dash_labels[acc_name].configure(text=f"{status}", text_color=color)

    def _update_row_states(self):
        """Lightweight in-place update of row widgets (no destroy/recreate).
        
        Only updates:  connection label color, action button text/colors, stats.
        ~100x faster than refresh_multi_acc_list() which rebuilds all widgets.
        """
        running_count = 0
        idle_count = 0
        
        for acc in self.multi_accounts:
            name = acc['name']
            is_running = self._is_running(name)
            
            if is_running:
                running_count += 1
            else:
                idle_count += 1
            
            # Update connection label color
            if name in self.dash_conn_labels:
                conn_color = COLOR["success"] if is_running else COLOR["text_muted"]
                self.dash_conn_labels[name].configure(text_color=conn_color)
            
            # Update action button (Start/Stop)
            if name in self._row_widgets:
                btn_frame = self._row_widgets[name].get("btn_frame")
                if btn_frame and btn_frame.winfo_exists():
                    # Destroy old button and create new one with correct state
                    for child in btn_frame.winfo_children():
                        child.destroy()
                    
                    btn_text = "Stop" if is_running else "Start"
                    btn_fg = COLOR["danger_dim"] if is_running else COLOR["success_dim"]
                    btn_color = COLOR["danger"] if is_running else COLOR["success"]
                    
                    def toggle_single(n=name):
                        if self._is_running(n):
                            self._stop_account(n)
                        else:
                            self._start_account(n)
                    
                    ctk.CTkButton(btn_frame, text=btn_text, width=50, height=22,
                                  fg_color=btn_fg, hover_color=COLOR["surface2"],
                                  text_color=btn_color, corner_radius=4,
                                  font=ctk.CTkFont(size=10, weight="bold"),
                                  command=toggle_single).pack(expand=True)
        
        # Update stats
        if hasattr(self, 'acc_stats_label'):
            parts = []
            if running_count: parts.append(f"● {running_count} running")
            if idle_count: parts.append(f"● {idle_count} idle")
            self.acc_stats_label.configure(text=" · ".join(parts) if parts else "")

    # ---- Batch Operations ----
    def _batch_start_all(self):
        # Smart wave-based start: groups of 5, 1s between waves
        # 15 accounts → 3 waves → fully started in ~2s
        WAVE_SIZE = 3
        delay_ms = 0
        count = 0
        for acc in self.multi_accounts:
            if acc.get("enabled", True):
                self.after(delay_ms, lambda n=acc['name']: self._start_account(n))
                count += 1
                if count % WAVE_SIZE == 0:
                    delay_ms += 2000  # 2s between waves (was 1s)
    
    def _batch_stop_all(self):
        for acc in self.multi_accounts:
            self._stop_account(acc['name'])
    
    def _batch_start_selected(self):
        selected = [acc['name'] for acc in self.multi_accounts
                    if self.dash_checkboxes.get(acc['name']) and self.dash_checkboxes[acc['name']].get()]
        WAVE_SIZE = 3
        delay_ms = 0
        for i, name in enumerate(selected):
            self.after(delay_ms, lambda n=name: self._start_account(n))
            if (i + 1) % WAVE_SIZE == 0:
                delay_ms += 2000
    
    def _batch_stop_selected(self):
        selected = [acc['name'] for acc in self.multi_accounts
                    if self.dash_checkboxes.get(acc['name']) and self.dash_checkboxes[acc['name']].get()]
        for name in selected:
            self._stop_account(name)
    
    def _toggle_select_all(self):
        val = self.select_all_var.get()
        for chk_var in self.dash_checkboxes.values():
            chk_var.set(val)
        self._update_toolbar_buttons()

    def _update_toolbar_buttons(self):
        """Update Start/Stop button text based on checkbox selection."""
        if not hasattr(self, '_btn_start'):
            return
        selected = [n for n, v in self.dash_checkboxes.items() if v.get()]
        total = len(self.dash_checkboxes)
        if selected and len(selected) < total:
            self._btn_start.configure(text="Start Sel.", command=self._batch_start_selected)
            self._btn_stop.configure(text="Stop Sel.", command=self._batch_stop_selected)
        else:
            self._btn_start.configure(text="Start All", command=self._batch_start_all)
            self._btn_stop.configure(text="Stop All", command=self._batch_stop_all)
    
    def _assign_function_to_selected(self):
        func_type = self.func_type_combo.get().strip()
        func_name = self.func_assign_combo.get().strip()
        if not func_name:
            self._acc_styled_info("Select a function", "Choose a function from the dropdown first")
            return
        
        # Build prefixed value: "loop - X" or "macro - X"
        prefix = "loop" if func_type == "Loop" else "macro"
        func_value = f"{prefix} - {func_name}"
        
        count = 0
        for acc in self.multi_accounts:
            name = acc['name']
            if self.dash_checkboxes.get(name) and self.dash_checkboxes[name].get():
                acc['loop'] = func_value
                count += 1
        
        if count == 0:
            self._acc_styled_info("No accounts selected", "Tick checkboxes to select accounts first")
            return
        
        self.save_multi()
        self.refresh_multi_acc_list()
        self.log_gui(f"[Accounts] Assigned '{func_value}' to {count} account(s)")
    
    def _on_func_type_changed(self, value):
        """Update function name dropdown when type changes."""
        self._refresh_func_combo()
    
    def _refresh_func_combo(self):
        """Update the function name dropdown based on selected type."""
        if not hasattr(self, 'func_assign_combo'):
            return
        func_type = self.func_type_combo.get().strip() if hasattr(self, 'func_type_combo') else "Loop"
        if func_type == "Macro":
            items = list(self.combos.keys()) if hasattr(self, 'combos') and self.combos else []
        else:
            items = list(self.loops.keys()) if hasattr(self, 'loops') and self.loops else []
        self.func_assign_combo.configure(values=items)
        self.func_assign_combo.set("")

    # ---- Sort ----
    def _sort_by(self, key):
        """Toggle sort by column key."""
        if self._acc_sort_key == key:
            self._acc_sort_reverse = not self._acc_sort_reverse
        else:
            self._acc_sort_key = key
            self._acc_sort_reverse = False
        self.refresh_multi_acc_list()

    def _update_sort_headers(self):
        """Update header button text with sort arrows."""
        if not hasattr(self, '_sort_header_btns'):
            return
        labels = {"port": "PORT", "tab": "TAB", "name": "NAME", "status": "STATUS", "function": "FUNCTION"}
        for key, btn in self._sort_header_btns.items():
            base = labels[key]
            if self._acc_sort_key == key:
                arrow = "▲" if not self._acc_sort_reverse else "▼"
                btn.configure(text=f"{base} {arrow}", text_color=COLOR["text"])
            else:
                btn.configure(text=base, text_color=COLOR["text_muted"])

    # ---- Delete Selected ----
    def _delete_selected_accounts(self):
        """Delete all checkbox-selected accounts after confirmation."""
        to_delete = [name for name, var in self.dash_checkboxes.items() if var.get()]
        if not to_delete:
            self._acc_styled_info("No accounts selected", "Tick checkboxes to select accounts first")
            return

        # Check if any selected are running
        running_selected = [n for n in to_delete if self._is_running(n)]

        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("380x180")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 380) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"380x180+{x}+{y}")

        result = {"confirmed": False}

        ctk.CTkLabel(
            dialog, text="Delete Accounts",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR["warning"]
        ).pack(pady=(20, 4))

        names_preview = ", ".join(to_delete[:3]) + ("..." if len(to_delete) > 3 else "")
        warn_text = f"Delete {len(to_delete)} account(s)?\n{names_preview}"
        if running_selected:
            warn_text += f"\n⚠ {len(running_selected)} are still running — they will be stopped."
        ctk.CTkLabel(
            dialog, text=warn_text,
            font=ctk.CTkFont(size=11),
            text_color=COLOR["text_muted"], justify="center"
        ).pack(pady=(0, 12))

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))

        def on_delete():
            result["confirmed"] = True
            dialog.destroy()

        ctk.CTkButton(
            btn_row, text="Delete", command=on_delete,
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

        dialog.wait_window()

        if result["confirmed"]:
            # Stop running accounts first
            for name in running_selected:
                self._stop_account(name)

            # Remove from list
            self.multi_accounts = [a for a in self.multi_accounts if a['name'] not in to_delete]
            self.save_multi()
            self.refresh_multi_acc_list()
            self.log_gui(f"[Accounts] Deleted {len(to_delete)} account(s): {names_preview}")

    def _start_account(self, acc_name):
        if self._is_running(acc_name):
            return
        
        acc = None
        for a in self.multi_accounts:
            if a['name'] == acc_name:
                acc = a
                break
        if not acc:
            return
        
        self._set_running(acc_name, True)
        self.state_db.save_account_state(acc_name, status="starting")
        
        t = threading.Thread(target=self._account_worker_thread, args=(acc,), daemon=True)
        self.account_workers[acc_name] = t
        t.start()
        
        self.update_dash_status(acc_name, "Starting...", COLOR["warning"])
        self.log_gui(f"[{acc_name}] Worker started")
    
    def _stop_account(self, acc_name):
        self._set_running(acc_name, False)
        self.state_db.save_account_state(acc_name, status="stopping")
        self.update_dash_status(acc_name, "Stopping...", COLOR["warning"])
        self.log_gui(f"[{acc_name}] Stop signal sent")
        # Use lightweight update instead of full rebuild
        self.after(1500, self._update_row_states)

    def toggle_coordinator(self):
        has_running = any(self._is_running(a['name']) for a in self.multi_accounts)
        if has_running:
            self._batch_stop_all()
        else:
            self._batch_start_all()

    def _refresh_accounts(self):
        """Re-scan all connected Chrome ports and update phone names."""
        def _do_refresh():
            # Collect unique ports from accounts
            ports = set(a.get('port', 9222) for a in self.multi_accounts)
            if not ports:
                self.gui_queue.put(("log", "[Refresh] No accounts to refresh"))
                return
            
            self.gui_queue.put(("log", f"[Refresh] Scanning {len(ports)} port(s): {sorted(ports)}..."))
            updated = 0
            
            for port in sorted(ports):
                try:
                    phone_names = self.chrome_mgr.scan_phone_names(port)
                    if not phone_names:
                        self.gui_queue.put(("log", f"[Refresh] Port {port}: no phone names found"))
                        continue
                    
                    # Update matching accounts
                    for acc in self.multi_accounts:
                        if acc.get('port') != port:
                            continue
                        tab_idx = int(acc.get('target', '0'))
                        if tab_idx in phone_names:
                            old_name = acc['name']
                            new_name = phone_names[tab_idx]
                            if old_name != new_name:
                                acc['name'] = new_name
                                updated += 1
                                self.gui_queue.put(("log", f"[Refresh] {old_name} → {new_name}"))
                except Exception as e:
                    self.gui_queue.put(("log", f"[Refresh] Port {port} error: {e}"))
            
            if updated > 0:
                self.save_multi()
            self.gui_queue.put(("log", f"[Refresh] Done! Updated {updated} account(s)"))
            
            # Rebuild table on main thread
            def _ui():
                self.refresh_multi_acc_list()
            self.after(100, _ui)
        
        threading.Thread(target=_do_refresh, daemon=True).start()

    def _acc_styled_info(self, title, text):
        """Reusable styled info popup for Accounts tab."""
        info = ctk.CTkToplevel(self)
        info.title("Lordbot Control")
        info.geometry("300x130")
        info.resizable(False, False)
        info.configure(fg_color=COLOR["surface"])
        info.transient(self)
        info.grab_set()
        info.after(200, lambda: info.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        info.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 300) // 2
        y = self.winfo_y() + (self.winfo_height() - 130) // 2
        info.geometry(f"300x130+{x}+{y}")
        ctk.CTkLabel(info, text=title, font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["text"]).pack(pady=(20, 4))
        ctk.CTkLabel(info, text=text, font=ctk.CTkFont(size=11), text_color=COLOR["text_muted"]).pack(pady=(0, 12))
        ctk.CTkButton(info, text="OK", command=info.destroy, fg_color=COLOR["primary"], text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"), height=30, corner_radius=6, width=100).pack()

    # ---- Health Monitor (optimized: only check running account ports, 60s interval) ----
    def _start_health_monitor(self):
        self.health_monitor_active = True
        
        def _monitor_loop():
            while self.health_monitor_active:
                try:
                    for acc_name, thread in list(self.account_workers.items()):
                        if self._is_running(acc_name) and not thread.is_alive():
                            db_state = self.state_db.get_account_state(acc_name)
                            db_status = db_state.get("status", "") if db_state else ""
                            last_active = db_state.get("last_active", 0) if db_state else 0
                            
                            if db_status in ("idle", "stopping", "stopped", "finished", "starting", "connection_failed", ""):
                                self._set_running(acc_name, False)
                                continue
                            
                            if time.time() - last_active < 10:
                                continue
                            
                            self.gui_queue.put(("log", f"[Health] Worker {acc_name} died (status={db_status})! Restarting..."))
                            self._set_running(acc_name, False)
                            self.state_db.save_account_state(acc_name, status="crashed")
                            for acc in self.multi_accounts:
                                if acc['name'] == acc_name:
                                    self._set_running(acc_name, True)
                                    t = threading.Thread(target=self._account_worker_thread, args=(acc,), daemon=True)
                                    self.account_workers[acc_name] = t
                                    t.start()
                                    self.gui_queue.put(("log", f"[Health] Worker {acc_name} restarted"))
                                    break
                    
                    # Periodic DB maintenance
                    try:
                        self.state_db.checkpoint()
                    except:
                        pass
                        
                except Exception as e:
                    pass
                
                # 60s interval (was 30s) — saves CPU/network
                for _ in range(120):
                    if not self.health_monitor_active:
                        return
                    time.sleep(0.5)
        
        threading.Thread(target=_monitor_loop, daemon=True).start()
    # ---- Worker Thread (per account) ----
    def _account_worker_thread(self, acc):
        acc_name = acc['name']
        func_value = acc.get('loop', '')
        tab_idx = int(acc.get('target', '0')) if str(acc.get('target', '0')).isdigit() else 0
        port = acc.get('port', 9222)
        
        # Parse function prefix: "loop - name" or "macro - name" (legacy: plain loop name)
        is_macro_mode = False
        if func_value.startswith("macro - "):
            is_macro_mode = True
            func_name = func_value[8:]  # strip "macro - "
        elif func_value.startswith("loop - "):
            func_name = func_value[7:]  # strip "loop - "
        else:
            func_name = func_value  # legacy: treat as loop name
        
        # [THREAD-SAFE] Cache threshold from GUI once at start
        try:
            threshold_val = self.slider.get()
        except:
            threshold_val = 0.54
        
        if is_macro_mode:
            # Macro mode: get macro steps from combos
            macro_steps = self.combos.get(func_name)
            if not macro_steps:
                self.update_dash_status(acc_name, f"Macro '{func_name}' not found", COLOR["danger"])
                self._set_running(acc_name, False)
                return
            graph = {}
            nodes = {}
            edges = []
        else:
            # Loop mode: get graph
            graph = self.loops.get(func_name, {})
            nodes = graph.get("nodes", {})
            edges = graph.get("edges", [])
        
        # Stagger start — batch 5 acc/sec to avoid overloading Chrome CDP
        if tab_idx > 0:
            import random
            batch_delay = tab_idx / 5   # 5 accounts per second (was 50)
            jitter = random.uniform(0, 1.0)  # Larger jitter to spread load
            stagger = batch_delay + jitter
            self.update_dash_status(acc_name, f"Starting in {stagger:.1f}s...", COLOR["text_dim"])
            time.sleep(stagger)
        
        self.update_dash_status(acc_name, "Connecting...", COLOR["warning"])
        self.state_db.save_account_state(acc_name, loop_name=func_value, status="connecting", 
                                          port=port, tab_index=tab_idx)
        
        # [v3.15.6] Raw CDPClient — no Node.js/Playwright needed.
        # Each CDPClient is ~1KB vs ~50-100MB per Playwright instance.
        cdp_client = None
        
        def connect_to_tab():
            nonlocal cdp_client
            
            max_retries = 5
            for attempt in range(max_retries):
                if not self._is_running(acc_name):
                    return False
                try:
                    if cdp_client:
                        try: cdp_client.close()
                        except: pass
                    
                    cdp_client = CDPClient.connect(port=port, tab_index=tab_idx)
                    self.log_gui(f"[{acc_name}] Connected to Port {port}, Tab {tab_idx}")
                    self.state_db.save_account_state(acc_name, status="connected")
                    return True
                        
                except Exception as e:
                    self.log_gui(f"[{acc_name}] Connection attempt {attempt+1}/{max_retries} failed: {str(e)[:60]}")
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1) + random.uniform(0, 1.5)  # Add jitter
                    self.update_dash_status(acc_name, f"Reconnecting in {wait_time:.0f}s... ({attempt+2}/{max_retries})", COLOR["warning"])
                    time.sleep(wait_time)
            
            return False
        
        if not connect_to_tab():
            self.update_dash_status(acc_name, "Connection Failed", COLOR["danger"])
            self.state_db.save_account_state(acc_name, status="connection_failed", 
                                              error_msg="Could not connect after retries")
            self._set_running(acc_name, False)
            if cdp_client:
                try: cdp_client.close()
                except: pass
            return
        
        self.update_dash_status(acc_name, "Connected, running...", COLOR["success"])
        bot_instance = BotAction(cdp_client=cdp_client, debug_visual_var=self.debug_visual_var)

        # Keep-alive: prevent cloud phone (Redfinger) from timing out
        _last_keepalive = time.time()
        _KEEPALIVE_INTERVAL = 270  # Send mouse move every 4.5 minutes

        # ======== MACRO MODE: run macro ONCE then stop ========
        if is_macro_mode:
            self.state_db.save_account_state(acc_name, status="running_macro", current_node=func_name)
            self.update_dash_status(acc_name, f"Macro: {func_name}", "#C084FC")
            self.state_db.log_action(acc_name, "macro_start", func_name)
            try:
                result = run_macro(
                    macro_steps, bot_instance, self.vision,
                    self.tracked_icons, threshold_val=threshold_val,
                    cdp_client=cdp_client,
                    log_fn=lambda msg: self.log_gui(f"[{acc_name}] {msg}"),
                    is_running_fn=lambda: self.account_running.get(acc_name, False),
                    use_direct_vision=True,
                )
                if result:
                    self.state_db.log_action(acc_name, "macro_done", func_name, "OK")
                    self.update_dash_status(acc_name, f"Macro Done ✓", COLOR["success"])
                else:
                    self.state_db.log_action(acc_name, "macro_done", func_name, "FAIL")
                    self.update_dash_status(acc_name, f"Macro Failed", COLOR["danger"])
            except Exception as e:
                self.log_gui(f"[{acc_name}] Macro error: {e}")
                self.state_db.log_action(acc_name, "macro_error", func_name, str(e)[:100])
                self.update_dash_status(acc_name, f"Macro Error", COLOR["danger"])
            
            # Macro done — cleanup
            self._set_running(acc_name, False)
            try:
                if cdp_client: cdp_client.close()
            except: pass
            return

        # ======== LOOP MODE: run loop graph (existing logic) ========
        def get_start_node():
            for nid, n in nodes.items():
                if n["type"] == "Start": return nid
            return None

        def get_next_node(nid, pin_name):
            for e in edges:
                if e["from"] == nid and e["from_pin"] == pin_name:
                    return e["to"]
            return None

        current_node_id = get_start_node()
        restart_count = 0  # Track consecutive restarts to prevent infinite loop
        max_restarts = 10
        _last_node_type = ""  # Track last node type for debugging
        _last_node_name = ""  
        
        self.state_db.save_account_state(acc_name, status="running", current_node=current_node_id or "")
        
        while self._is_running(acc_name):
            # ── Keep-alive: prevent cloud phone idle timeout ──
            if cdp_client and (time.time() - _last_keepalive) >= _KEEPALIVE_INTERVAL:
                try:
                    cdp_client.mouse_move(1, 1)
                except Exception:
                    pass
                _last_keepalive = time.time()

            if not current_node_id or current_node_id not in nodes:
                restart_count += 1
                if restart_count > max_restarts:
                    self.log_gui(f"[{acc_name}] Loop restarted {max_restarts} times consecutively. Stopping.")
                    self.update_dash_status(acc_name, "Loop Error: Too many restarts", COLOR["danger"])
                    break
                # Log exact cause of restart
                if _last_node_type:
                    self.log_gui(f"[{acc_name}] No next node after '{_last_node_type}' ({_last_node_name}). Restarting loop ({restart_count}/{max_restarts})...")
                else:
                    self.log_gui(f"[{acc_name}] Restarting loop ({restart_count}/{max_restarts})...")
                self.update_dash_status(acc_name, f"Restarting Loop ({restart_count}/{max_restarts})", COLOR["warning"])
                time.sleep(3.0)  # Longer delay to avoid rapid restart spam
                current_node_id = get_start_node()
                continue
            
            # Reset restart counter on successful node execution
            restart_count = 0

            n = nodes[current_node_id]
            ntype = n["type"]
            ndata = n.get("data", {})
            next_nid = None
            _last_node_type = ntype
            _last_node_name = ndata.get("image_name", ndata.get("name", current_node_id[:8]))

            self.state_db.save_account_state(acc_name, current_node=current_node_id)

            if ntype == "Start":
                self.update_dash_status(acc_name, "Running...", COLOR["success"])
                next_nid = get_next_node(current_node_id, "out")
                time.sleep(0.5)
                
            elif ntype == "Delay":
                delay_ms = float(ndata.get("time", 1000))
                delay_sec = delay_ms / 1000.0
                self.update_dash_status(acc_name, f"Delay ({delay_ms:.0f}ms)...", COLOR["accent"])
                self.state_db.log_action(acc_name, "delay", f"{delay_ms:.0f}ms")
                steps = int(delay_sec * 10)
                for _ in range(steps):
                    if not self._is_running(acc_name): break
                    time.sleep(0.1)
                next_nid = get_next_node(current_node_id, "out")
                
            elif ntype == "Condition":
                img_name = ndata.get("image_name")
                filepath = self.tracked_icons.get(img_name)
                # Use cached threshold (thread-safe)
                
                # Check if this is a text node (OCR-based detection)
                is_text = self._is_text_node(img_name) if img_name else False
                
                if not is_text and (not filepath or not os.path.exists(filepath)):
                    self.update_dash_status(acc_name, f"Cond Err: Missing Image", COLOR["danger"])
                    next_nid = get_next_node(current_node_id, "false")
                else:
                    self.update_dash_status(acc_name, f"Scanning: {img_name}...", COLOR["warning"])
                    
                    found_res = None
                    for attempt in range(3):
                        frame_bytes = None
                        try:
                            frame_bytes = cdp_client.screenshot(quality=70)
                        except Exception as e:
                            self.log_gui(f"[{acc_name}] Screenshot Error, reconnecting: {str(e)[:40]}")
                            self.state_db.log_action(acc_name, "reconnect", f"Screenshot failed: {e}")
                            if connect_to_tab():
                                bot_instance = BotAction(cdp_client=cdp_client, debug_visual_var=self.debug_visual_var)
                            else:
                                self.update_dash_status(acc_name, "Reconnect Failed", COLOR["danger"])
                                break
                            continue
                        
                        if is_text:
                            search_text = self._get_text_node_search(img_name)
                            res = self.vision.find_text_on_screen(search_text, frame_bytes=frame_bytes)
                        else:
                            from node_features import get_color_detect
                            _use_color = get_color_detect(filepath)
                            res = self.vision.find_template_direct(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes, fast_mode=True, use_color=_use_color)
                        if res:
                            found_res = res
                            break
                        time.sleep(0.5)
                    
                    if found_res:
                        next_nid = get_next_node(current_node_id, "true")
                        self.state_db.log_action(acc_name, "condition", img_name, "TRUE")
                    else:
                        next_nid = get_next_node(current_node_id, "false")
                        self.state_db.log_action(acc_name, "condition", img_name, "FALSE")
                    time.sleep(0.5)
                    
            elif ntype == "Macro":
                mac_name = ndata.get("macro_name")
                if mac_name and mac_name in self.combos:
                    self.update_dash_status(acc_name, f"Macro: {mac_name}", "#C084FC")
                    self.state_db.log_action(acc_name, "macro_start", mac_name)
                    try:
                        result = run_macro(
                            self.combos[mac_name], bot_instance, self.vision,
                            self.tracked_icons, threshold_val=threshold_val,
                            cdp_client=cdp_client,
                            log_fn=lambda msg: self.log_gui(f"[{acc_name}] {msg}"),
                            is_running_fn=lambda: self.account_running.get(acc_name, False),
                            use_direct_vision=True,
                        )
                        if result:
                            self.state_db.log_action(acc_name, "macro_done", mac_name, "OK")
                            next_nid = get_next_node(current_node_id, "true")
                        else:
                            self.state_db.log_action(acc_name, "macro_done", mac_name, "FAIL")
                            next_nid = get_next_node(current_node_id, "false")
                    except Exception as e:
                        self.log_gui(f"[{acc_name}] Macro error: {e}")
                        self.state_db.log_action(acc_name, "macro_error", mac_name, str(e))
                        next_nid = get_next_node(current_node_id, "false")
                        if connect_to_tab():
                            bot_instance = BotAction(cdp_client=cdp_client, debug_visual_var=self.debug_visual_var)
                        else:
                            self.update_dash_status(acc_name, "Reconnect Failed", COLOR["danger"])
                            break
                else:
                    self.update_dash_status(acc_name, f"Macro error: Not found", COLOR["danger"])
                    next_nid = get_next_node(current_node_id, "false")

            elif ntype == "Click":
                img_name = ndata.get("image_name")
                filepath = self.tracked_icons.get(img_name)
                # Use cached threshold (thread-safe)
                
                # Check if this is a text node (OCR-based detection)
                is_text = self._is_text_node(img_name) if img_name else False
                
                if not is_text and (not filepath or not os.path.exists(filepath)):
                    self.update_dash_status(acc_name, f"Click Err: Missing", COLOR["danger"])
                    self.state_db.log_action(acc_name, "click", img_name, "MISSING")
                else:
                    self.update_dash_status(acc_name, f"Click: {img_name}...", COLOR["warning"])
                    frame_bytes = None
                    try:
                        frame_bytes = cdp_client.screenshot(quality=70)
                    except Exception as e:
                        self.log_gui(f"[{acc_name}] Screenshot Error: {str(e)[:40]}")
                        if connect_to_tab():
                            bot_instance = BotAction(cdp_client=cdp_client, debug_visual_var=self.debug_visual_var)
                    
                    if frame_bytes:
                        if is_text:
                            search_text = self._get_text_node_search(img_name)
                            res = self.vision.find_text_on_screen(search_text, frame_bytes=frame_bytes)
                        else:
                            from node_features import get_color_detect
                            _use_color = get_color_detect(filepath)
                            res = self.vision.find_template_direct(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes, fast_mode=True, use_color=_use_color)
                        if res:
                            cx, cy = res[0], res[1]
                            bot_instance.click_at(cx, cy)
                            self.update_dash_status(acc_name, f"Clicked {img_name}", COLOR["success"])
                            self.state_db.log_action(acc_name, "click", img_name, "OK")
                        else:
                            self.update_dash_status(acc_name, f"Click: Not visible", COLOR["warning"])
                            self.state_db.log_action(acc_name, "click", img_name, "NOT_VISIBLE")
                
                next_nid = get_next_node(current_node_id, "out")
                time.sleep(0.3)

            elif ntype == "End":
                self.update_dash_status(acc_name, "Loop complete, restarting...", COLOR["success"])
                self.state_db.log_action(acc_name, "end", "Loop complete")
                self.log_gui(f"[{acc_name}] Reached END → restarting loop")
                time.sleep(1.0)
                current_node_id = get_start_node()
                continue  # Skip setting current_node_id = next_nid

            current_node_id = next_nid

        # ---- Cleanup (set flags FIRST to prevent health monitor restart) ----
        self._set_running(acc_name, False)
        self.state_db.save_account_state(acc_name, status="idle", current_node=current_node_id or "")
        self.update_dash_status(acc_name, "Stopped", COLOR["text_dim"])
        
        # Close CDP connection
        if cdp_client:
            try: cdp_client.close()
            except: pass
        
        self.log_gui(f"[{acc_name}] Worker stopped")
