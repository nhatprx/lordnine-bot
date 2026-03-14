"""Accounts tab mixin — Multi-account coordinator, Chrome management, workers."""
import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import os

from constants import COLOR, FONT, PAD, RADIUS, get_page_by_visual_index
from bot_action import BotAction
from playwright.sync_api import sync_playwright
from chrome_manager import ChromeManager
from state_db import StateDB


class AccountsMixin:
    """Mixin for the Accounts/Coordinator tab. Mixed into BotApp."""

    def setup_multi_tab(self):
        self.tab_multi.grid_columnconfigure(0, weight=1, minsize=280)
        self.tab_multi.grid_columnconfigure(1, weight=3)
        self.tab_multi.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE ======
        self.multi_left_pane = ctk.CTkFrame(self.tab_multi, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.multi_left_pane.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        self.multi_title = ctk.CTkLabel(self.multi_left_pane, text="ACCOUNTS", text_color=COLOR["accent"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=13))
        self.multi_title.pack(pady=(PAD["md"], PAD["sm"]))

        # Chrome Instances Panel
        chrome_frame = ctk.CTkFrame(self.multi_left_pane, fg_color=COLOR["surface2"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        chrome_frame.pack(fill="x", padx=PAD["md"], pady=(PAD["xs"], PAD["xs"]))

        ctk.CTkLabel(chrome_frame, text="CHROME INSTANCES", font=ctk.CTkFont(weight="bold", size=11), text_color=COLOR["accent"]).pack(padx=PAD["md"], pady=(PAD["sm"], 2), anchor="w")

        chrome_btn_row = ctk.CTkFrame(chrome_frame, fg_color="transparent")
        chrome_btn_row.pack(fill="x", padx=PAD["md"], pady=2)

        ctk.CTkButton(chrome_btn_row, text="+ Launch Chrome", command=self._launch_new_chrome, fg_color=COLOR["success"], hover_color=COLOR["success_h"], font=ctk.CTkFont(weight="bold", size=11), corner_radius=6, height=28).pack(side="left", expand=True, fill="x", padx=(0, 2))

        ctk.CTkButton(chrome_btn_row, text="Refresh", command=self._refresh_connection_status, fg_color=COLOR["surface3"], hover_color=COLOR["surface2"], text_color=COLOR["text"], corner_radius=6, height=28, width=70).pack(side="right", padx=(2, 0))

        self.chrome_instances_container = ctk.CTkFrame(chrome_frame, fg_color="transparent")
        self.chrome_instances_container.pack(fill="x", padx=PAD["md"], pady=(2, PAD["sm"]))

        self.conn_status_label = ctk.CTkLabel(self.chrome_instances_container, text="Not checked yet", text_color=COLOR["text_dim"], font=ctk.CTkFont(size=10))
        self.conn_status_label.pack(anchor="w")

        # Account List
        acc_header = ctk.CTkFrame(self.multi_left_pane, fg_color="transparent")
        acc_header.pack(fill="x", padx=PAD["md"], pady=(PAD["xs"], 0))
        ctk.CTkLabel(acc_header, text="Assigned Accounts:", text_color=COLOR["text"], font=ctk.CTkFont(weight="bold", size=12)).pack(side="left")

        self.acc_list_frame = ctk.CTkScrollableFrame(self.multi_left_pane, fg_color=COLOR["bg"], height=150, corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.acc_list_frame.pack(fill="both", expand=True, padx=PAD["md"], pady=PAD["xs"])

        self.multi_actions = ctk.CTkFrame(self.multi_left_pane, fg_color="transparent")
        self.multi_actions.pack(side="bottom", fill="x", pady=PAD["md"], padx=PAD["md"])

        ctk.CTkButton(self.multi_actions, text="+ Add Account", command=self.add_multi_account, fg_color=COLOR["success"], hover_color=COLOR["success_h"], font=ctk.CTkFont(weight="bold"), corner_radius=RADIUS).pack(side="top", fill="x", pady=2)

        # ====== RIGHT PANE (Dashboard) ======
        self.multi_right_pane = ctk.CTkFrame(self.tab_multi, fg_color=COLOR["bg"], corner_radius=0)
        self.multi_right_pane.grid(row=0, column=1, sticky="nsew", padx=(PAD["sm"], PAD["lg"]), pady=PAD["lg"])

        self.dash_top_bar = ctk.CTkFrame(self.multi_right_pane, fg_color="transparent", height=40)
        self.dash_top_bar.pack(fill="x", pady=(0, PAD["sm"]), padx=PAD["xl"])

        self.dash_title = ctk.CTkLabel(self.dash_top_bar, text="COORDINATOR DASHBOARD", font=ctk.CTkFont(family="Segoe UI", weight="bold", size=15), text_color=COLOR["accent"])
        self.dash_title.pack(side="left")

        # Batch controls
        batch_frame = ctk.CTkFrame(self.dash_top_bar, fg_color="transparent")
        batch_frame.pack(side="right")

        ctk.CTkButton(batch_frame, text="Start All", command=self._batch_start_all, fg_color=COLOR["success"], hover_color=COLOR["success_h"], font=ctk.CTkFont(weight="bold", size=11), corner_radius=6, height=30, width=80).pack(side="left", padx=2)

        ctk.CTkButton(batch_frame, text="Stop All", command=self._batch_stop_all, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(weight="bold", size=11), corner_radius=6, height=30, width=80).pack(side="left", padx=2)

        ctk.CTkButton(batch_frame, text="Start Selected", command=self._batch_start_selected, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(size=11), corner_radius=6, height=30, width=100).pack(side="left", padx=2)

        ctk.CTkButton(batch_frame, text="Stop Selected", command=self._batch_stop_selected, fg_color=COLOR["surface2"], hover_color=COLOR["surface3"], text_color=COLOR["text"], font=ctk.CTkFont(size=11), corner_radius=6, height=30, width=100).pack(side="left", padx=2)

        self.dash_grid = ctk.CTkScrollableFrame(self.multi_right_pane, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.dash_grid.pack(fill="both", expand=True, padx=PAD["xl"], pady=PAD["md"])

        self.dash_labels = {}
        self.dash_conn_labels = {}
        self.dash_checkboxes = {}
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

    def _refresh_connection_status(self):
        def _check():
            ports_info = self.chrome_mgr.get_all_ports_info()
            self.gui_queue.put(("conn_status", ports_info))
        
        self.conn_status_label.configure(text="Checking...", text_color=COLOR["warning"])
        threading.Thread(target=_check, daemon=True).start()

    def _render_connection_status(self, ports_info):
        for w in self.chrome_instances_container.winfo_children():
            w.destroy()
        
        if not ports_info:
            ctk.CTkLabel(self.chrome_instances_container, text="No Chrome instances detected", text_color=COLOR["text_dim"], font=ctk.CTkFont(size=10)).pack(anchor="w")
            if hasattr(self, 'dash_conn_labels'):
                for lbl in self.dash_conn_labels.values():
                    lbl.configure(text_color=COLOR["danger"])
            return
        
        total_tabs = sum(p["tab_count"] for p in ports_info)
        summary = ctk.CTkLabel(self.chrome_instances_container, 
                              text=f"{len(ports_info)} Chrome instance(s), {total_tabs} total tabs",
                              text_color=COLOR["success"], font=ctk.CTkFont(size=10, weight="bold"))
        summary.pack(anchor="w", pady=(0, 4))
        
        for pinfo in ports_info:
            row = ctk.CTkFrame(self.chrome_instances_container, fg_color=COLOR["surface2"], corner_radius=4, height=24)
            row.pack(fill="x", pady=1)
            
            proxy_text = f" | {pinfo['proxy']}" if pinfo.get('proxy') else ""
            ctk.CTkLabel(row, text=f"Port {pinfo['port']} — {pinfo['tab_count']} tabs{proxy_text}", 
                        font=ctk.CTkFont(size=10), text_color=COLOR["text"]).pack(side="left", padx=6)
            
            ctk.CTkButton(row, text="X", width=18, height=18, fg_color="transparent", 
                         text_color=COLOR["danger"], hover_color=COLOR["surface"],
                         font=ctk.CTkFont(size=10, weight="bold"),
                         command=lambda p=pinfo['port']: self._kill_chrome_port(p)).pack(side="right", padx=2)
        
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
            return messagebox.showwarning("Warning", "You need to create Tracking Nodes and Loops first!")
            
        top = ctk.CTkToplevel(self)
        top.title("Add Account")
        top.geometry("400x420")
        top.attributes("-topmost", True)

        ctk.CTkLabel(top, text="Display Name:", font=ctk.CTkFont(weight="bold")).pack(pady=(10,0), padx=20, anchor="w")
        ent_name = ctk.CTkEntry(top, width=300)
        ent_name.pack(pady=(0,8), padx=20)

        row1 = ctk.CTkFrame(top, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=(0, 8))
        
        ctk.CTkLabel(row1, text="Chrome Port:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ent_port = ctk.CTkEntry(row1, width=70, placeholder_text="9222")
        ent_port.insert(0, "9222")
        ent_port.pack(side="left", padx=(5, 15))
        
        ctk.CTkLabel(row1, text="Tab Index:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ent_target = ctk.CTkEntry(row1, width=50, placeholder_text="0")
        ent_target.pack(side="left", padx=5)

        ctk.CTkLabel(top, text="Assigned Loop:", font=ctk.CTkFont(weight="bold")).pack(padx=20, anchor="w")
        combo_loop = ctk.CTkComboBox(top, values=list(self.loops.keys()), width=300)
        combo_loop.pack(pady=(0,8), padx=20)

        ctk.CTkLabel(top, text="Proxy (optional):", font=ctk.CTkFont(weight="bold")).pack(pady=(8, 0), padx=20, anchor="w")
        ent_proxy = ctk.CTkEntry(top, width=300, placeholder_text="socks5://1.2.3.4:1080")
        ent_proxy.pack(pady=(0,8), padx=20)
        
        ctk.CTkLabel(top, text="Group:", font=ctk.CTkFont(weight="bold")).pack(padx=20, anchor="w")
        ent_group = ctk.CTkEntry(top, width=300, placeholder_text="default")
        ent_group.insert(0, "default")
        ent_group.pack(pady=(0,8), padx=20)

        def on_save():
            name = ent_name.get().strip()
            target = ent_target.get().strip()
            port_str = ent_port.get().strip()
            
            if not name or not target:
                return messagebox.showerror("Error", "Name and Tab Index are required!")
            if not target.isdigit():
                return messagebox.showerror("Error", "Tab Index must be a number!")
            if not port_str.isdigit():
                return messagebox.showerror("Error", "Port must be a number!")
                
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

        ctk.CTkButton(top, text="Save Account", command=on_save, fg_color=COLOR["success"], hover_color=COLOR["success_h"], font=ctk.CTkFont(weight="bold"), corner_radius=6).pack(pady=15, fill="x", padx=20)

    def refresh_multi_acc_list(self):
        for widget in self.acc_list_frame.winfo_children():
            widget.destroy()
        for widget in self.dash_grid.winfo_children():
            widget.destroy()
        self.dash_labels.clear()
        self.dash_conn_labels = {}
        self.dash_checkboxes = {}

        for idx, acc in enumerate(self.multi_accounts):
            name = acc['name']
            port = acc.get('port', 9222)
            
            # ---- Left panel list item ----
            row = ctk.CTkFrame(self.acc_list_frame, fg_color=COLOR["surface2"], corner_radius=4)
            row.pack(fill="x", pady=2)
            
            enabled = acc.get("enabled", True)
            color = COLOR["success"] if enabled else COLOR["text_dim"]
            ctk.CTkLabel(row, text=f"{name} (P{port}:T{acc.get('target', '?')})", 
                        text_color=color, font=ctk.CTkFont(size=11)).pack(side="left", padx=5)
            
            def del_acc(i=idx):
                self.multi_accounts.pop(i)
                self.save_multi()
                self.refresh_multi_acc_list()
                
            ctk.CTkButton(row, text="X", width=20, height=20, fg_color="transparent", 
                         text_color=COLOR["danger"], hover_color=COLOR["surface"], 
                         command=del_acc, corner_radius=4).pack(side="right", padx=2)

            # ---- Right panel Dashboard Card ----
            card = ctk.CTkFrame(self.dash_grid, fg_color=COLOR["surface2"], border_width=1, border_color="#3D5A80", corner_radius=8)
            card.pack(fill="x", pady=3, padx=5)
            
            card_top = ctk.CTkFrame(card, fg_color="transparent")
            card_top.pack(fill="x", padx=8, pady=(6, 2))
            
            chk_var = ctk.BooleanVar(value=False)
            self.dash_checkboxes[name] = chk_var
            ctk.CTkCheckBox(card_top, text="", variable=chk_var, width=20, height=20).pack(side="left", padx=(0, 4))
            
            lbl_conn = ctk.CTkLabel(card_top, text=f"P{port}:T{acc.get('target', '?')}", 
                                   font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR["text_dim"], width=60)
            lbl_conn.pack(side="left", padx=(0, 4))
            self.dash_conn_labels[name] = lbl_conn
            
            ctk.CTkLabel(card_top, text=name, font=ctk.CTkFont(weight="bold", size=13), 
                        text_color=COLOR["text"], anchor="w").pack(side="left", padx=(0, 8))
            
            lbl_status = ctk.CTkLabel(card_top, text="Idle", text_color=COLOR["text_dim"], 
                                     font=ctk.CTkFont(size=11), anchor="w")
            lbl_status.pack(side="left", fill="x", expand=True)
            self.dash_labels[name] = lbl_status
            
            is_running = self.account_running.get(name, False)
            btn_text = "Stop" if is_running else "Start"
            btn_color = COLOR["danger"] if is_running else COLOR["success"]
            
            def toggle_single(n=name):
                if self.account_running.get(n, False):
                    self._stop_account(n)
                else:
                    self._start_account(n)
            
            ctk.CTkButton(card_top, text=btn_text, width=50, height=24, fg_color=btn_color, 
                         corner_radius=4, font=ctk.CTkFont(size=11, weight="bold"),
                         command=toggle_single).pack(side="right", padx=2)
            
            info_parts = [f"Loop: {acc.get('loop', '?')}",
                         f"Group: {acc.get('group', 'default')}"]
            if acc.get('proxy'):
                info_parts.append(f"Proxy: {acc['proxy'][:25]}")
            
            ctk.CTkLabel(card, text=" | ".join(info_parts), font=ctk.CTkFont(size=10), 
                        text_color=COLOR["text_dim"]).pack(padx=12, pady=(0, 6), anchor="w")

    def update_dash_status(self, acc_name, status, color="white"):
        self.gui_queue.put(("dash_status", (acc_name, status, color)))
        
    def _internal_update_dash_status(self, acc_name, status, color):
        if acc_name in self.dash_labels:
            self.dash_labels[acc_name].configure(text=f"{status}", text_color=color)

    # ---- Batch Operations ----
    def _batch_start_all(self):
        for acc in self.multi_accounts:
            if acc.get("enabled", True):
                self._start_account(acc['name'])
    
    def _batch_stop_all(self):
        for acc in self.multi_accounts:
            self._stop_account(acc['name'])
    
    def _batch_start_selected(self):
        for acc in self.multi_accounts:
            name = acc['name']
            if self.dash_checkboxes.get(name) and self.dash_checkboxes[name].get():
                self._start_account(name)
    
    def _batch_stop_selected(self):
        for acc in self.multi_accounts:
            name = acc['name']
            if self.dash_checkboxes.get(name) and self.dash_checkboxes[name].get():
                self._stop_account(name)

    def _start_account(self, acc_name):
        if self.account_running.get(acc_name, False):
            return
        
        acc = None
        for a in self.multi_accounts:
            if a['name'] == acc_name:
                acc = a
                break
        if not acc:
            return
        
        self.account_running[acc_name] = True
        self.state_db.save_account_state(acc_name, status="starting")
        
        t = threading.Thread(target=self._account_worker_thread, args=(acc,), daemon=True)
        self.account_workers[acc_name] = t
        t.start()
        
        self.update_dash_status(acc_name, "Starting...", COLOR["warning"])
        self.log_gui(f"[{acc_name}] Worker started")
        self.refresh_multi_acc_list()
    
    def _stop_account(self, acc_name):
        self.account_running[acc_name] = False
        self.state_db.save_account_state(acc_name, status="stopping")
        self.update_dash_status(acc_name, "Stopping...", COLOR["warning"])
        self.log_gui(f"[{acc_name}] Stop signal sent")
        self.after(1500, self.refresh_multi_acc_list)

    def toggle_coordinator(self):
        has_running = any(self.account_running.get(a['name'], False) for a in self.multi_accounts)
        if has_running:
            self._batch_stop_all()
        else:
            self._batch_start_all()

    # ---- Health Monitor ----
    def _start_health_monitor(self):
        self.health_monitor_active = True
        
        def _monitor_loop():
            while self.health_monitor_active:
                try:
                    active_ports = self.chrome_mgr.get_active_ports()
                    
                    for acc_name, thread in list(self.account_workers.items()):
                        if self.account_running.get(acc_name, False) and not thread.is_alive():
                            self.gui_queue.put(("log", f"[Health] Worker {acc_name} died! Restarting..."))
                            self.account_running[acc_name] = False
                            self.state_db.save_account_state(acc_name, status="crashed")
                            for acc in self.multi_accounts:
                                if acc['name'] == acc_name:
                                    self.account_running[acc_name] = True
                                    t = threading.Thread(target=self._account_worker_thread, args=(acc,), daemon=True)
                                    self.account_workers[acc_name] = t
                                    t.start()
                                    self.gui_queue.put(("log", f"[Health] Worker {acc_name} restarted"))
                                    break
                except Exception as e:
                    pass
                
                for _ in range(60):
                    if not self.health_monitor_active:
                        return
                    time.sleep(0.5)
        
        threading.Thread(target=_monitor_loop, daemon=True).start()
    # ---- Worker Thread (per account) ----
    def _account_worker_thread(self, acc):
        acc_name = acc['name']
        loop_name = acc['loop']
        tab_idx = int(acc.get('target', '0')) if str(acc.get('target', '0')).isdigit() else 0
        port = acc.get('port', 9222)
        # NOTE: threshold is read fresh each iteration inside the loop, not frozen here
        
        graph = self.loops.get(loop_name, {})
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        
        self.update_dash_status(acc_name, "Connecting...", COLOR["warning"])
        self.state_db.save_account_state(acc_name, loop_name=loop_name, status="connecting", 
                                          port=port, tab_index=tab_idx)
        
        browser = None
        page = None
        pw = None
        
        def connect_to_tab():
            nonlocal browser, page, pw
            
            max_retries = 5
            for attempt in range(max_retries):
                if not self.account_running.get(acc_name, False):
                    return False
                try:
                    if pw is None:
                        pw = sync_playwright().start()
                    if browser is not None:
                        try: browser.close()
                        except: pass
                    
                    browser = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
                    context = browser.contexts[0]
                    p, info = get_page_by_visual_index(context, tab_idx, port=port)
                    
                    if p:
                        page = p
                        self.log_gui(f"[{acc_name}] Connected to Port {port}, Tab {tab_idx}")
                        self.state_db.save_account_state(acc_name, status="connected")
                        return True
                    else:
                        self.log_gui(f"[{acc_name}] Tab {tab_idx} not found on port {port}")
                        
                except Exception as e:
                    self.log_gui(f"[{acc_name}] Connection attempt {attempt+1}/{max_retries} failed: {str(e)[:60]}")
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    self.update_dash_status(acc_name, f"Reconnecting in {wait_time}s... ({attempt+2}/{max_retries})", COLOR["warning"])
                    time.sleep(wait_time)
            
            return False
        
        if not connect_to_tab():
            self.update_dash_status(acc_name, "Connection Failed", COLOR["danger"])
            self.state_db.save_account_state(acc_name, status="connection_failed", 
                                              error_msg="Could not connect after retries")
            self.account_running[acc_name] = False
            if pw: 
                try: pw.stop()
                except: pass
            return
        
        self.update_dash_status(acc_name, "Connected, running...", COLOR["success"])
        bot_instance = BotAction(page=page, debug_visual_var=self.debug_visual_var)

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
        
        self.state_db.save_account_state(acc_name, status="running", current_node=current_node_id or "")
        
        while self.account_running.get(acc_name, False):
            if not current_node_id or current_node_id not in nodes:
                self.update_dash_status(acc_name, "Restarting Loop", COLOR["warning"])
                time.sleep(1.0)
                current_node_id = get_start_node()
                continue

            n = nodes[current_node_id]
            ntype = n["type"]
            ndata = n.get("data", {})
            next_nid = None

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
                    if not self.account_running.get(acc_name, False): break
                    time.sleep(0.1)
                next_nid = get_next_node(current_node_id, "out")
                
            elif ntype == "Condition":
                img_name = ndata.get("image_name")
                filepath = self.tracked_icons.get(img_name)
                threshold_val = self.slider.get()  # Fresh threshold each iteration
                
                if not filepath or not os.path.exists(filepath):
                    self.update_dash_status(acc_name, f"Cond Err: Missing Image", COLOR["danger"])
                    next_nid = get_next_node(current_node_id, "false")
                else:
                    self.update_dash_status(acc_name, f"Scanning: {img_name}...", COLOR["warning"])
                    
                    found_res = None
                    for attempt in range(3):
                        frame_bytes = None
                        try:
                            frame_bytes = page.screenshot()
                        except Exception as e:
                            self.log_gui(f"[{acc_name}] Screenshot Error, reconnecting: {str(e)[:40]}")
                            self.state_db.log_action(acc_name, "reconnect", f"Screenshot failed: {e}")
                            if connect_to_tab():
                                bot_instance = BotAction(page=page, debug_visual_var=self.debug_visual_var)
                            else:
                                self.update_dash_status(acc_name, "Reconnect Failed", COLOR["danger"])
                                break
                            continue
                        
                        res = self.vision.find_template_direct(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
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
                        result = self._internal_macro_runner(self.combos[mac_name], bot_instance, acc_name=acc_name, page=page, use_direct_vision=True)
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
                            bot_instance = BotAction(page=page, debug_visual_var=self.debug_visual_var)
                        else:
                            self.update_dash_status(acc_name, "Reconnect Failed", COLOR["danger"])
                            break
                else:
                    self.update_dash_status(acc_name, f"Macro error: Not found", COLOR["danger"])
                    next_nid = get_next_node(current_node_id, "false")

            current_node_id = next_nid

        # ---- Cleanup ----
        self.update_dash_status(acc_name, "Stopped", COLOR["text_dim"])
        self.state_db.save_account_state(acc_name, status="idle", current_node=current_node_id or "")
        self.account_running[acc_name] = False
        
        if browser:
            try: browser.close()
            except: pass
        if pw:
            try: pw.stop()
            except: pass
        
        self.log_gui(f"[{acc_name}] Worker stopped")
