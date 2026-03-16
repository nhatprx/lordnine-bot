"""Macros tab mixin — Macro creation, editing, execution."""
import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
import threading
import time
import os
import random

from constants import COLOR, FONT, PAD, RADIUS
from bot_action import BotAction


class MacrosMixin:
    """Mixin for the Macros tab. Mixed into BotApp."""

    def setup_combo_tab(self):
        self.current_combo_name = None
        self.combo_buttons = {}
        self.combo_checkbox_vars = {}
        self.steps_labels = []

        self.tab_combo.grid_columnconfigure(0, weight=1, minsize=130, uniform="col")
        self.tab_combo.grid_columnconfigure(1, weight=3, uniform="col")
        self.tab_combo.grid_rowconfigure(0, weight=1)

        # Helper to blur searchbox - called from various click handlers
        def _blur_combo_search(event=None):
            if hasattr(self, 'combo_search_entry'):
                try: self.tab_combo.focus_set()
                except: pass
        self._blur_combo_search = _blur_combo_search

        # ====== LEFT PANE (Panel Card) ======
        self.combo_left_pane = ctk.CTkFrame(self.tab_combo, fg_color=COLOR["surface"], corner_radius=12, border_width=1, border_color=COLOR["border_subtle"])
        self.combo_left_pane.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        # -- Title row with inline action links --
        title_row = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent")
        title_row.pack(fill="x", padx=PAD["md"], pady=(PAD["md"], PAD["sm"]))

        ctk.CTkLabel(
            title_row, text="MACROS",
            text_color=COLOR["text_dim"],
            font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11)
        ).pack(side="left")

        self.del_selected_combo_btn = ctk.CTkButton(
            title_row, text="Delete", command=self.delete_selected_combos,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"),
            width=50, height=24, corner_radius=4
        )
        self.del_selected_combo_btn.pack(side="right", padx=(2, 0))

        self.add_combo_btn = ctk.CTkButton(
            title_row, text="+ Add", command=self.add_new_combo,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["primary"], font=ctk.CTkFont(size=11, weight="bold"),
            width=50, height=24, corner_radius=4
        )
        self.add_combo_btn.pack(side="right", padx=(0, 2))

        # Search bar
        self._combo_search_debounce_id = None
        def _debounced_combo_search(*a):
            if self._combo_search_debounce_id:
                self.after_cancel(self._combo_search_debounce_id)
            self._combo_search_debounce_id = self.after(150, self.refresh_combo_list)
        self.combo_search_entry = ctk.CTkEntry(
            self.combo_left_pane, placeholder_text="Search macros...",
            placeholder_text_color=COLOR["text_muted"],
            fg_color=COLOR["bg"], corner_radius=6, height=30,
            border_width=1, border_color=COLOR["border_subtle"]
        )
        self.combo_search_entry._entry.bind("<KeyRelease>", _debounced_combo_search)
        self.combo_search_entry.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        # Select All
        self.combo_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent", height=24)
        sa_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["xs"]))
        ctk.CTkCheckBox(
            sa_row, text="Select All", variable=self.combo_select_all_var,
            command=self._toggle_select_all_combos,
            checkbox_width=18, checkbox_height=18, corner_radius=4,
            border_width=1, font=ctk.CTkFont(size=11),
            text_color=COLOR["text_muted"], border_color=COLOR["border"],
            hover_color=COLOR["surface2"]
        ).pack(side="left")

        # Scrollable macro list
        self.combo_btn_container = ctk.CTkScrollableFrame(
            self.combo_left_pane, fg_color="transparent",
            scrollbar_button_color=COLOR["border"],
            scrollbar_button_hover_color=COLOR["text_muted"]
        )
        self.combo_btn_container.pack(fill="both", expand=True, padx=2, pady=(0, PAD["xs"]))

        # ====== RIGHT PANE ======
        self.combo_right_pane = ctk.CTkFrame(self.tab_combo, fg_color=COLOR["bg"], corner_radius=0)
        self.combo_right_pane.grid(row=0, column=1, sticky="nsew", padx=(PAD["sm"], PAD["lg"]), pady=PAD["lg"])

        # Detail area card
        self.combo_detail_area = ctk.CTkFrame(self.combo_right_pane, fg_color=COLOR["surface"], corner_radius=12, border_width=1, border_color=COLOR["border_subtle"])
        self.combo_detail_area.pack(fill="both", expand=True)

        # Bind blur to all major areas so clicking anywhere outside search blurs it
        for w in [self.combo_right_pane, self.combo_detail_area, self.combo_left_pane]:
            w.bind("<Button-1>", self._blur_combo_search)

        # -- Header bar --
        self.combo_header = ctk.CTkFrame(self.combo_detail_area, fg_color="transparent", height=42)
        self.combo_header.pack(fill="x", padx=6, pady=(6, 0))
        self.combo_header.pack_propagate(False)

        self.combo_name_label = ctk.CTkLabel(
            self.combo_header, text="[No Macro Selected]",
            font=ctk.CTkFont(family="Inter", size=14, weight="bold"),
            text_color=COLOR["text"]
        )
        self.combo_name_label.pack(side="left", padx=PAD["sm"])

        # Header separator
        ctk.CTkFrame(self.combo_detail_area, fg_color=COLOR["border_subtle"], height=1).pack(fill="x", padx=6)

        # -- Steps container --
        self.steps_container = ctk.CTkScrollableFrame(
            self.combo_detail_area, fg_color="transparent",
            scrollbar_button_color=COLOR["border"],
            scrollbar_button_hover_color=COLOR["text_muted"]
        )

        # -- Empty state overlay (non-scrollable, centered) --
        self.combo_empty_state = ctk.CTkFrame(self.combo_detail_area, fg_color="transparent")

        # Initially show the empty state
        self.combo_empty_state.pack(fill="both", expand=True, padx=PAD["md"], pady=PAD["xs"])

        # -- Bottom Toolbar (color-coded action buttons) --
        self.combo_toolbar = ctk.CTkFrame(self.combo_detail_area, fg_color=COLOR["surface"], corner_radius=0, height=44)
        self.combo_toolbar.pack(fill="x", side="bottom", padx=0, pady=0)
        self.combo_toolbar.pack_propagate(False)

        # + Step button (blue — matches click step accent)
        self.add_step_btn = ctk.CTkButton(
            self.combo_toolbar, text="+ Step", command=self.add_step_to_combo,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["primary"],
            text_color=COLOR["primary"], font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        )
        self.add_step_btn.pack(side="left", padx=(PAD["md"], 3), pady=6, expand=True, fill="x")

        # + Delay button (purple — matches delay step accent)
        self.add_delay_btn = ctk.CTkButton(
            self.combo_toolbar, text="+ Delay", command=self.add_delay_to_combo,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["purple"],
            text_color=COLOR["purple"], font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        )
        self.add_delay_btn.pack(side="left", padx=3, pady=6, expand=True, fill="x")

        # + Marker button (amber — matches marker step accent)
        self.add_marker_btn = ctk.CTkButton(
            self.combo_toolbar, text="+ Marker", command=self.add_marker_to_combo,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["warning"],
            text_color=COLOR["warning"], font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        )
        self.add_marker_btn.pack(side="left", padx=3, pady=6, expand=True, fill="x")

        # Execute button (green — action button, slightly wider)
        self.play_combo_btn = ctk.CTkButton(
            self.combo_toolbar, text="▶ Execute", command=self.play_current_combo,
            fg_color="transparent", hover_color="#2A5A4A",
            border_width=1, border_color="#3D8B6E",
            text_color="#3D8B6E", font=ctk.CTkFont(size=11, weight="bold"),
            width=120, height=30, corner_radius=6
        )
        self.play_combo_btn.pack(side="left", padx=(3, PAD["md"]), pady=6, expand=True, fill="x")

        # -- Result Verification Section --
        self.result_verify_frame = ctk.CTkFrame(self.combo_detail_area, fg_color=COLOR["bg_subtle"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
        self.result_verify_frame.pack(fill="x", padx=PAD["md"], pady=(PAD["xs"], PAD["md"]))

        # Bind blur to all child containers too
        for w in [self.combo_header, self.combo_toolbar, self.steps_container, self.result_verify_frame]:
            w.bind("<Button-1>", self._blur_combo_search)

        ctk.CTkLabel(
            self.result_verify_frame, text="RESULT VERIFICATION",
            font=ctk.CTkFont(weight="bold", size=10),
            text_color=COLOR["text_muted"]
        ).pack(padx=PAD["md"], pady=(PAD["sm"], PAD["xs"]), anchor="w")

        captures_row = ctk.CTkFrame(self.result_verify_frame, fg_color="transparent")
        captures_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["md"]))
        captures_row.grid_columnconfigure(0, weight=1)
        captures_row.grid_columnconfigure(1, weight=1)

        success_col = ctk.CTkFrame(captures_row, fg_color="transparent")
        success_col.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(success_col, text="Success Capture", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["success"]).pack(anchor="w")
        self.combo_success_capture = ctk.CTkOptionMenu(success_col, values=["None"], fg_color=COLOR["surface"], corner_radius=6, command=lambda v: self._save_macro_captures(), height=28, font=ctk.CTkFont(size=11))
        self.combo_success_capture.pack(fill="x", pady=2)

        failure_col = ctk.CTkFrame(captures_row, fg_color="transparent")
        failure_col.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(failure_col, text="Failure Capture", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["danger"]).pack(anchor="w")
        self.combo_failure_capture = ctk.CTkOptionMenu(failure_col, values=["None"], fg_color=COLOR["surface"], corner_radius=6, command=lambda v: self._save_macro_captures(), height=28, font=ctk.CTkFont(size=11))
        self.combo_failure_capture.pack(fill="x", pady=2)

        self.refresh_combo_list()
        self.refresh_steps_view()

    def refresh_combo_list(self):
        for widget in self.combo_btn_container.winfo_children():
            widget.destroy()
        self.combo_buttons.clear()
        self.combo_checkbox_vars.clear()

        search = self.combo_search_entry.get().strip().lower() if hasattr(self, 'combo_search_entry') else ""
        for cname in self.combos.keys():
            if search and search not in cname.lower():
                continue
            frame = ctk.CTkFrame(self.combo_btn_container, fg_color="transparent", height=30)
            frame.pack(fill="x", pady=1, padx=4)
            frame.pack_propagate(False)

            var = ctk.BooleanVar(value=False)
            self.combo_checkbox_vars[cname] = var
            ctk.CTkCheckBox(
                frame, text="", variable=var,
                checkbox_width=18, checkbox_height=18, corner_radius=4,
                border_width=1, width=18, border_color=COLOR["border"],
                hover_color=COLOR["surface2"],
                command=self._update_delete_combo_btn_color
            ).pack(side="left", padx=(4, 6))

            btn = ctk.CTkButton(
                frame, text=cname, anchor="w",
                fg_color="transparent", hover_color=COLOR["surface2"],
                text_color=COLOR["text_dim"],
                font=ctk.CTkFont(size=12),
                height=28, corner_radius=6,
                command=lambda n=cname: self.on_select_combo(n)
            )
            btn.pack(side="left", fill="x", expand=True)
            self.combo_buttons[cname] = btn

    def _update_delete_combo_btn_color(self):
        """Turn Delete button red when any checkbox is ticked."""
        any_checked = any(v.get() for v in self.combo_checkbox_vars.values())
        if any_checked:
            self.del_selected_combo_btn.configure(text_color=COLOR["danger"])
        else:
            self.del_selected_combo_btn.configure(text_color=COLOR["text_muted"])

    def _toggle_select_all_combos(self):
        val = self.combo_select_all_var.get()
        for v in self.combo_checkbox_vars.values():
            v.set(val)
        self._update_delete_combo_btn_color()

    def on_select_combo(self, name):
        # Blur searchbox
        self._blur_combo_search()

        # Just select this macro (no checkbox toggle)
        self.current_combo_name = name

        for n, btn in self.combo_buttons.items():
            if n == name:
                btn.configure(fg_color=COLOR["surface3"], text_color=COLOR["text"])
            else:
                btn.configure(fg_color="transparent", text_color=COLOR["text_dim"])

        # Force immediate visual refresh
        self.update_idletasks()

        # Only update right pane detail if a macro is selected
        if not self.current_combo_name:
            return

        self.combo_name_label.configure(text=name)
        

        
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
                    click_step = {"node": s["node"]}
                    if s.get("hard_click"):
                        click_step["hard_click"] = True
                    new_steps.append(click_step)
                    new_steps.append({"type": "marker", "marker": s["marker"], "mode": s.get("mode", "Wait until Appear"), "time": s.get("time", "0")})
                    migrated = True
                else:
                    # Clean up old marker fields from click steps
                    if isinstance(s, dict) and s.get("type") not in ("delay", "marker") and "marker" in s:
                        clean = {"node": s["node"]}
                        if s.get("hard_click"):
                            clean["hard_click"] = True
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

    def _show_empty_state(self, icon, title, subtitle):
        """Show centered empty state in the non-scrollable overlay."""
        self.steps_container.pack_forget()
        for w in self.combo_empty_state.winfo_children():
            w.destroy()
        self.combo_empty_state.pack(fill="both", expand=True, padx=PAD["md"], pady=PAD["xs"], before=self.result_verify_frame)

        # Center content using place
        center = ctk.CTkFrame(self.combo_empty_state, fg_color="transparent")
        center.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkLabel(center, text=icon, font=ctk.CTkFont(size=36)).pack()
        ctk.CTkLabel(
            center, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR["text_dim"]
        ).pack(pady=(8, 4))
        ctk.CTkLabel(
            center, text=subtitle,
            font=ctk.CTkFont(size=11),
            text_color=COLOR["text_muted"], justify="center"
        ).pack()

    def refresh_steps_view(self):
        for widget in self.steps_container.winfo_children():
            widget.destroy()

        if not self.current_combo_name:
            self._show_empty_state(
                "", "Select a macro",
                "Choose a macro from the left panel\nto view and edit its steps"
            )
            return

        macro_data = self.combos.get(self.current_combo_name, {"steps": []})
        steps = macro_data.get("steps", [])
        self._step_frames = []
        self._drop_indicator = None

        if not steps:
            self._show_empty_state(
                "", "No steps yet",
                "Use + Step, + Delay, or + Marker below\nto build your automation sequence"
            )
            return

        # Has steps — show scrollable container, hide empty state
        self.combo_empty_state.pack_forget()
        self.steps_container.pack(fill="both", expand=True, padx=PAD["md"], pady=PAD["xs"], before=self.result_verify_frame)
        for i, step_data in enumerate(steps):
            if isinstance(step_data, str): continue

            step_type = step_data.get("type", "click")
            
            # Determine fixed height + accent color per step type
            if step_type == "delay":
                step_height = 36
                border_color = COLOR["purple"]
            elif step_type == "marker":
                step_height = 52
                border_color = COLOR["warning"]
            else:
                step_height = 36
                border_color = COLOR["primary"]

            # Outer frame with left border effect
            frame = ctk.CTkFrame(self.steps_container, fg_color=COLOR["bg_subtle"], corner_radius=6, border_width=1, border_color=COLOR["border_subtle"], height=step_height)
            frame.pack(fill="x", pady=1, padx=4)
            frame.pack_propagate(False)
            frame._step_index = i
            self._step_frames.append(frame)

            # Color accent bar (left side)
            accent_bar = ctk.CTkFrame(frame, fg_color=border_color, width=3, corner_radius=0)
            accent_bar.pack(side="left", fill="y", padx=(0, 0))

            top_row = ctk.CTkFrame(frame, fg_color="transparent")
            top_row.pack(fill="x", padx=(4, 4), pady=(3, 0))
            
            # Pack right-side buttons FIRST so they never get pushed off
            del_step_btn = ctk.CTkButton(
                top_row, text="✕", width=24, height=24,
                fg_color="transparent", hover_color=COLOR["surface2"],
                text_color=COLOR["danger"], font=ctk.CTkFont(size=11),
                corner_radius=4,
                command=lambda idx=i: self.remove_step_from_combo(idx)
            )
            del_step_btn.pack(side="right", padx=1)
            
            edit_btn = ctk.CTkButton(
                top_row, text="✎", width=24, height=24,
                fg_color="transparent", hover_color=COLOR["surface2"],
                text_color=COLOR["text_dim"], font=ctk.CTkFont(size=11),
                corner_radius=4,
                command=lambda idx=i: self.edit_step(idx)
            )
            edit_btn.pack(side="right", padx=1)
            
            # Drag handle
            drag_handle = ctk.CTkLabel(top_row, text="⋮⋮", font=ctk.CTkFont(size=14), text_color=COLOR["text_muted"], width=16, cursor="fleur")
            drag_handle.pack(side="left", padx=(2, 6))
            drag_handle.bind("<Button-1>", lambda e, idx=i: self._drag_start(e, idx))
            drag_handle.bind("<B1-Motion>", self._drag_motion)
            drag_handle.bind("<ButtonRelease-1>", self._drag_drop)
            
            # Step label - builds text
            if step_type == "delay":
                delay_ms = step_data.get('time', 1000)
                num_lbl = ctk.CTkLabel(top_row, text=f"{i+1}.", font=ctk.CTkFont(size=12), text_color=COLOR["text_muted"], width=20)
                num_lbl.pack(side="left", padx=(0, 4))
                lbl = ctk.CTkLabel(top_row, text=f"Delay: {delay_ms}ms", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR["purple"], anchor="w")
                lbl.pack(side="left", fill="x", expand=True)
            elif step_type == "marker":
                marker_name = step_data.get('marker', 'None')
                mode_short = step_data.get('mode', 'Wait until Appear').replace('Wait until ', '')
                hold_ms = step_data.get('time', '0')
                timeout_ms = step_data.get('timeout', '0')
                fail_img = step_data.get('fail_image', 'None')
                
                num_lbl = ctk.CTkLabel(top_row, text=f"{i+1}.", font=ctk.CTkFont(size=12), text_color=COLOR["text_muted"], width=20)
                num_lbl.pack(side="left", padx=(0, 4))
                lbl = ctk.CTkLabel(top_row, text=f"Wait: {marker_name} — {mode_short}", font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR["warning"], anchor="w")
                lbl.pack(side="left", fill="x", expand=True)
                
                # Sub-text line for hold/timeout/fail info
                sub_parts = [f"hold {hold_ms}ms"]
                if str(timeout_ms) != '0': sub_parts.append(f"timeout {timeout_ms}ms")
                if fail_img and fail_img != 'None': sub_parts.append(f"fail: {fail_img}")
                sub_text = " · ".join(sub_parts)
                sub_lbl = ctk.CTkLabel(frame, text=sub_text, font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"], anchor="w")
                sub_lbl.pack(fill="x", padx=(30, 8), pady=(0, 4))
            else:
                num_lbl = ctk.CTkLabel(top_row, text=f"{i+1}.", font=ctk.CTkFont(size=12), text_color=COLOR["text_muted"], width=20)
                num_lbl.pack(side="left", padx=(0, 4))
                click_label = f"Click: {step_data.get('node', '?')}"
                if step_data.get('hard_click'):
                    click_label = f"⚡ Hard Click: {step_data.get('node', '?')}"
                lbl = ctk.CTkLabel(top_row, text=click_label, font=ctk.CTkFont(size=12, weight="bold"), text_color=COLOR["text"], anchor="w")
                lbl.pack(side="left", fill="x", expand=True)

    def _drag_start(self, event, index):
        self._drag_index = index
        self._drag_current_pos = index
        self._last_drag_target = index
        self._drag_last_time = 0
        
        # Build virtual order
        self._drag_order = list(range(len(self._step_frames)))
        
        # Highlight dragged item (set once, no need to re-set on every motion)
        if 0 <= index < len(self._step_frames):
            self._step_frames[index].configure(
                border_width=2, border_color=COLOR["primary"],
                fg_color=COLOR["surface2"]
            )
    
    def _drag_motion(self, event):
        if not hasattr(self, '_drag_index') or self._drag_index is None:
            return
        
        # Time throttle: skip if less than 50ms since last update
        import time as _time
        now = _time.time()
        if now - self._drag_last_time < 0.05:
            return
        self._drag_last_time = now
        
        try:
            mouse_y = event.widget.winfo_rooty() + event.y
        except:
            return
        
        # Find which position the mouse is over
        target_pos = len(self._step_frames) - 1
        for pos, orig_idx in enumerate(self._drag_order):
            frame = self._step_frames[orig_idx]
            try:
                frame_top = frame.winfo_rooty()
                frame_h = frame.winfo_height()
                if mouse_y < frame_top + frame_h / 2:
                    target_pos = pos
                    break
            except:
                continue
        
        # Only repack if target actually changed
        if self._last_drag_target == target_pos:
            return
        self._last_drag_target = target_pos
        
        # Rebuild virtual order
        src_idx = self._drag_index
        new_order = [i for i in self._drag_order if i != src_idx]
        new_order.insert(target_pos, src_idx)
        self._drag_order = new_order
        
        # Repack frames in new order (single loop)
        for orig_idx in new_order:
            self._step_frames[orig_idx].pack_forget()
        for orig_idx in new_order:
            self._step_frames[orig_idx].pack(fill="x", pady=1, padx=4)
    
    def _drag_drop(self, event):
        if not hasattr(self, '_drag_index') or self._drag_index is None:
            return
        
        # Reset all frame visuals
        for f in self._step_frames:
            f.configure(border_width=1, border_color=COLOR["border_subtle"], fg_color=COLOR["bg_subtle"])
        
        # Apply the new order to actual data
        if self.current_combo_name and hasattr(self, '_drag_order'):
            steps = self.combos[self.current_combo_name]["steps"]
            if len(self._drag_order) == len(steps):
                new_steps = [steps[i] for i in self._drag_order]
                self.combos[self.current_combo_name]["steps"] = new_steps
                self.save_combos()
                self.refresh_steps_view()
        
        self._drag_index = None
        self._drag_current_pos = None
        self._last_drag_target = None
        self._drag_order = None

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
            self._show_styled_info("No Target Nodes", "Add nodes in the Setup tab first")
            return
        
        top = ctk.CTkToplevel(self)
        top.title("Lordbot Control")
        top.geometry("380x250")
        top.resizable(False, False)
        top.configure(fg_color=COLOR["surface"])
        top.transient(self)
        top.grab_set()
        top.after(200, lambda: top.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        top.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 380) // 2
        y = self.winfo_y() + (self.winfo_height() - 250) // 2
        top.geometry(f"380x250+{x}+{y}")

        ctk.CTkLabel(
            top, text=f"Edit Click — Step {index+1}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR["primary"]
        ).pack(pady=(16, 8))

        form = ctk.CTkFrame(top, fg_color="transparent")
        form.pack(fill="x", padx=20)

        ctk.CTkLabel(form, text="Target Image:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        cb_node = ctk.CTkOptionMenu(form, values=valid_nodes, fg_color=COLOR["bg"], button_color=COLOR["border"], corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        cb_node.set(step_data.get("node", valid_nodes[0]))
        cb_node.pack(fill="x", pady=(0, 8))

        # Hard Click toggle
        hard_click_var = ctk.BooleanVar(value=step_data.get("hard_click", False))
        hc_row = ctk.CTkFrame(form, fg_color="transparent")
        hc_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(hc_row, text="⚡ Hard Click:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(side="left")
        ctk.CTkSwitch(
            hc_row, text="Click at saved position",
            variable=hard_click_var, onvalue=True, offvalue=False,
            font=ctk.CTkFont(size=10), text_color=COLOR["text_dim"],
            fg_color=COLOR["border"], progress_color=COLOR["primary"],
            height=20
        ).pack(side="left", padx=(8, 0))

        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 12))

        def _save():
            step_data["node"] = cb_node.get()
            step_data["hard_click"] = hard_click_var.get()
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
            
        ctk.CTkButton(
            btn_row, text="Save", command=_save,
            fg_color=COLOR["primary"], hover_color=COLOR["surface2"],
            text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Cancel", command=top.destroy,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def edit_step_delay(self, index):
        if not self.current_combo_name: return
        step_data = self.combos[self.current_combo_name]["steps"][index]
        
        top = ctk.CTkToplevel(self)
        top.title("Lordbot Control")
        top.geometry("340x200")
        top.resizable(False, False)
        top.configure(fg_color=COLOR["surface"])
        top.transient(self)
        top.grab_set()
        top.after(200, lambda: top.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        top.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 200) // 2
        top.geometry(f"340x200+{x}+{y}")

        ctk.CTkLabel(
            top, text=f"Edit Delay — Step {index+1}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR["purple"]
        ).pack(pady=(16, 8))

        form = ctk.CTkFrame(top, fg_color="transparent")
        form.pack(fill="x", padx=20)

        ctk.CTkLabel(form, text="Delay Duration (ms):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        entry_time = ctk.CTkEntry(form, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        entry_time.insert(0, str(step_data.get("time", 1000)))
        entry_time.pack(fill="x", pady=(0, 8))
        
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 12))

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
            
        ctk.CTkButton(
            btn_row, text="Save", command=_save,
            fg_color=COLOR["purple"], hover_color=COLOR["surface2"],
            text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Cancel", command=top.destroy,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def edit_step_marker(self, index):
        if not self.current_combo_name: return
        step_data = self.combos[self.current_combo_name]["steps"][index]
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            self._show_styled_info("No Target Nodes", "Add nodes in the Setup tab first")
            return
        
        top = ctk.CTkToplevel(self)
        top.title("Lordbot Control")
        top.geometry("400x340")
        top.resizable(False, False)
        top.configure(fg_color=COLOR["surface"])
        top.transient(self)
        top.grab_set()
        top.after(200, lambda: top.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        top.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 340) // 2
        top.geometry(f"400x340+{x}+{y}")

        ctk.CTkLabel(
            top, text=f"Edit Marker — Step {index+1}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR["warning"]
        ).pack(pady=(16, 8))

        form = ctk.CTkFrame(top, fg_color="transparent")
        form.pack(fill="x", padx=20)

        ctk.CTkLabel(form, text="Wait for Image:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        cb_marker = ctk.CTkOptionMenu(form, values=valid_nodes, fg_color=COLOR["bg"], button_color=COLOR["border"], corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        cb_marker.set(step_data.get("marker", valid_nodes[0]))
        cb_marker.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(form, text="Condition:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        cb_mode = ctk.CTkOptionMenu(form, values=["Wait until Appear", "Wait until Disappear"], fg_color=COLOR["bg"], button_color=COLOR["border"], corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        cb_mode.set(step_data.get("mode", "Wait until Appear"))
        cb_mode.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(form, text="Hold Duration (ms):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        entry_time = ctk.CTkEntry(form, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        entry_time.insert(0, str(step_data.get("time", "0")))
        entry_time.pack(fill="x", pady=(0, 8))
        
        # Advanced section (collapsible)
        adv_widgets = ctk.CTkFrame(top, fg_color=COLOR["bg"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
        
        ctk.CTkLabel(adv_widgets, text="Timeout (ms, 0=no limit):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(pady=(10, 0), anchor="w", padx=15)
        entry_timeout = ctk.CTkEntry(adv_widgets, fg_color=COLOR["surface"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=28, font=ctk.CTkFont(size=11))
        entry_timeout.insert(0, str(step_data.get("timeout", "0")))
        entry_timeout.pack(fill="x", padx=15, pady=4)
        
        ctk.CTkLabel(adv_widgets, text="Fail Image:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(pady=(6, 0), anchor="w", padx=15)
        fail_nodes = ["None"] + valid_nodes
        cb_fail = ctk.CTkOptionMenu(adv_widgets, values=fail_nodes, fg_color=COLOR["surface"], button_color=COLOR["border"], corner_radius=6, height=28, font=ctk.CTkFont(size=11))
        cb_fail.set(step_data.get("fail_image", "None"))
        cb_fail.pack(fill="x", padx=15, pady=4)
        
        ctk.CTkLabel(adv_widgets, text="Fail Condition:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(pady=(6, 0), anchor="w", padx=15)
        cb_fail_mode = ctk.CTkOptionMenu(adv_widgets, values=["Fail if Appear", "Fail if Disappear"], fg_color=COLOR["surface"], button_color=COLOR["border"], corner_radius=6, height=28, font=ctk.CTkFont(size=11))
        cb_fail_mode.set(step_data.get("fail_mode", "Fail if Appear"))
        cb_fail_mode.pack(fill="x", padx=15, pady=(4, 10))
        
        adv_visible = [False]
        def _toggle_adv():
            if adv_visible[0]:
                adv_widgets.pack_forget()
                adv_btn.configure(text="▼ Advanced")
                top.geometry("400x340")
            else:
                adv_widgets.pack(fill="x", padx=20, pady=4, after=adv_btn)
                top.geometry("400x570")
            adv_visible[0] = not adv_visible[0]
        
        adv_btn = ctk.CTkButton(
            top, text="▼ Advanced", command=_toggle_adv,
            fg_color="transparent", text_color=COLOR["text_muted"],
            hover_color=COLOR["surface2"], font=ctk.CTkFont(size=11), height=24
        )
        adv_btn.pack(pady=(4, 0))

        # Bottom buttons
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=20, pady=(0, 12))

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

        ctk.CTkButton(
            btn_row, text="Save", command=_save,
            fg_color=COLOR["warning"], hover_color="#E67E22",
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
        
        # Auto-expand if advanced fields are set
        has_adv = str(step_data.get("timeout", "0")) != "0" or step_data.get("fail_image", "None") != "None"
        if has_adv:
            _toggle_adv()

    def add_new_combo(self):
        # Custom styled dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("360x180")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))

        # Center over main window
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 360) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"360x180+{x}+{y}")

        result = {"name": None}

        ctk.CTkLabel(
            dialog, text="Enter macro name",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR["text"]
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            dialog, text="e.g. Buy Potion, Farm Route ...",
            font=ctk.CTkFont(size=10),
            text_color=COLOR["text_muted"]
        ).pack(pady=(0, 8))

        entry = ctk.CTkEntry(
            dialog, fg_color=COLOR["bg"], border_color=COLOR["border"],
            border_width=1, corner_radius=6, height=34,
            font=ctk.CTkFont(size=12), text_color=COLOR["text"],
            placeholder_text="Macro name...", placeholder_text_color=COLOR["text_muted"]
        )
        entry.pack(fill="x", padx=24, pady=(0, 12))
        entry.focus_set()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))

        def on_ok(*_):
            result["name"] = entry.get()
            dialog.destroy()

        def on_cancel(*_):
            dialog.destroy()

        entry.bind("<Return>", on_ok)
        entry.bind("<Escape>", on_cancel)

        ctk.CTkButton(
            btn_row, text="Create", command=on_ok,
            fg_color=COLOR["primary"], hover_color=COLOR["surface2"],
            text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Cancel", command=on_cancel,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"),
            height=30, corner_radius=6
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        dialog.wait_window()

        name = result["name"]
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
            # Styled info dialog
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
            ctk.CTkLabel(info, text="No macros selected", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["text"]).pack(pady=(20, 4))
            ctk.CTkLabel(info, text="Tick checkboxes to select macros first", font=ctk.CTkFont(size=11), text_color=COLOR["text_muted"]).pack(pady=(0, 12))
            ctk.CTkButton(info, text="OK", command=info.destroy, fg_color=COLOR["primary"], text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"), height=30, corner_radius=6, width=100).pack()
            return

        # Styled confirm dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("360x160")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 360) // 2
        y = self.winfo_y() + (self.winfo_height() - 160) // 2
        dialog.geometry(f"360x160+{x}+{y}")

        result = {"confirmed": False}

        ctk.CTkLabel(
            dialog, text="Confirm Delete",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR["warning"]
        ).pack(pady=(20, 4))

        names_preview = ", ".join(to_delete[:3]) + ("..." if len(to_delete) > 3 else "")
        ctk.CTkLabel(
            dialog, text=f"Delete {len(to_delete)} macro(s)?\n{names_preview}",
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
            for cname in to_delete:
                if cname in self.combos:
                    del self.combos[cname]
                if self.current_combo_name == cname:
                    self.current_combo_name = None
                    self.combo_name_label.configure(text="[Deleted]")
                    self.refresh_steps_view()

                    
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

    def add_step_to_combo(self):
        if not self.current_combo_name:
            self._show_styled_info("Select a macro", "Choose a macro from the left panel first")
            return
        
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            self._show_styled_info("No Target Nodes", "Add nodes in the Setup tab first")
            return
            
        top = ctk.CTkToplevel(self)
        top.title("Lordbot Control")
        top.geometry("380x420")
        top.resizable(False, False)
        top.configure(fg_color=COLOR["surface"])
        top.transient(self)
        top.grab_set()
        top.after(200, lambda: top.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        top.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 380) // 2
        y = self.winfo_y() + (self.winfo_height() - 420) // 2
        top.geometry(f"380x420+{x}+{y}")

        ctk.CTkLabel(
            top, text="Add Click Steps",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR["primary"]
        ).pack(pady=(16, 2))
        ctk.CTkLabel(
            top, text="Select nodes · numbered by selection order",
            font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"]
        ).pack(pady=(0, 8))
        
        ctk.CTkFrame(top, fg_color=COLOR["border_subtle"], height=1).pack(fill="x", padx=16)
        
        scroll_frame = ctk.CTkScrollableFrame(
            top, fg_color=COLOR["bg"],
            scrollbar_button_color=COLOR["border"],
            scrollbar_button_hover_color=COLOR["text_muted"],
            corner_radius=8
        )
        scroll_frame.pack(fill="both", expand=True, padx=16, pady=8)
        
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
            chk = ctk.CTkCheckBox(
                scroll_frame, text=node, variable=var,
                command=lambda n=node, v=var: on_check(n, v),
                checkbox_width=18, checkbox_height=18, corner_radius=4,
                border_width=1, font=ctk.CTkFont(size=12),
                text_color=COLOR["text_dim"], border_color=COLOR["border"],
                hover_color=COLOR["surface2"]
            )
            chk.pack(anchor="w", pady=4, padx=8)
            checkboxes[node] = chk

        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        def _add():
            if not selected_nodes_order: return
            for node_val in selected_nodes_order:
                step_obj = {"node": node_val, "marker": "None", "mode": "Wait until Appear", "time": "0"}
                self.combos[self.current_combo_name]["steps"].append(step_obj)
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
            
        ctk.CTkButton(
            btn_row, text="Add Selected", command=_add,
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

    def add_delay_to_combo(self):
        if not self.current_combo_name:
            self._show_styled_info("Select a macro", "Choose a macro from the left panel first")
            return
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("340x190")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 190) // 2
        dialog.geometry(f"340x190+{x}+{y}")

        result = {"val": None}

        ctk.CTkLabel(
            dialog, text="Add Delay Step",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR["purple"]
        ).pack(pady=(16, 4))
        ctk.CTkLabel(
            dialog, text="Pause duration in milliseconds",
            font=ctk.CTkFont(size=10), text_color=COLOR["text_muted"]
        ).pack(pady=(0, 8))

        entry = ctk.CTkEntry(
            dialog, fg_color=COLOR["bg"], border_color=COLOR["border"],
            border_width=1, corner_radius=6, height=34,
            font=ctk.CTkFont(size=12), text_color=COLOR["text"],
            placeholder_text="e.g. 1000", placeholder_text_color=COLOR["text_muted"]
        )
        entry.pack(fill="x", padx=24, pady=(0, 12))
        entry.insert(0, "1000")
        entry.select_range(0, "end")
        entry.focus_set()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 16))

        def on_ok(*_):
            try:
                val = float(entry.get())
                if val < 100: val = 100
                if val > 300000: val = 300000
                result["val"] = val
            except ValueError: return
            dialog.destroy()

        entry.bind("<Return>", on_ok)
        entry.bind("<Escape>", lambda _: dialog.destroy())

        ctk.CTkButton(
            btn_row, text="Add Delay", command=on_ok,
            fg_color=COLOR["purple"], hover_color=COLOR["surface2"],
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

        if result["val"] is not None:
            step_obj = {"type": "delay", "time": result["val"]}
            self.combos[self.current_combo_name]["steps"].append(step_obj)
            self.save_combos()
            self.refresh_steps_view()

    def add_marker_to_combo(self):
        if not self.current_combo_name:
            self._show_styled_info("Select a macro", "Choose a macro from the left panel first")
            return
        
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            self._show_styled_info("No Target Nodes", "Add nodes in the Setup tab first")
            return
        
        top = ctk.CTkToplevel(self)
        top.title("Lordbot Control")
        top.geometry("400x340")
        top.resizable(False, False)
        top.configure(fg_color=COLOR["surface"])
        top.transient(self)
        top.grab_set()
        top.after(200, lambda: top.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        top.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 340) // 2
        top.geometry(f"400x340+{x}+{y}")

        ctk.CTkLabel(
            top, text="Add Marker Step",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR["warning"]
        ).pack(pady=(16, 8))

        form = ctk.CTkFrame(top, fg_color="transparent")
        form.pack(fill="x", padx=20)

        ctk.CTkLabel(form, text="Wait for Image:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        cb_marker = ctk.CTkOptionMenu(form, values=valid_nodes, fg_color=COLOR["bg"], button_color=COLOR["border"], corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        cb_marker.set(valid_nodes[0])
        cb_marker.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(form, text="Condition:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        cb_mode = ctk.CTkOptionMenu(form, values=["Wait until Appear", "Wait until Disappear"], fg_color=COLOR["bg"], button_color=COLOR["border"], corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        cb_mode.set("Wait until Appear")
        cb_mode.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(form, text="Hold Duration (ms):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(anchor="w", pady=(0, 2))
        entry_time = ctk.CTkEntry(form, fg_color=COLOR["bg"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        entry_time.insert(0, "2000")
        entry_time.pack(fill="x", pady=(0, 8))
        
        # Advanced section (collapsible)
        adv_widgets = ctk.CTkFrame(top, fg_color=COLOR["bg"], corner_radius=8, border_width=1, border_color=COLOR["border_subtle"])
        
        ctk.CTkLabel(adv_widgets, text="Timeout (ms, 0=no limit):", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(pady=(10, 0), anchor="w", padx=15)
        entry_timeout = ctk.CTkEntry(adv_widgets, fg_color=COLOR["surface"], border_color=COLOR["border"], border_width=1, corner_radius=6, height=28, font=ctk.CTkFont(size=11))
        entry_timeout.insert(0, "0")
        entry_timeout.pack(fill="x", padx=15, pady=4)
        
        ctk.CTkLabel(adv_widgets, text="Fail Image:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(pady=(6, 0), anchor="w", padx=15)
        fail_nodes = ["None"] + valid_nodes
        cb_fail = ctk.CTkOptionMenu(adv_widgets, values=fail_nodes, fg_color=COLOR["surface"], button_color=COLOR["border"], corner_radius=6, height=28, font=ctk.CTkFont(size=11))
        cb_fail.set("None")
        cb_fail.pack(fill="x", padx=15, pady=4)
        
        ctk.CTkLabel(adv_widgets, text="Fail Condition:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["text"]).pack(pady=(6, 0), anchor="w", padx=15)
        cb_fail_mode = ctk.CTkOptionMenu(adv_widgets, values=["Fail if Appear", "Fail if Disappear"], fg_color=COLOR["surface"], button_color=COLOR["border"], corner_radius=6, height=28, font=ctk.CTkFont(size=11))
        cb_fail_mode.set("Fail if Appear")
        cb_fail_mode.pack(fill="x", padx=15, pady=(4, 10))
        
        adv_visible = [False]
        def _toggle_adv():
            if adv_visible[0]:
                adv_widgets.pack_forget()
                adv_btn.configure(text="▼ Advanced")
                top.geometry("400x340")
            else:
                adv_widgets.pack(fill="x", padx=20, pady=4, after=adv_btn)
                top.geometry("400x570")
            adv_visible[0] = not adv_visible[0]
        
        adv_btn = ctk.CTkButton(
            top, text="▼ Advanced", command=_toggle_adv,
            fg_color="transparent", text_color=COLOR["text_muted"],
            hover_color=COLOR["surface2"], font=ctk.CTkFont(size=11), height=24
        )
        adv_btn.pack(pady=(4, 0))

        # Bottom buttons
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=20, pady=(0, 12))

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

        ctk.CTkButton(
            btn_row, text="Add Marker", command=_add,
            fg_color=COLOR["warning"], hover_color="#E67E22",
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

    def _show_styled_info(self, title, text):
        """Reusable styled info popup."""
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

    def remove_step_from_combo(self, index):
        if not self.current_combo_name: return
        self.combos[self.current_combo_name]["steps"].pop(index)
        self.save_combos()
        self.refresh_steps_view()

    def play_current_combo(self):
        if not self.current_combo_name:
            self._show_styled_info("Select a macro", "Choose a macro from the left panel first")
            return
        macro_data = self.combos.get(self.current_combo_name, {"steps": []})
        steps = macro_data.get("steps", [])
        if not steps:
            messagebox.showwarning("Empty", "This Macro has no steps configured.")
            return
        
        port_str = self.footer_port_input.get().strip()
        port = int(port_str) if port_str.isdigit() else 9222
        tab_id_str = self.footer_tab_input.get().strip()
        tab_id = int(tab_id_str) if tab_id_str.isdigit() else 0
            
        if messagebox.askyesno("Execute Macro", f"Execute Macro [{self.current_combo_name}] on Port {port}, Tab {tab_id}?"):
            threading.Thread(target=self._macro_execution_worker, args=(macro_data, tab_id, port), daemon=True).start()

    def _macro_execution_worker(self, macro_data, tab_id=0, port=9222):
        self.log_gui(f"============== MACRO STARTING ==============")
        steps = macro_data.get("steps", [])
        threshold_val = self.slider.get()
        
        from cdp_client import CDPClient
        cdp_client = None
        
        if tab_id is not None:
             try:
                 self.log_gui(f"[Macro] Connecting to Port {port}, Tab {tab_id}...")
                 cdp_client = CDPClient.connect(port=port, tab_index=tab_id)
                 
                 # Log available tabs
                 tabs = CDPClient.list_tabs(port)
                 for idx_t, t in enumerate(tabs):
                     self.log_gui(f"[Macro]   Tab {idx_t}: {t.get('title', '?')[:25]}")
                 self.log_gui(f"[Macro] Hooked to Tab {tab_id}: {cdp_client.url[:60]}")
             except Exception as e:
                 self.log_gui(f"[Test Macro] Connection failed: {e}")
                 return
        else:
            self.log_gui(f"[Test Macro] Running in foreground (PyAutoGUI focus)")
        
        bot_instance = BotAction(cdp_client=cdp_client, debug_visual_var=self.debug_visual_var)
        
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
                        if cdp_client:
                            try: frame_bytes = cdp_client.screenshot()
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

                # ── HARD CLICK: skip detection, click at saved coordinates ──
                if step_data.get("hard_click"):
                    from node_features import get_click_zone, load_meta
                    zone = get_click_zone(filepath)
                    if zone:
                        cx, cy, w, h = zone
                        # Random point within 70% of the zone (avoid edge pixels)
                        rx = cx + random.randint(-w * 35 // 100, w * 35 // 100)
                        ry = cy + random.randint(-h * 35 // 100, h * 35 // 100)
                        # Debug: log full coordinate chain
                        meta = load_meta(filepath)
                        lp = meta.get('learned_position', {})
                        cp = meta.get('capture_position', {})
                        self.log_gui(f"        -> ⚡ Hard Click '{node_name}'")
                        self.log_gui(f"           learned_pos=({lp.get('x','?')},{lp.get('y','?')}) count={lp.get('count','?')}")
                        self.log_gui(f"           capture_pos=({cp.get('x','?')},{cp.get('y','?')}) [NOT USED]")
                        self.log_gui(f"           zone=({cx},{cy}) template={w}x{h}")
                        self.log_gui(f"           click_raw=({rx},{ry})")
                        try:
                            dpr = float(cdp_client.evaluate("window.devicePixelRatio")) if cdp_client else 1.0
                            self.log_gui(f"           DPR={dpr} -> css=({rx/dpr:.0f},{ry/dpr:.0f})")
                        except: pass
                        bot_instance.click_at(rx, ry, randomize=False)
                        time.sleep(random.uniform(1.2, 2.0))
                        continue
                    else:
                        self.log_gui(f"        -> ⚡ Hard Click: No learned position yet (need ≥1 detection). Falling back.")

                # ── Normal detect-then-click ──
                found = False
                for attempt in range(5):
                    frame_bytes = None
                    if cdp_client:
                        try: frame_bytes = cdp_client.screenshot()
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
            if cdp_client:
                try: cdp_client.close()
                except: pass
        self.log_gui(f"============== MACRO FINISHED ==============")
