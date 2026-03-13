import cv2
import numpy as np
import mss
import time
import os
import ctypes

# Bật chế độ DPI Aware
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) 
except Exception:
    pass

class Vision:
    def __init__(self):
        os.makedirs("debug", exist_ok=True)

    def find_template_on_screen(self, template_path, threshold=0.8, debug=True, region=None, frame_bytes=None):
        """
        [NÂNG CẤP V4] - HỖ TRỢ QUÉT THEO VÙNG (REGION) & ẢNH FRAME TRỰC TIẾP
        -> template_path: đường dẫn tới ảnh cần tìm.
        -> frame_bytes: Byte array của Screenshot chụp từ Playwright/CDP truyền vào. 
           Nếu None, fallback về mss chụp ảnh Window Desktop (Chế độ cũ).
        """
        template_bgr = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template_bgr is None:
            return None
            
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        template_edges = cv2.Canny(template_gray, 50, 200)

        # 1. Chụp ảnh (Hoặc lấy từ Frame Background)
        if frame_bytes is not None:
            # Chuyển đổi bytes thành OpenCV Image
            np_arr = np.frombuffer(frame_bytes, np.uint8)
            img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if img_bgr is None:
                return None
            
            # [CRITICAL FIX] Khi dùng Playwright, frame chụp được chỉ bao gồm Nội dung của Trang Web.
            # Tọa độ Region cũ do người dùng khoanh là tọa độ của Windows Desktop (Tuyệt đối).
            # Do đó chúng ta TUYỆT ĐỐI KHÔNG DÙNG Region này để crop hay bù offset cho ảnh Web.
            region = None 
        else:
            with mss.mss() as sct:
                if region:
                    # Dùng region do user khoanh (Trên màn hình thật)
                    monitor = {"left": region[0], "top": region[1], "width": int(region[2]), "height": int(region[3])}
                else:
                    # Quét full màn hình
                    monitor = sct.monitors[0]
                    
                screenshot = sct.grab(monitor)
            img_bgr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
            
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        img_edges = cv2.Canny(img_gray, 50, 200)

        found = None

        for scale in np.linspace(0.8, 1.2, 9)[::-1]:
            width = int(template_edges.shape[1] * scale)
            height = int(template_edges.shape[0] * scale)
            
            if width == 0 or height == 0 or width > img_edges.shape[1] or height > img_edges.shape[0]:
                continue
                
            resized_template_edges = cv2.resize(template_edges, (width, height))
            
            res = cv2.matchTemplate(img_edges, resized_template_edges, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if found is None or max_val > found[0]:
                found = (max_val, max_loc, width, height)

        if found:
            best_val, best_loc, best_w, best_h = found
            scaled_score = min(1.0, best_val * 1.5) 
            
            if debug:
                debug_img = img_bgr.copy()
                top_left = best_loc
                bottom_right = (top_left[0] + best_w, top_left[1] + best_h)
                
                color = (0, 255, 0) if best_val >= 0.4 else (0, 0, 255)
                cv2.rectangle(debug_img, top_left, bottom_right, color, 3)
                
                text = f"Edge Score: {scaled_score:.2f} (Raw: {best_val:.2f})"
                cv2.putText(debug_img, text, (top_left[0], top_left[1]-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                
                cv2.imwrite("debug/last_scan.jpg", debug_img)
                cv2.imwrite("debug/edge_view.jpg", img_edges)

            if best_val >= 0.4:
                if frame_bytes is not None:
                    # Tọa độ tương đối trên file ảnh nhận được
                    offset_x = region[0] if region else 0
                    offset_y = region[1] if region else 0
                else:
                    # Màn hình Windows Desktop thực tế
                    offset_x = monitor["left"]
                    offset_y = monitor["top"]
                
                center_x = best_loc[0] + best_w // 2 + offset_x
                center_y = best_loc[1] + best_h // 2 + offset_y
                return (center_x, center_y, scaled_score)

        return None
