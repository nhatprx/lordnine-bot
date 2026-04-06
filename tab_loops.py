"""Loops/Automation tab mixin — Flowchart-based automation engine."""
import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import os
import random

from constants import COLOR, FONT, PAD, RADIUS
from bot_action import BotAction
from cdp_client import CDPClient
from flowchart_ui import FlowchartUI
from ui_dialogs import show_styled_info, show_input_dialog, show_confirm_dialog


class LoopsMixin:
    """Mixin for the Automation/Loops tab. Mixed into BotApp."""

    def setup_loop_tab(self):
        self.current_loop_name = None
        self.loop_buttons = {}
        self.loop_checkbox_vars = {}

        self.tab_loop.grid_columnconfigure(0, weight=1, minsize=130, uniform="col")
        self.tab_loop.grid_columnconfigure(1, weight=3, uniform="col")
        self.tab_loop.grid_rowconfigure(0, weight=1)

        # Helper to blur searchbox
        def _blur_loop_search(event=None):
            if hasattr(self, 'loop_search_entry'):
                try: self.tab_loop.focus_set()
                except Exception: pass
        self._blur_loop_search = _blur_loop_search

        # ====== LEFT PANE (Panel Card) ======
        self.loop_left_pane = ctk.CTkFrame(self.tab_loop, fg_color=COLOR["surface"], corner_radius=12, border_width=1, border_color=COLOR["border_subtle"])
        self.loop_left_pane.grid(row=0, column=0, sticky="nsew", padx=(PAD["lg"], PAD["sm"]), pady=PAD["lg"])

        # -- Title row with inline action links --
        title_row = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent")
        title_row.pack(fill="x", padx=PAD["md"], pady=(PAD["md"], PAD["sm"]))

        ctk.CTkLabel(
            title_row, text="LOOPS",
            text_color=COLOR["text_dim"],
            font=ctk.CTkFont(family="Segoe UI", weight="bold", size=11)
        ).pack(side="left")

        self.del_selected_loop_btn = ctk.CTkButton(
            title_row, text="Delete", command=self.delete_selected_loops,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["text_muted"], font=ctk.CTkFont(size=11, weight="bold"),
            width=50, height=24, corner_radius=4
        )
        self.del_selected_loop_btn.pack(side="right", padx=(2, 0))

        self.add_loop_btn = ctk.CTkButton(
            title_row, text="+ Add", command=self.add_new_loop,
            fg_color="transparent", hover_color=COLOR["surface2"],
            text_color=COLOR["primary"], font=ctk.CTkFont(size=11, weight="bold"),
            width=50, height=24, corner_radius=4
        )
        self.add_loop_btn.pack(side="right", padx=(0, 2))

        # Search bar
        self._loop_search_debounce_id = None
        def _debounced_loop_search(*a):
            if self._loop_search_debounce_id:
                self.after_cancel(self._loop_search_debounce_id)
            self._loop_search_debounce_id = self.after(150, self.refresh_loop_list)
        self.loop_search_entry = ctk.CTkEntry(
            self.loop_left_pane, placeholder_text="Search loops...",
            placeholder_text_color=COLOR["text_muted"],
            fg_color=COLOR["bg"], corner_radius=6, height=30,
            border_width=1, border_color=COLOR["border_subtle"]
        )
        self.loop_search_entry._entry.bind("<KeyRelease>", _debounced_loop_search)
        self.loop_search_entry.pack(fill="x", padx=PAD["md"], pady=(0, PAD["sm"]))

        # Select All
        self.loop_select_all_var = ctk.BooleanVar(value=False)
        sa_row = ctk.CTkFrame(self.loop_left_pane, fg_color="transparent", height=24)
        sa_row.pack(fill="x", padx=PAD["md"], pady=(0, PAD["xs"]))
        ctk.CTkCheckBox(
            sa_row, text="Select All", variable=self.loop_select_all_var,
            command=self._toggle_select_all_loops,
            checkbox_width=18, checkbox_height=18, corner_radius=4,
            border_width=1, font=ctk.CTkFont(size=11),
            text_color=COLOR["text_muted"], border_color=COLOR["border"],
            hover_color=COLOR["surface2"]
        ).pack(side="left")

        # Scrollable loop list
        self.loop_btn_container = ctk.CTkScrollableFrame(
            self.loop_left_pane, fg_color="transparent",
            scrollbar_button_color=COLOR["border"],
            scrollbar_button_hover_color=COLOR["text_muted"]
        )
        self.loop_btn_container.pack(fill="both", expand=True, padx=2, pady=(0, PAD["xs"]))

        # ====== RIGHT PANE ======
        self.loop_right_pane = ctk.CTkFrame(self.tab_loop, fg_color=COLOR["bg"], corner_radius=0)
        self.loop_right_pane.grid(row=0, column=1, sticky="nsew", padx=(PAD["sm"], PAD["lg"]), pady=PAD["lg"])

        # Detail area card
        self.loop_detail_area = ctk.CTkFrame(self.loop_right_pane, fg_color=COLOR["surface"], corner_radius=12, border_width=1, border_color=COLOR["border_subtle"])

        # Bind blur to major areas
        for w in [self.loop_right_pane, self.loop_detail_area, self.loop_left_pane]:
            w.bind("<Button-1>", self._blur_loop_search)
        self.loop_detail_area.pack(fill="both", expand=True)

        # -- Header bar --
        self.loop_top_bar = ctk.CTkFrame(self.loop_detail_area, fg_color="transparent", height=42)
        self.loop_top_bar.pack(fill="x", padx=6, pady=(6, 0))
        self.loop_top_bar.pack_propagate(False)

        self.loop_name_label = ctk.CTkLabel(
            self.loop_top_bar, text="[No Loop Selected]",
            font=ctk.CTkFont(family="Inter", size=14, weight="bold"),
            text_color=COLOR["text"]
        )
        self.loop_name_label.pack(side="left", padx=PAD["sm"])

        # Inline status indicator
        status_frame = ctk.CTkFrame(self.loop_top_bar, fg_color="transparent")
        status_frame.pack(side="left", padx=PAD["sm"])
        self.loop_status_icon = ctk.CTkLabel(status_frame, text="●", text_color=COLOR["text_muted"], font=ctk.CTkFont(size=8), width=12)
        self.loop_status_icon.pack(side="left", padx=(0, 4))
        self.loop_status_label = ctk.CTkLabel(status_frame, text="Idle", text_color=COLOR["text_muted"], font=ctk.CTkFont(family="Consolas", size=11))
        self.loop_status_label.pack(side="left")

        # Execute button (right side)
        self.play_loop_btn = ctk.CTkButton(
            self.loop_top_bar, text="▶ Execute",
            command=self.toggle_loop_engine,
            fg_color="transparent", hover_color=COLOR["surface2"],
            border_width=1, border_color=COLOR["primary"],
            text_color=COLOR["primary"],
            state="disabled",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=100, height=28, corner_radius=6
        )
        self.play_loop_btn.pack(side="right", padx=PAD["sm"])

        # Header separator
        ctk.CTkFrame(self.loop_detail_area, fg_color=COLOR["border_subtle"], height=1).pack(fill="x", padx=6)

        # -- Flowchart Canvas --
        def get_macros_cb():
            return list(self.combos.keys())
        def get_images_cb():
            return list(self.tracked_icons.keys())
        def on_change_cb():
            if self.current_loop_name:
                self.loops[self.current_loop_name] = self.flowchart.export_graph()
                self.save_loops()

        self.flowchart = FlowchartUI(self.loop_detail_area, get_macros_cb=get_macros_cb, get_images_cb=get_images_cb, on_change_cb=on_change_cb)

        # -- Empty state overlay (non-scrollable, centered) --
        self.loop_empty_state = ctk.CTkFrame(self.loop_detail_area, fg_color="transparent")
        self.loop_empty_state.pack(fill="both", expand=True, padx=PAD["md"], pady=PAD["xs"])

        # -- Bottom Toolbar (color-coded action buttons) --
        self.flowchart_toolbar = ctk.CTkFrame(self.loop_detail_area, fg_color=COLOR["surface"], corner_radius=0, height=44)
        self.flowchart_toolbar.pack(fill="x", side="bottom", padx=0, pady=0)
        self.flowchart_toolbar.pack_propagate(False)

        # Color-coded node type buttons
        node_btns = [
            ("+ Start",    lambda: self.flowchart_add_node("Start"),     "#3D8B6E", "#2A5A4A"),
            ("+ Macro",    lambda: self.flowchart_add_node("Macro"),     COLOR["primary"], COLOR["surface2"]),
            ("+ If Image", lambda: self.flowchart_add_node("Condition"), COLOR["warning"], COLOR["surface2"]),
            ("+ Delay",    lambda: self.flowchart_add_node("Delay"),     COLOR["purple"], COLOR["surface2"]),
            ("+ Click",    lambda: self.flowchart_add_node("Click"),     "#5BC0DE", COLOR["surface2"]),
            ("+ End",      lambda: self.flowchart_add_node("End"),       COLOR["danger"], COLOR["surface2"]),
        ]

        for i, (text, cmd, color, hover) in enumerate(node_btns):
            padx_val = (PAD["sm"], 3) if i == 0 else (3, PAD["sm"]) if i == len(node_btns) - 1 else 3
            ctk.CTkButton(
                self.flowchart_toolbar, text=text, command=cmd,
                fg_color="transparent", hover_color=hover,
                border_width=1, border_color=color,
                text_color=color, font=ctk.CTkFont(size=11, weight="bold"),
                width=80, height=30, corner_radius=6
            ).pack(side="left", padx=padx_val, pady=6, expand=True, fill="x")

        self.refresh_loop_list()
        self._show_loop_empty_state(
            "", "Select a loop",
            "Choose a loop from the left panel\nto view and edit its flowchart"
        )

    def flowchart_add_node(self, ntype):
        if not self.current_loop_name:
            show_styled_info(self, "Select a loop", "Choose a loop from the left panel first")
            return
        self.flowchart.add_node(ntype)

    def refresh_loop_list(self):
        for widget in self.loop_btn_container.winfo_children():
            widget.destroy()
        self.loop_buttons.clear()
        self.loop_checkbox_vars.clear()

        search = self.loop_search_entry.get().strip().lower() if hasattr(self, 'loop_search_entry') else ""
        for lname in self.loops.keys():
            if search and search not in lname.lower():
                continue
            frame = ctk.CTkFrame(self.loop_btn_container, fg_color="transparent", height=30)
            frame.pack(fill="x", pady=1, padx=4)
            frame.pack_propagate(False)

            var = ctk.BooleanVar(value=False)
            self.loop_checkbox_vars[lname] = var
            ctk.CTkCheckBox(
                frame, text="", variable=var,
                checkbox_width=18, checkbox_height=18, corner_radius=4,
                border_width=1, width=18, border_color=COLOR["border"],
                hover_color=COLOR["surface2"],
                command=self._update_delete_loop_btn_color
            ).pack(side="left", padx=(4, 6))

            btn = ctk.CTkButton(
                frame, text=lname, anchor="w",
                fg_color="transparent", hover_color=COLOR["surface2"],
                text_color=COLOR["text_dim"],
                font=ctk.CTkFont(size=12),
                height=28, corner_radius=6,
                command=lambda n=lname: self.on_select_loop(n)
            )
            btn.pack(side="left", fill="x", expand=True)
            self.loop_buttons[lname] = btn

    def _update_delete_loop_btn_color(self):
        """Turn Delete button red when any checkbox is ticked."""
        any_checked = any(v.get() for v in self.loop_checkbox_vars.values())
        if any_checked:
            self.del_selected_loop_btn.configure(text_color=COLOR["danger"])
        else:
            self.del_selected_loop_btn.configure(text_color=COLOR["text_muted"])

    def _toggle_select_all_loops(self):
        val = self.loop_select_all_var.get()
        for v in self.loop_checkbox_vars.values():
            v.set(val)
        self._update_delete_loop_btn_color()

    def _show_loop_empty_state(self, icon, title, subtitle):
        """Show centered empty state in the non-scrollable overlay."""
        self.flowchart.pack_forget()
        for w in self.loop_empty_state.winfo_children():
            w.destroy()
        self.loop_empty_state.pack(fill="both", expand=True, padx=PAD["md"], pady=PAD["xs"], before=self.flowchart_toolbar)

        center = ctk.CTkFrame(self.loop_empty_state, fg_color="transparent")
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

    def on_select_loop(self, name):
        # Blur searchbox
        self._blur_loop_search()

        # Just select this loop (no checkbox toggle)
        self.current_loop_name = name

        for n, btn in self.loop_buttons.items():
            if n == name:
                btn.configure(fg_color=COLOR["surface3"], text_color=COLOR["text"])
            else:
                btn.configure(fg_color="transparent", text_color=COLOR["text_dim"])

        self.loop_name_label.configure(text=name)
        self.play_loop_btn.configure(state="normal")

        # Show flowchart, hide empty state
        self.loop_empty_state.pack_forget()
        self.flowchart.pack(fill="both", expand=True, padx=PAD["md"], pady=(0, PAD["xs"]), before=self.flowchart_toolbar)
        
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
        dialog = ctk.CTkToplevel(self)
        dialog.title("Lordbot Control")
        dialog.geometry("360x180")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR["surface"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.after(200, lambda: dialog.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")))
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 360) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"360x180+{x}+{y}")

        result = {"name": None}

        ctk.CTkLabel(
            dialog, text="Enter loop name",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR["text"]
        ).pack(pady=(20, 4))
        ctk.CTkLabel(
            dialog, text="e.g. Bot Farm, Auto Quest ...",
            font=ctk.CTkFont(size=10),
            text_color=COLOR["text_muted"]
        ).pack(pady=(0, 8))

        entry = ctk.CTkEntry(
            dialog, fg_color=COLOR["bg"], border_color=COLOR["border"],
            border_width=1, corner_radius=6, height=34,
            font=ctk.CTkFont(size=12), text_color=COLOR["text"],
            placeholder_text="Loop name...", placeholder_text_color=COLOR["text_muted"]
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
            if name in self.loops:
                show_styled_info(self, "Name exists", "A loop with this name already exists")
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
            show_styled_info(self, "No loops selected", "Tick checkboxes to select loops first")
            return

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
            dialog, text=f"Delete {len(to_delete)} loop(s)?\n{names_preview}",
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
            for lname in to_delete:
                if lname in self.loops:
                    del self.loops[lname]
                if self.current_loop_name == lname:
                    self.current_loop_name = None
                    self.loop_name_label.configure(text="[Deleted]")
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
        self.gui_queue.put(("run", lambda: self.loop_status_label.configure(text=text)))
        self.gui_queue.put(("run", lambda: self.loop_status_icon.configure(text_color=color)))

    def _highlight_node(self, node_id):
        """Thread-safe highlight of a node on the flowchart."""
        self.gui_queue.put(("run", lambda: self.flowchart.highlight_node(node_id)))

    def _clear_highlight(self):
        """Thread-safe clear of the node highlight."""
        self.gui_queue.put(("run", lambda: self.flowchart.clear_highlight()))

    def toggle_loop_engine(self):
        if not self.is_looping:
            if not self.current_loop_name:
                show_styled_info(self, "Select a loop", "Choose a loop from the left panel first")
                return
            graph = self.loops.get(self.current_loop_name, {})
            nodes = graph.get("nodes", {})
            if not nodes:
                show_styled_info(self, "Empty flowchart", "Add some nodes to the flowchart first")
                return
                
            start_node = None
            for nid, n in nodes.items():
                if n["type"] == "Start":
                    start_node = nid
                    break
                    
            if not start_node:
                show_styled_info(self, "No Start node", "Add a Start node to the flowchart")
                return
                
            # Read Port/Tab from footer inputs (shared with Nodes tab)
            port_str = self.footer_port_input.get().strip()
            port = int(port_str) if port_str.isdigit() else 9222
            tab_id_str = self.footer_tab_input.get().strip()
            tab_id = int(tab_id_str) if tab_id_str.isdigit() else 0
            
            self.is_looping = True
            self.play_loop_btn.configure(
                text="Stop Loop",
                fg_color=COLOR["danger"], hover_color=COLOR["danger_h"],
                border_width=0, text_color="#FFFFFF"
            )
            self._set_loop_status(f"Starting [{self.current_loop_name}] on Port {port} Tab {tab_id}...", COLOR["warning"])
            self.log_gui(f"*** FLOWCHART AUTO: [{self.current_loop_name}] Port {port}, Tab {tab_id} ***")
            
            threading.Thread(target=self._loop_engine_worker, args=(graph, start_node, tab_id, port), daemon=True).start()
        else:
            self.is_looping = False
            self.play_loop_btn.configure(
                text="▶ Execute",
                fg_color="transparent", hover_color=COLOR["surface2"],
                border_width=1, border_color=COLOR["primary"],
                text_color=COLOR["primary"]
            )
            self._set_loop_status("Idle — Loop stopped", COLOR["text_dim"])
            self._clear_highlight()
            self.log_gui("*** AUTO LOOP STOPPED ***")

    def _loop_engine_worker(self, graph, start_node, tab_id=0, port=9222):
        from cdp_client import CDPClient
        from graph_engine import GraphEngine

        cdp_client = None
        if tab_id is not None:
            try:
                self.log_gui(f"[Loop Engine] Connecting to Port {port}, Tab {tab_id}...")
                cdp_client = CDPClient.connect(port=port, tab_index=tab_id)
                tabs = CDPClient.list_tabs(port)
                for idx_t, t in enumerate(tabs):
                    self.log_gui(f"[Loop Engine]   Tab {idx_t}: {t.get('title', '?')[:25]}")
                self.log_gui(f"[Loop Engine] Hooked to Tab {tab_id}")
            except Exception as e:
                self.log_gui(f"[Loop Engine] Connection fail: {e}")
                return

        bot_instance = BotAction(cdp_client=cdp_client, debug_visual_var=self.debug_visual_var)

        # Map status_fn color strings to COLOR dict
        color_map = {
            "success": COLOR["success"], "danger": COLOR["danger"],
            "warning": COLOR["warning"], "accent": COLOR["accent"],
            "text_dim": COLOR["text_dim"],
        }

        def status_fn(msg, color_name):
            c = color_map.get(color_name, COLOR["text_dim"])
            self._set_loop_status(msg, c)

        engine = GraphEngine(
            graph=graph,
            vision=self.vision,
            tracked_icons=self.tracked_icons,
            combos=self.combos,
            bot_instance=bot_instance,
            cdp_client=cdp_client,
            threshold_fn=lambda: self.slider.get(),
            log_fn=self.log_gui,
            status_fn=status_fn,
            is_running_fn=lambda: self.is_looping,
            highlight_fn=self._highlight_node,
        )

        result = engine.run(start_node)

        if result == "ended":
            self.is_looping = False

        self._clear_highlight()
        self._set_loop_status("Idle — Loop ended", COLOR["text_dim"])
        if cdp_client:
            try:
                cdp_client.close()
            except Exception:
                pass

