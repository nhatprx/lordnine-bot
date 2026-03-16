import tkinter as tk

class ScreenCaptureTool:
    def __init__(self, master_coords_callback, region_bounds=None):
        """
        region_bounds: tuple (left, top, width, height) - Vùng giới hạn Cắt Ảnh
        Nếu truyền vào, công cụ chỉ cho phép cắt đúng trong phạm vi này.
        """
        self.master_coords_callback = master_coords_callback
        self.region_bounds = region_bounds
        
        self.root = tk.Toplevel()
        self.root.attributes("-alpha", 0.5)  # Mờ hơn 1 xíu để thấy rõ
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.config(cursor="cross")
        self.root.focus_force()

        self.canvas = tk.Canvas(self.root, cursor="cross", bg="black")
        self.canvas.pack(fill="both", expand=True)

        # Nếu có giới hạn vùng, bôi đen xám lại toàn màn nhưng để "Thủng" phần vùng xám cho user biết
        if self.region_bounds:
            x, y, w, h = self.region_bounds
            x, y, w, h = int(x), int(y), int(w), int(h)
            cx, cy = x + w, y + h
            
            # Lấy kích thước màn hình
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()

            # Vẽ 4 HCN xám đậm bao quanh cái lỗ
            # Top
            self.canvas.create_rectangle(0, 0, sw, y, fill="black", outline="")
            # Bottom
            self.canvas.create_rectangle(0, cy, sw, sh, fill="black", outline="")
            # Left
            self.canvas.create_rectangle(0, y, x, cy, fill="black", outline="")
            # Right
            self.canvas.create_rectangle(cx, y, sw, cy, fill="black", outline="")
            
            # Highlight vùng lõi xanh lá mờ mờ
            self.canvas.create_rectangle(x, y, cx, cy, fill="#2E4053", outline="#1ABC9C", dash=(4, 4))


        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.start_x = None
        self.start_y = None
        self.rect = None

    def _clamp(self, val, min_val, max_val):
        return max(min_val, min(val, max_val))

    def _get_clamped_coord(self, raw_x, raw_y):
        if not self.region_bounds:
            return raw_x, raw_y
            
        x, y, w, h = self.region_bounds
        cx, cy = x + w, y + h
        return self._clamp(raw_x, x, cx), self._clamp(raw_y, y, cy)

    def on_press(self, event):
        self.start_x, self.start_y = self._get_clamped_coord(event.x, event.y)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=2, fill="white", stipple="gray50")

    def on_drag(self, event):
        if self.start_x is None: return
        cur_x, cur_y = self._get_clamped_coord(event.x, event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
        if self.start_x is None or self.start_y is None:
            self.root.destroy()
            return
            
        end_x, end_y = self._get_clamped_coord(event.x, event.y)
        
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        self.root.destroy()
        
        if x2 - x1 > 5 and y2 - y1 > 5:
            self.master_coords_callback(x1, y1, x2, y2)

    def run(self):
        self.root.wait_window()
