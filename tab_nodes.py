"""Nodes tab mixin — Template tracking, testing, snipping."""
import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import os
import pyautogui
from PIL import Image
import json
from node_features import (precompute_features, batch_precompute, save_capture_position,
                           reset_learned_position, update_learned_position,
                           save_hard_click_position)

from constants import COLOR, FONT, PAD, RADIUS


class NodesMixin:
    """Mixin for the Nodes/Tracker tab. Mixed into BotApp."""

    def setup_tracker_tab(self):
        self.tracked_icons = {}
        self.current_selected_name = None
        self.icon_buttons = {}
        self.icon_checkbox_vars = {}
        self.is_tracking = False
        self.node_thresholds = {}  # per-node threshold: {name: float}
        self._load_node_thresholds()

        os.makedirs("trackers", exist_ok=True)

        self.tab_setup.grid_columnconfigure(0, weight=1, minsize=220)
        self.tab_setup.grid_columnconfigure(1, weight=3)
        self.tab_setup.grid_rowconfigure(0, weight=1)

        # Helper to blur searchbox - called from various click handlers
        def _blur_search_entry(event=None):
            if hasattr(self, 'node_search_entry'):
                try: self.tab_setup.focus_set()
                except: pass
        self._blur_search_entry = _blur_search_entry

        # ====== LEFT PANE (Panel card) ======
        self.left_pane = ctk.CTkFrame(self.tab_setup, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border_subtle"])
        self.left_pane.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        # -- Title row with inline action buttons --
        title_row = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        title_row.pack(fill="x", padx=PAD["md"], pady=(PAD["md"], PAD["sm"]))

        ctk.CTkLabel(
            title_row, text="TARGET NODES",
            text_color=COLOR["text_dim"],
            font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11)
        ).pack(side="left")

        # Inline text-link buttons (right side of title row)
        self.del_selected_btn = ctk.CTkButton(
            title_row, text="Delete", command=self.delete_selected_targets,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"),
            width=50, height=24, corner_radius=4
        )
        self.del_selected_btn.pack(side="right", padx=(2, 0))

        # Learn All button — right next to Delete
        self.learn_btn = ctk.CTkButton(
            title_row, text="⚡ Learn", command=self._learn_all_nodes,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["warning"], font=ctk.CTkFont(size=11, weight="bold"),
            width=55, height=24, corner_radius=4
        )
        self.learn_btn.pack(side="right", padx=(2, 0))

        self.add_btn = ctk.CTkButton(
            title_row, text="+ Add", command=self.add_new_target,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["primary"], font=ctk.CTkFont(size=11, weight="bold"),
            width=50, height=24, corner_radius=4
        )
        self.add_btn.pack(side="right", padx=(0, 2))

        # Search bar
        self._search_debounce_id = None
        def _debounced_search(*a):
            if self._search_debounce_id:
                self.after_cancel(self._search_debounce_id)
            self._search_debounce_id = self.after(150, self.refresh_tracked_list)
        self.node_search_entry = ctk.CTkEntry(
            self.left_pane, placeholder_text="Search nodes...",
            placeholder_text_color=COLOR["text_muted"],
            fg_color=COLOR["bg"], corner_radius=6, height=30,
            border_width=1, border_color=COLOR["border_subtle"]
        )
        self.node_search_entry._entry.bind("<KeyRelease>", _debounced_search)
        self.node_search_entry.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        # Select All (simple text label + small checkbox)
        self.node_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.left_pane, fg_color="transparent", height=24)
        sa_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["xs"]))
        ctk.CTkCheckBox(
            sa_row, text="Select All", variable=self.node_select_all_var,
            command=self._toggle_select_all_nodes,
            checkbox_width=18, checkbox_height=18, corner_radius=4,
            border_width=1, font=ctk.CTkFont(size=11),
            text_color=COLOR["text_muted"], border_color=COLOR["border"],
            hover_color=COLOR["surface2"]
        ).pack(side="left")

        # Scrollable node list
        self.btn_container = ctk.CTkScrollableFrame(
            self.left_pane, fg_color="transparent",
            scrollbar_button_color=COLOR["border"],
            scrollbar_button_hover_color=COLOR["text_muted"]
        )
        self.btn_container.pack(fill="both", expand=True, padx=2, pady=(0, PAD["xs"]))

        # ====== RIGHT PANE ======
        self.right_pane = ctk.CTkFrame(self.tab_setup, fg_color=COLOR["bg"], corner_radius=0)
        self.right_pane.grid(row=0, column=1, sticky="nsew", padx=(PAD["sm"], PAD["lg"]), pady=PAD["lg"])
        self.right_pane.bind("<Button-1>", self._blur_search_entry)

        # Detail area card
        self.detail_area = ctk.CTkFrame(self.right_pane, fg_color=COLOR["surface"], corner_radius=12)
        self.detail_area.pack(fill="both", expand=True)

        # Header bar with bottom separator
        self.top_bar = ctk.CTkFrame(self.detail_area, fg_color="transparent", height=38)
        self.top_bar.pack(fill="x", padx=6, pady=(6, 0))
        self.top_bar.pack_propagate(False)
        self.preview_title = ctk.CTkLabel(
            self.top_bar, text="TEMPLATE PREVIEW",
            font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11),
            text_color=COLOR["text_dim"]
        )
        self.preview_title.pack(side="left", padx=PAD["sm"], pady=PAD["sm"])
        ctk.CTkFrame(self.detail_area, height=1, fg_color=COLOR["border_subtle"]).pack(fill="x", padx=6)

        # Detail body
        self.detail_body = ctk.CTkFrame(self.detail_area, fg_color="transparent")
        self.detail_body.pack(fill="both", expand=True, padx=PAD["md"], pady=PAD["sm"])

        self.preview_name_frame = ctk.CTkFrame(self.detail_body, fg_color="transparent")
        self.preview_name_frame.pack(anchor="w", pady=(0, PAD["sm"]))
        self.preview_name_label = ctk.CTkLabel(
            self.preview_name_frame, text="No Target Selected",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.preview_name_label.pack(side="left")
        # Badge-style status label (hidden by default)
        self.preview_status_label = ctk.CTkLabel(
            self.preview_name_frame, text="",
            text_color=COLOR["success"],
            fg_color=COLOR["success_dim"],
            font=ctk.CTkFont(weight="bold", size=10),
            corner_radius=10, padx=8, pady=2
        )

        self.preview_image_label = ctk.CTkLabel(
            self.detail_body, text="[Select any target Node to view details]",
            text_color=COLOR["text_muted"], fg_color=COLOR["bg"],
            corner_radius=RADIUS, height=180
        )
        self.preview_image_label.pack(fill="x", pady=(0, PAD["xs"]), expand=True)

        self.preview_size_label = ctk.CTkLabel(
            self.detail_body, text="", text_color=COLOR["text_muted"],
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.preview_size_label.pack(anchor="e", pady=(0, PAD["xs"]))

        # Test Result Notification Banner
        self.test_notif_frame = ctk.CTkFrame(self.detail_area, fg_color=COLOR["bg_subtle"], corner_radius=8, height=0)
        self.test_notif_label = ctk.CTkLabel(self.test_notif_frame, text="", font=ctk.CTkFont(family="Inter", size=11), text_color=COLOR["text_dim"], wraplength=500, justify="left")
        self.test_notif_label.pack(padx=12, pady=6, anchor="w")
        self._test_notif_hide_id = None

        # Action buttons
        self.target_controls = ctk.CTkFrame(self.detail_area, fg_color="transparent")
        self.target_controls.pack(side="bottom", fill="x", pady=PAD["sm"], padx=PAD["md"])

        # Settings Section — row-based layout matching mockup
        self.settings_frame = ctk.CTkFrame(
            self.detail_body, fg_color=COLOR["bg_subtle"],
            corner_radius=RADIUS, border_width=1, border_color=COLOR["border_subtle"]
        )
        self.settings_frame.pack(fill="x", pady=(0, 0))

        # Row 1: Threshold slider
        thresh_row = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        thresh_row.pack(fill="x", padx=PAD["md"], pady=(PAD["sm"], PAD["xs"]))

        self.thresh_label = ctk.CTkLabel(
            thresh_row, text="Accuracy Threshold:",
            font=ctk.CTkFont(size=12), text_color=COLOR["text_dim"]
        )
        self.thresh_label.pack(side="left")

        self.thresh_value_label = ctk.CTkLabel(
            thresh_row, text="0.85",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=COLOR["text_dim"]
        )
        self.thresh_value_label.pack(side="right")

        self.slider = ctk.CTkSlider(
            thresh_row, from_=0.5, to=0.99,
            command=self._on_threshold_change,
            progress_color=COLOR["primary"], button_color=COLOR["text"],
            button_hover_color=COLOR["primary"],
            height=14, width=200
        )
        self.slider.pack(side="right", padx=(PAD["sm"], PAD["sm"]))

        saved_thresh = 0.7
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    cfg = json.load(f)
                saved_thresh = cfg.get("threshold", 0.7)
        except: pass
        self.slider.set(saved_thresh)
        self.thresh_value_label.configure(text=f"{saved_thresh:.2f}")
        self._default_threshold = saved_thresh  # Global default for nodes without per-node threshold

        # Row 2: Debug toggle
        debug_row = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        debug_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        ctk.CTkLabel(
            debug_row, text="Show Click Position (Red Dot)",
            font=ctk.CTkFont(size=12), text_color=COLOR["text_dim"]
        ).pack(side="left")

        self.debug_toggle_switch = ctk.CTkSwitch(
            debug_row, text="",
            variable=self.debug_visual_var, onvalue=True, offvalue=False,
            progress_color=COLOR["primary"], button_color=COLOR["text"],
            button_hover_color=COLOR["primary"],
            width=36, height=20
        )
        self.debug_toggle_switch.pack(side="right")

        # Action buttons — outline style, clean in both states
        self.test_node_btn = ctk.CTkButton(
            self.target_controls, text="Test Node", command=self.test_current_node,
            fg_color="transparent", hover_color="#2A5A4A",
            border_width=1, border_color="#3D8B6E",
            text_color="#3D8B6E", state="disabled",
            font=ctk.CTkFont(weight="bold", size=11), corner_radius=6, height=32
        )
        self.test_node_btn.pack(side="left", padx=(0, 4), expand=True, fill="x")

        self.recapture_btn = ctk.CTkButton(
            self.target_controls, text="Re-Capture", command=self.recapture_current,
            fg_color="transparent", hover_color="#2A3D5A",
            border_width=1, border_color=COLOR["primary"],
            text_color=COLOR["primary"],
            state="disabled", font=ctk.CTkFont(weight="bold", size=11),
            corner_radius=6, height=32
        )
        self.recapture_btn.pack(side="left", padx=4, expand=True, fill="x")

        self.delete_btn = ctk.CTkButton(
            self.target_controls, text="Delete Node", command=self.delete_current,
            fg_color="transparent", hover_color="#4A2A2A",
            border_width=1, border_color=COLOR["danger"],
            text_color=COLOR["danger"],
            state="disabled", font=ctk.CTkFont(weight="bold", size=11),
            corner_radius=6, height=32
        )
        self.delete_btn.pack(side="left", padx=(4, 0), expand=True, fill="x")

        self.load_saved_trackers()

    def _on_threshold_change(self, value):
        self.thresh_value_label.configure(text=f"{value:.2f}")
        # Save per-node threshold only
        if self.current_selected_name:
            self.node_thresholds[self.current_selected_name] = round(value, 2)
            self._save_node_thresholds()
        else:
            # No node selected → update global default
            self._default_threshold = round(value, 2)
            self._save_config_settings(threshold=round(value, 2))

    def _save_config_settings(self, **kwargs):
        """Save settings to config.json. Merges with existing values."""
        try:
            cfg = {}
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    cfg = json.load(f)
            # Always capture current state of all settings
            try: cfg["debug_visual"] = self.debug_visual_var.get()
            except: pass
            try: cfg["port"] = int(self.footer_port_input.get())
            except: pass
            try: cfg["tab"] = int(self.footer_tab_input.get())
            except: pass
            # Merge any explicit overrides
            cfg.update(kwargs)
            with open("config.json", "w") as f:
                json.dump(cfg, f)
        except: pass

    def _load_node_thresholds(self):
        """Load per-node thresholds from trackers/thresholds.json."""
        try:
            path = os.path.join("trackers", "thresholds.json")
            if os.path.exists(path):
                with open(path, "r") as f:
                    self.node_thresholds = json.load(f)
        except:
            self.node_thresholds = {}

    def _save_node_thresholds(self):
        """Save per-node thresholds to trackers/thresholds.json."""
        try:
            path = os.path.join("trackers", "thresholds.json")
            with open(path, "w") as f:
                json.dump(self.node_thresholds, f, indent=2)
        except:
            pass

    def get_node_threshold(self, name):
        """Get threshold for a specific node, falling back to global."""
        return self.node_thresholds.get(name, self.slider.get())

    def load_saved_trackers(self):
        if os.path.exists("trackers"):
            for filename in os.listdir("trackers"):
                if filename.endswith(".png"):
                    name = filename[:-4] 
                    filepath = os.path.abspath(os.path.join("trackers", filename))
                    self.tracked_icons[name] = filepath
            
            self.refresh_tracked_list()
            
            if self.tracked_icons:
                self.after(500, lambda: self.log_gui(f"[System] Setup restored {len(self.tracked_icons)} active nodes."))
                # Auto-learn features on startup for any templates missing .features.npz
                self.after(1000, self._auto_learn_if_needed)

    def refresh_tracked_list(self):
        for widget in self.btn_container.winfo_children():
            widget.destroy()
        self.icon_buttons.clear()
        self.icon_checkbox_vars.clear()
        
        search = self.node_search_entry.get().strip().lower() if hasattr(self, 'node_search_entry') else ""
        for name, filepath in self.tracked_icons.items():
            if search and search not in name.lower():
                continue
            self._add_icon_to_list(name, filepath)

    def _toggle_select_all_nodes(self):
        val = self.node_select_all_var.get()
        for v in self.icon_checkbox_vars.values():
            v.set(val)
        self._update_delete_btn_color()

    def _update_delete_btn_color(self):
        """Turn Delete button red when any checkbox is ticked."""
        any_checked = any(v.get() for v in self.icon_checkbox_vars.values())
        if any_checked:
            self.del_selected_btn.configure(text_color=COLOR["danger"])
        else:
            self.del_selected_btn.configure(text_color=COLOR["text_muted"])

    def _add_icon_to_list(self, name, filepath):
        frame = ctk.CTkFrame(self.btn_container, fg_color="transparent", height=30)
        frame.pack(fill="x", pady=1, padx=4)
        frame.pack_propagate(False)
        
        var = ctk.BooleanVar(value=False)
        self.icon_checkbox_vars[name] = var
        chk = ctk.CTkCheckBox(
            frame, text="", variable=var,
            checkbox_width=18, checkbox_height=18, corner_radius=4,
            border_width=1, width=18, border_color=COLOR["border"],
            hover_color=COLOR["surface2"],
            command=self._update_delete_btn_color
        )
        chk.pack(side="left", padx=(4, 6))
        
        btn = ctk.CTkButton(
            frame, text=name, anchor="w",
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["text_dim"],
            font=ctk.CTkFont(size=12),
            command=lambda n=name: self.on_select_target(n),
            height=28, corner_radius=6
        )
        btn.pack(side="left", fill="x", expand=True)
        
        # Status dot (green if file exists, gray if not)
        dot_color = COLOR["success"] if filepath and os.path.exists(filepath) else COLOR["text_muted"]
        dot = ctk.CTkFrame(frame, width=6, height=6, fg_color=dot_color, corner_radius=3)
        dot.pack(side="right", padx=(4, 8))
        
        self.icon_buttons[name] = btn

    def on_select_target(self, name):
        # Blur searchbox
        self._blur_search_entry()

        # Just select this node (no checkbox toggle)
        self.current_selected_name = name
        
        for n, btn in self.icon_buttons.items():
            if n == name:
                btn.configure(fg_color=COLOR["surface3"], text_color=COLOR["text"])
            else:
                btn.configure(fg_color="transparent", text_color=COLOR["text_dim"])

        self.preview_name_label.configure(text=name)
        
        filepath = self.tracked_icons.get(name)
        if filepath and os.path.exists(filepath):
            self.preview_status_label.pack_forget()
            try:
                img = Image.open(filepath)
                w, h = img.size
                ratio = min(300/w, 200/h)
                if ratio < 1:
                    disp_w, disp_h = int(w*ratio), int(h*ratio)
                else:
                    disp_w, disp_h = w, h
                
                self._current_preview_img = ctk.CTkImage(light_image=img, size=(disp_w, disp_h))
                self.preview_image_label.configure(image=self._current_preview_img, text="")
                self.preview_size_label.configure(text=f"Resolution: {w}x{h} px")
            except Exception as e:
                self._current_preview_img = None
                self.preview_image_label.configure(image="", text="[Image Load Error]")
        else:
            self.preview_status_label.pack_forget()
            self._current_preview_img = None
            self.preview_image_label.configure(image="", text="[Require Screen Snipping]")
            self.preview_size_label.configure(text="")

        self.recapture_btn.configure(state="normal")
        self.delete_btn.configure(state="normal")

        # Load per-node threshold (fallback to global default)
        node_thresh = self.node_thresholds.get(name, self._default_threshold)
        self.slider.set(node_thresh)
        self.thresh_value_label.configure(text=f"{node_thresh:.2f}")
        self.test_node_btn.configure(state="normal")

    def _show_test_notification(self, text, color, bg_color):
        """Show a toast notification in the Nodes tab. Must be called from main thread."""
        # Cancel pending hide
        if self._test_notif_hide_id:
            self.after_cancel(self._test_notif_hide_id)
            self._test_notif_hide_id = None

        self.test_notif_label.configure(text=text, text_color=color)
        self.test_notif_frame.configure(fg_color=bg_color)
        self.test_notif_frame.pack(fill="x", padx=PAD["md"], pady=(0, 5), before=self.target_controls)

        # Auto-hide after 8 seconds
        self._test_notif_hide_id = self.after(8000, self._hide_test_notification)

    def _hide_test_notification(self):
        self.test_notif_frame.pack_forget()
        self._test_notif_hide_id = None

    def test_current_node(self):
        if not self.current_selected_name: return
        name = self.current_selected_name
        filepath = self.tracked_icons.get(name)
        
        if not filepath or not os.path.exists(filepath):
            messagebox.showwarning("Error", f"No file found for node '{name}'")
            return

        # IMPORTANT: Capture values on the main thread BEFORE spawning background thread
        # This fixes the race condition where changing values after clicking Test
        # would cause the wrong tab/port to be used.
        # Read Port/Tab from footer inputs (moved from old Node tab header)
        frozen_port_str = self.footer_port_input.get().strip()
        frozen_port = int(frozen_port_str) if frozen_port_str.isdigit() else 9222
        frozen_tab_id_str = self.footer_tab_input.get().strip()
        frozen_tab_id = int(frozen_tab_id_str) if frozen_tab_id_str.isdigit() else 0
        frozen_threshold = self.slider.get()

        # Show scanning notification immediately
        self._show_test_notification(
            f"Scanning '{name}' on Port {frozen_port}, Tab {frozen_tab_id}...",
            COLOR["text_dim"], COLOR["bg_subtle"]
        )
            
        # Run in background thread to avoid blocking GUI
        def _run_test():
            import urllib.request
            import json as _json_test
            
            # Use frozen values captured at click-time
            port = frozen_port
            tab_id = frozen_tab_id
            threshold_val = frozen_threshold
            
            page = None
            cdp_client = None
            try:
                from cdp_client import CDPClient
                
                # Log available tabs
                try:
                    import urllib.request
                    import json as _json_tabs
                    resp = urllib.request.urlopen(f"http://localhost:{port}/json")
                    targets = _json_tabs.loads(resp.read().decode())
                    page_targets = [t for t in targets if t.get("type") == "page"]
                    tab_list = " | ".join([f"[{i}] {t.get('title', '?')[:25]}" for i, t in enumerate(page_targets)])
                    self.log_gui(f"[TEST] Port {port} | Tabs: {tab_list}")
                    self.log_gui(f"[TEST] Using Tab {tab_id}")
                except:
                    pass
                
                cdp_client = CDPClient.connect(port=port, tab_index=tab_id)
            except Exception as e:
                self.log_gui(f"[TEST] Connection failed: {str(e)[:60]}")
            
            frame_bytes = None
            if cdp_client:
                try: frame_bytes = cdp_client.screenshot()
                except: pass
            
            debug_result = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=True, frame_bytes=frame_bytes)
            # debug=True returns (result, debug_lines)
            if isinstance(debug_result, tuple) and len(debug_result) == 2 and isinstance(debug_result[1], list):
                res, debug_lines = debug_result
            else:
                res = debug_result
                debug_lines = []
            
            if res:
                x, y, score = res
                # Store for Mark Wrong
                self._last_test = {
                    "filepath": filepath,
                    "frame_bytes": frame_bytes,
                    "x": x, "y": y, "score": score,
                    "name": name
                }
                self.gui_queue.put(("test_notif", (
                    f"Found '{name}' at ({x}, {y}) — Accuracy: {score:.2f}",
                    COLOR["success"], "#0D3320"
                )))
                self.log_gui(f"[TEST] Found '{name}' at ({x}, {y}) — Accuracy: {score:.2f}")
                # Log debug details
                for line in debug_lines:
                    self.log_gui(f"  {line}")
                # Save detected position
                if frame_bytes and score >= 0.65:
                    import numpy as np
                    _arr = np.frombuffer(frame_bytes, np.uint8)
                    _img = __import__('cv2').imdecode(_arr, __import__('cv2').IMREAD_GRAYSCALE)
                    if _img is not None:
                        fh, fw = _img.shape[:2]
                        save_capture_position(filepath, x, y, fw, fh)
                        reset_learned_position(filepath, x, y, score)
                        save_hard_click_position(filepath, x, y, fw, fh)
                        self.vision.refresh_template(filepath)
                        self.log_gui(f"[TEST] Saved Hard Click position ({x}, {y}) in CDP space")
                # Show red debug dot
                if cdp_client and self.debug_visual_var.get():
                    try:
                        dpr = float(cdp_client.evaluate("window.devicePixelRatio"))
                    except:
                        dpr = 1.0
                    css_x = x / dpr
                    css_y = y / dpr
                    
                    js_dot = """
                    (args) => {
                        const dot = document.createElement('div');
                        dot.style.cssText = `width:16px;height:16px;background:red;border:3px solid white;border-radius:50%;position:fixed;left:${args.x-8}px;top:${args.y-8}px;z-index:999999;pointer-events:none;box-shadow:0 0 10px red;`;
                        document.body.appendChild(dot);
                        setTimeout(() => dot.remove(), 3000);
                    }
                    """
                    try:
                        canvas_frame = cdp_client.find_canvas_frame()
                        if canvas_frame:
                            cdp_client.evaluate_in_specific_frame(
                                canvas_frame,
                                f"({js_dot})({{x: {css_x}, y: {css_y}}})"
                            )
                        else:
                            cdp_client.evaluate(f"({js_dot})({{x: {css_x}, y: {css_y}}})")
                    except:
                        pass
            else:
                self.gui_queue.put(("test_notif", (
                    f"Not found '{name}' on screen (Threshold: {threshold_val:.2f})",
                    COLOR["danger"], "#3D1111"
                )))
                self.log_gui(f"[TEST] Not found '{name}' on screen (Threshold: {threshold_val:.2f})")
                # Log debug details showing WHY it failed
                for line in debug_lines:
                    self.log_gui(f"  {line}")
            
            # Cleanup
            if cdp_client:
                try: cdp_client.close()
                except: pass
        
        threading.Thread(target=_run_test, daemon=True).start()


    def add_new_target(self):
        # Custom styled dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("New Tracking Node")
        dialog.geometry("380x280")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=COLOR["bg"])

        # Set window icon (after delay for CTkToplevel)
        ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        if os.path.exists(ico_path):
            dialog.after(200, lambda: dialog.iconbitmap(ico_path))

        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 190
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 140
        dialog.geometry(f"+{x}+{y}")

        # Flash animation when user clicks main window
        def _flash(e=None):
            if not dialog.winfo_exists():
                return
            dialog.lift()
            dialog.focus_set()
            colors = [COLOR["danger"], COLOR["bg"], COLOR["danger"], COLOR["bg"], COLOR["danger"], COLOR["bg"]]
            for i, c in enumerate(colors):
                dialog.after(i * 100, lambda col=c: dialog.configure(fg_color=col) if dialog.winfo_exists() else None)

        # Bind click on main window to trigger flash
        main_win = self.winfo_toplevel()
        bind_id = main_win.bind("<Button-1>", _flash, add="+")

        # Cleanup binding when dialog closes
        def _on_close():
            try:
                main_win.unbind("<Button-1>", bind_id)
            except Exception:
                pass
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", _on_close)

        # Title
        ctk.CTkLabel(
            dialog, text="New Tracking Node",
            font=ctk.CTkFont(family="Inter", size=15, weight="bold"),
            text_color=COLOR["text"]
        ).pack(pady=(16, 4))

        # Mode toggle: Image / Text
        mode_var = ctk.StringVar(value="Image")
        mode_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        mode_frame.pack(pady=(4, 8))
        
        ctk.CTkSegmentedButton(
            mode_frame, values=["Image", "Text"],
            variable=mode_var, width=200,
            font=ctk.CTkFont(size=11, weight="bold"),
            selected_color=COLOR["primary"],
            selected_hover_color=COLOR["primary_h"],
            command=lambda v: _toggle_mode(v)
        ).pack()

        # Subtitle
        subtitle = ctk.CTkLabel(
            dialog, text="e.g., hp_bar, potion, settings...",
            font=ctk.CTkFont(family="Inter", size=11),
            text_color=COLOR["text_muted"]
        )
        subtitle.pack(pady=(0, 6))

        # Name entry
        entry = ctk.CTkEntry(
            dialog, width=300, height=36,
            fg_color=COLOR["surface"], border_width=1,
            border_color=COLOR["border"], corner_radius=8,
            font=ctk.CTkFont(family="Inter", size=12),
            placeholder_text="Enter node name..."
        )
        entry.pack(pady=(0, 6))
        entry.focus_set()

        # Text search entry (hidden by default, shown in Text mode)
        text_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        text_entry = ctk.CTkEntry(
            text_frame, width=300, height=36,
            fg_color=COLOR["surface"], border_width=1,
            border_color=COLOR["accent"], corner_radius=8,
            font=ctk.CTkFont(family="Inter", size=12),
            placeholder_text="Text to search (e.g. Supplies, Auto Attack...)"
        )
        text_entry.pack()
        
        def _toggle_mode(v):
            if v == "Text":
                subtitle.configure(text="OCR will search for this text on screen")
                text_frame.pack(after=entry, pady=(0, 6))
            else:
                subtitle.configure(text="e.g., hp_bar, potion, settings...")
                text_frame.pack_forget()
        
        result = {"name": None, "mode": None, "search_text": None}

        def on_ok(*_):
            result["name"] = entry.get().strip()
            result["mode"] = mode_var.get()
            result["search_text"] = text_entry.get().strip() if mode_var.get() == "Text" else None
            _on_close()

        def on_cancel():
            _on_close()

        entry.bind("<Return>", on_ok)
        text_entry.bind("<Return>", on_ok)

        # Button row
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=40, pady=(4, 0))

        ctk.CTkButton(
            btn_row, text="Create", command=on_ok,
            fg_color=COLOR["primary"], hover_color=COLOR["primary_h"],
            text_color="#ffffff", font=ctk.CTkFont(family="Inter", size=12, weight="bold"),
            corner_radius=8, height=34, width=140
        ).pack(side="left", expand=True, padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Cancel", command=on_cancel,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_dim"], font=ctk.CTkFont(family="Inter", size=12),
            corner_radius=8, height=34, width=140
        ).pack(side="left", expand=True, padx=(4, 0))

        dialog.wait_window()

        name = result["name"]
        if name:
            if name in self.tracked_icons:
                messagebox.showerror("Error", "This Node Name already exists! Provide a unique name.")
                return
            
            if result["mode"] == "Text" and result["search_text"]:
                # Save text node config
                self._save_text_node(name, result["search_text"])
                self._add_icon_to_list(name, "")
                self.on_select_target(name)
                self.log_gui(f"[Nodes] 🔤 Text Node '{name}' created (search: '{result['search_text']}')")
            else:
                # Image mode — proceed with screenshot capture
                self._add_icon_to_list(name, "")
                self.on_select_target(name)
                self._show_capture_confirm(name)
    
    def _load_text_nodes(self):
        """Load text node configs from trackers/text_nodes.json."""
        self.text_nodes = {}  # name -> search_text
        path = os.path.join("trackers", "text_nodes.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.text_nodes = json.load(f)
            except:
                pass
    
    def _save_text_node(self, name, search_text):
        """Save a text node config."""
        if not hasattr(self, 'text_nodes'):
            self._load_text_nodes()
        self.text_nodes[name] = search_text
        path = os.path.join("trackers", "text_nodes.json")
        os.makedirs("trackers", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.text_nodes, f, indent=2, ensure_ascii=False)
    
    def _is_text_node(self, name):
        """Check if a node is a text node."""
        if not hasattr(self, 'text_nodes'):
            self._load_text_nodes()
        return name in self.text_nodes
    
    def _get_text_node_search(self, name):
        """Get search text for a text node."""
        if not hasattr(self, 'text_nodes'):
            self._load_text_nodes()
        return self.text_nodes.get(name, "")

    def _show_capture_confirm(self, name):
        """Show styled confirm dialog for screen capture."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Capture Screen")
        dlg.geometry("380x150")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(fg_color=COLOR["bg"])

        ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        if os.path.exists(ico_path):
            dlg.after(200, lambda: dlg.iconbitmap(ico_path))

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 190
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 75
        dlg.geometry(f"+{x}+{y}")

        # Success message
        ctk.CTkLabel(
            dlg, text=f"Node '{name}' created successfully!",
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            text_color=COLOR["text"]
        ).pack(pady=(20, 2))

        ctk.CTkLabel(
            dlg, text="Capture its screen boundary now?",
            font=ctk.CTkFont(family="Inter", size=11),
            text_color=COLOR["text_muted"]
        ).pack(pady=(0, 12))

        result = {"capture": False}

        def on_capture():
            result["capture"] = True
            dlg.destroy()

        def on_skip():
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=40)

        ctk.CTkButton(
            btn_row, text="Capture", command=on_capture,
            fg_color=COLOR["success"], hover_color="#2A8A5A",
            text_color="#ffffff", font=ctk.CTkFont(family="Inter", size=12, weight="bold"),
            corner_radius=8, height=34, width=140
        ).pack(side="left", expand=True, padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Skip", command=on_skip,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_dim"], font=ctk.CTkFont(family="Inter", size=12),
            corner_radius=8, height=34, width=140
        ).pack(side="left", expand=True, padx=(4, 0))

        dlg.wait_window()

        if result["capture"]:
            self.after(100, self.recapture_current)

    def _styled_confirm(self, title, message, confirm_text="Confirm", confirm_color=None):
        """Reusable styled confirmation dialog. Returns True if confirmed."""
        if confirm_color is None:
            confirm_color = COLOR["danger"]
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("380x160")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(fg_color=COLOR["bg"])

        ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")
        if os.path.exists(ico_path):
            dlg.after(200, lambda: dlg.iconbitmap(ico_path))

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 190
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 80
        dlg.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dlg, text=title,
            font=ctk.CTkFont(family="Inter", size=14, weight="bold"),
            text_color=COLOR["text"]
        ).pack(pady=(20, 6))

        ctk.CTkLabel(
            dlg, text=message,
            font=ctk.CTkFont(family="Inter", size=12),
            text_color=COLOR["text_dim"]
        ).pack(pady=(0, 16))

        result = {"ok": False}

        def on_yes():
            result["ok"] = True
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=40)

        ctk.CTkButton(
            btn_row, text=confirm_text, command=on_yes,
            fg_color=confirm_color, hover_color=COLOR["surface3"],
            text_color="#ffffff", font=ctk.CTkFont(family="Inter", size=12, weight="bold"),
            corner_radius=8, height=34, width=140
        ).pack(side="left", expand=True, padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="Cancel", command=dlg.destroy,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_dim"], font=ctk.CTkFont(family="Inter", size=12),
            corner_radius=8, height=34, width=140
        ).pack(side="left", expand=True, padx=(4, 0))

        dlg.wait_window()
        return result["ok"]

    def recapture_current(self):
        if not self.current_selected_name: return
        name = self.current_selected_name
        
        save_path = os.path.abspath(f"trackers/{name}.png")
        
        def success(w, h):
            self.tracked_icons[name] = save_path
            self.log_gui(f"Template acquired for Node [{name}] ({w}x{h} px)")
            self.refresh_tracked_list()
            # Restore highlight for the recaptured node
            self.current_selected_name = name
            if name in self.icon_buttons:
                for n, btn in self.icon_buttons.items():
                    if n == name:
                        btn.configure(fg_color=COLOR["surface3"], text_color=COLOR["text"])
                    else:
                        btn.configure(fg_color="transparent", text_color=COLOR["text_dim"])
            # Refresh preview
            self.preview_name_label.configure(text=name)
            try:
                img = Image.open(save_path)
                w2, h2 = img.size
                ratio = min(300/w2, 200/h2)
                dw, dh = (int(w2*ratio), int(h2*ratio)) if ratio < 1 else (w2, h2)
                self._current_preview_img = ctk.CTkImage(light_image=img, size=(dw, dh))
                self.preview_image_label.configure(image=self._current_preview_img, text="")
                self.preview_size_label.configure(text=f"Resolution: {w2}x{h2} px")
            except:
                pass
            self.recapture_btn.configure(state="normal")
            self.delete_btn.configure(state="normal")
            self.test_node_btn.configure(state="normal")
            
        self.snip_process(save_path, success)


    def delete_selected_targets(self):
        to_delete = [name for name, var in self.icon_checkbox_vars.items() if var.get()]
        if not to_delete:
            return
            
        if self._styled_confirm("Delete Nodes", f"Delete {len(to_delete)} selected node(s)?", "Delete"):
            for name in to_delete:
                filepath = self.tracked_icons.get(name)
                if filepath and os.path.exists(filepath):
                    try: os.remove(filepath)
                    except: pass
                if name in self.tracked_icons:
                    del self.tracked_icons[name]
                if self.current_selected_name == name:
                    self.current_selected_name = None
                    self.preview_name_label.configure(text="Deleted!")
                    self.preview_status_label.configure(text="")
                    self._current_preview_img = None
                    self.preview_image_label.configure(image="", text="[Empty/Null]")
                    self.preview_size_label.configure(text="")
                    self.recapture_btn.configure(state="disabled")
                    self.delete_btn.configure(state="disabled")
                    self.test_node_btn.configure(state="disabled")
                    
            self.refresh_tracked_list()
            self.log_gui(f"[System] Deleted {len(to_delete)} Nodes successfully.")

    def delete_current(self):
        if not self.current_selected_name: return
        name = self.current_selected_name
        if self._styled_confirm("Delete Node", f"Permanently delete '{name}'?", "Delete"):
            filepath = self.tracked_icons.get(name)
            if filepath and os.path.exists(filepath):
                try: os.remove(filepath)
                except: pass
            
            if name in self.tracked_icons:
                del self.tracked_icons[name]
            
            self.current_selected_name = None
            self.preview_name_label.configure(text="Deleted!")
            self.preview_status_label.configure(text="")
            self._current_preview_img = None
            self.preview_image_label.configure(image="", text="[Empty/Null]")
            self.preview_size_label.configure(text="")
            self.recapture_btn.configure(state="disabled")
            self.delete_btn.configure(state="disabled")
            self.test_node_btn.configure(state="disabled")
            self.refresh_tracked_list()

    def toggle_tracker(self):
        if not self.is_tracking:
            valid_targets = [v for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
            if len(valid_targets) == 0:
                return messagebox.showerror("System Error", "No Node has valid picture bound. Please Capture them first.")
            
            self.is_tracking = True
            self.start_tracking_btn.configure(text="STOP MONITOR PROCESS", fg_color="red", hover_color="darkred")
            self.log_gui(f"--- INITIATING RADAR SCAN: {len(valid_targets)} TARGETS ENQUEUED ---")
            
            self.log_gui(f"[Alert] No Game Window set! Scanning FULL Desktop -> Slower Performance")
                
            threading.Thread(target=self.tracker_loop, daemon=True).start()
        else:
            self.is_tracking = False
            self.start_tracking_btn.configure(text="MASTER MONITOR: TRACK ALL NODES", fg_color=['#3B8ED0', '#1F6AA5'])
            self.log_gui("--- RADAR SCAN SHUT DOWN ---")

    def tracker_loop(self):
        threshold_val = self.slider.get()
        while self.is_tracking:
            for name, filepath in self.tracked_icons.items():
                if not filepath or not os.path.exists(filepath): continue
                
                res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False)
                if res:
                    x, y, score = res
                    self.log_gui(f"MATCHED [{name}] -> Cord({x}, {y}) | Conf: {score:.2f}")
            time.sleep(1.0)

    def snip_process(self, save_path, success_callback):
        self.iconify()
        time.sleep(0.3)
        from screencapture import ScreenCaptureTool
        def on_snip(x1, y1, x2, y2):
            img = pyautogui.screenshot(region=(x1, y1, x2-x1, y2-y1))
            img.save(save_path)
            self.deiconify()
            success_callback(x2-x1, y2-y1)
            # Save screen coords
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            sw = pyautogui.size()[0]
            sh = pyautogui.size()[1]
            save_capture_position(save_path, cx, cy, sw, sh)
            # Auto-detect CDP position for hard click
            threading.Thread(
                target=self._detect_hard_click_position,
                args=(save_path,),
                daemon=True
            ).start()
            threading.Thread(
                target=self._precompute_and_validate,
                args=(save_path, cx, cy),
                daemon=True
            ).start()

        snipper = ScreenCaptureTool(on_snip)
        snipper.run()
        self.deiconify()

    def _detect_hard_click_position(self, template_path):
        """Match snipped template against CDP screenshot to get CDP-space coords for hard click."""
        try:
            port_str = self.footer_port_input.get().strip()
            port = int(port_str) if port_str.isdigit() else 9222
            tab_str = self.footer_tab_input.get().strip()
            tab_id = int(tab_str) if tab_str.isdigit() else 0
        except:
            port, tab_id = 9222, 0

        cdp_client = None
        try:
            import cv2
            import numpy as np
            from cdp_client import CDPClient

            cdp_client = CDPClient.connect(port=port, tab_index=tab_id)
            frame_bytes = cdp_client.screenshot()

            # Decode screenshot and template
            frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
            template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            if frame is None or template is None:
                self.log_gui(f"[Nodes] Hard Click: Could not read images")
                return

            th, tw = template.shape[:2]
            fh, fw = frame.shape[:2]
            if tw > fw or th > fh:
                self.log_gui(f"[Nodes] Hard Click: Template larger than viewport")
                return

            result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > 0.7:
                cdp_cx = max_loc[0] + tw // 2
                cdp_cy = max_loc[1] + th // 2
                save_hard_click_position(template_path, cdp_cx, cdp_cy, fw, fh)
                self.log_gui(f"[Nodes] ⚡ Hard Click position saved: ({cdp_cx},{cdp_cy}) in CDP space (match={max_val:.2f})")
            else:
                self.log_gui(f"[Nodes] Hard Click: Template not found in viewport (best={max_val:.2f})")
        except Exception as e:
            name = os.path.splitext(os.path.basename(template_path))[0]
            self.log_gui(f"[Nodes] Hard Click auto-detect failed for '{name}': {str(e)[:80]}")
        finally:
            if cdp_client:
                try: cdp_client.close()
                except: pass

    def _precompute_and_validate(self, template_path, cap_x, cap_y):
        """Extract features + auto-validate at captured coords."""
        try:
            name = os.path.splitext(os.path.basename(template_path))[0]
            if not extract_and_store_features(template_path):
                self.log_gui(f"[⚡ Learn] Failed to extract features for [{name}]")
                return

            vc = get_variant_count(template_path)
            self.log_gui(f"[⚡ Learn] Extracted features for [{name}] ({vc} capture{'s' if vc > 1 else ''})")

            # Auto-validate: re-detect at captured coords
            self.vision.refresh_template(template_path)
            try:
                from cdp_client import CDPClient
                cdp = CDPClient.connect(port=self.port_var.get(), tab_index=self.tab_var.get())
                fb = cdp.screenshot(format='jpeg', quality=80)
                cdp.close()
                res = self.vision.find_template_on_screen(
                    template_path, threshold=0.65, frame_bytes=fb)
                if res:
                    x, y, score = res
                    self.log_gui(f"[⚡ Validate] ✓ [{name}] found at ({x},{y}) score={score:.2f}")
                else:
                    self.log_gui(f"[⚡ Validate] ✗ [{name}] NOT found — try re-capturing or adding variant")
            except Exception as e:
                self.log_gui(f"[⚡ Validate] Skip — no CDP: {str(e)[:40]}")

        except Exception as e:
            self.log_gui(f"[⚡ Learn] Error: {str(e)[:50]}")

    def _precompute_node(self, template_path):
        """Legacy: precompute features."""
        self._precompute_and_validate(template_path, 0, 0)

    def _auto_learn_if_needed(self):
        """Check if any templates are missing features and auto-learn them."""
        from node_features import get_feature_status
        status = get_feature_status("trackers")
        missing = [(name, has, stale) for name, has, stale in status if not has or stale]
        if missing:
            self.log_gui(f"[⚡ Learn] {len(missing)} nodes need learning, starting...")
            threading.Thread(target=self._auto_learn_batch, daemon=True).start()

    def _auto_learn_batch(self):
        try:
            s, f, sk = batch_precompute("trackers")
            if s > 0:
                self.log_gui(f"[⚡ Learn] Auto-learned {s} nodes on startup")
        except:
            pass

    def _learn_all_nodes(self):
        """Batch precompute features for all node templates."""
        if hasattr(self, '_learn_done') and not self._learn_done:
            return  # Already running
        self.learn_btn.configure(state="disabled", text="Learning...")
        self._learn_done = False
        def _run():
            try:
                success, failed, skipped = batch_precompute("trackers")
                total = success + failed + skipped
                if success > 0:
                    self.log_gui(f"[⚡ Learn] Done! {success} new nodes learned" + (f", {skipped} already learned" if skipped else ""))
                elif skipped > 0:
                    self.log_gui(f"[⚡ Learn] All {skipped} nodes already learned ✓ (features up-to-date)")
                else:
                    self.log_gui(f"[⚡ Learn] No nodes to learn")
                if failed > 0:
                    self.log_gui(f"[⚡ Learn] Warning: {failed} nodes failed")
            except Exception as e:
                self.log_gui(f"[⚡ Learn] Batch error: {str(e)[:60]}")
            finally:
                self._learn_done = True
        threading.Thread(target=_run, daemon=True).start()
        def _poll():
            if self._learn_done:
                self.learn_btn.configure(state="normal", text="⚡ Learn All")
            else:
                self.after(300, _poll)
        self.after(300, _poll)
