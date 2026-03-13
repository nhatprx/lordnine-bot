import pyautogui
import time
import random

class BotAction:
    def __init__(self, page=None):
        """
        page: Một Intance của Playwright Page (nếu chạy nền)
              Nếu None, fallback về click chuột hệ thống bằng PyAutoGUI
        """
        self.page = page
        self.cdp = None
        if self.page:
            try:
                self.cdp = self.page.context.new_cdp_session(self.page)
            except Exception as e:
                print(f"[BotAction] Could not hook CDP: {e}")

    def click_at(self, x, y, randomize=True):
        """
        Di chuyển chuột đến tọa độ (x, y) để thực thi click.
        randomize: Cho phép sai số vị trí khi click nhằm qua mặt AntiCheat.
        """
        if randomize:
            x += random.randint(-3, 3)
            y += random.randint(-3, 3)

        if self.page:
            # CLICK NGẦM BẰNG PLAYWRIGHT
            try:
                # [CRITICAL FIX] 1: Coordinates returned by cv2 on page.screenshot() are PHYSICAL Image pixels.
                # However, page.mouse.click() expects CSS Element pixels!
                # We MUST divide by devicePixelRatio to land the click on the correct spot.
                try:
                    dpr = float(self.page.evaluate("window.devicePixelRatio"))
                except:
                    dpr = 1.0
                
                css_x = x / dpr
                css_y = y / dpr
                
                # --- VISUAL DEBUGGER & CLICK INJECTION ---
                # Cloud emulators use iframes. We must inject the dot and the click into the correct child frame.
                frames = self.page.frames
                target_frame = self.page.main_frame
                
                # Biện pháp tìm Iframe chứa Game (thường là frame to nhất hoặc có chứa thẻ <canvas>)
                for f in frames:
                    try:
                        # Thử xem frame nào có thẻ canvas
                        has_canvas = f.evaluate("document.querySelectorAll('canvas').length > 0")
                        if has_canvas:
                            target_frame = f
                            break
                    except:
                        pass
                
                js_draw_dot = """
                (args) => {
                    const dot = document.createElement('div');
                    dot.style.width = '12px';
                    dot.style.height = '12px';
                    dot.style.backgroundColor = 'red';
                    dot.style.border = '2px solid white';
                    dot.style.borderRadius = '50%';
                    dot.style.position = 'fixed';
                    dot.style.left = (args.x - 6) + 'px';
                    dot.style.top = (args.y - 6) + 'px';
                    dot.style.zIndex = '999999';
                    dot.style.pointerEvents = 'none';
                    document.body.appendChild(dot);
                    setTimeout(() => dot.remove(), 2500);
                }
                """
                try: 
                    target_frame.evaluate(js_draw_dot, {'x': css_x, 'y': css_y})
                except Exception as e:
                    print(f"Failed to draw dot: {e}")
                
                # --- THỰC THI CLICK ---
                if self.cdp:
                    # CDP gửi event ở Application level, có thể bị chặn bởi Iframe
                    self.cdp.send("Input.dispatchTouchEvent", {
                        "type": "touchStart",
                        "touchPoints": [{"x": css_x, "y": css_y, "id": 1}]
                    })
                    time.sleep(random.uniform(0.05, 0.1))
                    self.cdp.send("Input.dispatchTouchEvent", {
                        "type": "touchEnd",
                        "touchPoints": []
                    })
                else:
                    target_frame.mouse.click(css_x, css_y, delay=random.randint(50, 150))
                    
                time.sleep(random.uniform(0.1, 0.2))
            except Exception as e:
                print(f"[BotAction] Lỗi Click Background: {str(e)}")
        else:
            # CLICK NỔI BẰNG PYAUTOGUI
            duration = random.uniform(0.1, 0.3)
            pyautogui.moveTo(x, y, duration=duration)
            time.sleep(random.uniform(0.05, 0.15))
            pyautogui.click()

    def press_key(self, keys_str):
        """
        Gửi phím tắt hoặc chuỗi phím.
        """
        parts = [p.strip().lower() for p in keys_str.split('+')]
        if not parts or parts == [""]:
            return
            
        print(f"[DEBUG HOTKEY] Sending keys -> {parts}")
        time.sleep(random.uniform(0.1, 0.3))
        
        if self.page:
            # Gửi bằng Playwright Background
            try:
                playwright_key = keys_str.replace("ctrl", "Control").replace("shift", "Shift").replace("alt", "Alt")
                self.page.keyboard.press(playwright_key)
            except Exception as e:
                print(f"[BotAction] Lỗi Key Background: {str(e)}")
        else:
            # Gửi phím Windows thật
            if len(parts) == 1:
                pyautogui.press(parts[0])
            else:
                pyautogui.hotkey(*parts)
