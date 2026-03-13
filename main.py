import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
import threading
import time
import os
import pyautogui
from PIL import Image
from flowchart_ui import FlowchartUI
import random
import json
import queue
import shutil
from vision import Vision
from bot_action import BotAction
from playwright.sync_api import sync_playwright
import multiprocessing
from chrome_manager import ChromeManager
from state_db import StateDB

# Design System
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- Unified Color Palette ---
COLOR = {
    "bg":         "#0F172A",   # Deep navy background
    "surface":    "#1E293B",   # Card/panel background
    "surface2":   "#334155",   # Elevated surface
    "primary":    "#3B82F6",   # Action blue
    "primary_h":  "#2563EB",   # Blue hover
    "success":    "#22C55E",   # Green
    "success_h":  "#16A34A",   # Green hover
    "danger":     "#EF4444",   # Red
    "danger_h":   "#DC2626",   # Red hover
    "warning":    "#F59E0B",   # Amber
    "warning_h":  "#D97706",   # Amber hover
    "accent":     "#06B6D4",   # Cyan accent
    "text":       "#F1F5F9",   # Primary text
    "text_dim":   "#94A3B8",   # Secondary text
    "text_dark":  "#1E293B",   # Dark text (on light bg)
}

def get_page_by_visual_index(browser_context, tab_index, port=9222):
    """
    Get a Playwright Page by its VISUAL position in Chrome (left-to-right).
    
    Chrome CDP /json returns targets in visual tab order.
    Playwright context.pages returns them in creation order.
    This maps visual position -> correct Playwright page using CDP Target IDs.
    """
    import urllib.request, json as _json
    try:
        # Get tabs in visual order from Chrome
        resp = urllib.request.urlopen(f"http://localhost:{port}/json")
        targets = _json.loads(resp.read().decode())
        page_targets = [t for t in targets if t.get("type") == "page"]
        
        if tab_index >= len(page_targets):
            return None, f"Tab {tab_index} not found (only {len(page_targets)} tabs)"
        
        # Get the unique target ID at the desired visual position
        desired_target_id = page_targets[tab_index]["id"]
        
        # Match to Playwright page by CDP Target ID
        all_pages = browser_context.pages
        for p in all_pages:
            try:
                cdp_session = browser_context.new_cdp_session(p)
                info = cdp_session.send("Target.getTargetInfo")
                page_target_id = info["targetInfo"]["targetId"]
                cdp_session.detach()
                if page_target_id == desired_target_id:
                    tab_info = [(i, t.get("title", "")[:40]) for i, t in enumerate(page_targets)]
                    return p, tab_info
            except:
                continue
        
        # Fallback: if CDP matching fails, use index directly
        if tab_index < len(all_pages):
            return all_pages[tab_index], f"(fallback) CDP matching failed, using creation order"
        return None, f"No matching page found for target ID {desired_target_id}"
        
    except Exception as e:
        # Fallback to Playwright ordering if /json fails
        all_pages = browser_context.pages
        if tab_index < len(all_pages):
            return all_pages[tab_index], f"(fallback) /json failed: {e}"
        return None, f"/json failed: {e}, index {tab_index} >= {len(all_pages)} pages"



class BotApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LordNine Bot Control")
        self.geometry("1000x700")
        self.configure(fg_color=COLOR["bg"])

        self.vision = Vision()

        # (Bỏ qua self.game_region vì Playwright chụp Frame chuẩn 100%)
        self.debug_visual_var = ctk.BooleanVar(value=True)  # Bật/tắt chấm đỏ debug click
        
        # Load hệ thống Combo cũ nếu có
        self.combos = {}
        self.load_combos()

        # Load hệ thống Loop cũ nếu có
        self.loops = {}
        self.load_loops()

        # Load hệ thống Multi-Account 
        self.multi_accounts = []
        self.load_multi()
        
        # Scale infrastructure
        self.chrome_mgr = ChromeManager()
        self.state_db = StateDB()
        self.account_workers = {}    # name -> threading.Thread
        self.account_running = {}    # name -> bool (per-account start/stop)
        self.health_monitor_active = False

        # Tabview
        self.tabview = ctk.CTkTabview(self, fg_color=COLOR["bg"], segmented_button_fg_color=COLOR["surface"], segmented_button_selected_color=COLOR["primary"], segmented_button_unselected_color=COLOR["surface"])
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        self.tab_setup = self.tabview.add("Nodes")
        self.tab_combo = self.tabview.add("Macros")
        self.tab_loop = self.tabview.add("Automation")
        self.tab_multi = self.tabview.add("Accounts")
        self.tab_output = self.tabview.add("Output")

        # ====== OUTPUT TAB (System Log) ======
        self.log_header_frame = ctk.CTkFrame(self.tab_output, fg_color="transparent")
        self.log_header_frame.pack(fill="x", padx=10, pady=(8, 0))
        
        self.log_title = ctk.CTkLabel(self.log_header_frame, text="SYSTEM LOG", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR["accent"])
        self.log_title.pack(side="left")
        
        def clear_log():
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.configure(state="disabled")
            
        self.btn_clear_log = ctk.CTkButton(self.log_header_frame, text="Clear Log", width=80, height=28, font=ctk.CTkFont(size=12), fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], command=clear_log, corner_radius=6)
        self.btn_clear_log.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(self.tab_output, state="disabled", fg_color=COLOR["surface"], text_color=COLOR["accent"], font=ctk.CTkFont(family="Consolas", size=12), corner_radius=8)
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        self.setup_tracker_tab()
        self.setup_combo_tab()
        self.setup_loop_tab()
        self.setup_multi_tab()
        self.is_looping = False
        self.is_coordinating = False
        
        # --- THREAD-SAFE UI QUEUES ---
        self.gui_queue = queue.Queue()
        self.process_gui_queue()


    def process_gui_queue(self):
        """Processes pending GUI update requests from background threads safely in the main thread."""
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
                    
                self.gui_queue.task_done()
        except queue.Empty:
            pass
            
            self.after(100, self.process_gui_queue)

    def load_combos(self):
        if os.path.exists("combos.json"):
            try:
                with open("combos.json", "r", encoding="utf-8") as f:
                    self.combos = json.load(f)
            except Exception as e:
                print("Lỗi load combos:", e)
                
    def save_combos(self):
        try:
            if os.path.exists("combos.json"):
                shutil.copy("combos.json", "combos.json.bak")
            with open("combos.json", "w", encoding="utf-8") as f:
                json.dump(self.combos, f, indent=4)
        except Exception as e:
            print("Lỗi save combos:", e)

    def load_loops(self):
        if os.path.exists("loops.json"):
            try:
                with open("loops.json", "r", encoding="utf-8") as f:
                    self.loops = json.load(f)
            except Exception as e:
                print("Lỗi load loops:", e)
                
    def save_loops(self):
        try:
            if os.path.exists("loops.json"):
                shutil.copy("loops.json", "loops.json.bak")
            with open("loops.json", "w", encoding="utf-8") as f:
                json.dump(self.loops, f, indent=4)
        except Exception as e:
            print("Lỗi save loops:", e)

    def load_multi(self):
        if os.path.exists("multi.json"):
            try:
                with open("multi.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.multi_accounts = data.get("accounts", [])
            except Exception as e:
                print("Lỗi load multi:", e)
                
    def save_multi(self):
        try:
            if os.path.exists("multi.json"):
                shutil.copy("multi.json", "multi.json.bak")
            with open("multi.json", "w", encoding="utf-8") as f:
                json.dump({"accounts": self.multi_accounts}, f, indent=4)
        except Exception as e:
            print("Lỗi save multi:", e)

    # ================= TAB COMBO MACRO =================
    def setup_combo_tab(self):
        self.current_combo_name = None
        self.combo_buttons = {}
        self.combo_checkbox_vars = {}
        self.steps_labels = []

        self.tab_combo.grid_columnconfigure(0, weight=1, minsize=220)
        self.tab_combo.grid_columnconfigure(1, weight=3)
        self.tab_combo.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE (fixed header + scrollable list) ======
        self.combo_left_pane = ctk.CTkFrame(self.tab_combo, fg_color=COLOR["surface"])
        self.combo_left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        # -- Fixed header --
        ctk.CTkLabel(self.combo_left_pane, text="MACROS", text_color=COLOR["accent"], font=ctk.CTkFont(weight="bold", size=13)).pack(padx=8, pady=(8, 4), anchor="w")

        # Action buttons (at top!)
        combo_actions_top = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent")
        combo_actions_top.pack(fill="x", padx=8, pady=(0, 4))

        self.add_combo_btn = ctk.CTkButton(combo_actions_top, text="+ Add", command=self.add_new_combo, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(weight="bold", size=12), corner_radius=6, height=28)
        self.add_combo_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        self.del_selected_combo_btn = ctk.CTkButton(combo_actions_top, text="Delete Selected", command=self.delete_selected_combos, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(weight="bold", size=12), corner_radius=6, height=28)
        self.del_selected_combo_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # Search bar
        self.combo_search_var = ctk.StringVar()
        self.combo_search_var.trace_add("write", lambda *a: self.refresh_combo_list())
        ctk.CTkEntry(self.combo_left_pane, placeholder_text="Search macros...", textvariable=self.combo_search_var, fg_color=COLOR["bg"], corner_radius=6, height=28).pack(fill="x", padx=8, pady=(0, 4))

        # Select All
        self.combo_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent")
        sa_row.pack(fill="x", padx=8, pady=(0, 2))
        ctk.CTkCheckBox(sa_row, text="Select All", variable=self.combo_select_all_var, command=self._toggle_select_all_combos, width=20, height=20, font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left")

        # -- Scrollable list body --
        self.combo_btn_container = ctk.CTkScrollableFrame(self.combo_left_pane, fg_color="transparent")
        self.combo_btn_container.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # ====== RIGHT PANE (Chi tiết Combo) ======
        self.combo_right_pane = ctk.CTkFrame(self.tab_combo, fg_color=COLOR["bg"])
        self.combo_right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.combo_top_bar = ctk.CTkFrame(self.combo_right_pane, fg_color="transparent", height=40)
        self.combo_top_bar.pack(fill="x", pady=(10, 0), padx=20)
        
        self.combo_preview_title = ctk.CTkLabel(self.combo_top_bar, text="MACRO SEQUENCE", font=ctk.CTkFont(weight="bold", size=15), text_color=COLOR["accent"])
        self.combo_preview_title.pack()
        
        tab_idx_frame = ctk.CTkFrame(self.combo_top_bar, fg_color="transparent")
        tab_idx_frame.pack(pady=2)
        ctk.CTkLabel(tab_idx_frame, text="Target Tab Index:", font=ctk.CTkFont(size=12), text_color=COLOR["text_dim"]).pack(side="left", padx=5)
        self.combo_tab_index = ctk.CTkEntry(tab_idx_frame, width=50, placeholder_text="0", fg_color=COLOR["surface"], corner_radius=4)
        self.combo_tab_index.insert(0, "0")
        self.combo_tab_index.pack(side="left")

        self.combo_name_label = ctk.CTkLabel(self.combo_right_pane, text="[No Macro Selected]", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLOR["warning"])
        self.combo_name_label.pack(pady=10)

        self.steps_container = ctk.CTkScrollableFrame(self.combo_right_pane, fg_color=COLOR["surface"], height=150)
        self.steps_container.pack(fill="both", expand=True, padx=20, pady=5)

        # Result Verification Section
        self.result_verify_frame = ctk.CTkFrame(self.combo_right_pane, fg_color=COLOR["surface"], corner_radius=8)
        self.result_verify_frame.pack(fill="x", padx=20, pady=(5, 0))
        
        ctk.CTkLabel(self.result_verify_frame, text="RESULT VERIFICATION", font=ctk.CTkFont(weight="bold", size=12), text_color=COLOR["accent"]).pack(padx=12, pady=(8, 4), anchor="w")
        ctk.CTkLabel(self.result_verify_frame, text="Check these images after macro runs to determine success/failure", font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(padx=12, anchor="w")
        
        captures_row = ctk.CTkFrame(self.result_verify_frame, fg_color="transparent")
        captures_row.pack(fill="x", padx=12, pady=(4, 10))
        captures_row.grid_columnconfigure(0, weight=1)
        captures_row.grid_columnconfigure(1, weight=1)
        
        # Success capture
        success_col = ctk.CTkFrame(captures_row, fg_color="transparent")
        success_col.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(success_col, text="Success Capture:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["success"]).pack(anchor="w")
        self.combo_success_capture = ctk.CTkOptionMenu(success_col, values=["None"], fg_color=COLOR["surface2"], corner_radius=4, command=lambda v: self._save_macro_captures())
        self.combo_success_capture.pack(fill="x", pady=2)
        
        # Failure capture
        failure_col = ctk.CTkFrame(captures_row, fg_color="transparent")
        failure_col.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ctk.CTkLabel(failure_col, text="Failure Capture:", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR["danger"]).pack(anchor="w")
        self.combo_failure_capture = ctk.CTkOptionMenu(failure_col, values=["None"], fg_color=COLOR["surface2"], corner_radius=4, command=lambda v: self._save_macro_captures())
        self.combo_failure_capture.pack(fill="x", pady=2)

        self.combo_controls = ctk.CTkFrame(self.combo_right_pane, fg_color="transparent")
        self.combo_controls.pack(side="bottom", fill="x", pady=20, padx=20)
        
        self.add_step_btn = ctk.CTkButton(self.combo_controls, text="+ Add Step", command=self.add_step_to_combo, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], state="disabled", corner_radius=6)
        self.add_step_btn.pack(side="top", pady=(5, 2), fill="x")

        self.add_delay_btn = ctk.CTkButton(self.combo_controls, text="+ Add Delay", command=self.add_delay_to_combo, fg_color="#7C3AED", hover_color="#6D28D9", state="disabled", corner_radius=6)
        self.add_delay_btn.pack(side="top", pady=(0, 5), fill="x")

        self.play_combo_btn = ctk.CTkButton(self.combo_controls, text="Execute Macro", command=self.play_current_combo, fg_color=COLOR["success"], hover_color=COLOR["success_h"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=6)
        self.play_combo_btn.pack(side="left", padx=(0, 5), expand=True, fill="x")

        self.delete_combo_btn = ctk.CTkButton(self.combo_controls, text="Delete Macro", command=self.delete_current_combo, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], state="disabled", corner_radius=6)
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
        self.play_combo_btn.configure(state="normal")
        self.delete_combo_btn.configure(state="normal")
        
        # Data Migration for per-step markers
        macro_data = self.combos.get(name, {})
        migrated = False
        
        # If macro_data is still a list (very old version)
        if isinstance(macro_data, list):
            new_steps = [{"node": n, "marker": "None", "mode": "Wait until Appear", "time": "0"} for n in macro_data]
            self.combos[name] = {"steps": new_steps}
            migrated = True
        # If it's a dict, check if steps are strings (old single-marker combo version)
        elif "steps" in macro_data and macro_data["steps"] and isinstance(macro_data["steps"][0], str):
            global_marker = macro_data.get("completion_marker", "None")
            global_mode = macro_data.get("marker_mode", "Wait until Appear")
            global_time = macro_data.get("marker_time", "0")
            
            new_steps = []
            for i, n in enumerate(macro_data["steps"]):
                if i == len(macro_data["steps"]) - 1:
                    # Apply global marker to the last step
                    new_steps.append({"node": n, "marker": global_marker, "mode": global_mode, "time": global_time})
                else:
                    new_steps.append({"node": n, "marker": "None", "mode": "Wait until Appear", "time": "0"})
            
            self.combos[name] = {"steps": new_steps}
            migrated = True
            
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
        
        for i, step_data in enumerate(steps):
            if isinstance(step_data, str): continue # Đang migrate
            
            is_delay = step_data.get("type") == "delay"
            
            frame = ctk.CTkFrame(self.steps_container, fg_color="#1A1030" if is_delay else "#15202B")
            frame.pack(fill="x", pady=2, padx=5)
            
            # Row 1: Node Name & Actions
            top_row = ctk.CTkFrame(frame, fg_color="transparent")
            top_row.pack(fill="x")
            
            if is_delay:
                delay_sec = step_data.get('time', 1.0)
                lbl = ctk.CTkLabel(top_row, text=f"{i+1}. Delay: {delay_sec}s", font=ctk.CTkFont(weight="bold", size=13), text_color="#A78BFA")
            else:
                lbl = ctk.CTkLabel(top_row, text=f"{i+1}. Click: {step_data['node']}", font=ctk.CTkFont(weight="bold", size=13))
            lbl.pack(side="left", padx=10, pady=2)
            
            # Row 2: Condition settings info (only for click steps)
            if not is_delay and step_data.get("marker", "None") != "None":
                condText = f"↳ Wait for '{step_data['marker']}' to {step_data.get('mode', 'Wait until Appear').replace('Wait until ', '')} ({step_data.get('time', '0')}s hold)"
                cond_lbl = ctk.CTkLabel(frame, text=condText, font=ctk.CTkFont(size=11), text_color="#AAB7B8", anchor="w")
                cond_lbl.pack(fill="x", padx=30, pady=(0, 2))
            
            del_step_btn = ctk.CTkButton(top_row, text="X", width=28, height=28, fg_color="transparent", text_color="#E74C3C", hover_color="#34495E", font=ctk.CTkFont(weight="bold"), command=lambda idx=i: self.remove_step_from_combo(idx))
            del_step_btn.pack(side="right", padx=2)
            
            edit_btn = ctk.CTkButton(top_row, text="Edit", width=28, height=28, fg_color="transparent", text_color="#F39C12", hover_color="#34495E", font=ctk.CTkFont(weight="bold"), command=lambda idx=i: self.edit_step_marker(idx))
            edit_btn.pack(side="right", padx=2)

            down_btn = ctk.CTkButton(top_row, text="Dn", width=28, height=28, fg_color="transparent", text_color="white", hover_color="#34495E", font=ctk.CTkFont(weight="bold"), command=lambda idx=i: self.move_step(idx, 1))
            if i == len(steps) - 1: down_btn.configure(state="disabled", text_color="#2C3E50")
            down_btn.pack(side="right", padx=1)
                
            up_btn = ctk.CTkButton(top_row, text="Up", width=28, height=28, fg_color="transparent", text_color="white", hover_color="#34495E", font=ctk.CTkFont(weight="bold"), command=lambda idx=i: self.move_step(idx, -1))
            if i == 0: up_btn.configure(state="disabled", text_color="#2C3E50")
            up_btn.pack(side="right", padx=1)

    def move_step(self, index, direction):
        if not self.current_combo_name: return
        steps = self.combos[self.current_combo_name]["steps"]
        
        new_index = index + direction
        if 0 <= new_index < len(steps):
            steps[index], steps[new_index] = steps[new_index], steps[index]
            self.save_combos()
            self.refresh_steps_view()

    def edit_step_marker(self, index):
        if not self.current_combo_name: return
        step_data = self.combos[self.current_combo_name]["steps"][index]
        
        valid_nodes = ["None"] + [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        
        top = ctk.CTkToplevel(self)
        top.title(f"Edit Marker - Step {index+1}")
        top.geometry("400x350")
        top.attributes("-topmost", True)
        
        # 1. Chọn Marker Done
        ctk.CTkLabel(top, text="1. Wait until Marker (Optional):", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        cb_marker = ctk.CTkOptionMenu(top, values=valid_nodes)
        cb_marker.set(step_data.get("marker", "None"))
        cb_marker.pack(fill="x", padx=20, pady=5)
        
        # 2. Chọn Điều kiện Marker
        ctk.CTkLabel(top, text="2. Marker Condition:", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        cb_mode = ctk.CTkOptionMenu(top, values=["Wait until Appear", "Wait until Disappear"])
        cb_mode.set(step_data.get("mode", "Wait until Appear"))
        cb_mode.pack(fill="x", padx=20, pady=5)
        
        # 3. Thời gian Hold
        ctk.CTkLabel(top, text="3. Hold Duration (ms):", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        entry_time = ctk.CTkEntry(top)
        entry_time.insert(0, str(step_data.get("time", "0")))
        entry_time.pack(fill="x", padx=20, pady=5)
        
        def _save():
            marker_val = cb_marker.get()
            mode_val = cb_mode.get()
            time_val = entry_time.get()
            try:
                float(time_val)
            except ValueError:
                time_val = "0"
            
            step_data["marker"] = marker_val
            step_data["mode"] = mode_val
            step_data["time"] = time_val
            
            self.save_combos()
            self.refresh_steps_view()
            top.destroy()
            
        btn_save = ctk.CTkButton(top, text="SAVE CHANGES", command=_save, fg_color="#3498DB", hover_color="#2980B9", font=ctk.CTkFont(weight="bold", size=14))
        btn_save.pack(pady=30, fill="x", padx=20)

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
        
        # Chỉ lấy những Node đã khoanh vùng hợp lệ (có file tracking)
        valid_nodes = [k for k, v in self.tracked_icons.items() if v and os.path.exists(v)]
        if not valid_nodes:
            messagebox.showwarning("Empty", "You haven't added any Target Nodes in the Setup tab yet!")
            return
            
        # Tạo cửa sổ phụ (Toplevel) để User chọn Node đưa vào Combo
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
                    
            # Update label numbers
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
        
        val = simpledialog.askfloat("Add Delay", "Enter delay time in seconds:", 
                                      initialvalue=1.0, minvalue=0.1, maxvalue=300)
        if val is not None:
            step_obj = {
                "type": "delay",
                "time": val
            }
            self.combos[self.current_combo_name]["steps"].append(step_obj)
            self.save_combos()
            self.refresh_steps_view()

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
            
        tab_id_str = self.combo_tab_index.get().strip()
        tab_id = int(tab_id_str) if tab_id_str.isdigit() else None
            
        if messagebox.askyesno("Execute Macro", f"Execute Macro [{self.current_combo_name}] on Tab Index {tab_id}?"):
            threading.Thread(target=self._macro_execution_worker, args=(macro_data, tab_id), daemon=True).start()

    def _macro_execution_worker(self, macro_data, tab_id=None):
        self.log_gui(f"============== MACRO STARTING ==============")
        steps = macro_data.get("steps", [])
        threshold_val = self.slider.get()
        
        playwright_ctx = sync_playwright().start()
        browser = None
        page = None
        
        if tab_id is not None:
             try:
                 self.log_gui(f"[Test Macro] Connecting to Tab {tab_id} at localhost:9222...")
                 browser = playwright_ctx.chromium.connect_over_cdp("http://localhost:9222")
                 context = browser.contexts[0]
                 page, info = get_page_by_visual_index(context, tab_id)
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
        
        for idx, step_data in enumerate(steps):
            if isinstance(step_data, str):
                node_name = step_data
                marker = "None"
                marker_mode = "Wait until Appear"
                marker_time = 0
            else:
                # Handle delay steps
                if step_data.get("type") == "delay":
                    delay_time = float(step_data.get("time", 1.0))
                    self.log_gui(f"[Macro] ({idx+1}/{len(steps)}) Delay: {delay_time}s...")
                    time.sleep(delay_time)
                    continue
                
                node_name = step_data.get("node", "")
                marker = step_data.get("marker", "None")
                marker_mode = step_data.get("mode", "Wait until Appear")
                try:
                    marker_time = float(step_data.get("time", "0")) / 1000.0
                except:
                    marker_time = 0
                    
            if not node_name: continue
            
            self.log_gui(f"[Macro] ({idx+1}/{len(steps)}) Finding Node: {node_name}...")
            
            filepath = self.tracked_icons.get(node_name)
            if not filepath or not os.path.exists(filepath):
                self.log_gui(f"[Macro] SKIP: Node '{node_name}' missing image file.")
                continue
                
            found = False
            # Retries tối đa 5 lần (5s) cho 1 Node tải lên chậm
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
                    # Chờ 1 thời gian trước khi tìm Node kế tiếp (Giả sử UI game load)
                    time.sleep(random.uniform(1.2, 2.0))
                    break
                time.sleep(1.0) # Quét lại mỗi 1 giây
                
            if not found:
                self.log_gui(f"[Macro] SKIP: Could not find Node '{node_name}' after 5 seconds.")
                continue
                
            # Nếu có Completion Marker ở step này, Loop chờ ảnh đó xuất hiện/biến mất mới đi tiếp
            if marker != "None":
                mode_str = "APPEARS" if marker_mode == "Wait until Appear" else "DISAPPEARS"
                self.log_gui(f"[Macro] Waiting for Marker: '{marker}' {mode_str} (Holding {marker_time}s)...")
                marker_path = self.tracked_icons.get(marker)
                if marker_path and os.path.exists(marker_path):
                    # Đợi tối đa 60s cho màn hình Load xong cảnh
                    marker_found_or_lost = False
                    hold_start = None
                    last_log_time = 0
                    
                    for attempt in range(99999): # Đợi vô hạn cho Marker xuất hiện/biến mất
                        frame_bytes = None
                        if page:
                            try: frame_bytes = page.screenshot()
                            except: pass
                        res = self.vision.find_template_on_screen(marker_path, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                        
                        is_condition_met = (marker_mode == "Wait until Appear" and res) or (marker_mode == "Wait until Disappear" and not res)
                        
                        if is_condition_met:
                            if hold_start is None:
                                hold_start = time.time()
                                if marker_time > 0:
                                    self.log_gui(f"[Macro] Marker Triggered. Hold timer started ({marker_time}s)...")
                            
                            elapsed = time.time() - hold_start
                            
                            # Cập nhật Log đếm ngược mỗi giây
                            current_sec = int(elapsed)
                            if marker_time > 0 and current_sec > last_log_time:
                                self.log_gui(f"[Macro] Holding... {current_sec}/{marker_time}s")
                                last_log_time = current_sec
                                
                            if elapsed >= marker_time:
                                self.log_gui(f"[Macro] Confirmed Marker '{marker}' {mode_str} status!")
                                marker_found_or_lost = True
                                break
                        else:
                            if hold_start is not None:
                                self.log_gui(f"[Macro] Interrupted! Marker condition changed. Resetting timer.")
                                hold_start = None
                                last_log_time = 0
                            
                        time.sleep(1.0)
                        
                    if not marker_found_or_lost:
                        self.log_gui(f"[Macro] Timeout Error: Stuck at Marker '{marker}'. Aborting!")
                        return
                else:
                    self.log_gui(f"[Macro] Skipped Marker because image '{marker}' no longer exists!")
                
        if browser: browser.close()
        playwright_ctx.stop()
        self.log_gui(f"============== MACRO FINISHED ==============")

    def _internal_macro_runner(self, macro_data, bot_instance, acc_name="", page=None, threshold_override=None):
        """Run macro steps using an existing bot_instance and page (for coordinator workers)."""
        steps = macro_data.get("steps", [])
        threshold_val = threshold_override if threshold_override is not None else self.slider.get()
        
        for idx, step_data in enumerate(steps):
            if isinstance(step_data, str):
                node_name = step_data
                marker = "None"
                marker_mode = "Wait until Appear"
                marker_time = 0
            else:
                if step_data.get("type") == "delay":
                    delay_time = float(step_data.get("time", 1.0))
                    time.sleep(delay_time)
                    continue
                node_name = step_data.get("node", "")
                marker = step_data.get("marker", "None")
                marker_mode = step_data.get("mode", "Wait until Appear")
                try: marker_time = float(step_data.get("time", "0")) / 1000.0
                except: marker_time = 0
            if not node_name: continue
            filepath = self.tracked_icons.get(node_name)
            if not filepath or not os.path.exists(filepath): continue
            found = False
            for attempt in range(5):
                frame_bytes = None
                if page:
                    try: frame_bytes = page.screenshot()
                    except: pass
                res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                if res:
                    x, y, score = res
                    bot_instance.click_at(x, y, randomize=True)
                    found = True
                    time.sleep(random.uniform(1.2, 2.0))
                    break
                time.sleep(1.0)
            if not found: continue
            if marker != "None":
                marker_path = self.tracked_icons.get(marker)
                if marker_path and os.path.exists(marker_path):
                    hold_start = None
                    for _ in range(99999):
                        frame_bytes = None
                        if page:
                            try: frame_bytes = page.screenshot()
                            except: pass
                        res = self.vision.find_template_on_screen(marker_path, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                        is_met = (marker_mode == "Wait until Appear" and res) or (marker_mode == "Wait until Disappear" and not res)
                        if is_met:
                            if hold_start is None: hold_start = time.time()
                            if time.time() - hold_start >= marker_time: break
                        else:
                            hold_start = None
                        time.sleep(1.0)

    # ================= TAB AUTO LOOPS (Trí Tuệ Nhân Tạo Bot) =================
    def setup_loop_tab(self):
        self.current_loop_name = None
        self.loop_buttons = {}
        self.loop_checkbox_vars = {}

        self.tab_loop.grid_columnconfigure(0, weight=1, minsize=220)
        self.tab_loop.grid_columnconfigure(1, weight=3)
        self.tab_loop.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE (fixed header + scrollable list) ======
        self.loop_left_pane = ctk.CTkFrame(self.tab_loop, fg_color=COLOR["surface"])
        self.loop_left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        # -- Fixed header --
        ctk.CTkLabel(self.loop_left_pane, text="LOOPS", text_color=COLOR["accent"], font=ctk.CTkFont(weight="bold", size=13)).pack(padx=8, pady=(8, 4), anchor="w")

        # Action buttons (at top!)
        loop_actions_top = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent")
        loop_actions_top.pack(fill="x", padx=8, pady=(0, 4))

        self.add_loop_btn = ctk.CTkButton(loop_actions_top, text="+ Create", command=self.add_new_loop, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(weight="bold", size=12), corner_radius=6, height=28)
        self.add_loop_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        self.del_selected_loop_btn = ctk.CTkButton(loop_actions_top, text="Delete Selected", command=self.delete_selected_loops, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(weight="bold", size=12), corner_radius=6, height=28)
        self.del_selected_loop_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # Search bar
        self.loop_search_var = ctk.StringVar()
        self.loop_search_var.trace_add("write", lambda *a: self.refresh_loop_list())
        ctk.CTkEntry(self.loop_left_pane, placeholder_text="Search loops...", textvariable=self.loop_search_var, fg_color=COLOR["bg"], corner_radius=6, height=28).pack(fill="x", padx=8, pady=(0, 4))

        # Select All
        self.loop_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent")
        sa_row.pack(fill="x", padx=8, pady=(0, 2))
        ctk.CTkCheckBox(sa_row, text="Select All", variable=self.loop_select_all_var, command=self._toggle_select_all_loops, width=20, height=20, font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left")

        # -- Scrollable list body --
        self.loop_btn_container = ctk.CTkScrollableFrame(self.loop_left_pane, fg_color="transparent")
        self.loop_btn_container.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # ====== RIGHT PANE (Chi tiết Loop - Flowchart) ======
        self.loop_right_pane = ctk.CTkFrame(self.tab_loop, fg_color=COLOR["bg"])
        self.loop_right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.loop_top_bar = ctk.CTkFrame(self.loop_right_pane, fg_color="transparent", height=40)
        self.loop_top_bar.pack(fill="x", pady=(10, 0), padx=20)
        
        self.loop_name_label = ctk.CTkLabel(self.loop_top_bar, text="[No Loop Selected]", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLOR["text"])
        self.loop_name_label.pack(side="left")

        tab_idx_frame = ctk.CTkFrame(self.loop_top_bar, fg_color="transparent")
        tab_idx_frame.pack(side="left", padx=20)
        ctk.CTkLabel(tab_idx_frame, text="Tab ID:", font=ctk.CTkFont(size=12), text_color=COLOR["text_dim"]).pack(side="left", padx=2)
        self.loop_tab_index = ctk.CTkEntry(tab_idx_frame, width=30, placeholder_text="0", fg_color=COLOR["surface"], corner_radius=4)
        self.loop_tab_index.insert(0, "0")
        self.loop_tab_index.pack(side="left")

        self.play_loop_btn = ctk.CTkButton(self.loop_top_bar, text="Start Auto Loop", command=self.toggle_loop_engine, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], state="disabled", font=ctk.CTkFont(weight="bold"), width=150, corner_radius=6)
        self.play_loop_btn.pack(side="right")

        # Flowchart Toolbar
        self.flowchart_toolbar = ctk.CTkFrame(self.loop_right_pane, fg_color=COLOR["surface2"], height=40, corner_radius=6)
        self.flowchart_toolbar.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkButton(self.flowchart_toolbar, text="+ Start", width=80, fg_color=COLOR["success"], hover_color=COLOR["success_h"], command=lambda: self.flowchart_add_node("Start"), corner_radius=4).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ Macro", width=80, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], command=lambda: self.flowchart_add_node("Macro"), corner_radius=4).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ If Image", width=80, fg_color=COLOR["warning"], hover_color=COLOR["warning_h"], text_color=COLOR["text_dark"], command=lambda: self.flowchart_add_node("Condition"), corner_radius=4).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ Delay", width=80, fg_color="#7C3AED", hover_color="#6D28D9", command=lambda: self.flowchart_add_node("Delay"), corner_radius=4).pack(side="left", padx=5, pady=5)
        
        ctk.CTkLabel(self.flowchart_toolbar, text="Right-click to edit. Drag pins to connect.", text_color=COLOR["text_dim"], font=ctk.CTkFont(size=11)).pack(side="right", padx=10)

        # The Flowchart Canvas
        def get_macros_cb():
            return list(self.combos.keys())
        def get_images_cb():
            return list(self.tracked_icons.keys())
        def on_change_cb():
            if self.current_loop_name:
                self.loops[self.current_loop_name] = self.flowchart.export_graph()
                self.save_loops()

        self.flowchart = FlowchartUI(self.loop_right_pane, get_macros_cb=get_macros_cb, get_images_cb=get_images_cb, on_change_cb=on_change_cb)
        self.flowchart.pack(fill="both", expand=True, padx=20, pady=(0, 20))

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
                btn.configure(fg_color="#D35400") # Cam đậm
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
        dialog = ctk.CTkInputDialog(text="Tên Vòng Lặp mới (ví dụ: Bot Farm):", title="New Loop")
        name = dialog.get_input()
        if name:
            name = name.strip()
            if not name: return
            if name in self.loops:
                messagebox.showerror("Error", "Tên Loop này đã tồn tại!")
                return
            
            # Khởi tạo Graph rỗng
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
            messagebox.showinfo("Info", "Bạn chưa chọn Loop nào để xóa!")
            return
            
        if messagebox.askyesno("Confirm", f"Xóa {len(to_delete)} Loop đã chọn?"):
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
            self.log_gui(f"[System] Đã xóa {len(to_delete)} Loop thành công.")

    def delete_current_loop(self):
        pass # Optional convenience

    def toggle_loop_engine(self):
        if not self.is_looping:
            if not self.current_loop_name: return
            graph = self.loops.get(self.current_loop_name, {})
            nodes = graph.get("nodes", {})
            if not nodes:
                return messagebox.showwarning("Empty", "Flowchart is empty!")
                
            # Find start node
            start_node = None
            for nid, n in nodes.items():
                if n["type"] == "Start":
                    start_node = nid
                    break
                    
            if not start_node:
                return messagebox.showerror("Error", "Flowchart does not have a Start node!")
                
            tab_id_str = self.loop_tab_index.get().strip()
            tab_id = int(tab_id_str) if tab_id_str.isdigit() else None
            
            self.is_looping = True
            self.play_loop_btn.configure(text="⏹ DỪNG LOOP AUTO", fg_color="#E74C3C", hover_color="#C0392B")
            self.log_gui(f"★★★ KÍCH HOẠT HỆ THỐNG FLOWCHART AUTO: [{self.current_loop_name}] TRÊN TAB {tab_id} ★★★")
            
            threading.Thread(target=self._loop_engine_worker, args=(graph, start_node, tab_id), daemon=True).start()
        else:
            self.is_looping = False
            self.play_loop_btn.configure(text="⭕ START AUTO LOOP", fg_color="#C0392B", hover_color="#A93226")
            self.log_gui("★★★ HỆ THỐNG AUTO LOOP ĐÃ TẮT ★★★")

    def _loop_engine_worker(self, graph, start_node, tab_id=None):
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", {})
        
        current_node_id = start_node
        
        # Helper to find next node ID given a pin
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
                 self.log_gui(f"[Loop Engine] Connect Tab {tab_id} at localhost:9222...")
                 browser = playwright_ctx.chromium.connect_over_cdp("http://localhost:9222")
                 context = browser.contexts[0]
                 page, info = get_page_by_visual_index(context, tab_id)
                 if page:
                     if isinstance(info, list):
                         for idx_t, title_t in info:
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
            threshold_val = self.slider.get()  # Refresh each iteration
            
            if ntype == "Start":
                self.log_gui(f"[FLOWCHART] ---> START")
                current_node_id = get_next_node(current_node_id, "out")
                time.sleep(0.5)
                
            elif ntype == "Macro":
                mac_name = ndata.get("macro_name")
                if mac_name and mac_name in self.combos:
                    self.log_gui(f"[FLOWCHART] Executing Macro: {mac_name}")
                    macro_data = self.combos[mac_name]
                    result = self._internal_macro_runner(macro_data, bot_instance, page=page)
                    if result:
                        self.log_gui(f"[FLOWCHART] -> Macro OK. Following success path.")
                        current_node_id = get_next_node(current_node_id, "true")
                    else:
                        self.log_gui(f"[FLOWCHART] -> Macro FAILED. Following failure path.")
                        current_node_id = get_next_node(current_node_id, "false")
                else:
                    self.log_gui(f"[FLOWCHART] Warning: Invalid Macro '{mac_name}'. Following failure path.")
                    current_node_id = get_next_node(current_node_id, "false")
                
            elif ntype == "Delay":
                delay_time = ndata.get("time", 1.0)
                self.log_gui(f"[FLOWCHART] ⏳ Waiting {delay_time}s...")
                
                # Check looping status while sleeping to allow early exit
                steps = int(delay_time * 10)
                for _ in range(steps):
                    if not self.is_looping: break
                    time.sleep(0.1)
                
                current_node_id = get_next_node(current_node_id, "out")
                
            elif ntype == "Condition":
                img_name = ndata.get("image_name")
                filepath = self.tracked_icons.get(img_name)
                
                if not filepath or not os.path.exists(filepath):
                    self.log_gui(f"[FLOWCHART] ⚠️ Image condition '{img_name}' not found. Defaulting to False.")
                    current_node_id = get_next_node(current_node_id, "false")
                else:
                    self.log_gui(f"[FLOWCHART] Checking: Is '{img_name}' on screen?")
                    
                    # Retry up to 3 times to handle screenshot timing variability
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
                        self.log_gui(f"[FLOWCHART] -> TRUE (Found '{img_name}')")
                        current_node_id = get_next_node(current_node_id, "true")
                    else:
                        self.log_gui(f"[FLOWCHART] → FALSE (Not Found)")
                        current_node_id = get_next_node(current_node_id, "false")
                time.sleep(0.5)
                
        if browser: browser.close()
        playwright_ctx.stop()

    def _internal_macro_runner(self, macro_data, bot_instance, acc_name=None, page=None):
        # Hàm chạy lõi của Combo. Có thể truyền tùy chọn Page (nếu chạy nền)
        steps = macro_data.get("steps", [])
        threshold_val = self.slider.get()
        
        def local_log(msg):
            if acc_name:
                self.log_gui(f"[{acc_name}] {msg}")
            else:
                self.log_gui(msg)
        
        for idx, step_data in enumerate(steps):
            if isinstance(step_data, str):
                node_name = step_data
                marker = "None"
                marker_mode = "Wait until Appear"
                marker_time = 0
            else:
                node_name = step_data.get("node", "")
                marker = step_data.get("marker", "None")
                marker_mode = step_data.get("mode", "Wait until Appear")
                try:
                    marker_time = float(step_data.get("time", "0")) / 1000.0
                except:
                    marker_time = 0
                    
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
                res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
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
                
            # Marker verification — wait for image appear/disappear before next step
            if marker != "None":
                mode_str = "APPEAR" if marker_mode == "Wait until Appear" else "DISAPPEAR"
                local_log(f"    - Waiting for Marker '{marker}' to {mode_str} (hold {marker_time}s)...")
                marker_path = self.tracked_icons.get(marker)
                if marker_path and os.path.exists(marker_path):
                    marker_found_or_lost = False
                    hold_start = None
                    last_log_time = 0
                    
                    timeout = time.time() + 300  # 5 min watchdog
                    
                    for attempt in range(99999):
                        if time.time() > timeout:
                            local_log(f"    - Marker TIMEOUT (5 min): '{marker}'. Macro FAILED.")
                            return False
                            
                        if not self.is_looping and not self.is_coordinating: break
                        
                        frame_bytes = None
                        if page:
                            try:
                                frame_bytes = page.screenshot()
                            except: pass
                            
                        res = self.vision.find_template_on_screen(marker_path, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                        
                        is_condition_met = (marker_mode == "Wait until Appear" and res) or (marker_mode == "Wait until Disappear" and not res)
                        
                        if is_condition_met:
                            if hold_start is None:
                                hold_start = time.time()
                                if marker_time > 0:
                                    local_log(f"    - Marker triggered. Holding {marker_time}s...")
                            
                            elapsed = time.time() - hold_start
                            
                            current_sec = int(elapsed)
                            if marker_time > 0 and current_sec > last_log_time:
                                local_log(f"    - Holding... {current_sec}/{marker_time}s")
                                last_log_time = current_sec
                                
                            if elapsed >= marker_time:
                                local_log(f"    - Marker OK: '{marker}' confirmed {mode_str}.")
                                marker_found_or_lost = True
                                break
                        else:
                            if hold_start is not None:
                                local_log(f"    - Marker interrupted. Resetting hold timer.")
                                hold_start = None
                                last_log_time = 0
                            
                        time.sleep(1.0)
                        
                    if not marker_found_or_lost and (self.is_looping or self.is_coordinating):
                        local_log(f"    - Marker FAILED: '{marker}' did not {mode_str} in time.")
                        return False
                    
        local_log(f"[STATE MACHINE] Macro steps completed. Checking result...")

        # Result verification via success/failure capture
        success_capture = macro_data.get("success_capture", "None")
        failure_capture = macro_data.get("failure_capture", "None")
        
        if success_capture == "None" and failure_capture == "None":
            local_log(f"[STATE MACHINE] Macro finished (no capture check configured).")
            return True  # No verification = assume success
        
        # Wait a moment for UI to settle before checking
        time.sleep(1.0)
        
        frame_bytes = None
        if page:
            try: frame_bytes = page.screenshot()
            except: pass
        
        # Check success capture first
        if success_capture != "None":
            s_path = self.tracked_icons.get(success_capture)
            if s_path and os.path.exists(s_path):
                res = self.vision.find_template_on_screen(s_path, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                if res:
                    local_log(f"[STATE MACHINE] Result: SUCCESS (found '{success_capture}')")
                    return True
                else:
                    local_log(f"[STATE MACHINE] Result: FAILURE ('{success_capture}' not found)")
                    return False
        
        # If only failure capture is set, check it
        if failure_capture != "None":
            f_path = self.tracked_icons.get(failure_capture)
            if f_path and os.path.exists(f_path):
                res = self.vision.find_template_on_screen(f_path, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                if res:
                    local_log(f"[STATE MACHINE] Result: FAILURE (found '{failure_capture}')")
                    return False
                else:
                    local_log(f"[STATE MACHINE] Result: SUCCESS ('{failure_capture}' not found)")
                    return True
        
        local_log(f"[STATE MACHINE] Macro finished (capture images not available).")
        return True


    # ================= FUNC TION MULTI TRACKER (Bên Tab Tracking) =================
    def setup_tracker_tab(self):
        self.tracked_icons = {}
        self.current_selected_name = None
        self.icon_buttons = {}
        self.icon_checkbox_vars = {}
        self.is_tracking = False

        os.makedirs("trackers", exist_ok=True)

        self.tab_setup.grid_columnconfigure(0, weight=1, minsize=220)
        self.tab_setup.grid_columnconfigure(1, weight=3)
        self.tab_setup.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE (fixed header + scrollable list) ======
        self.left_pane = ctk.CTkFrame(self.tab_setup, fg_color=COLOR["surface"])
        self.left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        # -- Fixed header --
        self.node_header = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        self.node_header.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(self.node_header, text="TARGET NODES", text_color=COLOR["accent"], font=ctk.CTkFont(weight="bold", size=13)).pack(anchor="w")

        # Action buttons (at top!)
        node_actions = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        node_actions.pack(fill="x", padx=8, pady=(0, 4))
        
        self.add_btn = ctk.CTkButton(node_actions, text="+ Add", command=self.add_new_target, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(weight="bold", size=12), corner_radius=6, height=28)
        self.add_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        self.del_selected_btn = ctk.CTkButton(node_actions, text="Delete Selected", command=self.delete_selected_targets, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(weight="bold", size=12), corner_radius=6, height=28)
        self.del_selected_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # Search bar
        self.node_search_var = ctk.StringVar()
        self.node_search_var.trace_add("write", lambda *a: self.refresh_tracked_list())
        self.node_search_entry = ctk.CTkEntry(self.left_pane, placeholder_text="Search nodes...", textvariable=self.node_search_var, fg_color=COLOR["bg"], corner_radius=6, height=28)
        self.node_search_entry.pack(fill="x", padx=8, pady=(0, 4))

        # Select All row
        self.node_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        sa_row.pack(fill="x", padx=8, pady=(0, 2))
        ctk.CTkCheckBox(sa_row, text="Select All", variable=self.node_select_all_var, command=self._toggle_select_all_nodes, width=20, height=20, font=ctk.CTkFont(size=11), text_color=COLOR["text_dim"]).pack(side="left")

        # -- Scrollable list body --
        self.btn_container = ctk.CTkScrollableFrame(self.left_pane, fg_color="transparent")
        self.btn_container.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # ====== RIGHT PANE ======
        self.right_pane = ctk.CTkFrame(self.tab_setup, fg_color=COLOR["bg"])
        self.right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.top_bar = ctk.CTkFrame(self.right_pane, fg_color="transparent", height=40)
        self.top_bar.pack(fill="x", pady=(10, 0), padx=20)
        
        self.preview_title = ctk.CTkLabel(self.top_bar, text="TEMPLATE PREVIEW", font=ctk.CTkFont(weight="bold", size=15), text_color=COLOR["accent"])
        self.preview_title.pack()


        # Nơi chứa config Nút hiện tại
        self.preview_name_frame = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        self.preview_name_frame.pack(pady=5)
        self.preview_name_label = ctk.CTkLabel(self.preview_name_frame, text="No Target Selected", font=ctk.CTkFont(size=14))
        self.preview_name_label.pack(side="left")
        self.preview_status_label = ctk.CTkLabel(self.preview_name_frame, text="", text_color=COLOR["success"], font=ctk.CTkFont(weight="bold"))
        self.preview_status_label.pack(side="left", padx=5)

        self.preview_image_label = ctk.CTkLabel(self.right_pane, text="[Select any target Node to view details]")
        self.preview_image_label.pack(pady=30, expand=True)

        self.preview_size_label = ctk.CTkLabel(self.right_pane, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.preview_size_label.pack(pady=0, anchor="e", padx=20)

        self.target_controls = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        self.target_controls.pack(side="bottom", fill="x", pady=20, padx=20)
        
        # Settings Section
        self.settings_frame = ctk.CTkFrame(self.right_pane, fg_color=COLOR["surface"], corner_radius=8)
        self.settings_frame.pack(side="bottom", fill="x", pady=(0, 10), padx=20)
        
        self.thresh_label = ctk.CTkLabel(self.settings_frame, text="Accuracy Threshold: 0.85", font=ctk.CTkFont(size=12), text_color=COLOR["text_dim"])
        self.thresh_label.pack(padx=12, pady=(8, 2), anchor="w")
        self.slider = ctk.CTkSlider(self.settings_frame, from_=0.5, to=0.99, command=self._on_threshold_change, progress_color=COLOR["primary"], button_color=COLOR["primary"])
        
        # Load saved threshold
        saved_thresh = 0.85
        try:
            if os.path.exists("config.json"):
                import json as _json
                with open("config.json", "r") as f:
                    cfg = _json.load(f)
                saved_thresh = cfg.get("threshold", 0.85)
        except: pass
        self.slider.set(saved_thresh)
        self.thresh_label.configure(text=f"Accuracy Threshold: {saved_thresh:.2f}")
        self.slider.pack(fill="x", padx=12, pady=(0, 4))
        
        self.debug_toggle_switch = ctk.CTkSwitch(
            self.settings_frame,
            text="Show Click Position (Red Dot)",
            variable=self.debug_visual_var,
            onvalue=True, offvalue=False,
            font=ctk.CTkFont(size=12),
            progress_color=COLOR["danger"]
        )
        self.debug_toggle_switch.pack(anchor="w", padx=12, pady=(2, 10))

        self.test_node_btn = ctk.CTkButton(self.target_controls, text="Test Node", command=self.test_current_node, fg_color=COLOR["warning"], hover_color=COLOR["warning_h"], text_color=COLOR["text_dark"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=6)
        self.test_node_btn.pack(side="top", pady=(0, 8), expand=True, fill="x", padx=5)

        self.recapture_btn = ctk.CTkButton(self.target_controls, text="Re-Capture", command=self.recapture_current, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=6)
        self.recapture_btn.pack(side="left", padx=5, expand=True, fill="x")

        self.delete_btn = ctk.CTkButton(self.target_controls, text="Delete Node", command=self.delete_current, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], state="disabled", font=ctk.CTkFont(weight="bold"), corner_radius=6)
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

    def test_current_node(self):
        if not self.current_selected_name: return
        name = self.current_selected_name
        filepath = self.tracked_icons.get(name)
        
        if not filepath or not os.path.exists(filepath):
            messagebox.showwarning("Error", f"No file found for node '{name}'")
            return
            
        # Chạy trong thread riêng để không block GUI
        def _run_test():
            self.log_gui(f"[TEST] Bắt đầu scan thử Node '{name}'...")
            threshold_val = self.slider.get()
            
            # Kết nối Playwright để lấy frame_bytes giống Macro
            page = None
            playwright_ctx = None
            browser = None
            try:
                from playwright.sync_api import sync_playwright
                playwright_ctx = sync_playwright().start()
                browser = playwright_ctx.chromium.connect_over_cdp("http://localhost:9222")
                if browser.contexts and browser.contexts[0].pages:
                    # Log available tabs
                    context = browser.contexts[0]
                    for i, p in enumerate(context.pages):
                        self.log_gui(f"[TEST]   Tab {i}: {p.url[:80]}")
                    page, info = get_page_by_visual_index(context, 0)
                    if isinstance(info, list):
                        for idx_t, title_t, url_t in info:
                            self.log_gui(f"[TEST]   Tab {idx_t}: {title_t}")
                    self.log_gui(f"[TEST] Using Tab 0: {page.url[:60] if page else 'NOT FOUND'}")
            except:
                pass
            
            frame_bytes = None
            if page:
                try: frame_bytes = page.screenshot()
                except: pass
            
            res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=True, frame_bytes=frame_bytes)
            if res:
                x, y, score = res
                self.log_gui(f"[TEST] ✅ Success! Tìm thấy '{name}' tại ({x}, {y}) với độ chính xác {score:.2f}")
                # Hiện chấm đỏ thay vì move chuột
                if page and self.debug_visual_var.get():
                    try:
                        dpr = float(page.evaluate("window.devicePixelRatio"))
                    except:
                        dpr = 1.0
                    css_x = x / dpr
                    css_y = y / dpr
                    
                    # Tìm frame chứa canvas
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
                self.log_gui(f"[TEST] ❌ Failed. KHÔNG tìm thấy '{name}' trên màn hình với Threshold={threshold_val:.2f}")
            
            # Cleanup
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
            self.log_gui(f"📸 Template acquired for Node [{name}] ({w}x{h} px)")
            self.on_select_target(name)
            
        self.snip_process(save_path, success)

    def delete_selected_targets(self):
        to_delete = [name for name, var in self.icon_checkbox_vars.items() if var.get()]
        if not to_delete:
            messagebox.showinfo("Info", "Bạn chưa chọn Node nào để xóa!")
            return
            
        if messagebox.askyesno("Confirm", f"Xóa {len(to_delete)} Node đã chọn?"):
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
            self.log_gui(f"[System] Đã xóa {len(to_delete)} Node thành công.")

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
            self.start_tracking_btn.configure(text="⏹ STOP MONITOR PROCESS", fg_color="red", hover_color="darkred")
            self.log_gui(f"--- INITIATING RADAR SCAN: {len(valid_targets)} TARGETS ENQUEUED ---")
            
            self.log_gui(f"[Alert] No Game Window set! Scanning FULL Desktop -> Slower Performance")
                
            threading.Thread(target=self.tracker_loop, daemon=True).start()
        else:
            self.is_tracking = False
            self.start_tracking_btn.configure(text="👁 MASTER MONITOR: TRACK ALL NODES", fg_color=['#3B8ED0', '#1F6AA5'])
            self.log_gui("--- RADAR SCAN SHUT DOWN ---")

    def tracker_loop(self):
        threshold_val = self.slider.get()
        while self.is_tracking:
            for name, filepath in self.tracked_icons.items():
                if not filepath or not os.path.exists(filepath): continue
                
                # Quét và truyển luôn self.game_region xuống để Vision thư viện thu hẹp Mắt nhìn lại
                res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False)
                if res:
                    x, y, score = res
                    self.log_gui(f"✔️ MATCHED [{name}] -> Cord({x}, {y}) | Edge Conf: {score:.2f}")
            time.sleep(1.0) 

    # ================= FUNC TION CHUNG=================
    def log_gui(self, text):
        """Puts a log message into the thread-safe queue."""
        self.gui_queue.put(("log", text))
        
    def _internal_log_gui(self, text):
        """Actual Tkinter update function (Must only be called by Main Thread via queue)"""
        self.log_textbox.configure(state="normal")
        lines = int(self.log_textbox.index('end').split('.')[0]) - 1
        if lines > 150:
            self.log_textbox.delete("1.0", "20.0")
        current_time = time.strftime("%H:%M:%S")
        self.log_textbox.insert("end", f"[{current_time}] {text}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def snip_process(self, save_path, success_callback):
        # Bắt buộc user phải Set Game Window trước khi cho phép Cắt Hình Mục tiêu
        # if not self.game_region:
        #     messagebox.showwarning("Warning", "Please [📐 SET GAME WINDOW] first before adding any Target Nodes!")
        #     return
            
        self.withdraw()
        time.sleep(0.3)
        from screencapture import ScreenCaptureTool
        def on_snip(x1, y1, x2, y2):
            img = pyautogui.screenshot(region=(x1, y1, x2-x1, y2-y1))
            img.save(save_path)
            self.deiconify()
            success_callback(x2-x1, y2-y1)
            
        # Truyền game_region vào Tool cắt để khoanh vùng giới hạn
        snipper = ScreenCaptureTool(on_snip)
        snipper.run()

    # ================= TAB MULTI-ACCOUNTS (Coordinator Dashboard) =================
    def setup_multi_tab(self):
        self.tab_multi.grid_columnconfigure(0, weight=1, minsize=280)
        self.tab_multi.grid_columnconfigure(1, weight=3)
        self.tab_multi.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE (Settings) ======
        self.multi_left_pane = ctk.CTkFrame(self.tab_multi, fg_color=COLOR["surface"])
        self.multi_left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        self.multi_title = ctk.CTkLabel(self.multi_left_pane, text="ACCOUNTS", text_color=COLOR["accent"], font=ctk.CTkFont(weight="bold", size=13))
        self.multi_title.pack(pady=(10, 5))

        # ---- Chrome Instances Panel ----
        chrome_frame = ctk.CTkFrame(self.multi_left_pane, fg_color=COLOR["surface2"], corner_radius=8)
        chrome_frame.pack(fill="x", padx=10, pady=(5, 5))
        
        ctk.CTkLabel(chrome_frame, text="CHROME INSTANCES", font=ctk.CTkFont(weight="bold", size=11), text_color=COLOR["accent"]).pack(padx=10, pady=(6, 2), anchor="w")
        
        chrome_btn_row = ctk.CTkFrame(chrome_frame, fg_color="transparent")
        chrome_btn_row.pack(fill="x", padx=10, pady=2)
        
        ctk.CTkButton(chrome_btn_row, text="+ Launch Chrome", command=self._launch_new_chrome, fg_color=COLOR["success"], hover_color=COLOR["success_h"], font=ctk.CTkFont(weight="bold", size=11), corner_radius=6, height=28).pack(side="left", expand=True, fill="x", padx=(0, 2))
        
        ctk.CTkButton(chrome_btn_row, text="Refresh", command=self._refresh_connection_status, fg_color=COLOR["surface"], hover_color="#3D5A80", text_color=COLOR["text"], corner_radius=6, height=28, width=70).pack(side="right", padx=(2, 0))
        
        self.chrome_instances_container = ctk.CTkFrame(chrome_frame, fg_color="transparent")
        self.chrome_instances_container.pack(fill="x", padx=10, pady=(2, 8))
        
        self.conn_status_label = ctk.CTkLabel(self.chrome_instances_container, text="Not checked yet", text_color=COLOR["text_dim"], font=ctk.CTkFont(size=10))
        self.conn_status_label.pack(anchor="w")

        # ---- Account List ----
        acc_header = ctk.CTkFrame(self.multi_left_pane, fg_color="transparent")
        acc_header.pack(fill="x", padx=10, pady=(5, 0))
        ctk.CTkLabel(acc_header, text="Assigned Accounts:", text_color=COLOR["text"], font=ctk.CTkFont(weight="bold")).pack(side="left")
        
        self.acc_list_frame = ctk.CTkScrollableFrame(self.multi_left_pane, fg_color=COLOR["bg"], height=150)
        self.acc_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.multi_actions = ctk.CTkFrame(self.multi_left_pane, fg_color="transparent")
        self.multi_actions.pack(side="bottom", fill="x", pady=10, padx=10)

        ctk.CTkButton(self.multi_actions, text="+ Add Account", command=self.add_multi_account, fg_color=COLOR["success"], hover_color=COLOR["success_h"], font=ctk.CTkFont(weight="bold"), corner_radius=6).pack(side="top", fill="x", pady=2)

        # ====== RIGHT PANE (Dashboard) ======
        self.multi_right_pane = ctk.CTkFrame(self.tab_multi, fg_color=COLOR["bg"])
        self.multi_right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.dash_top_bar = ctk.CTkFrame(self.multi_right_pane, fg_color="transparent", height=40)
        self.dash_top_bar.pack(fill="x", pady=(10, 0), padx=20)

        self.dash_title = ctk.CTkLabel(self.dash_top_bar, text="COORDINATOR DASHBOARD", font=ctk.CTkFont(weight="bold", size=15), text_color=COLOR["accent"])
        self.dash_title.pack(side="left")
        
        # Batch controls
        batch_frame = ctk.CTkFrame(self.dash_top_bar, fg_color="transparent")
        batch_frame.pack(side="right")
        
        ctk.CTkButton(batch_frame, text="Start All", command=self._batch_start_all, fg_color=COLOR["success"], hover_color=COLOR["success_h"], font=ctk.CTkFont(weight="bold", size=11), corner_radius=6, height=30, width=80).pack(side="left", padx=2)
        
        ctk.CTkButton(batch_frame, text="Stop All", command=self._batch_stop_all, fg_color=COLOR["danger"], hover_color=COLOR["danger_h"], font=ctk.CTkFont(weight="bold", size=11), corner_radius=6, height=30, width=80).pack(side="left", padx=2)
        
        ctk.CTkButton(batch_frame, text="Start Selected", command=self._batch_start_selected, fg_color=COLOR["primary"], hover_color=COLOR["primary_h"], font=ctk.CTkFont(size=11), corner_radius=6, height=30, width=100).pack(side="left", padx=2)
        
        ctk.CTkButton(batch_frame, text="Stop Selected", command=self._batch_stop_selected, fg_color=COLOR["surface2"], hover_color="#3D5A80", text_color=COLOR["text"], font=ctk.CTkFont(size=11), corner_radius=6, height=30, width=100).pack(side="left", padx=2)

        self.dash_grid = ctk.CTkScrollableFrame(self.multi_right_pane, fg_color=COLOR["surface"])
        self.dash_grid.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.dash_labels = {}
        self.dash_conn_labels = {}
        self.dash_checkboxes = {}  # name -> BooleanVar
        self.refresh_multi_acc_list()
        
        # Auto-check connection on startup (delayed)
        self.after(2000, self._refresh_connection_status)
        # Start health monitor
        self._start_health_monitor()

    # ---- Chrome Management ----
    def _launch_new_chrome(self):
        """Launch a new Chrome instance on the next available port."""
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
        """Kill Chrome instance on a specific port."""
        success, msg = self.chrome_mgr.kill(port)
        self.log_gui(f"[Chrome] {msg}")
        self.state_db.remove_chrome_instance(port)
        self.after(500, self._refresh_connection_status)

    def _refresh_connection_status(self):
        """Check all Chrome instances and update UI."""
        def _check():
            ports_info = self.chrome_mgr.get_all_ports_info()
            self.gui_queue.put(("conn_status", ports_info))
        
        self.conn_status_label.configure(text="Checking...", text_color=COLOR["warning"])
        threading.Thread(target=_check, daemon=True).start()

    def _render_connection_status(self, ports_info):
        """Render Chrome instances status in the UI."""
        for w in self.chrome_instances_container.winfo_children():
            w.destroy()
        
        if not ports_info:
            ctk.CTkLabel(self.chrome_instances_container, text="No Chrome instances detected", text_color=COLOR["text_dim"], font=ctk.CTkFont(size=10)).pack(anchor="w")
            # Mark all cards disconnected
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
        
        # Update per-card connection indicators
        if hasattr(self, 'dash_conn_labels'):
            all_ports_tabs = {}  # port -> tab_count
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

        # Port + Tab index
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
            
            # Enabled indicator
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
            
            # Checkbox for batch select
            chk_var = ctk.BooleanVar(value=False)
            self.dash_checkboxes[name] = chk_var
            ctk.CTkCheckBox(card_top, text="", variable=chk_var, width=20, height=20).pack(side="left", padx=(0, 4))
            
            # Connection indicator
            lbl_conn = ctk.CTkLabel(card_top, text=f"P{port}:T{acc.get('target', '?')}", 
                                   font=ctk.CTkFont(size=10, weight="bold"), text_color=COLOR["text_dim"], width=60)
            lbl_conn.pack(side="left", padx=(0, 4))
            self.dash_conn_labels[name] = lbl_conn
            
            # Account name
            ctk.CTkLabel(card_top, text=name, font=ctk.CTkFont(weight="bold", size=13), 
                        text_color=COLOR["text"], anchor="w").pack(side="left", padx=(0, 8))
            
            # Status label
            lbl_status = ctk.CTkLabel(card_top, text="Idle", text_color=COLOR["text_dim"], 
                                     font=ctk.CTkFont(size=11), anchor="w")
            lbl_status.pack(side="left", fill="x", expand=True)
            self.dash_labels[name] = lbl_status
            
            # Per-card start/stop button
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
            
            # Info row
            info_parts = [f"Loop: {acc.get('loop', '?')}",
                         f"Group: {acc.get('group', 'default')}"]
            if acc.get('proxy'):
                info_parts.append(f"Proxy: {acc['proxy'][:25]}")
            
            ctk.CTkLabel(card, text=" | ".join(info_parts), font=ctk.CTkFont(size=10), 
                        text_color=COLOR["text_dim"]).pack(padx=12, pady=(0, 6), anchor="w")

    def update_dash_status(self, acc_name, status, color="white"):
        """Thread-safe dashboard status update."""
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
        """Start a single account worker."""
        if self.account_running.get(acc_name, False):
            return  # Already running
        
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
        """Stop a single account worker."""
        self.account_running[acc_name] = False
        self.state_db.save_account_state(acc_name, status="stopping")
        self.update_dash_status(acc_name, "Stopping...", COLOR["warning"])
        self.log_gui(f"[{acc_name}] Stop signal sent")
        self.after(1500, self.refresh_multi_acc_list)

    # ---- Legacy coordinator toggle (now uses batch) ----
    def toggle_coordinator(self):
        has_running = any(self.account_running.get(a['name'], False) for a in self.multi_accounts)
        if has_running:
            self._batch_stop_all()
        else:
            self._batch_start_all()

    # ---- Health Monitor ----
    def _start_health_monitor(self):
        """Background thread that checks health every 30 seconds."""
        self.health_monitor_active = True
        
        def _monitor_loop():
            while self.health_monitor_active:
                try:
                    # Check Chrome instances
                    active_ports = self.chrome_mgr.get_active_ports()
                    
                    # Check worker threads
                    for acc_name, thread in list(self.account_workers.items()):
                        if self.account_running.get(acc_name, False) and not thread.is_alive():
                            self.gui_queue.put(("log", f"[Health] Worker {acc_name} died! Restarting..."))
                            self.account_running[acc_name] = False
                            self.state_db.save_account_state(acc_name, status="crashed")
                            # Auto-restart
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
                
                # Sleep in small intervals so we can stop quickly
                for _ in range(60):  # 30 seconds total
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
        threshold_val = self.slider.get()
        
        graph = self.loops.get(loop_name, {})
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        
        self.update_dash_status(acc_name, "Connecting...", COLOR["warning"])
        self.state_db.save_account_state(acc_name, loop_name=loop_name, status="connecting", 
                                          port=port, tab_index=tab_idx)
        
        # ---- Connection with auto-reconnect ----
        browser = None
        page = None
        pw = None
        
        def connect_to_tab():
            """Connect or reconnect to the correct tab."""
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
                    p, info = get_page_by_visual_index(context, tab_idx)
                    
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
                    wait_time = 2 ** (attempt + 1)  # Exponential backoff: 2, 4, 8, 16s
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

        # Always start from the beginning
        current_node_id = get_start_node()
        
        self.state_db.save_account_state(acc_name, status="running", current_node=current_node_id or "")
        
        # ---- Main execution loop ----
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

            # Save state on every node transition
            self.state_db.save_account_state(acc_name, current_node=current_node_id)

            if ntype == "Start":
                self.update_dash_status(acc_name, "Running...", COLOR["success"])
                next_nid = get_next_node(current_node_id, "out")
                time.sleep(0.5)
                
            elif ntype == "Delay":
                delay_time = ndata.get("time", 1.0)
                self.update_dash_status(acc_name, f"Delay ({delay_time}s)...", COLOR["accent"])
                self.state_db.log_action(acc_name, "delay", f"{delay_time}s")
                steps = int(float(delay_time) * 10)
                for _ in range(steps):
                    if not self.account_running.get(acc_name, False): break
                    time.sleep(0.1)
                next_nid = get_next_node(current_node_id, "out")
                
            elif ntype == "Condition":
                img_name = ndata.get("image_name")
                filepath = self.tracked_icons.get(img_name)
                
                if not filepath or not os.path.exists(filepath):
                    self.update_dash_status(acc_name, f"Cond Err: Missing Image", COLOR["danger"])
                    next_nid = get_next_node(current_node_id, "false")
                else:
                    self.update_dash_status(acc_name, f"Scanning: {img_name}...", COLOR["warning"])
                    
                    frame_bytes = None
                    try:
                        frame_bytes = page.screenshot()
                    except Exception as e:
                        self.log_gui(f"[{acc_name}] Screenshot Error, reconnecting: {str(e)[:40]}")
                        self.state_db.log_action(acc_name, "reconnect", f"Screenshot failed: {e}")
                        if connect_to_tab():
                            bot_instance = BotAction(page=page, debug_visual_var=self.debug_visual_var)
                            continue  # Retry this node
                        else:
                            self.update_dash_status(acc_name, "Reconnect Failed", COLOR["danger"])
                            break
                        
                    res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                    if res:
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
                        self._internal_macro_runner(self.combos[mac_name], bot_instance, acc_name=acc_name, page=page)
                        self.state_db.log_action(acc_name, "macro_done", mac_name, "OK")
                        next_nid = get_next_node(current_node_id, "true")
                    except Exception as e:
                        self.log_gui(f"[{acc_name}] Macro error: {e}")
                        self.state_db.log_action(acc_name, "macro_error", mac_name, str(e))
                        next_nid = get_next_node(current_node_id, "false")
                        # Try reconnecting
                        if connect_to_tab():
                            bot_instance = BotAction(page=page, debug_visual_var=self.debug_visual_var)
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

if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for ProcessPoolExecutor on Windows
    app = BotApp()
    try:
        app.mainloop()
    finally:
        # Dọn dẹp ProcessPool khi thoát
        app.vision.shutdown_pool()
