"""Loops/Automation tab mixin — Flowchart-based automation engine."""
import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import os
import random

from constants import COLOR, FONT, PAD, RADIUS, get_page_by_visual_index
from bot_action import BotAction
from playwright.sync_api import sync_playwright
from flowchart_ui import FlowchartUI


class LoopsMixin:
    """Mixin for the Automation/Loops tab. Mixed into BotApp."""

    def setup_loop_tab(self):
        self.current_loop_name = None
        self.loop_buttons = {}
        self.loop_checkbox_vars = {}

        self.tab_loop.grid_columnconfigure(0, weight=1, minsize=240)
        self.tab_loop.grid_columnconfigure(1, weight=3)
        self.tab_loop.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE ======
        self.loop_left_pane = ctk.CTkFrame(self.tab_loop, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.loop_left_pane.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        ctk.CTkLabel(self.loop_left_pane, text="LOOPS", text_color=COLOR["accent"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=13)).pack(padx=PAD["md"], pady=(PAD["md"], PAD["sm"]), anchor="w")

        loop_actions_top = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent")
        loop_actions_top.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        self.add_loop_btn = ctk.CTkButton(loop_actions_top, text="+ Create", command=self.add_new_loop, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11), corner_radius=RADIUS, height=30)
        self.add_loop_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.del_selected_loop_btn = ctk.CTkButton(loop_actions_top, text="Delete Selected", command=self.delete_selected_loops, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11), corner_radius=RADIUS, height=30)
        self.del_selected_loop_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))

        self.loop_search_var = ctk.StringVar()
        self.loop_search_var.trace_add("write", lambda *a: self.refresh_loop_list())
        ctk.CTkEntry(self.loop_left_pane, placeholder_text="Search loops...", textvariable=self.loop_search_var, fg_color=COLOR["bg"], corner_radius=RADIUS, height=32, border_width=1, border_color=COLOR["border"]).pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        self.loop_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent")
        sa_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["xs"]))
        ctk.CTkCheckBox(sa_row, text="Select All", variable=self.loop_select_all_var, command=self._toggle_select_all_loops, width=20, height=20, font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left")

        self.loop_btn_container = ctk.CTkScrollableFrame(self.loop_left_pane, fg_color="transparent")
        self.loop_btn_container.pack(fill="both", expand=True, padx=PAD["xs"], pady=(0, PAD["sm"]))

        # ====== RIGHT PANE (Flowchart) ======
        self.loop_right_pane = ctk.CTkFrame(self.tab_loop, fg_color=COLOR["bg"], corner_radius=0)
        self.loop_right_pane.grid(row=0, column=1, sticky="nsew", padx=(PAD["sm"], PAD["lg"]), pady=PAD["lg"])

        self.loop_top_bar = ctk.CTkFrame(self.loop_right_pane, fg_color="transparent", height=40)
        self.loop_top_bar.pack(fill="x", pady=(0, PAD["sm"]), padx=PAD["xl"])

        self.loop_name_label = ctk.CTkLabel(self.loop_top_bar, text="[No Loop Selected]", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), text_color=COLOR["text"])
        self.loop_name_label.pack(side="left")

        tab_idx_frame = ctk.CTkFrame(self.loop_top_bar, fg_color="transparent")
        tab_idx_frame.pack(side="left", padx=PAD["xl"])
        ctk.CTkLabel(tab_idx_frame, text="Port:", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left", padx=2)
        self.loop_chrome_port = ctk.CTkEntry(tab_idx_frame, width=50, placeholder_text="9222", fg_color=COLOR["surface"], corner_radius=6, height=28, border_width=1, border_color=COLOR["border"])
        self.loop_chrome_port.insert(0, "9222")
        self.loop_chrome_port.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(tab_idx_frame, text="Tab:", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left", padx=2)
        self.loop_tab_index = ctk.CTkEntry(tab_idx_frame, width=30, placeholder_text="0", fg_color=COLOR["surface"], corner_radius=6, height=28, border_width=1, border_color=COLOR["border"])
        self.loop_tab_index.insert(0, "0")
        self.loop_tab_index.pack(side="left")

        self.play_loop_btn = ctk.CTkButton(self.loop_top_bar, text="Start Auto Loop", command=self.toggle_loop_engine, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], state="disabled", font=ctk.CTkFont(weight="bold"), width=150, corner_radius=RADIUS)
        self.play_loop_btn.pack(side="right")

        # Running Status Bar
        self.loop_status_bar = ctk.CTkFrame(self.loop_right_pane, fg_color=COLOR["surface2"], height=28, corner_radius=6, border_width=1, border_color=COLOR["border"])
        self.loop_status_bar.pack(fill="x", padx=PAD["xl"], pady=(0, PAD["xs"]))
        self.loop_status_bar.pack_propagate(False)
        self.loop_status_icon = ctk.CTkLabel(self.loop_status_bar, text="●", text_color=COLOR["text_dim"], font=ctk.CTkFont(size=10), width=16)
        self.loop_status_icon.pack(side="left", padx=(PAD["sm"], 2))
        self.loop_status_label = ctk.CTkLabel(self.loop_status_bar, text="Idle — No loop running", text_color=COLOR["text_dim"], font=ctk.CTkFont(family="Consolas", size=11))
        self.loop_status_label.pack(side="left", fill="x", expand=True)

        # Flowchart Toolbar
        self.flowchart_toolbar = ctk.CTkFrame(self.loop_right_pane, fg_color=COLOR["surface2"], height=40, corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.flowchart_toolbar.pack(fill="x", padx=PAD["xl"], pady=PAD["xs"])

        ctk.CTkButton(self.flowchart_toolbar, text="+ Start", width=80, fg_color=COLOR["success"], hover_color=COLOR["success_h"], command=lambda: self.flowchart_add_node("Start"), corner_radius=6).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ Macro", width=80, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], command=lambda: self.flowchart_add_node("Macro"), corner_radius=6).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ If Image", width=80, fg_color=COLOR["warning"], hover_color=COLOR["warning_h"], text_color=COLOR["text_dark"], command=lambda: self.flowchart_add_node("Condition"), corner_radius=6).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ Delay", width=80, fg_color=COLOR["purple"], hover_color=COLOR["purple_h"], command=lambda: self.flowchart_add_node("Delay"), corner_radius=6).pack(side="left", padx=5, pady=5)

        ctk.CTkLabel(self.flowchart_toolbar, text="Right-click to edit. Drag pins to connect.", text_color=COLOR["text_dim"], font=ctk.CTkFont(size=11)).pack(side="right", padx=PAD["sm"])

        # Flowchart Canvas
        def get_macros_cb():
            return list(self.combos.keys())
        def get_images_cb():
            return list(self.tracked_icons.keys())
        def on_change_cb():
            if self.current_loop_name:
                self.loops[self.current_loop_name] = self.flowchart.export_graph()
                self.save_loops()

        self.flowchart = FlowchartUI(self.loop_right_pane, get_macros_cb=get_macros_cb, get_images_cb=get_images_cb, on_change_cb=on_change_cb)
        self.flowchart.pack(fill="both", expand=True, padx=PAD["xl"], pady=(0, PAD["xl"]))

        self.refresh_loop_list()

    def flowchart_add_node(self, ntype):
        if not self.current_loop_name:
            messagebox.showwarning("Warning", "Select or create a Loop first!")
            return
        self.flowchart.add_node(ntype)

    def refresh_loop_list(self):
        for widget in self.loop_btn_container.winfo_children():
            widget.destroy()
        self.loop_buttons.clear()
        self.loop_checkbox_vars.clear()

        search = self.loop_search_var.get().strip().lower() if hasattr(self, 'loop_search_var') else ""
        for lname in self.loops.keys():
            if search and search not in lname.lower():
                continue
            frame = ctk.CTkFrame(self.loop_btn_container, fg_color="transparent")
            frame.pack(fill="x", pady=2, padx=5)
            
            var = ctk.BooleanVar(value=False)
            self.loop_checkbox_vars[lname] = var
            chk = ctk.CTkCheckBox(frame, text="", variable=var, width=20, height=20)
            chk.pack(side="left", padx=(0, 5))
            
            btn = ctk.CTkButton(frame, text=lname, anchor="w", fg_color="transparent", hover_color="#2C3E50", text_color="white", command=lambda n=lname: self.on_select_loop(n))
            btn.pack(side="left", fill="x", expand=True)
            self.loop_buttons[lname] = btn

    def _toggle_select_all_loops(self):
        val = self.loop_select_all_var.get()
        for v in self.loop_checkbox_vars.values():
            v.set(val)

    def on_select_loop(self, name):
        self.current_loop_name = name
        for n, btn in self.loop_buttons.items():
            if n == name:
                btn.configure(fg_color="#D35400")
            else:
                btn.configure(fg_color="transparent")

        self.loop_name_label.configure(text=name)
        self.play_loop_btn.configure(state="normal")
        
        # Load graph
        loop_data = self.loops.get(name)
        if isinstance(loop_data, list):
            # Migrate legacy list to graph
            graph = {"nodes": {}, "edges": []}
            import uuid
            prev_id = None
            start_id = str(uuid.uuid4())[:8]
            graph["nodes"][start_id] = {"id": start_id, "type": "Start", "x": 50, "y": 50, "w": 140, "h": 60, "data": {"title": "Start"}}
            prev_id = start_id
            
            for i, mac in enumerate(loop_data):
                mid = str(uuid.uuid4())[:8]
                graph["nodes"][mid] = {"id": mid, "type": "Macro", "x": 50, "y": 50 + (i+1)*80, "w": 140, "h": 60, "data": {"macro_name": mac}}
                graph["edges"].append({"from": prev_id, "from_pin": "out", "to": mid, "to_pin": "in"})
                prev_id = mid
                
            self.loops[name] = graph
            self.save_loops()
            loop_data = graph
            
        self.flowchart.load_graph(loop_data)

    def add_new_loop(self):
        dialog = ctk.CTkInputDialog(text="New Loop name (e.g: Bot Farm):", title="New Loop")
        name = dialog.get_input()
        if name:
            name = name.strip()
            if not name: return
            if name in self.loops:
                messagebox.showerror("Error", "Loop name already exists!")
                return
            
            import uuid
            start_id = str(uuid.uuid4())[:8]
            self.loops[name] = {
                "nodes": {start_id: {"id": start_id, "type": "Start", "x": 300, "y": 50, "w": 140, "h": 60, "data": {"title": "Start"}}},
                "edges": []
            }
            self.save_loops()
            self.refresh_loop_list()
            self.on_select_loop(name)

    def delete_selected_loops(self):
        to_delete = [lname for lname, var in self.loop_checkbox_vars.items() if var.get()]
        if not to_delete:
            messagebox.showinfo("Info", "Please select Loops to delete!")
            return
            
        if messagebox.askyesno("Confirm", f"Delete {len(to_delete)} selected Loops?"):
            for lname in to_delete:
                if lname in self.loops:
                    del self.loops[lname]
                if self.current_loop_name == lname:
                    self.current_loop_name = None
                    self.loop_name_label.configure(text="[Deleted]")
                    self.play_loop_btn.configure(state="disabled")
                    self.flowchart.delete("all")
                    
            self.save_loops()
            self.refresh_loop_list()
            self.log_gui(f"[System] Deleted {len(to_delete)} Loops successfully.")

    def delete_current_loop(self):
        pass

    def _set_loop_status(self, text, color=None):
        """Thread-safe update of the loop status bar."""
        if color is None:
            color = COLOR["accent"]
        self.gui_queue.put(lambda: self.loop_status_label.configure(text=text))
        self.gui_queue.put(lambda: self.loop_status_icon.configure(text_color=color))

    def _highlight_node(self, node_id):
        """Thread-safe highlight of a node on the flowchart."""
        self.gui_queue.put(lambda: self.flowchart.highlight_node(node_id))

    def _clear_highlight(self):
        """Thread-safe clear of the node highlight."""
        self.gui_queue.put(lambda: self.flowchart.clear_highlight())

    def toggle_loop_engine(self):
        if not self.is_looping:
            if not self.current_loop_name: return
            graph = self.loops.get(self.current_loop_name, {})
            nodes = graph.get("nodes", {})
            if not nodes:
                return messagebox.showwarning("Empty", "Flowchart is empty!")
                
            start_node = None
            for nid, n in nodes.items():
                if n["type"] == "Start":
                    start_node = nid
                    break
                    
            if not start_node:
                return messagebox.showerror("Error", "Flowchart does not have a Start node!")
                
            port_str = self.loop_chrome_port.get().strip()
            port = int(port_str) if port_str.isdigit() else 9222
            tab_id_str = self.loop_tab_index.get().strip()
            tab_id = int(tab_id_str) if tab_id_str.isdigit() else 0
            
            self.is_looping = True
            self.play_loop_btn.configure(text="STOP LOOP AUTO", fg_color="#E74C3C", hover_color="#C0392B")
            self._set_loop_status(f"Starting [{self.current_loop_name}] on Port {port} Tab {tab_id}...", COLOR["warning"])
            self.log_gui(f"*** FLOWCHART AUTO: [{self.current_loop_name}] Port {port}, Tab {tab_id} ***")
            
            threading.Thread(target=self._loop_engine_worker, args=(graph, start_node, tab_id, port), daemon=True).start()
        else:
            self.is_looping = False
            self.play_loop_btn.configure(text="START AUTO LOOP", fg_color="#C0392B", hover_color="#A93226")
            self._set_loop_status("Idle — Loop stopped", COLOR["text_dim"])
            self._clear_highlight()
            self.log_gui("*** AUTO LOOP STOPPED ***")

    def _loop_engine_worker(self, graph, start_node, tab_id=0, port=9222):
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        
        current_node_id = start_node
        
        def get_next_node(nid, pin_name):
            for e in edges:
                if e["from"] == nid and e["from_pin"] == pin_name:
                    return e["to"]
            return None
            
        playwright_ctx = sync_playwright().start()
        browser = None
        page = None
        
        if tab_id is not None:
             try:
                 self.log_gui(f"[Loop Engine] Connecting to Port {port}, Tab {tab_id}...")
                 browser = playwright_ctx.chromium.connect_over_cdp(f"http://localhost:{port}")
                 context = browser.contexts[0]
                 page, info = get_page_by_visual_index(context, tab_id, port=port)
                 if page:
                     if isinstance(info, list):
                         for idx_t, title_t, url_t in info:
                             self.log_gui(f"[Loop Engine]   Tab {idx_t}: {title_t}")
                     self.log_gui(f"[Loop Engine] Hooked to Tab {tab_id}")
                 else:
                     self.log_gui(f"[Loop Engine] {info}")
                     playwright_ctx.stop()
                     return
             except Exception as e:
                 self.log_gui(f"[Loop Engine] Connection fail: {e}")
                 playwright_ctx.stop()
                 return
                 
        bot_instance = BotAction(page=page, debug_visual_var=self.debug_visual_var)
        
        while self.is_looping:
            if not current_node_id or current_node_id not in nodes:
                self.log_gui(f"[FLOWCHART] End of path reached. Restarting from Start Node in 1s...")
                time.sleep(1.0)
                current_node_id = start_node
                continue
                
            n = nodes[current_node_id]
            ntype = n["type"]
            ndata = n.get("data", {})
            threshold_val = self.slider.get()
            
            # Highlight the active node on the flowchart
            self._highlight_node(current_node_id)
            
            if ntype == "Start":
                self._set_loop_status("START → Following entry path", COLOR["success"])
                self.log_gui(f"[FLOWCHART] ---> START")
                current_node_id = get_next_node(current_node_id, "out")
                time.sleep(0.5)
                
            elif ntype == "Macro":
                mac_name = ndata.get("macro_name")
                if mac_name and mac_name in self.combos:
                    self._set_loop_status(f"Running Macro: {mac_name}", COLOR["accent"])
                    self.log_gui(f"[FLOWCHART] Executing Macro: {mac_name}")
                    macro_data = self.combos[mac_name]
                    result = self._internal_macro_runner(macro_data, bot_instance, page=page)
                    if result:
                        self._set_loop_status(f"Macro [{mac_name}] → OK", COLOR["success"])
                        self.log_gui(f"[FLOWCHART] -> Macro OK. Following success path.")
                        current_node_id = get_next_node(current_node_id, "true")
                    else:
                        self._set_loop_status(f"Macro [{mac_name}] → FAILED", COLOR["danger"])
                        self.log_gui(f"[FLOWCHART] -> Macro FAILED. Following failure path.")
                        current_node_id = get_next_node(current_node_id, "false")
                else:
                    self._set_loop_status(f"Macro [{mac_name}] → INVALID", COLOR["danger"])
                    self.log_gui(f"[FLOWCHART] Warning: Invalid Macro '{mac_name}'. Following failure path.")
                    current_node_id = get_next_node(current_node_id, "false")
                
            elif ntype == "Delay":
                delay_ms = float(ndata.get("time", 1000))
                delay_sec = delay_ms / 1000.0
                self._set_loop_status(f"Waiting {delay_ms:.0f}ms...", COLOR["warning"])
                self.log_gui(f"[FLOWCHART] Waiting {delay_ms:.0f}ms ({delay_sec:.1f}s)...")
                
                steps = int(delay_sec * 10)
                for i in range(steps):
                    if not self.is_looping: break
                    remaining_ms = delay_ms - (i * 100)
                    if i % 10 == 0:  # Update status every second
                        self._set_loop_status(f"Delay: {remaining_ms:.0f}ms remaining", COLOR["warning"])
                    time.sleep(0.1)
                
                current_node_id = get_next_node(current_node_id, "out")
                
            elif ntype == "Condition":
                img_name = ndata.get("image_name")
                filepath = self.tracked_icons.get(img_name)
                
                if not filepath or not os.path.exists(filepath):
                    self._set_loop_status(f"Condition [{img_name}] → NOT FOUND", COLOR["danger"])
                    self.log_gui(f"[FLOWCHART] Image condition '{img_name}' not found. Defaulting to False.")
                    current_node_id = get_next_node(current_node_id, "false")
                else:
                    self._set_loop_status(f"Checking: {img_name}...", COLOR["warning"])
                    self.log_gui(f"[FLOWCHART] Checking: Is '{img_name}' on screen?")
                    
                    found_res = None
                    for attempt in range(3):
                        frame_bytes = None
                        if page:
                            try: frame_bytes = page.screenshot()
                            except: pass
                        res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                        if res:
                            found_res = res
                            break
                        time.sleep(0.5)
                    
                    if found_res:
                        self._set_loop_status(f"Condition [{img_name}] → TRUE", COLOR["success"])
                        self.log_gui(f"[FLOWCHART] -> TRUE (Found '{img_name}')")
                        current_node_id = get_next_node(current_node_id, "true")
                    else:
                        self._set_loop_status(f"Condition [{img_name}] → FALSE", COLOR["danger"])
                        self.log_gui(f"[FLOWCHART] -> FALSE (Not Found)")
                        current_node_id = get_next_node(current_node_id, "false")
                time.sleep(0.5)
                
        self._clear_highlight()
        self._set_loop_status("Idle — Loop ended", COLOR["text_dim"])
        if browser: browser.close()
        playwright_ctx.stop()

    def _internal_macro_runner(self, macro_data, bot_instance, acc_name=None, page=None, use_direct_vision=False):
        """Core macro runner used by loop engine and coordinator workers."""
        steps = macro_data.get("steps", [])
        threshold_val = self.slider.get()
        
        # Route vision calls: direct (multi-account) or pooled (single-tab)
        def _find(path, threshold, debug=False, frame_bytes=None):
            if use_direct_vision:
                return self.vision.find_template_direct(path, threshold=threshold, debug=debug, frame_bytes=frame_bytes)
            return self.vision.find_template_on_screen(path, threshold=threshold, debug=debug, frame_bytes=frame_bytes)
        
        def local_log(msg):
            if acc_name:
                self.log_gui(f"[{acc_name}] {msg}")
            else:
                self.log_gui(msg)
        
        for idx, step_data in enumerate(steps):
            if isinstance(step_data, str):
                step_data = {"node": step_data}
            
            step_type = step_data.get("type", "click")
            
            # --- DELAY step ---
            if step_type == "delay":
                delay_ms = float(step_data.get("time", 1000))
                delay_sec = delay_ms / 1000.0
                local_log(f"[Macro] ({idx+1}/{len(steps)}) Delay: {delay_ms:.0f}ms ({delay_sec:.1f}s)...")
                time.sleep(delay_sec)
                local_log(f"[Macro] Delay completed.")
                continue
            
            # --- MARKER step (standalone wait-for-image) ---
            if step_type == "marker":
                marker = step_data.get("marker", "")
                marker_mode = step_data.get("mode", "Wait until Appear")
                try:
                    marker_time = float(step_data.get("time", "0")) / 1000.0
                except:
                    marker_time = 0
                try:
                    marker_timeout = float(step_data.get("timeout", "0")) / 1000.0
                except:
                    marker_timeout = 0
                fail_image = step_data.get("fail_image", "None")
                
                mode_str = "APPEAR" if marker_mode == "Wait until Appear" else "DISAPPEAR"
                timeout_str = f", timeout {marker_timeout:.0f}s" if marker_timeout > 0 else ""
                local_log(f"[Macro] ({idx+1}/{len(steps)}) Waiting: '{marker}' to {mode_str} (hold {marker_time:.1f}s{timeout_str})...")
                marker_path = self.tracked_icons.get(marker)
                if not marker_path or not os.path.exists(marker_path):
                    local_log(f"    - Step FAILED: Marker '{marker}' image missing.")
                    return False
                
                fail_path = None
                if fail_image and fail_image != "None":
                    fail_path = self.tracked_icons.get(fail_image)
                
                hold_start = None
                last_log_time = 0
                start_time = time.time()
                marker_failed = False
                
                for attempt in range(99999):
                    # Timeout check
                    if marker_timeout > 0 and (time.time() - start_time) > marker_timeout:
                        local_log(f"    - Marker TIMEOUT ({marker_timeout:.0f}s): '{marker}'. Macro FAILED.")
                        return False
                    if acc_name:
                        # Coordinator mode: check per-account running flag
                        if not self.account_running.get(acc_name, False): break
                    else:
                        # Single-tab loop mode
                        if not self.is_looping: break
                    
                    frame_bytes = None
                    if page:
                        try: frame_bytes = page.screenshot()
                        except: pass
                    
                    # Fail image check
                    if fail_path and os.path.exists(fail_path):
                        fail_res = _find(fail_path, threshold_val, debug=False, frame_bytes=frame_bytes)
                        fail_mode = step_data.get("fail_mode", "Fail if Appear")
                        fail_triggered = (fail_mode == "Fail if Appear" and fail_res) or (fail_mode == "Fail if Disappear" and not fail_res)
                        if fail_triggered:
                            local_log(f"    - CANCEL: Fail image '{fail_image}' ({fail_mode})! Macro FAILED.")
                            return False
                    
                    res = _find(marker_path, threshold_val, debug=False, frame_bytes=frame_bytes)
                    is_condition_met = (marker_mode == "Wait until Appear" and res) or (marker_mode == "Wait until Disappear" and not res)
                    
                    if is_condition_met:
                        if hold_start is None:
                            hold_start = time.time()
                            if marker_time > 0:
                                local_log(f"    - Marker triggered. Holding {marker_time:.1f}s...")
                        elapsed = time.time() - hold_start
                        current_sec = int(elapsed)
                        if marker_time > 0 and current_sec > last_log_time:
                            local_log(f"    - Holding... {current_sec}/{marker_time:.0f}s")
                            last_log_time = current_sec
                        if elapsed >= marker_time:
                            local_log(f"    - Marker OK: '{marker}' confirmed {mode_str}.")
                            break
                    else:
                        if hold_start is not None:
                            local_log(f"    - Marker interrupted. Resetting hold timer.")
                            hold_start = None
                            last_log_time = 0
                    time.sleep(1.0)
                continue
            
            # --- CLICK step (find + click, no marker) ---
            node_name = step_data.get("node", "")
            if not node_name: continue
            
            filepath = self.tracked_icons.get(node_name)
            if not filepath or not os.path.exists(filepath):
                local_log(f"    - Step FAILED: Node '{node_name}' image file missing.")
                return False
                
            found = False
            for attempt in range(5):
                frame_bytes = None
                if page:
                    try:
                        frame_bytes = page.screenshot()
                    except: pass
                res = _find(filepath, threshold_val, debug=False, frame_bytes=frame_bytes)
                if res:
                    x, y, _ = res
                    bot_instance.click_at(x, y, randomize=True)
                    local_log(f"    - Step OK: Clicked '{node_name}'")
                    found = True
                    time.sleep(random.uniform(1.2, 2.0))
                    break
                time.sleep(1.0)
            if not found:
                local_log(f"    - Step FAILED: Could not find '{node_name}' after 5s.")
                return False
                    
        local_log(f"[STATE MACHINE] Macro steps completed. Checking result...")

        # Result verification via success/failure capture
        success_capture = macro_data.get("success_capture", "None")
        failure_capture = macro_data.get("failure_capture", "None")
        
        if success_capture == "None" and failure_capture == "None":
            local_log(f"[STATE MACHINE] Macro finished (no capture check configured).")
            return True
        
        time.sleep(1.0)
        
        frame_bytes = None
        if page:
            try: frame_bytes = page.screenshot()
            except: pass
        
        if success_capture != "None":
            s_path = self.tracked_icons.get(success_capture)
            if s_path and os.path.exists(s_path):
                res = _find(s_path, threshold_val, debug=False, frame_bytes=frame_bytes)
                if res:
                    local_log(f"[STATE MACHINE] Result: SUCCESS (found '{success_capture}')")
                    return True
                else:
                    local_log(f"[STATE MACHINE] Result: FAILURE ('{success_capture}' not found)")
                    return False
        
        if failure_capture != "None":
            f_path = self.tracked_icons.get(failure_capture)
            if f_path and os.path.exists(f_path):
                res = _find(f_path, threshold_val, debug=False, frame_bytes=frame_bytes)
                if res:
                    local_log(f"[STATE MACHINE] Result: FAILURE (found '{failure_capture}')")
                    return False
                else:
                    local_log(f"[STATE MACHINE] Result: SUCCESS ('{failure_capture}' not found)")
                    return True
        
        local_log(f"[STATE MACHINE] Macro finished (capture images not available).")
        return True
