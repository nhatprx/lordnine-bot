"""Macros tab mixin — Macro creation, editing, execution."""
import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
import threading
import time
import os
import random

from constants import COLOR, FONT, PAD, RADIUS, get_page_by_visual_index
from bot_action import BotAction
from playwright.sync_api import sync_playwright


class MacrosMixin:
    """Mixin for the Macros tab. Mixed into BotApp."""

    def setup_combo_tab(self):
        self.current_combo_name = None
        self.combo_buttons = {}
        self.combo_checkbox_vars = {}
        self.steps_labels = []

        self.tab_combo.grid_columnconfigure(0, weight=1, minsize=240)
        self.tab_combo.grid_columnconfigure(1, weight=3)
        self.tab_combo.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE ======
        self.combo_left_pane = ctk.CTkFrame(self.tab_combo, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.combo_left_pane.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        ctk.CTkLabel(self.combo_left_pane, text="MACROS", text_color=COLOR["accent"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=13)).pack(padx=PAD["md"], pady=(PAD["md"], PAD["sm"]), anchor="w")

        combo_actions_top = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent")
        combo_actions_top.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        self.add_combo_btn = ctk.CTkButton(combo_actions_top, text="+ Add", command=self.add_new_combo, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11), corner_radius=RADIUS, height=30)
        self.add_combo_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.del_selected_combo_btn = ctk.CTkButton(combo_actions_top, text="Delete Selected", command=self.delete_selected_combos, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11), corner_radius=RADIUS, height=30)
        self.del_selected_combo_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # Search
        self.combo_search_var = ctk.StringVar()
        self.combo_search_var.trace_add("write", lambda *a: self.refresh_combo_list())
        ctk.CTkEntry(self.combo_left_pane, placeholder_text="Search macros...", textvariable=self.combo_search_var, fg_color=COLOR["bg"], corner_radius=RADIUS, height=32, border_width=1, border_color=COLOR["border"]).pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        # Select All
        self.combo_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent")
        sa_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["xs"]))
        ctk.CTkCheckBox(sa_row, text="Select All", variable=self.combo_select_all_var, command=self._toggle_select_all_combos, width=20, height=20, font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left")

        self.combo_btn_container = ctk.CTkScrollableFrame(self.combo_left_pane, fg_color="transparent")
        self.combo_btn_container.pack(fill="both", expand=True, padx=PAD["xs"], pady=(0, PAD["sm"]))

        # ====== RIGHT PANE ======
        self.combo_right_pane = ctk.CTkFrame(self.tab_combo, fg_color=COLOR["bg"], corner_radius=0)
        self.combo_right_pane.grid(row=0, column=1, sticky="nsew", padx=(PAD["sm"], PAD["lg"]), pady=PAD["lg"])

        self.combo_top_bar = ctk.CTkFrame(self.combo_right_pane, fg_color="transparent", height=40)
        self.combo_top_bar.pack(fill="x", pady=(0, PAD["sm"]), padx=PAD["xl"])

        self.combo_preview_title = ctk.CTkLabel(self.combo_top_bar, text="MACRO SEQUENCE", font=ctk.CTkFont(family="Segoe UI", weight="bold", size=15), text_color=COLOR["accent"])
        self.combo_preview_title.pack()

        tab_idx_frame = ctk.CTkFrame(self.combo_top_bar, fg_color="transparent")
        tab_idx_frame.pack(pady=2)
        ctk.CTkLabel(tab_idx_frame, text="Port:", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left", padx=(5, 2))
        self.combo_chrome_port = ctk.CTkEntry(tab_idx_frame, width=55, placeholder_text="9222", fg_color=COLOR["surface"], corner_radius=6, height=28, border_width=1, border_color=COLOR["border"])
        self.combo_chrome_port.insert(0, "9222")
        self.combo_chrome_port.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(tab_idx_frame, text="Tab:", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left", padx=(0, 2))
        self.combo_tab_index = ctk.CTkEntry(tab_idx_frame, width=50, placeholder_text="0", fg_color=COLOR["surface"], corner_radius=6, height=28, border_width=1, border_color=COLOR["border"])
        self.combo_tab_index.insert(0, "0")
        self.combo_tab_index.pack(side="left")

        self.combo_name_label = ctk.CTkLabel(self.combo_right_pane, text="[No Macro Selected]", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLOR["warning"])
        self.combo_name_label.pack(pady=PAD["sm"])

        self.steps_container = ctk.CTkScrollableFrame(self.combo_right_pane, fg_color=COLOR["surface"], height=150, corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.steps_container.pack(fill="both", expand=True, padx=PAD["xl"], pady=PAD["xs"])

        # Result Verification Section
        self.result_verify_frame = ctk.CTkFrame(self.combo_right_pane, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.result_verify_frame.pack(fill="x", padx=PAD["xl"], pady=(PAD["xs"], 0))

        ctk.CTkLabel(self.result_verify_frame, text="RESULT VERIFICATION", font=ctk.CTkFont(weight="bold", size=12), text_color=COLOR["accent"]).pack(padx=PAD["md"], pady=(PAD["sm"], PAD["xs"]), anchor="w")
        ctk.CTkLabel(self.result_verify_frame, text="Check these images after macro runs to determine success/failure", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(padx=PAD["md"], anchor="w")

        captures_row = ctk.CTkFrame(self.result_verify_frame, fg_color="transparent")
        captures_row.pack(fill="x", padx=PAD["md"], pady=(PAD["xs"], PAD["md"]))
        captures_row.grid_columnconfigure(0, weight=1)
        captures_row.grid_columnconfigure(1, weight=1)

        success_col = ctk.CTkFrame(captures_row, fg_color="transparent")
        success_col.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(success_col, text="Success Capture:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["success"]).pack(anchor="w")
        self.combo_success_capture = ctk.CTkOptionMenu(success_col, values=["None"], fg_color=COLOR["surface2"], corner_radius=6, command=lambda v: self._save_macro_captures())
        self.combo_success_capture.pack(fill="x", pady=2)

        failure_col = ctk.CTkFrame(captures_row, fg_color="transparent")
        failure_col.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(failure_col, text="Failure Capture:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["danger"]).pack(anchor="w")
        self.combo_failure_capture = ctk.CTkOptionMenu(failure_col, values=["None"], fg_color=COLOR["surface2"], corner_radius=6, command=lambda v: self._save_macro_captures())
        self.combo_failure_capture.pack(fill="x", pady=2)

        self.combo_controls = ctk.CTkFrame(self.combo_right_pane, fg_color="transparent")
        self.combo_controls.pack(side="bottom", fill="x", pady=PAD["lg"], padx=PAD["xl"])

        self.add_step_btn = ctk.CTkButton(self.combo_controls, text="+ Add Step", command=self.add_step_to_combo, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], state="disabled", corner_radius=RADIUS)
        self.add_step_btn.pack(side="top", pady=(5, 2), fill="x")

        self.add_delay_btn = ctk.CTkButton(self.combo_controls, text="+ Add Delay", command=self.add_delay_to_combo, fg_color=COLOR["purple"], hover_color=COLOR["purple_h"], state="disabled", corner_radius=RADIUS)
        self.add_delay_btn.pack(side="top", pady=(0, 2), fill="x")

        self.add_marker_btn = ctk.CTkButton(self.combo_controls, text="+ Add Marker (Wait)", command=self.add_marker_to_combo, fg_color=COLOR["warning"], hover_color="#E67E22", state="disabled", corner_radius=RADIUS)
        self.add_marker_btn.pack(side="top", pady=(0, 5), fill="x")

        self.play_combo_btn = ctk.CTkButton(self.combo_controls, text="Execute Macro", command=self.play_current_combo, fg_color=COLOR["success"], hover_color=COLOR["success_h"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=RADIUS)
        self.play_combo_btn.pack(side="left", padx=(0, 5), expand=True, fill="x")

        self.delete_combo_btn = ctk.CTkButton(self.combo_controls, text="Delete Macro", command=self.delete_current_combo, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], state="disabled", corner_radius=RADIUS)
        self.delete_combo_btn.pack(side="right", padx=(5, 0), expand=True, fill="x")

        self.refresh_combo_list()

    def refresh_combo_list(self):
        for widget in self.combo_btn_container.winfo_children():
            widget.destroy()
        self.combo_buttons.clear()
        self.combo_checkbox_vars.clear()

        search = self.combo_search_var.get().strip().lower() if hasattr(self, 'combo_search_var') else ""
        for cname in self.combos.keys():
            if search and search not in cname.lower():
                continue
            frame = ctk.CTkFrame(self.combo_btn_container, fg_color="transparent")
            frame.pack(fill="x", pady=2, padx=5)
            
            var = ctk.BooleanVar(value=False)
            self.combo_checkbox_vars[cname] = var
            chk = ctk.CTkCheckBox(frame, text="", variable=var, width=20, height=20)
            chk.pack(side="left", padx=(0, 5))
            
            btn = ctk.CTkButton(frame, text=cname, anchor="w", fg_color="transparent", hover_color="#2C3E50", text_color="white", command=lambda n=cname: self.on_select_combo(n))
            btn.pack(side="left", fill="x", expand=True)
            self.combo_buttons[cname] = btn

    def _toggle_select_all_combos(self):
        val = self.combo_select_all_var.get()
        for v in self.combo_checkbox_vars.values():
            v.set(val)

    def on_select_combo(self, name):
        self.current_combo_name = name
        
        for n, btn in self.combo_buttons.items():
            if n == name:
                btn.configure(fg_color="#2980B9") 
            else:
                btn.configure(fg_color="transparent")

        self.combo_name_label.configure(text=name)
        
        self.add_step_btn.configure(state="normal")
        self.add_delay_btn.configure(state="normal")
        self.add_marker_btn.configure(state="normal")
        self.play_combo_btn.configure(state="normal")
        self.delete_combo_btn.configure(state="normal")
        
        # Data Migration
        macro_data = self.combos.get(name, {})
        migrated = False
        
        # If macro_data is still a list (very old version)
        if isinstance(macro_data, list):
            new_steps = [{"node": n} for n in macro_data]
            self.combos[name] = {"steps": new_steps}
            migrated = True
        # If it's a dict, check if steps are strings (old single-marker combo version)
        elif "steps" in macro_data and macro_data["steps"] and isinstance(macro_data["steps"][0], str):
            global_marker = macro_data.get("completion_marker", "None")
            global_mode = macro_data.get("marker_mode", "Wait until Appear")
            global_time = macro_data.get("marker_time", "0")
            
            new_steps = [{"node": n} for n in macro_data["steps"]]
            if global_marker != "None":
                new_steps.append({"type": "marker", "marker": global_marker, "mode": global_mode, "time": global_time})
            
            self.combos[name] = {"steps": new_steps}
            migrated = True
        else:
            # Migrate click+marker steps: split into click + standalone marker
            steps = macro_data.get("steps", [])
            new_steps = []
            for s in steps:
                if isinstance(s, dict) and s.get("type") not in ("delay", "marker") and s.get("marker", "None") != "None":
                    # Split: click step (without marker) + marker step
                    new_steps.append({"node": s["node"]})
                    new_steps.append({"type": "marker", "marker": s["marker"], "mode": s.get("mode", "Wait until Appear"), "time": s.get("time", "0")})
                    migrated = True
                else:
                    # Clean up old marker fields from click steps
                    if isinstance(s, dict) and s.get("type") not in ("delay", "marker") and "marker" in s:
                        clean = {"node": s["node"]}
                        new_steps.append(clean)
                        migrated = True
                    else:
                        new_steps.append(s)
            if migrated:
                macro_data["steps"] = new_steps
            
        if migrated:
            self.save_combos()

        self.refresh_steps_view()
        self._refresh_capture_dropdowns()

    def _refresh_capture_dropdowns(self):
        """Update success/failure capture dropdowns with current tracked nodes."""
        valid_nodes = ["None"] + [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        self.combo_success_capture.configure(values=valid_nodes)
        self.combo_failure_capture.configure(values=valid_nodes)
        
        if self.current_combo_name:
            macro_data = self.combos.get(self.current_combo_name, {})
            self.combo_success_capture.set(macro_data.get("success_capture", "None"))
            self.combo_failure_capture.set(macro_data.get("failure_capture", "None"))

    def _save_macro_captures(self, _=None):
        """Save current capture selections to combo data."""
        if not self.current_combo_name: return
        macro_data = self.combos.get(self.current_combo_name, {})
        macro_data["success_capture"] = self.combo_success_capture.get()
        macro_data["failure_capture"] = self.combo_failure_capture.get()
        self.save_combos()

    def refresh_steps_view(self):
        for widget in self.steps_container.winfo_children():
            widget.destroy()

        if not self.current_combo_name: return
        macro_data = self.combos.get(self.current_combo_name, {"steps": []})
        steps = macro_data.get("steps", [])
        self._step_frames = []
        self._drop_indicator = None
        
        for i, step_data in enumerate(steps):
            if isinstance(step_data, str): continue

            step_type = step_data.get("type", "click")
            
            if step_type == "delay":
                bg_color = "#1A1030"
            elif step_type == "marker":
                bg_color = "#1A2A10"
            else:
                bg_color = "#15202B"
            
            frame = ctk.CTkFrame(self.steps_container, fg_color=bg_color)
            frame.pack(fill="x", pady=2, padx=5)
            frame._step_index = i
            self._step_frames.append(frame)
            
            top_row = ctk.CTkFrame(frame, fg_color="transparent")
            top_row.pack(fill="x")
            
            # Pack right-side buttons FIRST so they never get pushed off
            del_step_btn = ctk.CTkButton(top_row, text="X", width=28, height=28, fg_color="transparent", text_color="#E74C3C", hover_color="#34495E", font=ctk.CTkFont(weight="bold"), command=lambda idx=i: self.remove_step_from_combo(idx))
            del_step_btn.pack(side="right", padx=2)
            
            edit_btn = ctk.CTkButton(top_row, text="Edit", width=35, height=28, fg_color="transparent", text_color="#F39C12", hover_color="#34495E", font=ctk.CTkFont(weight="bold"), command=lambda idx=i: self.edit_step(idx))
            edit_btn.pack(side="right", padx=2)
            
            # Drag handle
            drag_handle = ctk.CTkLabel(top_row, text="≡", font=ctk.CTkFont(size=16, weight="bold"), text_color="#555", width=20, cursor="fleur")
            drag_handle.pack(side="left", padx=(5, 2))
            drag_handle.bind("<Button-1>", lambda e, idx=i: self._drag_start(e, idx))
            drag_handle.bind("<B1-Motion>", self._drag_motion)
            drag_handle.bind("<ButtonRelease-1>", self._drag_drop)
            
            # Step label - builds text
            if step_type == "delay":
                delay_ms = step_data.get('time', 1000)
                txt = f"{i+1}. Delay: {delay_ms}ms"
                color = "#A78BFA"
            elif step_type == "marker":
                marker_name = step_data.get('marker', 'None')
                mode_short = step_data.get('mode', 'Wait until Appear').replace('Wait until ', '')
                hold_ms = step_data.get('time', '0')
                timeout_ms = step_data.get('timeout', '0')
                fail_img = step_data.get('fail_image', 'None')
                fail_mode = step_data.get('fail_mode', 'Fail if Appear').replace('Fail if ', '')
                parts = [f"{i+1}. Wait: {marker_name} {mode_short} (hold {hold_ms}ms)"]
                if str(timeout_ms) != '0': parts.append(f"T/O:{timeout_ms}ms")
                if fail_img and fail_img != 'None': parts.append(f"Fail:{fail_img} {fail_mode}")
                txt = " | ".join(parts)
                color = "#F39C12"
            else:
                txt = f"{i+1}. Click: {step_data.get('node', '?')}"
                color = "white"
            
            lbl = ctk.CTkLabel(top_row, text=txt, font=ctk.CTkFont(weight="bold", size=13), text_color=color, anchor="w")
            lbl.pack(side="left", padx=(2, 5), pady=2, fill="x", expand=True)

    def _drag_start(self, event, index):
        self._drag_index = index
        self._drag_target = index
        if 0 <= index < len(self._step_frames):
            self._step_frames[index].configure(border_width=2, border_color="#3498DB")
    
    def _drag_motion(self, event):
        if not hasattr(self, '_drag_index') or self._drag_index is None: return
        try:
            mouse_y = event.widget.winfo_rooty() + event.y
            container_y = self.steps_container.winfo_rooty()
            rel_y = mouse_y - container_y
        except:
            return
        
        # Find target using frame midpoints for smoother detection
        target = self._drag_index
        for i, frame in enumerate(self._step_frames):
            fy = frame.winfo_y()
            fh = frame.winfo_height()
            mid = fy + fh / 2
            if rel_y < mid:
                target = i
                break
            target = i
        
        # Remove old drop indicator
        if self._drop_indicator:
            self._drop_indicator.destroy()
            self._drop_indicator = None
        
        if target != self._drag_index:
            # Show drop indicator line
            indicator = ctk.CTkFrame(self.steps_container, fg_color="#E67E22", height=3)
            ref_frame = self._step_frames[target]
            if target < self._drag_index:
                indicator.pack(fill="x", padx=10, before=ref_frame)
            else:
                indicator.pack(fill="x", padx=10, after=ref_frame)
            self._drop_indicator = indicator
        
        self._drag_target = target
    
    def _drag_drop(self, event):
        if not hasattr(self, '_drag_index') or self._drag_index is None: return
        src = self._drag_index
        dst = self._drag_target
        
        # Cleanup
        if self._drop_indicator:
            self._drop_indicator.destroy()
            self._drop_indicator = None
        for f in self._step_frames:
            f.configure(border_width=0)
        
        if src != dst and self.current_combo_name:
            steps = self.combos[self.current_combo_name]["steps"]
            if 0 <= src < len(steps) and 0 <= dst < len(steps):
                item = steps.pop(src)
                steps.insert(dst, item)
                self.save_combos()
                self.refresh_steps_view()
        
        self._drag_index = None
        self._drag_target = None

    def edit_step(self, index):
        if not self.current_combo_name: return
        step_data = self.combos[self.current_combo_name]["steps"][index]
        step_type = step_data.get("type", "click")
        if step_type == "marker":
            self.edit_step_marker(index)
        elif step_type == "delay":
            self.edit_step_delay(index)
        else:
            self.edit_step_click(index)

    def edit_step_click(self, index):
        if not self.current_combo_name: return
        step_data = self.combos[self.current_combo_name]["steps"][index]
        
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            messagebox.showinfo("Empty", "No tracked images available!")
            return
        
        top = ctk.CTkToplevel(self)
        top.title(f"Edit Click - Step {index+1}")
        top.geometry("400x200")
        top.attributes("-topmost", True)
        
        ctk.CTkLabel(top, text="Target Image:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        cb_node = ctk.CTkOptionMenu(top, values=valid_nodes)
        cb_node.set(step_data.get("node", valid_nodes[0]))
        cb_node.pack(fill="x", padx=20, pady=5)
        
        def _save():
            step_data["node"] = cb_node.get()
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
            
        btn_save = ctk.CTkButton(top, text="SAVE CHANGES", command=_save, fg_color="#3498DB", hover_color="#2980B9", font=ctk.CTkFont(weight="bold", size=14))
        btn_save.pack(pady=30, fill="x", padx=20)

    def edit_step_delay(self, index):
        if not self.current_combo_name: return
        step_data = self.combos[self.current_combo_name]["steps"][index]
        
        top = ctk.CTkToplevel(self)
        top.title(f"Edit Delay - Step {index+1}")
        top.geometry("400x200")
        top.attributes("-topmost", True)
        
        ctk.CTkLabel(top, text="Delay Duration (ms):", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        entry_time = ctk.CTkEntry(top)
        entry_time.insert(0, str(step_data.get("time", 1000)))
        entry_time.pack(fill="x", padx=20, pady=5)
        
        def _save():
            try:
                val = float(entry_time.get())
                if val < 100: val = 100
                if val > 300000: val = 300000
            except ValueError:
                val = 1000
            step_data["time"] = val
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
            
        btn_save = ctk.CTkButton(top, text="SAVE CHANGES", command=_save, fg_color="#3498DB", hover_color="#2980B9", font=ctk.CTkFont(weight="bold", size=14))
        btn_save.pack(pady=30, fill="x", padx=20)

    def edit_step_marker(self, index):
        if not self.current_combo_name: return
        step_data = self.combos[self.current_combo_name]["steps"][index]
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            messagebox.showinfo("Empty", "No tracked images available!")
            return
        
        top = ctk.CTkToplevel(self)
        top.title(f"Edit Marker - Step {index+1}")
        top.geometry("420x350")
        top.attributes("-topmost", True)
        
        # --- Define save button and anchor at bottom FIRST ---
        def _save():
            time_val = entry_time.get()
            try: float(time_val)
            except ValueError: time_val = "0"
            timeout_val = entry_timeout.get()
            try: float(timeout_val)
            except ValueError: timeout_val = "0"
            step_data["marker"] = cb_marker.get()
            step_data["mode"] = cb_mode.get()
            step_data["time"] = time_val
            step_data["timeout"] = timeout_val
            step_data["fail_image"] = cb_fail.get()
            step_data["fail_mode"] = cb_fail_mode.get()
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
        
        btn_save = ctk.CTkButton(top, text="SAVE CHANGES", command=_save, fg_color="#3498DB", hover_color="#2980B9", font=ctk.CTkFont(weight="bold", size=14))
        btn_save.pack(side="bottom", pady=(5, 15), fill="x", padx=20)
        
        # --- Main fields (pack top-down) ---
        ctk.CTkLabel(top, text="1. Wait for Image:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        cb_marker = ctk.CTkOptionMenu(top, values=valid_nodes)
        cb_marker.set(step_data.get("marker", valid_nodes[0]))
        cb_marker.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(top, text="2. Condition:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=20)
        cb_mode = ctk.CTkOptionMenu(top, values=["Wait until Appear", "Wait until Disappear"])
        cb_mode.set(step_data.get("mode", "Wait until Appear"))
        cb_mode.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(top, text="3. Hold Duration (ms):", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=20)
        entry_time = ctk.CTkEntry(top)
        entry_time.insert(0, str(step_data.get("time", "0")))
        entry_time.pack(fill="x", padx=20, pady=5)
        
        # --- Advanced section (collapsible, no wrapper frame) ---
        adv_widgets = ctk.CTkFrame(top, fg_color="#1a1a2e", corner_radius=8)
        
        ctk.CTkLabel(adv_widgets, text="Timeout (ms, 0=no limit):", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=15)
        entry_timeout = ctk.CTkEntry(adv_widgets)
        entry_timeout.insert(0, str(step_data.get("timeout", "0")))
        entry_timeout.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(adv_widgets, text="Fail Image (cancel marker):", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=15)
        fail_nodes = ["None"] + valid_nodes
        cb_fail = ctk.CTkOptionMenu(adv_widgets, values=fail_nodes)
        cb_fail.set(step_data.get("fail_image", "None"))
        cb_fail.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(adv_widgets, text="Fail Condition:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=15)
        cb_fail_mode = ctk.CTkOptionMenu(adv_widgets, values=["Fail if Appear", "Fail if Disappear"])
        cb_fail_mode.set(step_data.get("fail_mode", "Fail if Appear"))
        cb_fail_mode.pack(fill="x", padx=15, pady=(5, 10))
        
        adv_visible = [False]
        def _toggle_adv():
            if adv_visible[0]:
                adv_widgets.pack_forget()
                adv_btn.configure(text="Advanced ▼")
                top.geometry("420x350")
            else:
                adv_widgets.pack(fill="x", padx=20, pady=5, after=adv_btn)
                top.geometry("420x600")
            adv_visible[0] = not adv_visible[0]
        
        adv_btn = ctk.CTkButton(top, text="Advanced ▼", command=_toggle_adv, fg_color="transparent", text_color="#888", hover_color="#2C3E50", font=ctk.CTkFont(size=12), height=24)
        adv_btn.pack(pady=(10, 0))
        
        # Auto-expand if advanced fields are set
        has_adv = str(step_data.get("timeout", "0")) != "0" or step_data.get("fail_image", "None") != "None"
        if has_adv:
            _toggle_adv()

    def add_new_combo(self):
        dialog = ctk.CTkInputDialog(text="New Macro Name (e.g. Buy Potion):", title="New Macro")
        name = dialog.get_input()
        if name:
            name = name.strip()
            if not name: return
            if name in self.combos:
                messagebox.showerror("Error", "Macro name already exists!")
                return
            
            self.combos[name] = {"steps": []}
            self.save_combos()
            self.refresh_combo_list()
            self.on_select_combo(name)

    def delete_selected_combos(self):
        to_delete = [cname for cname, var in self.combo_checkbox_vars.items() if var.get()]
        if not to_delete:
            messagebox.showinfo("Info", "Please select Macros to delete!")
            return
            
        if messagebox.askyesno("Confirm", f"Delete {len(to_delete)} selected Macros?"):
            for cname in to_delete:
                if cname in self.combos:
                    del self.combos[cname]
                if self.current_combo_name == cname:
                    self.current_combo_name = None
                    self.combo_name_label.configure(text="[Deleted]")
                    self.refresh_steps_view()
                    self.delete_combo_btn.configure(state="disabled")
                    self.add_step_btn.configure(state="disabled")
                    self.play_combo_btn.configure(state="disabled")
                    
            self.save_combos()
            self.refresh_combo_list()
            self.log_gui(f"[System] Deleted {len(to_delete)} Macros successfully.")

    def delete_current_combo(self):
        if not self.current_combo_name: return
        if messagebox.askyesno("Confirm", f"Delete entire Macro '{self.current_combo_name}'?"):
            del self.combos[self.current_combo_name]
            self.save_combos()
            self.current_combo_name = None
            self.combo_name_label.configure(text="[Deleted]")
            self.refresh_combo_list()
            self.refresh_steps_view()
            self.delete_combo_btn.configure(state="disabled")

    def add_step_to_combo(self):
        if not self.current_combo_name: return
        
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            messagebox.showwarning("Empty", "You haven't added any Target Nodes in the Setup tab yet!")
            return
            
        top = ctk.CTkToplevel(self)
        top.title("Add New Steps")
        top.geometry("400x450")
        top.attributes("-topmost", True)
        
        ctk.CTkLabel(top, text="Select Target Nodes to add:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 5), anchor="w", padx=20)
        ctk.CTkLabel(top, text="(Numbered by selection order)", font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 10), anchor="w", padx=20)
        
        scroll_frame = ctk.CTkScrollableFrame(top, fg_color="#1E2B3C")
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        selected_nodes_order = []
        checkboxes = {}
        
        def on_check(node_name, var):
            if var.get():
                if node_name not in selected_nodes_order:
                    selected_nodes_order.append(node_name)
            else:
                if node_name in selected_nodes_order:
                    selected_nodes_order.remove(node_name)
                    
            for n, chk in checkboxes.items():
                if n in selected_nodes_order:
                    idx = selected_nodes_order.index(n) + 1
                    chk.configure(text=f"[{idx}] {n}")
                else:chk.configure(text=n)

        for node in valid_nodes:
            var = ctk.BooleanVar(value=False)
            chk = ctk.CTkCheckBox(scroll_frame, text=node, variable=var, command=lambda n=node, v=var: on_check(n, v))
            chk.pack(anchor="w", pady=5, padx=10)
            checkboxes[node] = chk
            
        def _add():
            if not selected_nodes_order:
                messagebox.showinfo("Info", "No nodes selected!")
                return
                
            for node_val in selected_nodes_order:
                step_obj = {
                    "node": node_val,
                    "marker": "None",
                    "mode": "Wait until Appear",
                    "time": "0"
                }
                self.combos[self.current_combo_name]["steps"].append(step_obj)
                
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
            
        btn_add = ctk.CTkButton(top, text="ADD SELECTED STEPS", command=_add, fg_color="#2ECC71", hover_color="#27AE60", font=ctk.CTkFont(weight="bold", size=14))
        btn_add.pack(pady=15, fill="x", padx=20)

    def add_delay_to_combo(self):
        if not self.current_combo_name: return
        
        val = simpledialog.askfloat("Add Delay", "Enter delay time in milliseconds (ms):", 
                                      initialvalue=1000, minvalue=100, maxvalue=300000)
        if val is not None:
            step_obj = {
                "type": "delay",
                "time": val
            }
            self.combos[self.current_combo_name]["steps"].append(step_obj)
            self.save_combos()
            self.refresh_steps_view()

    def add_marker_to_combo(self):
        if not self.current_combo_name: return
        
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            messagebox.showinfo("Empty", "No tracked images available!")
            return
        
        top = ctk.CTkToplevel(self)
        top.title("Add Marker (Wait for Image)")
        top.geometry("420x350")
        top.attributes("-topmost", True)
        
        # --- Define add button and anchor at bottom FIRST ---
        def _add():
            time_val = entry_time.get()
            try: float(time_val)
            except ValueError: time_val = "0"
            timeout_val = entry_timeout.get()
            try: float(timeout_val)
            except ValueError: timeout_val = "0"
            step_obj = {
                "type": "marker",
                "marker": cb_marker.get(),
                "mode": cb_mode.get(),
                "time": time_val,
                "timeout": timeout_val,
                "fail_image": cb_fail.get(),
                "fail_mode": cb_fail_mode.get()
            }
            self.combos[self.current_combo_name]["steps"].append(step_obj)
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
        
        btn_add = ctk.CTkButton(top, text="ADD MARKER STEP", command=_add, fg_color=COLOR["warning"], hover_color="#E67E22", font=ctk.CTkFont(weight="bold", size=14))
        btn_add.pack(side="bottom", pady=(5, 15), fill="x", padx=20)
        
        # --- Main fields (pack top-down) ---
        ctk.CTkLabel(top, text="1. Wait for Image:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        cb_marker = ctk.CTkOptionMenu(top, values=valid_nodes)
        cb_marker.set(valid_nodes[0])
        cb_marker.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(top, text="2. Condition:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=20)
        cb_mode = ctk.CTkOptionMenu(top, values=["Wait until Appear", "Wait until Disappear"])
        cb_mode.set("Wait until Appear")
        cb_mode.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(top, text="3. Hold Duration (ms):", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=20)
        entry_time = ctk.CTkEntry(top)
        entry_time.insert(0, "2000")
        entry_time.pack(fill="x", padx=20, pady=5)
        
        # --- Advanced section (collapsible, no wrapper frame) ---
        adv_widgets = ctk.CTkFrame(top, fg_color="#1a1a2e", corner_radius=8)
        
        ctk.CTkLabel(adv_widgets, text="Timeout (ms, 0=no limit):", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=15)
        entry_timeout = ctk.CTkEntry(adv_widgets)
        entry_timeout.insert(0, "0")
        entry_timeout.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(adv_widgets, text="Fail Image (cancel marker):", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=15)
        fail_nodes = ["None"] + valid_nodes
        cb_fail = ctk.CTkOptionMenu(adv_widgets, values=fail_nodes)
        cb_fail.set("None")
        cb_fail.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(adv_widgets, text="Fail Condition:", font=ctk.CTkFont(weight="bold")).pack(pady=(10, 0), anchor="w", padx=15)
        cb_fail_mode = ctk.CTkOptionMenu(adv_widgets, values=["Fail if Appear", "Fail if Disappear"])
        cb_fail_mode.set("Fail if Appear")
        cb_fail_mode.pack(fill="x", padx=15, pady=(5, 10))
        
        adv_visible = [False]
        def _toggle_adv():
            if adv_visible[0]:
                adv_widgets.pack_forget()
                adv_btn.configure(text="Advanced ▼")
                top.geometry("420x350")
            else:
                adv_widgets.pack(fill="x", padx=20, pady=5, after=adv_btn)
                top.geometry("420x600")
            adv_visible[0] = not adv_visible[0]
        
        adv_btn = ctk.CTkButton(top, text="Advanced ▼", command=_toggle_adv, fg_color="transparent", text_color="#888", hover_color="#2C3E50", font=ctk.CTkFont(size=12), height=24)
        adv_btn.pack(pady=(10, 0))

    def remove_step_from_combo(self, index):
        if not self.current_combo_name: return
        self.combos[self.current_combo_name]["steps"].pop(index)
        self.save_combos()
        self.refresh_steps_view()

    def play_current_combo(self):
        if not self.current_combo_name: return
        macro_data = self.combos.get(self.current_combo_name, {"steps": []})
        steps = macro_data.get("steps", [])
        if not steps:
            messagebox.showwarning("Empty", "This Macro has no steps configured.")
            return
        
        port_str = self.combo_chrome_port.get().strip()
        port = int(port_str) if port_str.isdigit() else 9222
        tab_id_str = self.combo_tab_index.get().strip()
        tab_id = int(tab_id_str) if tab_id_str.isdigit() else 0
            
        if messagebox.askyesno("Execute Macro", f"Execute Macro [{self.current_combo_name}] on Port {port}, Tab {tab_id}?"):
            threading.Thread(target=self._macro_execution_worker, args=(macro_data, tab_id, port), daemon=True).start()

    def _macro_execution_worker(self, macro_data, tab_id=0, port=9222):
        self.log_gui(f"============== MACRO STARTING ==============")
        steps = macro_data.get("steps", [])
        threshold_val = self.slider.get()
        
        playwright_ctx = sync_playwright().start()
        browser = None
        page = None
        
        if tab_id is not None:
             try:
                 self.log_gui(f"[Macro] Connecting to Port {port}, Tab {tab_id}...")
                 browser = playwright_ctx.chromium.connect_over_cdp(f"http://localhost:{port}")
                 context = browser.contexts[0]
                 page, info = get_page_by_visual_index(context, tab_id, port=port)
                 if page:
                     if isinstance(info, list):
                         for idx_t, title_t, url_t in info:
                             self.log_gui(f"[Macro]   Tab {idx_t}: {title_t}")
                     self.log_gui(f"[Macro] Hooked to Tab {tab_id}: {page.url[:60]}")
                 else:
                     self.log_gui(f"[Macro] Error: {info}")
                     playwright_ctx.stop()
                     return
             except Exception as e:
                 self.log_gui(f"[Test Macro] Connection failed: {e}")
                 playwright_ctx.stop()
                 return
        else:
            self.log_gui(f"[Test Macro] Running in foreground (PyAutoGUI focus)")
        
        bot_instance = BotAction(page=page, debug_visual_var=self.debug_visual_var)
        
        try:
            for idx, step_data in enumerate(steps):
                if isinstance(step_data, str):
                    step_data = {"node": step_data}
                
                step_type = step_data.get("type", "click")
                
                # --- DELAY step ---
                if step_type == "delay":
                    delay_ms = float(step_data.get("time", 1000))
                    delay_sec = delay_ms / 1000.0
                    self.log_gui(f"[Macro] ({idx+1}/{len(steps)}) Delay: {delay_ms:.0f}ms ({delay_sec:.1f}s)...")
                    time.sleep(delay_sec)
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
                    
                    mode_str = "APPEARS" if marker_mode == "Wait until Appear" else "DISAPPEARS"
                    timeout_str = f", timeout {marker_timeout:.0f}s" if marker_timeout > 0 else ""
                    self.log_gui(f"[Macro] ({idx+1}/{len(steps)}) Waiting: '{marker}' {mode_str} (hold {marker_time:.1f}s{timeout_str})...")
                    marker_path = self.tracked_icons.get(marker)
                    if not marker_path or not os.path.exists(marker_path):
                        self.log_gui(f"[Macro] SKIP: Marker '{marker}' image missing.")
                        continue
                    
                    fail_path = None
                    if fail_image and fail_image != "None":
                        fail_path = self.tracked_icons.get(fail_image)
                    
                    hold_start = None
                    last_log_time = 0
                    start_time = time.time()
                    for attempt in range(99999):
                        # Timeout check
                        if marker_timeout > 0 and (time.time() - start_time) > marker_timeout:
                            self.log_gui(f"[Macro] TIMEOUT: Marker '{marker}' after {marker_timeout:.0f}s. Aborting!")
                            break
                        
                        frame_bytes = None
                        if page:
                            try: frame_bytes = page.screenshot()
                            except: pass
                        
                        # Fail image check
                        if fail_path and os.path.exists(fail_path):
                            fail_res = self.vision.find_template_on_screen(fail_path, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                            fail_mode = step_data.get("fail_mode", "Fail if Appear")
                            fail_triggered = (fail_mode == "Fail if Appear" and fail_res) or (fail_mode == "Fail if Disappear" and not fail_res)
                            if fail_triggered:
                                self.log_gui(f"[Macro] CANCEL: Fail image '{fail_image}' ({fail_mode})! Aborting marker.")
                                break
                        
                        res = self.vision.find_template_on_screen(marker_path, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                        is_condition_met = (marker_mode == "Wait until Appear" and res) or (marker_mode == "Wait until Disappear" and not res)
                        if is_condition_met:
                            if hold_start is None:
                                hold_start = time.time()
                                if marker_time > 0:
                                    self.log_gui(f"[Macro] Marker Triggered. Hold timer started ({marker_time:.1f}s)...")
                            elapsed = time.time() - hold_start
                            current_sec = int(elapsed)
                            if marker_time > 0 and current_sec > last_log_time:
                                self.log_gui(f"[Macro] Holding... {current_sec}/{marker_time:.0f}s")
                                last_log_time = current_sec
                            if elapsed >= marker_time:
                                self.log_gui(f"[Macro] Confirmed '{marker}' {mode_str}!")
                                break
                        else:
                            if hold_start is not None:
                                self.log_gui(f"[Macro] Interrupted! Resetting timer.")
                                hold_start = None
                                last_log_time = 0
                        time.sleep(1.0)
                    continue
                
                # --- CLICK step (find + click, no marker) ---
                node_name = step_data.get("node", "")
                if not node_name: continue
                
                self.log_gui(f"[Macro] ({idx+1}/{len(steps)}) Finding Node: {node_name}...")
                
                filepath = self.tracked_icons.get(node_name)
                if not filepath or not os.path.exists(filepath):
                    self.log_gui(f"[Macro] SKIP: Node '{node_name}' missing image file.")
                    continue
                    
                found = False
                for attempt in range(5):
                    frame_bytes = None
                    if page:
                        try: frame_bytes = page.screenshot()
                        except: pass
                    res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                    if res:
                        x, y, score = res
                        self.log_gui(f"        -> Node Found. Clicking coordinates ({x},{y}).")
                        bot_instance.click_at(x, y, randomize=True)
                        found = True
                        time.sleep(random.uniform(1.2, 2.0))
                        break
                    time.sleep(1.0)
                    
                if not found:
                    self.log_gui(f"[Macro] SKIP: Could not find Node '{node_name}' after 5 seconds.")
                    continue
        finally:
            if browser:
                try: browser.close()
                except: pass
            playwright_ctx.stop()
        self.log_gui(f"============== MACRO FINISHED ==============")
