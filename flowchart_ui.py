import tkinter as tk
import customtkinter as ctk
import uuid
from tkinter import messagebox, simpledialog

# Unified palette (matches constants.py COLOR dict)
_FC = {
    "bg":       "#0B0F19",
    "surface":  "#141B2D",
    "surface2": "#1C2640",
    "primary":  "#3B82F6",
    "success":  "#10B981",
    "danger":   "#F43F5E",
    "warning":  "#F59E0B",
    "accent":   "#06B6D4",
    "text":     "#E2E8F0",
    "text_dim": "#64748B",
    "node_macro":  "#2563EB",
    "node_cond":   "#D97706",
    "node_delay":  "#8B5CF6",
    "node_start":  "#059669",
    "node_default":"#475569",
    "wire":     "#64748B",
    "wire_true":"#10B981",
    "wire_false":"#F43F5E",
    "wire_drag":"#F59E0B",
    "pin_in":   "#64748B",
    "pin_out":  "#F59E0B",
}


class FlowchartUI(ctk.CTkCanvas):
    def __init__(self, master, get_macros_cb=None, get_images_cb=None, on_change_cb=None, **kwargs):
        super().__init__(master, bg=_FC["bg"], highlightthickness=0, **kwargs)
        self.nodes = {}
        self.edges = []
        
        # State
        self.selected_node = None
        self.active_node_id = None  # Currently executing node (for highlight)
        self.dragging_node = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # Wiring state
        self.wiring = False
        self.wire_start_node = None
        self.wire_start_pin = None
        self.wire_line = None
        
        # Pan state (middle mouse OR right-drag)
        self.panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        
        # View offset (for panning)
        self.view_offset_x = 0
        self.view_offset_y = 0
        
        # Zoom state
        self.zoom = 1.0
        self.ZOOM_MIN = 0.3
        self.ZOOM_MAX = 2.0
        
        # Hand (pan) mode — toggled by H key
        self.hand_mode = False
        
        # Track last mouse position on canvas (for placing new nodes)
        self.last_mouse_x = 200
        self.last_mouse_y = 150
        
        self.get_macros_cb = get_macros_cb
        self.get_images_cb = get_images_cb
        self.on_change_cb = on_change_cb
        
        # Node sizing
        self.NODE_W = 160
        self.NODE_H = 70
        self.NODE_H_COND = 90
        self.PIN_R = 9  # Pin radius for drawing
        self.PIN_HIT = 14  # Pin hit area radius
        self.CORNER_R = 8  # Rounded corner radius
        
        # Bindings
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Button-3>", self.on_right_click)
        
        # Middle mouse pan
        self.bind("<ButtonPress-2>", self.on_pan_start)
        self.bind("<B2-Motion>", self.on_pan_drag)
        self.bind("<ButtonRelease-2>", self.on_pan_end)
        
        # Ctrl+Scroll = Zoom, Scroll = vertical pan, Shift+Scroll = horizontal pan
        self.bind("<Control-MouseWheel>", self.on_zoom)
        self.bind("<MouseWheel>", self.on_scroll)
        self.bind("<Shift-MouseWheel>", self.on_scroll_h)
        
        # Track mouse movement for cursor-based node placement
        self.bind("<Motion>", self.on_mouse_move)
        
        # H key = toggle hand/pan mode, Escape = exit hand mode
        self.bind("<Key-h>", self.toggle_hand_mode)
        self.bind("<Key-H>", self.toggle_hand_mode)
        self.bind("<Escape>", self.exit_hand_mode)
        
        # Auto-grab focus when mouse enters canvas (needed for key events)
        self.bind("<Enter>", lambda e: self.focus_set())

    def highlight_node(self, node_id):
        """Highlight a node as actively running (called from loop engine via gui_queue)."""
        self.active_node_id = node_id
        self.redraw()

    def clear_highlight(self):
        """Remove the active node highlight."""
        self.active_node_id = None
        self.redraw()

    def load_graph(self, data):
        self.nodes = data.get("nodes", {}) if data else {}
        self.edges = data.get("edges", []) if data else []
        self.view_offset_x = 0
        self.view_offset_y = 0
        self.zoom = 1.0
        self.redraw()
    
    def screen_to_world(self, sx, sy):
        """Convert screen coordinates to world coordinates (accounting for pan + zoom)."""
        wx = sx / self.zoom + self.view_offset_x
        wy = sy / self.zoom + self.view_offset_y
        return wx, wy
    
    def world_to_screen(self, wx, wy):
        """Convert world coordinates to screen coordinates."""
        sx = (wx - self.view_offset_x) * self.zoom
        sy = (wy - self.view_offset_y) * self.zoom
        return sx, sy
        
    def export_graph(self):
        return {"nodes": self.nodes, "edges": self.edges}
        
    def add_node(self, ntype, x=None, y=None):
        """Add node near cursor position. x,y params are ignored - uses last mouse pos."""
        nid = str(uuid.uuid4())[:8]
        # Place at cursor position (converted to world coords)
        world_x, world_y = self.screen_to_world(self.last_mouse_x, self.last_mouse_y)
        # Offset slightly so it's centered on cursor
        world_x -= self.NODE_W // 2
        world_y -= self.NODE_H // 2
        
        node = {
            "id": nid, "type": ntype, 
            "x": world_x, 
            "y": world_y, 
            "w": self.NODE_W, "h": self.NODE_H, "data": {}
        }
        if ntype == "Start":
            node["data"] = {"title": "Start"}
        elif ntype == "Macro":
            node["data"] = {"macro_name": "None"}
            node["h"] = self.NODE_H_COND  # Taller to fit dual pins
        elif ntype == "Condition":
            node["data"] = {"image_name": "None"}
            node["h"] = self.NODE_H_COND
        elif ntype == "Delay":
            node["data"] = {"time": 1000}
            
        self.nodes[nid] = node
        self.redraw()
        if self.on_change_cb: self.on_change_cb()
        return nid

    # --- Mouse tracking ---
    def on_mouse_move(self, event):
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y
    
    def toggle_hand_mode(self, event=None):
        self.hand_mode = not self.hand_mode
        self.configure(cursor="fleur" if self.hand_mode else "")
        self.redraw()
    
    def exit_hand_mode(self, event=None):
        self.hand_mode = False
        self.configure(cursor="")
        self.redraw()

    # --- Scroll & Pan & Zoom ---
    def on_scroll(self, event):
        delta = -event.delta // 120 * 30
        self.view_offset_y += delta / self.zoom
        self.redraw()
    
    def on_scroll_h(self, event):
        delta = -event.delta // 120 * 30
        self.view_offset_x += delta / self.zoom
        self.redraw()
    
    def on_zoom(self, event):
        """Ctrl+Scroll = Zoom centered on mouse position."""
        # Get world coords at current mouse position before zoom
        old_wx, old_wy = self.screen_to_world(event.x, event.y)
        
        # Adjust zoom
        factor = 1.1 if event.delta > 0 else 0.9
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom * factor))
        self.zoom = new_zoom
        
        # Adjust offset so the world point under the mouse stays put
        self.view_offset_x = old_wx - event.x / self.zoom
        self.view_offset_y = old_wy - event.y / self.zoom
        
        self.redraw()
    
    def on_pan_start(self, event):
        self.panning = True
        self.pan_start_x = event.x
        self.pan_start_y = event.y
    
    def on_pan_drag(self, event):
        if not self.panning: return
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        self.view_offset_x -= dx / self.zoom
        self.view_offset_y -= dy / self.zoom
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.redraw()
    
    def on_pan_end(self, event):
        self.panning = False

    # --- Pin coords (with view offset + zoom) ---
    def get_pin_coords(self, nid, pin_name):
        n = self.nodes[nid]
        # Convert world coords to screen coords
        sx, sy = self.world_to_screen(n["x"], n["y"])
        sw = n["w"] * self.zoom
        sh = n["h"] * self.zoom
        if pin_name == "in":
            return sx + sw/2, sy
        elif pin_name == "out":
            return sx + sw/2, sy + sh
        elif pin_name == "true":
            return sx + sw/4, sy + sh
        elif pin_name == "false":
            return sx + 3*sw/4, sy + sh
        return sx, sy

    # --- Drawing ---
    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Draw a rounded rectangle on canvas."""
        points = [
            x1+r, y1,  x2-r, y1,  x2, y1,  x2, y1+r,
            x2, y2-r,  x2, y2,  x2-r, y2,  x1+r, y2,
            x1, y2,  x1, y2-r,  x1, y1+r,  x1, y1,  x1+r, y1
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def redraw(self):
        self.delete("all")
        z = self.zoom
        
        # Draw grid (subtle dots)
        cw = self.winfo_width() or 800
        ch = self.winfo_height() or 500
        grid_size = max(20, int(40 * z))
        for gx in range(0, cw, grid_size):
            for gy in range(0, ch, grid_size):
                self.create_oval(gx, gy, gx+2, gy+2, fill="#1E293B", outline="")
        
        # Draw edges (curved bezier-like lines)
        for edge in self.edges:
            try:
                x1, y1 = self.get_pin_coords(edge["from"], edge["from_pin"])
                x2, y2 = self.get_pin_coords(edge["to"], edge["to_pin"])
            except KeyError:
                continue
            
            color = _FC["wire"]
            if edge["from_pin"] == "true": color = _FC["wire_true"]
            elif edge["from_pin"] == "false": color = _FC["wire_false"]
            
            # Smooth curve via midpoints
            mid_y = (y1 + y2) / 2
            self.create_line(
                x1, y1, x1, mid_y, x2, mid_y, x2, y2,
                arrow=tk.LAST, fill=color, width=max(1, int(2*z)), smooth=True,
                tags=("edge", edge["from"], edge["to"])
            )
            
        # Draw nodes
        for nid, n in self.nodes.items():
            sx, sy = self.world_to_screen(n["x"], n["y"])
            sw = n["w"] * z
            sh = n["h"] * z
            
            # Skip if off-screen
            if sx + sw < -50 or sx > cw + 50 or sy + sh < -50 or sy > ch + 50:
                continue
            
            # Node colors
            bg = _FC["node_default"]
            if n["type"] == "Start":      bg = _FC["node_start"]
            elif n["type"] == "Macro":    bg = _FC["node_macro"]
            elif n["type"] == "Condition":bg = _FC["node_cond"]
            elif n["type"] == "Delay":    bg = _FC["node_delay"]
            
            # Active execution glow (bright cyan pulse)
            is_active = (self.active_node_id == nid)
            
            # Selection glow
            if is_active:
                outline_color = "#06B6D4"  # Cyan glow for running node
                outline_width = 4
            elif self.selected_node == nid:
                outline_color = "#FFFFFF"
                outline_width = 3
            else:
                outline_color = bg
                outline_width = 1
            
            cr = max(2, int(self.CORNER_R * z))
            
            # Outer glow for active node
            if is_active:
                glow_pad = max(3, int(6 * z))
                self._round_rect(sx - glow_pad, sy - glow_pad, 
                               sx + sw + glow_pad, sy + sh + glow_pad, cr + 2,
                               fill="", outline="#06B6D4", width=2)
            
            # Shadow
            self._round_rect(sx+3, sy+3, sx+sw+3, sy+sh+3, cr, 
                           fill="#0A0F1A", outline="")
            
            # Node body
            self._round_rect(sx, sy, sx+sw, sy+sh, cr,
                           fill=bg, outline=outline_color, width=outline_width,
                           tags=("node", nid))
            
            # Title text
            title = n["type"]
            if n["type"] == "Macro":
                title = f"Macro\n{n['data'].get('macro_name','None')}"
            elif n["type"] == "Condition":
                title = f"If Found\n{n['data'].get('image_name','None')}"
            elif n["type"] == "Delay":
                delay_val = n['data'].get('time', 1000)
                title = f"Wait\n{delay_val}ms"
            elif n["type"] == "Start":
                title = "START"
            
            font_size = max(7, int(11 * z))
            self.create_text(sx+sw/2, sy+sh/2, text=title, fill=_FC["text"],
                           font=("Segoe UI", font_size, "bold"), tags=("node", nid),
                           width=sw-16*z, justify="center")
            
            # Draw pins
            pr = max(4, int(self.PIN_R * z))
            
            # IN pin (top, except Start)
            if n["type"] != "Start":
                px, py = self.get_pin_coords(nid, "in")
                self.create_oval(px-pr, py-pr, px+pr, py+pr, 
                               fill=_FC["pin_in"], outline=_FC["bg"], width=2,
                               tags=("pin", nid, "in"))
                
            # OUT pins
            if n["type"] == "Condition" or n["type"] == "Macro":
                # Dual pins: success (left) / failure (right)
                px, py = self.get_pin_coords(nid, "true")
                self.create_oval(px-pr, py-pr, px+pr, py+pr,
                               fill=_FC["wire_true"], outline=_FC["bg"], width=2,
                               tags=("pin", nid, "true"))
                label_t = "TRUE" if n["type"] == "Condition" else "OK"
                lfs = max(6, int(8 * z))
                self.create_text(px, py+14*z, text=label_t, fill=_FC["wire_true"],
                               font=("Segoe UI", lfs, "bold"))
                
                # False pin (right)
                px, py = self.get_pin_coords(nid, "false")
                self.create_oval(px-pr, py-pr, px+pr, py+pr,
                               fill=_FC["wire_false"], outline=_FC["bg"], width=2,
                               tags=("pin", nid, "false"))
                label_f = "FALSE" if n["type"] == "Condition" else "FAIL"
                self.create_text(px, py+14*z, text=label_f, fill=_FC["wire_false"],
                               font=("Segoe UI", lfs, "bold"))
            else:
                # Single out pin (bottom)
                px, py = self.get_pin_coords(nid, "out")
                self.create_oval(px-pr, py-pr, px+pr, py+pr,
                               fill=_FC["pin_out"], outline=_FC["bg"], width=2,
                               tags=("pin", nid, "out"))
        
        # Zoom indicator (bottom-right)
        zoom_pct = int(self.zoom * 100)
        self.create_text(cw - 10, ch - 10, text=f"{zoom_pct}%", 
                        fill=_FC["text_dim"], font=("Segoe UI", 9), anchor="se")
        
        # Hand mode indicator
        if self.hand_mode:
            self.create_text(cw - 10, ch - 26, text="HAND (H)", 
                            fill=_FC["warning"], font=("Segoe UI", 9, "bold"), anchor="se")
                
    # --- Interaction ---
    def on_press(self, event):
        self.focus_set()  # Ensure we receive key events
        
        # Hand mode: left click starts panning
        if self.hand_mode:
            self.panning = True
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            return
        
        item = self.find_withtag("current")
        if not item:
            self.selected_node = None
            self.redraw()
            return
            
        tags = self.gettags(item[0])
        if "pin" in tags:
            # Can only wire FROM an output pin
            if tags[2] != "in":
                self.wiring = True
                self.wire_start_node = tags[1]
                self.wire_start_pin = tags[2]
                px, py = self.get_pin_coords(self.wire_start_node, self.wire_start_pin)
                self.wire_line = self.create_line(px, py, event.x, event.y, 
                    fill=_FC["wire_drag"], width=3, dash=(6, 3))
        elif "node" in tags:
            self.selected_node = tags[1]
            self.dragging_node = True
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.redraw()
            
    def on_drag(self, event):
        # Hand mode panning (left click drag)
        if self.panning:
            dx = event.x - self.pan_start_x
            dy = event.y - self.pan_start_y
            self.view_offset_x -= dx / self.zoom
            self.view_offset_y -= dy / self.zoom
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            self.redraw()
        elif self.wiring and self.wire_line:
            px, py = self.get_pin_coords(self.wire_start_node, self.wire_start_pin)
            self.coords(self.wire_line, px, py, event.x, event.y)
        elif self.dragging_node and self.selected_node:
            dx = (event.x - self.drag_start_x) / self.zoom
            dy = (event.y - self.drag_start_y) / self.zoom
            self.nodes[self.selected_node]["x"] += dx
            self.nodes[self.selected_node]["y"] += dy
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.redraw()
            
    def on_release(self, event):
        if self.panning:
            self.panning = False
            return
            
        if self.wiring:
            self.wiring = False
            self.delete(self.wire_line)
            self.wire_line = None
            
            # Find target pin — generous snap radius
            x, y = event.x, event.y
            items = self.find_overlapping(x - self.PIN_HIT, y - self.PIN_HIT, 
                                          x + self.PIN_HIT, y + self.PIN_HIT)
            
            for item in items:
                tags = self.gettags(item)
                if "pin" in tags and tags[2] == "in" and tags[1] != self.wire_start_node:
                    from_node = self.wire_start_node
                    from_pin = self.wire_start_pin
                    to_node = tags[1]
                    to_pin = tags[2]
                    
                    # Remove existing out connection from same pin
                    self.edges = [e for e in self.edges if not (e["from"] == from_node and e["from_pin"] == from_pin)]
                    
                    if from_node != to_node:
                        self.edges.append({"from": from_node, "from_pin": from_pin, "to": to_node, "to_pin": to_pin})
                        if self.on_change_cb: self.on_change_cb()
                    break
                    
            self.redraw()
            
        if self.dragging_node:
            self.dragging_node = False
            if self.on_change_cb: self.on_change_cb()

    def on_right_click(self, event):
        item = self.find_withtag("current")
        if not item: return
        tags = self.gettags(item[0])
        
        if "node" in tags:
            nid = tags[1]
            self.show_node_menu(nid, event.x_root, event.y_root)
        elif "edge" in tags:
            from_nid = tags[1]
            to_nid = tags[2]
            self.edges = [e for e in self.edges if not (e["from"] == from_nid and e["to"] == to_nid)]
            self.redraw()
            if self.on_change_cb: self.on_change_cb()
            
    def show_node_menu(self, nid, x, y):
        menu = tk.Menu(self, tearoff=0, bg=_FC["surface"], fg=_FC["text"],
                      activebackground=_FC["primary"], activeforeground="white",
                      font=("Segoe UI", 10))
        n = self.nodes[nid]
        
        if n["type"] == "Macro":
            menu.add_command(label="Select Macro...", command=lambda: self.config_macro(nid))
        elif n["type"] == "Condition":
            menu.add_command(label="Select Target Image...", command=lambda: self.config_condition(nid))
        elif n["type"] == "Delay":
            menu.add_command(label="Set Delay Time...", command=lambda: self.config_delay(nid))
            
        if n["type"] != "Start":
            menu.add_separator()
            menu.add_command(label="Delete Node", command=lambda: self.delete_node(nid))
        menu.tk_popup(x, y)
        
    def config_macro(self, nid):
        if not self.get_macros_cb: return
        macros = self.get_macros_cb()
        if not macros:
            messagebox.showinfo("Empty", "No macros available!")
            return
        
        top = ctk.CTkToplevel(self)
        top.title("Select Macro")
        top.geometry("280x350")
        top.attributes("-topmost", True)
        
        ctk.CTkLabel(top, text="Choose a Macro", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 8))
        
        frame = ctk.CTkScrollableFrame(top, fg_color=_FC["surface"])
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        
        def on_sel(m):
            self.nodes[nid]["data"]["macro_name"] = m
            self.redraw()
            if self.on_change_cb: self.on_change_cb()
            top.destroy()
            
        for m in macros:
            ctk.CTkButton(frame, text=m, command=lambda x=m: on_sel(x),
                         fg_color=_FC["node_macro"], hover_color=_FC["primary"],
                         corner_radius=6).pack(pady=3, fill="x")
        
    def config_condition(self, nid):
        if not self.get_images_cb: return
        images = self.get_images_cb()
        if not images:
            messagebox.showinfo("Empty", "No images tracked!")
            return
            
        top = ctk.CTkToplevel(self)
        top.title("Select Image")
        top.geometry("280x350")
        top.attributes("-topmost", True)
        
        ctk.CTkLabel(top, text="Choose Target Image", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 8))
        
        frame = ctk.CTkScrollableFrame(top, fg_color=_FC["surface"])
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        
        def on_sel(m):
            self.nodes[nid]["data"]["image_name"] = m
            self.redraw()
            if self.on_change_cb: self.on_change_cb()
            top.destroy()
            
        for m in images:
            ctk.CTkButton(frame, text=m, command=lambda x=m: on_sel(x),
                         fg_color=_FC["node_cond"], hover_color=_FC["warning"],
                         corner_radius=6).pack(pady=3, fill="x")
        
    def config_delay(self, nid):
        val = simpledialog.askfloat("Set Delay", "Enter delay in milliseconds (ms):", 
                                     initialvalue=self.nodes[nid]["data"].get("time", 1000))
        if val is not None:
            self.nodes[nid]["data"]["time"] = max(0, val)
            self.redraw()
            if self.on_change_cb: self.on_change_cb()
            
    def delete_node(self, nid):
        if nid in self.nodes:
            del self.nodes[nid]
        self.edges = [e for e in self.edges if e["from"] != nid and e["to"] != nid]
        self.redraw()
        if self.on_change_cb: self.on_change_cb()
