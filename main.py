import customtkinter as ctk
from tkinter import filedialog, messagebox
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

# Thiết lập Giao diện tối mang phong cách LordNine Bot Control
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class BotApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LordNine Bot Control")
        self.geometry("900x650")

        self.vision = Vision()

        # (Bỏ qua self.game_region vì Playwright chụp Frame chuẩn 100%)
        
        # Load hệ thống Combo cũ nếu có
        self.combos = {}
        self.load_combos()

        # Load hệ thống Loop cũ nếu có
        self.loops = {}
        self.load_loops()

        # Load hệ thống Multi-Account 
        self.multi_accounts = []
        self.load_multi()

        # Tạo Tabview
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        self.tab_setup = self.tabview.add("Setup & Tracking")
        self.tab_combo = self.tabview.add("Combo Macros")
        self.tab_loop = self.tabview.add("Auto Loops")
        self.tab_multi = self.tabview.add("Multi-Accounts")

        self.system_log_frame = ctk.CTkFrame(self)
        self.system_log_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        
        self.log_header_frame = ctk.CTkFrame(self.system_log_frame, fg_color="transparent")
        self.log_header_frame.pack(fill="x", pady=2)
        
        self.log_title = ctk.CTkLabel(self.log_header_frame, text="System Logs", font=ctk.CTkFont(size=12, weight="bold"))
        self.log_title.pack(side="left", padx=5)
        
        def clear_log():
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.configure(state="disabled")
            
        self.btn_clear_log = ctk.CTkButton(self.log_header_frame, text="🗑 Clear", width=50, height=20, font=ctk.CTkFont(size=11), fg_color="#E74C3C", hover_color="#C0392B", command=clear_log)
        self.btn_clear_log.pack(side="right", padx=5)

        self.log_textbox = ctk.CTkTextbox(self.system_log_frame, height=120, state="disabled", fg_color="#0D1117", text_color="#1ABC9C")
        self.log_textbox.pack(fill="both", expand=True)

        self.setup_tracker_tab()
        self.setup_combo_tab()
        self.setup_loop_tab()
        self.setup_multi_tab()
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

        # ====== LEFT PANE (Danh sách Combo) ======
        self.combo_left_pane = ctk.CTkScrollableFrame(self.tab_combo, fg_color="#1E2B3C")
        self.combo_left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        self.combo_list_title = ctk.CTkLabel(self.combo_left_pane, text="--- MACROS LIST ---", text_color="#1ABC9C", font=ctk.CTkFont(weight="bold"))
        self.combo_list_title.pack(pady=(5, 15))
        
        self.combo_btn_container = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent")
        self.combo_btn_container.pack(fill="x", expand=True)
        
        self.combo_actions = ctk.CTkFrame(self.combo_left_pane, fg_color="transparent")
        self.combo_actions.pack(side="bottom", fill="x", pady=(20, 5))

        self.add_combo_btn = ctk.CTkButton(self.combo_actions, text="+ ADD NEW MACRO", command=self.add_new_combo, fg_color="#F2994A", text_color="black", hover_color="#F2C94C", font=ctk.CTkFont(weight="bold"))
        self.add_combo_btn.pack(side="top", fill="x", pady=2)
        
        self.del_selected_combo_btn = ctk.CTkButton(self.combo_actions, text="🗑 DELETE SELECTED", command=self.delete_selected_combos, fg_color="#EB5757", text_color="white", hover_color="#C0392B", font=ctk.CTkFont(weight="bold"))
        self.del_selected_combo_btn.pack(side="top", fill="x", pady=2)

        # ====== RIGHT PANE (Chi tiết Combo) ======
        self.combo_right_pane = ctk.CTkFrame(self.tab_combo, fg_color="#15202B")
        self.combo_right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.combo_top_bar = ctk.CTkFrame(self.combo_right_pane, fg_color="transparent", height=40)
        self.combo_top_bar.pack(fill="x", pady=(10, 0), padx=20)
        
        self.combo_preview_title = ctk.CTkLabel(self.combo_top_bar, text="MACRO SEQUENCE", font=ctk.CTkFont(weight="bold", size=15), text_color="#1ABC9C")
        self.combo_preview_title.pack()
        
        tab_idx_frame = ctk.CTkFrame(self.combo_top_bar, fg_color="transparent")
        tab_idx_frame.pack(pady=2)
        ctk.CTkLabel(tab_idx_frame, text="Target Tab Index (Playwright):", font=ctk.CTkFont(size=12)).pack(side="left", padx=5)
        self.combo_tab_index = ctk.CTkEntry(tab_idx_frame, width=50, placeholder_text="0")
        self.combo_tab_index.insert(0, "0")
        self.combo_tab_index.pack(side="left")

        self.combo_name_label = ctk.CTkLabel(self.combo_right_pane, text="[No Macro Selected]", font=ctk.CTkFont(size=16, weight="bold"), text_color="yellow")
        self.combo_name_label.pack(pady=10)

        self.steps_container = ctk.CTkScrollableFrame(self.combo_right_pane, fg_color="#1E2B3C", height=150)
        self.steps_container.pack(fill="both", expand=True, padx=20, pady=5)

        # Vùng cấu hình Completion Marker chung đã bị loại bỏ để tích hợp vào từng Step.

        self.combo_controls = ctk.CTkFrame(self.combo_right_pane, fg_color="transparent")
        self.combo_controls.pack(side="bottom", fill="x", pady=20, padx=20)
        
        self.add_step_btn = ctk.CTkButton(self.combo_controls, text="➕ ADD STEP TO SEQUENCE", command=self.add_step_to_combo, fg_color="#3498DB", hover_color="#2980B9", state="disabled")
        self.add_step_btn.pack(side="top", pady=5, fill="x")

        self.play_combo_btn = ctk.CTkButton(self.combo_controls, text="▶ EXECUTE MACRO SEQUENCE", command=self.play_current_combo, fg_color="#2ECC71", hover_color="#27AE60", state="disabled", font=ctk.CTkFont(weight="bold"))
        self.play_combo_btn.pack(side="left", padx=(0, 5), expand=True, fill="x")

        self.delete_combo_btn = ctk.CTkButton(self.combo_controls, text="🗑 DELETE MACRO", command=self.delete_current_combo, fg_color="#EB5757", hover_color="#C0392B", state="disabled")
        self.delete_combo_btn.pack(side="right", padx=(5, 0), expand=True, fill="x")

        self.refresh_combo_list()

    def refresh_combo_list(self):
        for widget in self.combo_btn_container.winfo_children():
            widget.destroy()
        self.combo_buttons.clear()
        self.combo_checkbox_vars.clear()

        for cname in self.combos.keys():
            frame = ctk.CTkFrame(self.combo_btn_container, fg_color="transparent")
            frame.pack(fill="x", pady=2, padx=5)
            
            var = ctk.BooleanVar(value=False)
            self.combo_checkbox_vars[cname] = var
            chk = ctk.CTkCheckBox(frame, text="", variable=var, width=20, height=20)
            chk.pack(side="left", padx=(0, 5))
            
            btn = ctk.CTkButton(frame, text=cname, anchor="w", fg_color="transparent", hover_color="#2C3E50", text_color="white", command=lambda n=cname: self.on_select_combo(n))
            btn.pack(side="left", fill="x", expand=True)
            self.combo_buttons[cname] = btn

    def on_select_combo(self, name):
        self.current_combo_name = name
        
        for n, btn in self.combo_buttons.items():
            if n == name:
                btn.configure(fg_color="#2980B9") 
            else:
                btn.configure(fg_color="transparent")

        self.combo_name_label.configure(text=name)
        
        self.add_step_btn.configure(state="normal")
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

    def refresh_steps_view(self):
        for widget in self.steps_container.winfo_children():
            widget.destroy()

        if not self.current_combo_name: return
        macro_data = self.combos.get(self.current_combo_name, {"steps": []})
        steps = macro_data.get("steps", [])
        
        for i, step_data in enumerate(steps):
            if isinstance(step_data, str): continue # Đang migrate
                
            frame = ctk.CTkFrame(self.steps_container, fg_color="#15202B")
            frame.pack(fill="x", pady=2, padx=5)
            
            # Row 1: Node Name & Actions
            top_row = ctk.CTkFrame(frame, fg_color="transparent")
            top_row.pack(fill="x")
            
            lbl = ctk.CTkLabel(top_row, text=f"{i+1}. Click: {step_data['node']}", font=ctk.CTkFont(weight="bold", size=13))
            lbl.pack(side="left", padx=10, pady=2)
            
            # Row 2: Condition settings info
            if step_data.get("marker", "None") != "None":
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
        ctk.CTkLabel(top, text="3. Hold Duration (s):", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 0), anchor="w", padx=20)
        entry_time = ctk.CTkEntry(top)
        entry_time.insert(0, str(step_data.get("time", "0")))
        entry_time.pack(fill="x", padx=20, pady=5)
        
        def _save():
            marker_val = cb_marker.get()
            mode_val = cb_mode.get()
            time_val = entry_time.get()
            if not time_val.isdigit(): time_val = "0"
            
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
                 if tab_id < len(context.pages):
                     page = context.pages[tab_id]
                     self.log_gui(f"[Test Macro] Hooked Playwright to Tab {tab_id}")
                 else:
                     self.log_gui(f"[Test Macro] Error: Tab index {tab_id} not found!")
                     playwright_ctx.stop()
                     return
             except Exception as e:
                 self.log_gui(f"[Test Macro] Connection failed: {e}")
                 playwright_ctx.stop()
                 return
        else:
            self.log_gui(f"[Test Macro] Running in foreground (PyAutoGUI focus)")
        
        bot_instance = BotAction(page=page)
        
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
                    marker_time = int(step_data.get("time", "0"))
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

    # ================= TAB AUTO LOOPS (Trí Tuệ Nhân Tạo Bot) =================
    def setup_loop_tab(self):
        self.current_loop_name = None
        self.loop_buttons = {}
        self.loop_checkbox_vars = {}

        self.tab_loop.grid_columnconfigure(0, weight=1, minsize=220)
        self.tab_loop.grid_columnconfigure(1, weight=3)
        self.tab_loop.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE (Danh sách Loop) ======
        self.loop_left_pane = ctk.CTkScrollableFrame(self.tab_loop, fg_color="#1E2B3C")
        self.loop_left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        self.loop_list_title = ctk.CTkLabel(self.loop_left_pane, text="--- AUTO LOOPS ---", text_color="#F1C40F", font=ctk.CTkFont(weight="bold"))
        self.loop_list_title.pack(pady=(5, 15))
        
        self.loop_btn_container = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent")
        self.loop_btn_container.pack(fill="x", expand=True)
        
        self.loop_actions = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent")
        self.loop_actions.pack(side="bottom", fill="x", pady=(20, 5))

        self.add_loop_btn = ctk.CTkButton(self.loop_actions, text="+ CREATE NEW LOOP", command=self.add_new_loop, fg_color="#E67E22", text_color="white", hover_color="#D35400", font=ctk.CTkFont(weight="bold"))
        self.add_loop_btn.pack(side="top", fill="x", pady=2)
        
        self.del_selected_loop_btn = ctk.CTkButton(self.loop_actions, text="🗑 DELETE SELECTED", command=self.delete_selected_loops, fg_color="#EB5757", text_color="white", hover_color="#C0392B", font=ctk.CTkFont(weight="bold"))
        self.del_selected_loop_btn.pack(side="top", fill="x", pady=2)

        # ====== RIGHT PANE (Chi tiết Loop - Flowchart) ======
        self.loop_right_pane = ctk.CTkFrame(self.tab_loop, fg_color="#15202B")
        self.loop_right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.loop_top_bar = ctk.CTkFrame(self.loop_right_pane, fg_color="transparent", height=40)
        self.loop_top_bar.pack(fill="x", pady=(10, 0), padx=20)
        
        self.loop_name_label = ctk.CTkLabel(self.loop_top_bar, text="[No Loop Selected]", font=ctk.CTkFont(size=16, weight="bold"), text_color="white")
        self.loop_name_label.pack(side="left")

        tab_idx_frame = ctk.CTkFrame(self.loop_top_bar, fg_color="transparent")
        tab_idx_frame.pack(side="left", padx=20)
        ctk.CTkLabel(tab_idx_frame, text="Target Tab ID:", font=ctk.CTkFont(size=12)).pack(side="left", padx=2)
        self.loop_tab_index = ctk.CTkEntry(tab_idx_frame, width=30, placeholder_text="0")
        self.loop_tab_index.insert(0, "0")
        self.loop_tab_index.pack(side="left")

        self.play_loop_btn = ctk.CTkButton(self.loop_top_bar, text="⭕ START AUTO LOOP", command=self.toggle_loop_engine, fg_color="#C0392B", hover_color="#A93226", state="disabled", font=ctk.CTkFont(weight="bold"), width=150)
        self.play_loop_btn.pack(side="right")

        # Flowchart Toolbar
        self.flowchart_toolbar = ctk.CTkFrame(self.loop_right_pane, fg_color="#2C3E50", height=40)
        self.flowchart_toolbar.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkButton(self.flowchart_toolbar, text="+ Start", width=80, fg_color="#27AE60", hover_color="#2ECC71", command=lambda: self.flowchart_add_node("Start")).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ Macro", width=80, fg_color="#2980B9", hover_color="#3498DB", command=lambda: self.flowchart_add_node("Macro")).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ If Image", width=80, fg_color="#D35400", hover_color="#E67E22", command=lambda: self.flowchart_add_node("Condition")).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(self.flowchart_toolbar, text="+ Delay", width=80, fg_color="#8E44AD", hover_color="#9B59B6", command=lambda: self.flowchart_add_node("Delay")).pack(side="left", padx=5, pady=5)
        
        ctk.CTkLabel(self.flowchart_toolbar, text="(Right-click node to edit/delete. Drag from True/False/Out pins to In pins)", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="right", padx=10)

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
        # Find a random valid position
        x = random.randint(50, 400)
        y = random.randint(50, 300)
        self.flowchart.add_node(ntype, x, y)

    def refresh_loop_list(self):
        for widget in self.loop_btn_container.winfo_children():
            widget.destroy()
        self.loop_buttons.clear()
        self.loop_checkbox_vars.clear()

        for lname in self.loops.keys():
            frame = ctk.CTkFrame(self.loop_btn_container, fg_color="transparent")
            frame.pack(fill="x", pady=2, padx=5)
            
            var = ctk.BooleanVar(value=False)
            self.loop_checkbox_vars[lname] = var
            chk = ctk.CTkCheckBox(frame, text="", variable=var, width=20, height=20)
            chk.pack(side="left", padx=(0, 5))
            
            btn = ctk.CTkButton(frame, text=lname, anchor="w", fg_color="transparent", hover_color="#2C3E50", text_color="white", command=lambda n=lname: self.on_select_loop(n))
            btn.pack(side="left", fill="x", expand=True)
            self.loop_buttons[lname] = btn

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
        edges = graph.get("edges", [])
        threshold_val = self.slider.get()
        
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
                 if tab_id < len(context.pages):
                     page = context.pages[tab_id]
                     self.log_gui(f"[Loop Engine] Hooked to Tab {tab_id}")
                 else:
                     self.log_gui(f"[Loop Engine] Tab index {tab_id} not found!")
                     playwright_ctx.stop()
                     return
             except Exception as e:
                 self.log_gui(f"[Loop Engine] Connection fail: {e}")
                 playwright_ctx.stop()
                 return
                 
        bot_instance = BotAction(page=page)
        
        while self.is_looping:
            if not current_node_id or current_node_id not in nodes:
                self.log_gui(f"[FLOWCHART] End of path reached. Restarting from Start Node in 1s...")
                time.sleep(1.0)
                current_node_id = start_node
                continue
                
            n = nodes[current_node_id]
            ntype = n["type"]
            ndata = n.get("data", {})
            
            if ntype == "Start":
                self.log_gui(f"[FLOWCHART] ---> START")
                current_node_id = get_next_node(current_node_id, "out")
                time.sleep(0.5)
                
            elif ntype == "Macro":
                mac_name = ndata.get("macro_name")
                if mac_name and mac_name in self.combos:
                    self.log_gui(f"[FLOWCHART] ⚡ Executing Macro: {mac_name}")
                    macro_data = self.combos[mac_name]
                    self._internal_macro_runner(macro_data, bot_instance, page=page)
                else:
                    self.log_gui(f"[FLOWCHART] ⚠️ Invalid Macro: {mac_name}")
                current_node_id = get_next_node(current_node_id, "out")
                
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
                    self.log_gui(f"[FLOWCHART] 👁 Visual Check: Is '{img_name}' on screen?")
                    frame_bytes = None
                    if page:
                        try: frame_bytes = page.screenshot()
                        except: pass
                    res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                    if res:
                        self.log_gui(f"[FLOWCHART] → TRUE (Found {img_name})")
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
                    marker_time = int(step_data.get("time", "0"))
                except:
                    marker_time = 0
                    
            if not node_name: continue
            
            filepath = self.tracked_icons.get(node_name)
            if not filepath or not os.path.exists(filepath):
                local_log(f"    - Macro chắp vá: Bỏ qua Node '{node_name}' do lỗi file.")
                continue
                
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
                    local_log(f"    - Macro step done: Click '{node_name}'")
                    found = True
                    time.sleep(random.uniform(1.2, 2.0))
                    break
                time.sleep(1.0)
            if not found:
                local_log(f"    - Macro chắp vá: Bỏ qua Node '{node_name}' vì quá giới hạn tgian.")
                continue
                
            # Logic Loop chờ Completion Marker ở Từng Step trước khi qua Step tiếp theo
            if marker != "None":
                mode_str = "XUẤT HIỆN" if marker_mode == "Wait until Appear" else "BIẾN MẤT"
                local_log(f"    - Macro Blocking: Đang chờ Image '{marker}' {mode_str} (Giữ trạng thái {marker_time}s)...")
                marker_path = self.tracked_icons.get(marker)
                if marker_path and os.path.exists(marker_path):
                    marker_found_or_lost = False
                    hold_start = None
                    last_log_time = 0
                    
                    timeout = time.time() + 300 # Giới hạn Watchdog Timeout 5 PHÚT
                    
                    for attempt in range(99999): # Loop chặn đến khi Marker xảy ra hoặc Timeout
                        if time.time() > timeout:
                            local_log(f"    - [TIMEOUT Vượt quá 5 phút] Bỏ qua chờ Marker '{marker}'!")
                            break
                            
                        if not self.is_looping and not self.is_coordinating: break # Ngắt an toàn
                        
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
                                    local_log(f"    - Macro 🕒 Marker đạt chuẩn. Bắt đầu đếm ngược Hold ({marker_time}s)...")
                            
                            elapsed = time.time() - hold_start
                            
                            current_sec = int(elapsed)
                            if marker_time > 0 and current_sec > last_log_time:
                                local_log(f"    - Macro ⏳ Đang Hold... {current_sec}/{marker_time}s")
                                last_log_time = current_sec
                                
                            if elapsed >= marker_time:
                                marker_found_or_lost = True
                                break
                        else:
                            if hold_start is not None:
                                local_log(f"    - Macro Bị gián đoạn Marker '{marker}'. Reset lại Time.")
                                hold_start = None
                                last_log_time = 0
                            
                        time.sleep(1.0)
                        
                    if not marker_found_or_lost and (self.is_looping or self.is_coordinating):
                        local_log(f"    - Lỗi Tắc Nghẽn: Kẹt Macro tại Marker {marker} vượt quá thời gian!")
                        return
                    
        local_log(f"[STATE MACHINE] ✅ Hoàn tất Macro. Quay lại giám sát luồng mốc...")


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

        # ====== LEFT PANE ======
        self.left_pane = ctk.CTkScrollableFrame(self.tab_setup, width=220, fg_color="#1E2B3C")
        self.left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        self.list_title = ctk.CTkLabel(self.left_pane, text="--- TARGET LIST ---", text_color="#1ABC9C", font=ctk.CTkFont(weight="bold"))
        self.list_title.pack(pady=(5, 15))
        
        self.btn_container = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        self.btn_container.pack(fill="x", expand=True)
        
        self.target_actions = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        self.target_actions.pack(side="bottom", fill="x", pady=(20, 5))

        self.add_btn = ctk.CTkButton(self.target_actions, text="+ ADD NEW NODE", command=self.add_new_target, fg_color="#F2994A", text_color="black", hover_color="#F2C94C", font=ctk.CTkFont(weight="bold"))
        self.add_btn.pack(side="top", fill="x", pady=2)
        
        self.del_selected_btn = ctk.CTkButton(self.target_actions, text="🗑 DELETE SELECTED", command=self.delete_selected_targets, fg_color="#EB5757", text_color="white", hover_color="#C0392B", font=ctk.CTkFont(weight="bold"))
        self.del_selected_btn.pack(side="top", fill="x", pady=2)

        # ====== RIGHT PANE ======
        self.right_pane = ctk.CTkFrame(self.tab_setup, fg_color="#15202B")
        self.right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.top_bar = ctk.CTkFrame(self.right_pane, fg_color="transparent", height=40)
        self.top_bar.pack(fill="x", pady=(10, 0), padx=20)
        
        self.preview_title = ctk.CTkLabel(self.top_bar, text="TEMPLATE PREVIEW", font=ctk.CTkFont(weight="bold", size=15), text_color="#1ABC9C")
        self.preview_title.pack()

        # Cụm UI cho Thiết lập VÙNG GAME (GAME REGION)
        # self.region_frame = ctk.CTkFrame(self.right_pane, fg_color="#1E2B3C", border_width=1, border_color="#3B8ED0")
        # self.region_frame.pack(fill="x", padx=20, pady=(10, 5))
        
        # self.region_label = ctk.CTkLabel(self.region_frame, text="Current Game Region: FULL SCREEN (Slow)", text_color="yellow")
        # self.region_label.pack(side="left", padx=10, pady=10)
        
        # self.set_region_btn = ctk.CTkButton(self.region_frame, text="📐 SET GAME WINDOW", command=self.capture_game_region, fg_color="#8E44AD", hover_color="#9B59B6", width=120)
        # self.set_region_btn.pack(side="right", padx=10, pady=10)


        # Nơi chứa config Nút hiện tại
        self.preview_name_frame = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        self.preview_name_frame.pack(pady=5)
        self.preview_name_label = ctk.CTkLabel(self.preview_name_frame, text="No Target Selected", font=ctk.CTkFont(size=14))
        self.preview_name_label.pack(side="left")
        self.preview_status_label = ctk.CTkLabel(self.preview_name_frame, text="", text_color="#2ECC71", font=ctk.CTkFont(weight="bold"))
        self.preview_status_label.pack(side="left", padx=5)

        self.preview_image_label = ctk.CTkLabel(self.right_pane, text="[Select any target Node to view details]")
        self.preview_image_label.pack(pady=30, expand=True)

        self.preview_size_label = ctk.CTkLabel(self.right_pane, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.preview_size_label.pack(pady=0, anchor="e", padx=20)

        self.target_controls = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        self.target_controls.pack(side="bottom", fill="x", pady=20, padx=20)
        
        # Nhét thêm Slider xuống dưới để cấu hình độ nhạy ảnh
        self.slider_frame = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        self.slider_frame.pack(side="bottom", fill="x", pady=(0, 10), padx=20)
        self.thresh_label = ctk.CTkLabel(self.slider_frame, text="Accuracy Threshold: 0.85")
        self.thresh_label.pack()
        self.slider = ctk.CTkSlider(self.slider_frame, from_=0.5, to=0.99, command=lambda v: self.thresh_label.configure(text=f"Accuracy Threshold: {v:.2f}"))
        self.slider.set(0.85)
        self.slider.pack()

        self.test_node_btn = ctk.CTkButton(self.target_controls, text="🎯 TEST THIS NODE", command=self.test_current_node, fg_color="#F39C12", hover_color="#D68910", state="disabled")
        self.test_node_btn.pack(side="top", pady=(0, 10), expand=True, fill="x", padx=5)

        self.recapture_btn = ctk.CTkButton(self.target_controls, text="📷 RE-CAPTURE REGION", command=self.recapture_current, fg_color="#C850C0", hover_color="#FFCC70", state="disabled")
        self.recapture_btn.pack(side="left", padx=5, expand=True, fill="x")

        self.delete_btn = ctk.CTkButton(self.target_controls, text="🗑 DELETE THIS NODE", command=self.delete_current, fg_color="#EB5757", hover_color="#C0392B", state="disabled")
        self.delete_btn.pack(side="right", padx=5, expand=True, fill="x")


        # ====== BOTOOM PANE (Log & Tracker) ======
        self.bottom_frame = ctk.CTkFrame(self.tab_setup, fg_color="#1E2B3C")
        self.bottom_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        
        self.start_tracking_btn = ctk.CTkButton(self.bottom_frame, text="👁 MASTER MONITOR: TRACK ALL NODES", command=self.toggle_tracker, height=40, font=ctk.CTkFont(size=14, weight="bold"))
        self.start_tracking_btn.pack(pady=5, fill="x", padx=10)

        self.load_saved_trackers()


    def capture_game_region(self):
        """Hàm này Cắt để lấy Tọa Độ Vùng Game, ko lấy ảnh"""
        self.withdraw()
        time.sleep(0.3)
        from screencapture import ScreenCaptureTool
        
        def on_snip(x1, y1, x2, y2):
            w = x2 - x1
            # Biến lưu trữ Vùng Game (Region) - Không còn dung toi vi Playwright tu Crop
            self.game_region = None
            self.deiconify()
            self.log_gui(f"[System] Optimized Scanning Region assigned to bounding box ({x1},{y1}) -> {w}x{h} px")
            
        snipper = ScreenCaptureTool(on_snip)
        snipper.run()


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
        
        for name, filepath in self.tracked_icons.items():
            self._add_icon_to_list(name, filepath)

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
            
        self.log_gui(f"[TEST] Bắt đầu scan thử Node '{name}'...")
        threshold_val = self.slider.get()
        
        # Test 1 lần duy nhất
        res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=True)
        if res:
            x, y, score = res
            self.log_gui(f"[TEST] ✅ Success! Tìm thấy '{name}' tại ({x}, {y}) với độ chính xác {score:.2f}")
            # Highlight nhẹ chuột
            pyautogui.moveTo(x, y, duration=0.2)
        else:
            self.log_gui(f"[TEST] ❌ Failed. KHÔNG tìm thấy '{name}' trên màn hình với Threshold={threshold_val:.2f}")

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

    # ================= TAB MULTI-ACCOUNTS (Trí Tuệ Nhân Tạo Điều Phối) =================
    def setup_multi_tab(self):
        self.tab_multi.grid_columnconfigure(0, weight=1, minsize=250)
        self.tab_multi.grid_columnconfigure(1, weight=3)
        self.tab_multi.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANE (Settings) ======
        self.multi_left_pane = ctk.CTkFrame(self.tab_multi, fg_color="#1E2B3C")
        self.multi_left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)

        self.multi_title = ctk.CTkLabel(self.multi_left_pane, text="--- MULTI-ACCOUNTS ---", text_color="#3498DB", font=ctk.CTkFont(weight="bold"))
        self.multi_title.pack(pady=(10, 5))

        # Account List
        lbl_acclist = ctk.CTkLabel(self.multi_left_pane, text="Assigned Accounts:", text_color="white", font=ctk.CTkFont(weight="bold"))
        lbl_acclist.pack(anchor="w", padx=10, pady=(15, 0))

        self.acc_list_frame = ctk.CTkScrollableFrame(self.multi_left_pane, fg_color="#15202B", height=150)
        self.acc_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.multi_actions = ctk.CTkFrame(self.multi_left_pane, fg_color="transparent")
        self.multi_actions.pack(side="bottom", fill="x", pady=10, padx=10)

        btn_add_acc = ctk.CTkButton(self.multi_actions, text="+ ADD ACCOUNT", command=self.add_multi_account, fg_color="#27AE60", hover_color="#2ECC71")
        btn_add_acc.pack(side="top", fill="x", pady=2)

        # ====== RIGHT PANE (Dashboard) ======
        self.multi_right_pane = ctk.CTkFrame(self.tab_multi, fg_color="#15202B")
        self.multi_right_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)

        self.dash_top_bar = ctk.CTkFrame(self.multi_right_pane, fg_color="transparent", height=40)
        self.dash_top_bar.pack(fill="x", pady=(10, 0), padx=20)

        self.dash_title = ctk.CTkLabel(self.dash_top_bar, text="COORDINATOR DASHBOARD", font=ctk.CTkFont(weight="bold", size=15), text_color="#3498DB")
        self.dash_title.pack(side="left")

        self.btn_toggle_coord = ctk.CTkButton(self.dash_top_bar, text="🟢 START COORDINATOR", command=self.toggle_coordinator, fg_color="#C0392B", hover_color="#A93226", font=ctk.CTkFont(weight="bold"))
        self.btn_toggle_coord.pack(side="right")

        self.dash_grid = ctk.CTkScrollableFrame(self.multi_right_pane, fg_color="#1E2B3C")
        self.dash_grid.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.dash_labels = {}
        self.refresh_multi_acc_list()

    def add_multi_account(self):
        if not self.tracked_icons or not self.loops:
            return messagebox.showwarning("Warning", "You need to create Tracking Nodes and Loops first!")
            
        top = ctk.CTkToplevel(self)
        top.title("Add Account")
        top.geometry("350x400")
        top.attributes("-topmost", True)

        ctk.CTkLabel(top, text="Display Name:").pack(pady=(10,0))
        ent_name = ctk.CTkEntry(top, width=200)
        ent_name.pack(pady=(0,10))

        ctk.CTkLabel(top, text="Browser Tab Index:").pack()
        ent_target = ctk.CTkEntry(top, width=200, placeholder_text="e.g. 0, 1, 2...")
        ent_target.pack(pady=(0,2))
        ctk.CTkLabel(top, text="(0 = Tab đầu tiên, 1 = Tab thứ 2...)", font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0,10))

        ctk.CTkLabel(top, text="Assigned Loop:").pack()
        combo_loop = ctk.CTkComboBox(top, values=list(self.loops.keys()), width=200)
        combo_loop.pack(pady=(0,10))

        def on_save():
            name = ent_name.get().strip()
            target = ent_target.get().strip()
            loop = combo_loop.get()
            
            if not name or not target:
                return messagebox.showerror("Error", "Name and Tab Index are required!")
                
            if not target.isdigit():
                return messagebox.showerror("Error", "Tab Index must be a number (0, 1, 2...)!")
                
            self.multi_accounts.append({
                "name": name,
                "target": target,
                "loop": loop
            })
            self.save_multi()
            self.refresh_multi_acc_list()
            top.destroy()

        ctk.CTkButton(top, text="Save Account", command=on_save, fg_color="#2ECC71").pack()

    def refresh_multi_acc_list(self):
        for widget in self.acc_list_frame.winfo_children():
            widget.destroy()
        for widget in self.dash_grid.winfo_children():
            widget.destroy()
        self.dash_labels.clear()

        for idx, acc in enumerate(self.multi_accounts):
            # Left panel list item
            row = ctk.CTkFrame(self.acc_list_frame, fg_color="#2C3E50")
            row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(row, text=f"{acc['name']} (Tab ID: {acc.get('target', '?')})").pack(side="left", padx=5)
            
            def del_acc(i=idx):
                self.multi_accounts.pop(i)
                self.save_multi()
                self.refresh_multi_acc_list()
                
            btn_frame = ctk.CTkFrame(row, fg_color="transparent")
            btn_frame.pack(side="right", padx=5)
            
            ctk.CTkButton(btn_frame, text="✖", width=20, fg_color="transparent", text_color="red", command=del_acc).pack(side="left")

            # Right panel Dashboard Card
            card = ctk.CTkFrame(self.dash_grid, fg_color="#34495E", border_width=1, border_color="#7F8C8D")
            card.pack(fill="x", pady=5, padx=5)
            
            ctk.CTkLabel(card, text=acc['name'], font=ctk.CTkFont(weight="bold", size=14), width=100, anchor="w").pack(side="left", padx=10)
            
            lbl_status = ctk.CTkLabel(card, text="Status: Idle", text_color="gray", width=400, anchor="w")
            lbl_status.pack(side="left", padx=10)
            self.dash_labels[acc['name']] = lbl_status

    def update_dash_status(self, acc_name, status, color="white"):
        """Puts a dash status update into the thread-safe queue."""
        self.gui_queue.put(("dash_status", (acc_name, status, color)))
        
    def _internal_update_dash_status(self, acc_name, status, color):
        if acc_name in self.dash_labels:
            self.dash_labels[acc_name].configure(text=f"Status: {status}", text_color=color)

    def toggle_coordinator(self):
        if not self.is_coordinating:
            if not self.multi_accounts:
                return messagebox.showwarning("Warning", "No accounts configured!")
                
            self.is_coordinating = True
            self.btn_toggle_coord.configure(text="🔴 STOP COORDINATOR")
            self.log_gui("★★★ MULTI-ACCOUNT COORDINATOR STARTED ★★★")
            
            # Reset all states
            for acc in self.multi_accounts:
                self.update_dash_status(acc['name'], "Waiting for turn...", "yellow")
                
            # Multithreaded Launcher
            for acc in self.multi_accounts:
                threading.Thread(target=self._account_worker_thread, args=(acc,), daemon=True).start()
        else:
            self.is_coordinating = False
            self.btn_toggle_coord.configure(text="🟢 START COORDINATOR")
            for acc in self.multi_accounts:
                self.update_dash_status(acc['name'], "Idle", "gray")
            self.log_gui("★★★ COORDINATOR STOPPED ★★★")

    def _account_worker_thread(self, acc):
        acc_name = acc['name']
        loop_name = acc['loop']
        tab_index_str = acc.get('target', '0')
        threshold_val = self.slider.get()
        
        tab_idx = 0
        if tab_index_str.isdigit():
            tab_idx = int(tab_index_str)
            
        graph = self.loops.get(loop_name, {})
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
        
        self.update_dash_status(acc_name, "Initializing Connection...", "yellow")
        
        with sync_playwright() as p:
            browser = None
            page = None
            try:
                self.log_gui(f"[{acc_name}] Connecting to Chromium at localhost:9222...")
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                default_context = browser.contexts[0]
                
                # Cố gắng lấy đúng Tab bằng Index (Vị trí mở tab trên Chrome)
                all_pages = default_context.pages
                
                if tab_idx < len(all_pages):
                    page = all_pages[tab_idx]
                    self.update_dash_status(acc_name, f"Connected to Tab {tab_idx}", "lime")
                else:
                    self.log_gui(f"[{acc_name}] ❌ Tab index {tab_idx} out of range! (Found {len(all_pages)} tabs).")
                    self.update_dash_status(acc_name, "Tab Not Found", "red")
                    return
            except Exception as e:
                self.log_gui(f"[{acc_name}] ❌ Connection Failed: {str(e)}")
                self.update_dash_status(acc_name, "API Connection Error (Check port 9222)", "red")
                return
                
            bot_instance = BotAction(page=page)

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
            
            # The Infinite Synchronous Sandbox Loop for this single account
            while self.is_coordinating:
                if not current_node_id or current_node_id not in nodes:
                    self.update_dash_status(acc_name, "Restarting Loop Sequence", "orange")
                    time.sleep(1.0)
                    current_node_id = get_start_node()
                    continue

                n = nodes[current_node_id]
                ntype = n["type"]
                ndata = n.get("data", {})

                next_nid = None

                if ntype == "Start":
                    self.update_dash_status(acc_name, "Running...", "lime")
                    next_nid = get_next_node(current_node_id, "out")
                    time.sleep(0.5)
                    
                elif ntype == "Delay":
                    delay_time = ndata.get("time", 1.0)
                    self.update_dash_status(acc_name, f"Delay ({delay_time}s)...", "cyan")
                    # Breakable sleep
                    steps = int(delay_time * 10)
                    for _ in range(steps):
                        if not self.is_coordinating: break
                        time.sleep(0.1)
                    next_nid = get_next_node(current_node_id, "out")
                    
                elif ntype == "Condition":
                    img_name = ndata.get("image_name")
                    filepath = self.tracked_icons.get(img_name)
                    
                    if not filepath or not os.path.exists(filepath):
                        self.update_dash_status(acc_name, f"Cond Err: Missing Image", "red")
                        next_nid = get_next_node(current_node_id, "false")
                    else:
                        self.update_dash_status(acc_name, f"Visual Scan: {img_name}...", "yellow")
                        
                        frame_bytes = None
                        try:
                            frame_bytes = page.screenshot()
                        except Exception as e:
                            self.log_gui(f"[{acc_name}] Screenshot Error: {str(e)}")
                            
                        res = self.vision.find_template_on_screen(filepath, threshold=threshold_val, debug=False, frame_bytes=frame_bytes)
                        if res:
                            next_nid = get_next_node(current_node_id, "true")
                            self.update_dash_status(acc_name, f"Condition TRUE", "lime")
                        else:
                            next_nid = get_next_node(current_node_id, "false")
                            self.update_dash_status(acc_name, f"Condition FALSE", "orange")
                        time.sleep(0.5)
                        
                elif ntype == "Macro":
                    mac_name = ndata.get("macro_name")
                    if mac_name and mac_name in self.combos:
                        self.update_dash_status(acc_name, f"Exec Macro: {mac_name}", "magenta")
                        self._internal_macro_runner(self.combos[mac_name], bot_instance, acc_name=acc_name, page=page)
                    else:
                        self.update_dash_status(acc_name, f"Macro error: Not found", "red")
                    next_nid = get_next_node(current_node_id, "out")

                current_node_id = next_nid

            # Shutdown cleanup
            if browser:
                browser.close()

if __name__ == "__main__":
    app = BotApp()
    app.mainloop()
