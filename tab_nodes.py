"""Nodes tab mixin — Template tracking, testing, snipping."""
import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import os
import pyautogui
from PIL import Image
import json

from constants import COLOR, FONT, PAD, RADIUS, get_page_by_visual_index


class NodesMixin:
    """Mixin for the Nodes/Tracker tab. Mixed into BotApp."""

    def setup_tracker_tab(self):
        self.tracked_icons = {}
        self.current_selected_name = None
        self.icon_buttons = {}
        self.icon_checkbox_vars = {}
        self.is_tracking = False

        os.makedirs("trackers", exist_ok=True)

        self.tab_setup.grid_columnconfigure(0, weight=1, minsize=240)
        self.tab_setup.grid_columnconfigure(1, weight=3)
        self.tab_setup.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE (Glassmorphism panel) ======
        self.left_pane = ctk.CTkFrame(self.tab_setup, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.left_pane.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        # -- Fixed header --
        self.node_header = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        self.node_header.pack(fill="x", padx=PAD["md"], pady=(PAD["md"], PAD["sm"]))
        ctk.CTkLabel(self.node_header, text="TARGET NODES", text_color=COLOR["accent"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=13)).pack(anchor="w")

        # Action buttons
        node_actions = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        node_actions.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))
        self.add_btn = ctk.CTkButton(node_actions, text="+ Add", command=self.add_new_target, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11), corner_radius=RADIUS, height=30)
        self.add_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.del_selected_btn = ctk.CTkButton(node_actions, text="Delete Selected", command=self.delete_selected_targets, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11), corner_radius=RADIUS, height=30)
        self.del_selected_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # Search bar
        self.node_search_var = ctk.StringVar()
        self.node_search_var.trace_add("write", lambda *a: self.refresh_tracked_list())
        self.node_search_entry = ctk.CTkEntry(self.left_pane, placeholder_text="Search nodes...", textvariable=self.node_search_var, fg_color=COLOR["bg"], corner_radius=RADIUS, height=32, border_width=1, border_color=COLOR["border"])
        self.node_search_entry.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        # Select All
        self.node_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        sa_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["xs"]))
        ctk.CTkCheckBox(sa_row, text="Select All", variable=self.node_select_all_var, command=self._toggle_select_all_nodes, width=20, height=20, font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left")

        # Scrollable list
        self.btn_container = ctk.CTkScrollableFrame(self.left_pane, fg_color="transparent")
        self.btn_container.pack(fill="both", expand=True, padx=PAD["xs"], pady=(0, PAD["sm"]))

        # ====== RIGHT PANE ======
        self.right_pane = ctk.CTkFrame(self.tab_setup, fg_color=COLOR["bg"], corner_radius=0)
        self.right_pane.grid(row=0, column=1, sticky="nsew", padx=(PAD["sm"], PAD["lg"]), pady=PAD["lg"])

        self.top_bar = ctk.CTkFrame(self.right_pane, fg_color="transparent", height=40)
        self.top_bar.pack(fill="x", pady=(0, PAD["sm"]), padx=PAD["sm"])
        self.preview_title = ctk.CTkLabel(self.top_bar, text="TEMPLATE PREVIEW", font=ctk.CTkFont(family="Segoe UI", weight="bold", size=15), text_color=COLOR["accent"])
        self.preview_title.pack(side="left")

        test_tab_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        test_tab_frame.pack(side="right")
        ctk.CTkLabel(test_tab_frame, text="Port:", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left", padx=(5, 2))
        self.test_chrome_port = ctk.CTkEntry(test_tab_frame, width=55, placeholder_text="9222", fg_color=COLOR["surface"], corner_radius=6, height=28, border_width=1, border_color=COLOR["border"])
        self.test_chrome_port.insert(0, "9222")
        self.test_chrome_port.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(test_tab_frame, text="Tab:", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left", padx=(0, 2))
        self.test_tab_index = ctk.CTkEntry(test_tab_frame, width=40, placeholder_text="0", fg_color=COLOR["surface"], corner_radius=6, height=28, border_width=1, border_color=COLOR["border"])
        self.test_tab_index.insert(0, "0")
        self.test_tab_index.pack(side="left")

        self.preview_name_frame = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        self.preview_name_frame.pack(pady=PAD["xs"])
        self.preview_name_label = ctk.CTkLabel(self.preview_name_frame, text="No Target Selected", font=ctk.CTkFont(size=14))
        self.preview_name_label.pack(side="left")
        self.preview_status_label = ctk.CTkLabel(self.preview_name_frame, text="", text_color=COLOR["success"], font=ctk.CTkFont(weight="bold"))
        self.preview_status_label.pack(side="left", padx=5)

        self.preview_image_label = ctk.CTkLabel(self.right_pane, text="[Select any target Node to view details]", text_color=COLOR["text_dim"])
        self.preview_image_label.pack(pady=30, expand=True)

        self.preview_size_label = ctk.CTkLabel(self.right_pane, text="", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11))
        self.preview_size_label.pack(pady=0, anchor="e", padx=PAD["xl"])

        # Test Result Notification Banner
        self.test_notif_frame = ctk.CTkFrame(self.right_pane, fg_color=COLOR["surface2"], corner_radius=RADIUS, height=0, border_width=1, border_color=COLOR["border"])
        self.test_notif_label = ctk.CTkLabel(self.test_notif_frame, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["text"], wraplength=500, justify="left")
        self.test_notif_label.pack(padx=14, pady=10, anchor="w")
        self._test_notif_hide_id = None

        self.target_controls = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        self.target_controls.pack(side="bottom", fill="x", pady=PAD["lg"], padx=PAD["xl"])

        # Settings Section (glassmorphism card)
        self.settings_frame = ctk.CTkFrame(self.right_pane, fg_color=COLOR["surface"], corner_radius=RADIUS, border_width=1, border_color=COLOR["border"])
        self.settings_frame.pack(side="bottom", fill="x", pady=(0, PAD["sm"]), padx=PAD["xl"])

        self.thresh_label = ctk.CTkLabel(self.settings_frame, text="Accuracy Threshold: 0.85", font=ctk.CTkFont(size=12), text_color=COLOR["text_dim"])
        self.thresh_label.pack(padx=PAD["md"], pady=(PAD["sm"], 2), anchor="w")
        self.slider = ctk.CTkSlider(self.settings_frame, from_=0.5, to=0.99, command=self._on_threshold_change, progress_color=COLOR["primary"], button_color=COLOR["primary"])

        saved_thresh = 0.85
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    cfg = json.load(f)
                saved_thresh = cfg.get("threshold", 0.85)
        except: pass
        self.slider.set(saved_thresh)
        self.thresh_label.configure(text=f"Accuracy Threshold: {saved_thresh:.2f}")
        self.slider.pack(fill="x", padx=PAD["md"], pady=(0, PAD["xs"]))

        self.debug_toggle_switch = ctk.CTkSwitch(
            self.settings_frame, text="Show Click Position (Red Dot)",
            variable=self.debug_visual_var, onvalue=True, offvalue=False,
            font=ctk.CTkFont(size=12), progress_color=COLOR["danger"]
        )
        self.debug_toggle_switch.pack(anchor="w", padx=PAD["md"], pady=(2, PAD["md"]))

        self.test_node_btn = ctk.CTkButton(self.target_controls, text="Test Node", command=self.test_current_node, fg_color=COLOR["warning"], hover_color=COLOR["warning_h"], text_color=COLOR["text_dark"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=RADIUS)
        self.test_node_btn.pack(side="top", pady=(0, PAD["sm"]), expand=True, fill="x", padx=5)

        self.recapture_btn = ctk.CTkButton(self.target_controls, text="Re-Capture", command=self.recapture_current, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=RADIUS)
        self.recapture_btn.pack(side="left", padx=5, expand=True, fill="x")

        self.delete_btn = ctk.CTkButton(self.target_controls, text="Delete Node", command=self.delete_current, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=RADIUS)
        self.delete_btn.pack(side="right", padx=5, expand=True, fill="x")

        self.load_saved_trackers()

    def _on_threshold_change(self, value):
        self.thresh_label.configure(text=f"Accuracy Threshold: {value:.2f}")
        try:
            cfg = {}
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    cfg = json.load(f)
            cfg["threshold"] = round(value, 2)
            with open("config.json", "w") as f:
                json.dump(cfg, f)
        except: pass

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

    def refresh_tracked_list(self):
        for widget in self.btn_container.winfo_children():
            widget.destroy()
        self.icon_buttons.clear()
        self.icon_checkbox_vars.clear()
        
        search = self.node_search_var.get().strip().lower() if hasattr(self, 'node_search_var') else ""
        for name, filepath in self.tracked_icons.items():
            if search and search not in name.lower():
                continue
            self._add_icon_to_list(name, filepath)

    def _toggle_select_all_nodes(self):
        val = self.node_select_all_var.get()
        for v in self.icon_checkbox_vars.values():
            v.set(val)

    def _add_icon_to_list(self, name, filepath):
        frame = ctk.CTkFrame(self.btn_container, fg_color="transparent")
        frame.pack(fill="x", pady=2, padx=5)
        
        var = ctk.BooleanVar(value=False)
        self.icon_checkbox_vars[name] = var
        chk = ctk.CTkCheckBox(frame, text="", variable=var, width=20, height=20)
        chk.pack(side="left", padx=(0, 5))
        
        btn = ctk.CTkButton(frame, text=name, anchor="w", fg_color="transparent", hover_color="#2C3E50", text_color="white", command=lambda n=name: self.on_select_target(n))
        btn.pack(side="left", fill="x", expand=True)
        self.icon_buttons[name] = btn

    def on_select_target(self, name):
        self.current_selected_name = name
        
        for n, btn in self.icon_buttons.items():
            if n == name:
                btn.configure(fg_color="#2980B9") 
            else:
                btn.configure(fg_color="transparent")

        self.preview_name_label.configure(text=f"{name}.png")
        
        filepath = self.tracked_icons.get(name)
        if filepath and os.path.exists(filepath):
            self.preview_status_label.configure(text="✔️ VALID")
            try:
                img = Image.open(filepath)
                w, h = img.size
                ratio = min(300/w, 200/h)
                if ratio < 1:
                    disp_w, disp_h = int(w*ratio), int(h*ratio)
                else:
                    disp_w, disp_h = w, h
                
                ctk_img = ctk.CTkImage(light_image=img, size=(disp_w, disp_h))
                self.preview_image_label.configure(image=ctk_img, text="")
                self.preview_size_label.configure(text=f"Resolution: {w}x{h} px")
            except Exception as e:
                self.preview_image_label.configure(image="", text="[Image Load Error]")
        else:
            self.preview_status_label.configure(text="❌ ERR")
            self.preview_image_label.configure(image="", text="[Require Screen Snipping]")
            self.preview_size_label.configure(text="")

        self.recapture_btn.configure(state="normal")
        self.delete_btn.configure(state="normal")
        self.test_node_btn.configure(state="normal")

    def _show_test_notification(self, text, color, bg_color):
        """Show a toast notification in the Nodes tab. Must be called from main thread."""
        # Cancel pending hide
        if self._test_notif_hide_id:
            self.after_cancel(self._test_notif_hide_id)
            self._test_notif_hide_id = None

        self.test_notif_label.configure(text=text, text_color=color)
        self.test_notif_frame.configure(fg_color=bg_color)
        self.test_notif_frame.pack(fill="x", padx=20, pady=(0, 5), before=self.target_controls)

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
        frozen_port_str = self.test_chrome_port.get().strip()
        frozen_port = int(frozen_port_str) if frozen_port_str.isdigit() else 9222
        frozen_tab_id_str = self.test_tab_index.get().strip()
        frozen_tab_id = int(frozen_tab_id_str) if frozen_tab_id_str.isdigit() else 0
        frozen_threshold = self.slider.get()

        # Show scanning notification immediately
        self._show_test_notification(
            f"Scanning '{name}' on Port {frozen_port}, Tab {frozen_tab_id}...",
            COLOR["warning"], COLOR["surface2"]
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
            playwright_ctx = None
            browser = None
            try:
                from playwright.sync_api import sync_playwright
                playwright_ctx = sync_playwright().start()
                browser = playwright_ctx.chromium.connect_over_cdp(f"http://localhost:{port}")
                if browser.contexts and browser.contexts[0].pages:
                    context = browser.contexts[0]
                    
                    # Log available tabs so user knows which index to use
                    try:
                        resp = urllib.request.urlopen(f"http://localhost:{port}/json")
                        targets = _json_test.loads(resp.read().decode())
                        page_targets = [t for t in targets if t.get("type") == "page"]
                        tab_list = " | ".join([f"[{i}] {t.get('title', '?')[:25]}" for i, t in enumerate(page_targets)])
                        self.log_gui(f"[TEST] Port {port} | Tabs: {tab_list}")
                        self.log_gui(f"[TEST] Using Tab {tab_id}")
                    except:
                        pass
                    
                    page, info = get_page_by_visual_index(context, tab_id, port=port)
            except:
                pass
            
            frame_bytes = None
            if page:
                try: frame_bytes = page.screenshot()
                except: pass
            
            res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=True, frame_bytes=frame_bytes)
            if res:
                x, y, score = res
                # Show success notification via gui_queue
                self.gui_queue.put(("test_notif", (
                    f"Found '{name}' at ({x}, {y}) — Accuracy: {score:.2f}",
                    COLOR["success"], "#0D3320"
                )))
                self.log_gui(f"[TEST] Found '{name}' at ({x}, {y}) — Accuracy: {score:.2f}")
                # Show red debug dot
                if page and self.debug_visual_var.get():
                    try:
                        dpr = float(page.evaluate("window.devicePixelRatio"))
                    except:
                        dpr = 1.0
                    css_x = x / dpr
                    css_y = y / dpr
                    
                    target_frame = page.main_frame
                    for f in page.frames:
                        try:
                            if f.evaluate("document.querySelectorAll('canvas').length > 0"):
                                target_frame = f
                                break
                        except:
                            pass
                    
                    js_dot = """
                    (args) => {
                        const dot = document.createElement('div');
                        dot.style.cssText = `width:16px;height:16px;background:red;border:3px solid white;border-radius:50%;position:fixed;left:${args.x-8}px;top:${args.y-8}px;z-index:999999;pointer-events:none;box-shadow:0 0 10px red;`;
                        document.body.appendChild(dot);
                        setTimeout(() => dot.remove(), 3000);
                    }
                    """
                    try:
                        target_frame.evaluate(js_dot, {'x': css_x, 'y': css_y})
                    except:
                        pass
            else:
                # Show failure notification via gui_queue
                self.gui_queue.put(("test_notif", (
                    f"Not found '{name}' on screen (Threshold: {threshold_val:.2f})",
                    COLOR["danger"], "#3D1111"
                )))
                self.log_gui(f"[TEST] Not found '{name}' on screen (Threshold: {threshold_val:.2f})")
            
            # Cleanup — always runs
            if browser:
                try: browser.close()
                except: pass
            if playwright_ctx:
                try: playwright_ctx.stop()
                except: pass
        
        threading.Thread(target=_run_test, daemon=True).start()

    def add_new_target(self):
        dialog = ctk.CTkInputDialog(text="Enter Target Node Name\n(e.g., hp_bar, potion, settings...):", title="New Tracking Node")
        name = dialog.get_input()
        if name:
            name = name.strip()
            if name in self.tracked_icons:
                messagebox.showerror("Error", "This Node Name already exists! Provide a unique name.")
                return
            
            self._add_icon_to_list(name, "")
            self.on_select_target(name)
            
            if messagebox.askyesno("Capture Screen", f"Successfully created Node '{name}'.\nProcess to snipping tool to capture its boundary now?"):
                self.recapture_current()

    def recapture_current(self):
        if not self.current_selected_name: return
        name = self.current_selected_name
        
        save_path = os.path.abspath(f"trackers/{name}.png")
        
        def success(w, h):
            self.tracked_icons[name] = save_path
            self.log_gui(f"Template acquired for Node [{name}] ({w}x{h} px)")
            self.on_select_target(name)
            
        self.snip_process(save_path, success)

    def delete_selected_targets(self):
        to_delete = [name for name, var in self.icon_checkbox_vars.items() if var.get()]
        if not to_delete:
            messagebox.showinfo("Info", "Please select Nodes to delete!")
            return
            
        if messagebox.askyesno("Confirm", f"Delete {len(to_delete)} selected Nodes?"):
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
        if messagebox.askyesno("Confirm", f"Permanently delete Node '{name}'?"):
            filepath = self.tracked_icons.get(name)
            if filepath and os.path.exists(filepath):
                try: os.remove(filepath)
                except: pass
            
            if name in self.tracked_icons:
                del self.tracked_icons[name]
            
            self.current_selected_name = None
            self.preview_name_label.configure(text="Deleted!")
            self.preview_status_label.configure(text="")
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
        self.withdraw()
        time.sleep(0.3)
        from screencapture import ScreenCaptureTool
        def on_snip(x1, y1, x2, y2):
            img = pyautogui.screenshot(region=(x1, y1, x2-x1, y2-y1))
            img.save(save_path)
            self.deiconify()
            success_callback(x2-x1, y2-y1)
            
        snipper = ScreenCaptureTool(on_snip)
        snipper.run()
