import tkinter as tk
import customtkinter as ctk
import uuid
from tkinter import messagebox, simpledialog

class FlowchartUI(ctk.CTkCanvas):
    def __init__(self, master, get_macros_cb=None, get_images_cb=None, on_change_cb=None, **kwargs):
        super().__init__(master, bg="#1E2B3C", highlightthickness=0, **kwargs)
        self.nodes = {}
        self.edges = [] # dicts: {'from': node_id, 'from_pin': pin_name, 'to': node_id, 'to_pin': pin_name}
        
        # State
        self.selected_node = None
        self.dragging_node = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        self.wiring = False
        self.wire_start_node = None
        self.wire_start_pin = None
        self.wire_line = None
        
        self.get_macros_cb = get_macros_cb
        self.get_images_cb = get_images_cb
        self.on_change_cb = on_change_cb
        
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Button-3>", self.on_right_click)

    def load_graph(self, data):
        self.nodes = data.get("nodes", {})
        self.edges = data.get("edges", [])
        self.redraw()
        
    def export_graph(self):
        return {"nodes": self.nodes, "edges": self.edges}
        
    def add_node(self, ntype, x=50, y=50):
        nid = str(uuid.uuid4())[:8]
        node = {
            "id": nid, "type": ntype, "x": x, "y": y, 
            "w": 140, "h": 60, "data": {}
        }
        if ntype == "Start":
            node["data"] = {"title": "Start"}
        elif ntype == "Macro":
            node["data"] = {"macro_name": "None"}
        elif ntype == "Condition":
            node["data"] = {"image_name": "None"}
            node["h"] = 80
        elif ntype == "Delay":
            node["data"] = {"time": 1.0}
            
        self.nodes[nid] = node
        self.redraw()
        if self.on_change_cb: self.on_change_cb()
        return nid
        
    # Helper to calculate pin positions
    def get_pin_coords(self, nid, pin_name):
        n = self.nodes[nid]
        if pin_name == "in":
            return n["x"] + n["w"]/2, n["y"]
        elif pin_name == "out":
            return n["x"] + n["w"]/2, n["y"] + n["h"]
        elif pin_name == "true":
            return n["x"] + n["w"]/4, n["y"] + n["h"]
        elif pin_name == "false":
            return n["x"] + 3*n["w"]/4, n["y"] + n["h"]
        return n["x"], n["y"]

    # Redraw everything
    def redraw(self):
        self.delete("all")
        # Draw edges
        for edge in self.edges:
            x1, y1 = self.get_pin_coords(edge["from"], edge["from_pin"])
            x2, y2 = self.get_pin_coords(edge["to"], edge["to_pin"])
            color = "#2ECC71" if edge["from_pin"] == "true" else "#E74C3C" if edge["from_pin"] == "false" else "#BDC3C7"
            self.create_line(x1, y1, x2, y2, arrow=tk.LAST, fill=color, width=3, tags=("edge", edge["from"], edge["to"]))
            
        # Draw nodes
        for nid, n in self.nodes.items():
            x, y, w, h = n["x"], n["y"], n["w"], n["h"]
            bg_color = "#34495E"
            if n["type"] == "Start": bg_color = "#27AE60"
            elif n["type"] == "Condition": bg_color = "#D35400"
            elif n["type"] == "Delay": bg_color = "#8E44AD"
            elif n["type"] == "Macro": bg_color = "#2980B9"
            
            outline = "white" if self.selected_node == nid else "black"
            
            self.create_rectangle(x, y, x+w, y+h, fill=bg_color, outline=outline, width=2, tags=("node", nid))
            
            # Title
            title = n["type"]
            if n["type"] == "Macro": title = f"Macro:\n{n['data'].get('macro_name','None')}"
            elif n["type"] == "Condition": title = f"If Found:\n{n['data'].get('image_name','None')}"
            elif n["type"] == "Delay": title = f"Wait: {n['data'].get('time',1)}s"
            
            self.create_text(x+w/2, y+h/2, text=title, fill="white", font=("Arial", 10, "bold"), tags=("node", nid), width=w-10, justify="center")
            
            # Draw pins (larger hitboxes)
            if n["type"] != "Start":
                px, py = self.get_pin_coords(nid, "in")
                self.create_oval(px-8, py-8, px+8, py+8, fill="#BDC3C7", tags=("pin", nid, "in"))
                
            if n["type"] == "Condition":
                px, py = self.get_pin_coords(nid, "true")
                self.create_oval(px-8, py-8, px+8, py+8, fill="#2ECC71", tags=("pin", nid, "true"))
                self.create_text(px, py-14, text="T", fill="#2ECC71", font=("Arial", 8, "bold"))
                
                px, py = self.get_pin_coords(nid, "false")
                self.create_oval(px-8, py-8, px+8, py+8, fill="#E74C3C", tags=("pin", nid, "false"))
                self.create_text(px, py-14, text="F", fill="#E74C3C", font=("Arial", 8, "bold"))
            else:
                px, py = self.get_pin_coords(nid, "out")
                self.create_oval(px-8, py-8, px+8, py+8, fill="#F39C12", tags=("pin", nid, "out"))
                
    def on_press(self, event):
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
                self.wire_line = self.create_line(px, py, event.x, event.y, fill="#F1C40F", width=3, dash=(5,2))
        elif "node" in tags:
            self.selected_node = tags[1]
            self.dragging_node = True
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.redraw()
            
    def on_drag(self, event):
        if self.wiring and self.wire_line:
            px, py = self.get_pin_coords(self.wire_start_node, self.wire_start_pin)
            self.coords(self.wire_line, px, py, event.x, event.y)
        elif self.dragging_node and self.selected_node:
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            self.nodes[self.selected_node]["x"] += dx
            self.nodes[self.selected_node]["y"] += dy
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.redraw()
            
    def on_release(self, event):
        if self.wiring:
            self.wiring = False
            self.delete(self.wire_line)
            self.wire_line = None
            
            # Find the element under the mouse when released - HUGE HITBOX FOR SNAPPING
            x, y = event.x, event.y
            items = self.find_overlapping(x-15, y-15, x+15, y+15)
            
            for item in items:
                tags = self.gettags(item)
                if "pin" in tags and tags[2] == "in" and tags[1] != self.wire_start_node:
                    # Valid connection
                    from_node = self.wire_start_node
                    from_pin = self.wire_start_pin
                    to_node = tags[1]
                    to_pin = tags[2]
                    
                    # Prevent multiple out connections from same out pin
                    self.edges = [e for e in self.edges if not (e["from"] == from_node and e["from_pin"] == from_pin)]
                    # Prevent cycle from self to self
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
            # Delete edge
            from_nid = tags[1]
            to_nid = tags[2]
            self.edges = [e for e in self.edges if not (e["from"] == from_nid and e["to"] == to_nid)]
            self.redraw()
            if self.on_change_cb: self.on_change_cb()
            
    def show_node_menu(self, nid, x, y):
        menu = tk.Menu(self, tearoff=0)
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
        top.geometry("250x300")
        top.attributes("-topmost", True)
        
        frame = ctk.CTkScrollableFrame(top)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        def on_sel(m):
            self.nodes[nid]["data"]["macro_name"] = m
            self.redraw()
            if self.on_change_cb: self.on_change_cb()
            top.destroy()
            
        for m in macros:
            ctk.CTkButton(frame, text=m, command=lambda x=m: on_sel(x)).pack(pady=2, fill="x")
        
    def config_condition(self, nid):
        if not self.get_images_cb: return
        images = self.get_images_cb()
        if not images:
            messagebox.showinfo("Empty", "No images tracked!")
            return
            
        top = ctk.CTkToplevel(self)
        top.title("Select Image")
        top.geometry("250x300")
        top.attributes("-topmost", True)
        
        frame = ctk.CTkScrollableFrame(top)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        def on_sel(m):
            self.nodes[nid]["data"]["image_name"] = m
            self.redraw()
            if self.on_change_cb: self.on_change_cb()
            top.destroy()
            
        for m in images:
            ctk.CTkButton(frame, text=m, command=lambda x=m: on_sel(x)).pack(pady=2, fill="x")
        
    def config_delay(self, nid):
        val = simpledialog.askfloat("Set Delay", "Enter delay in seconds:", initialvalue=self.nodes[nid]["data"].get("time", 1.0))
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
