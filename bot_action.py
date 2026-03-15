import pyautogui
import time
import random

class BotAction:
    def __init__(self, page=None, debug_visual_var=None):
        """
        page: Một Instance của Playwright Page (nếu chạy nền)
              Nếu None, fallback về click chuột hệ thống bằng PyAutoGUI
        debug_visual_var: BooleanVar để bật/tắt chấm đỏ debug click
        """
        self.page = page
        self.debug_visual_var = debug_visual_var
        self.cdp = None
        self._create_cdp_session()

    def _create_cdp_session(self):
        """Create a fresh CDP session for the current page."""
        self._detach_cdp()  # Close existing session first
        if self.page:
            try:
                self.cdp = self.page.context.new_cdp_session(self.page)
            except Exception as e:
                print(f"[BotAction] Could not hook CDP: {e}")
                self.cdp = None
    
    def _detach_cdp(self):
        """Safely detach and close the current CDP session."""
        if self.cdp:
            try:
                self.cdp.detach()
            except Exception:
                pass
            self.cdp = None
    
    def refresh_cdp(self):
        """Refresh CDP session (call after reconnect)."""
        self._create_cdp_session()
    
    def _cdp_send_safe(self, method, params):
        """Send CDP command with 1 retry on session error."""
        try:
            self.cdp.send(method, params)
            return True
        except Exception as e:
            err_str = str(e).lower()
            if "session" in err_str or "detach" in err_str or "closed" in err_str:
                # Session died — recreate and retry once
                print(f"[BotAction] CDP session lost, recreating: {e}")
                self._create_cdp_session()
                if self.cdp:
                    try:
                        self.cdp.send(method, params)
                        return True
                    except Exception as e2:
                        print(f"[BotAction] CDP retry failed: {e2}")
            else:
                print(f"[BotAction] CDP error: {e}")
            return False

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
                # [CRITICAL FIX] Coordinates from cv2 on page.screenshot() are PHYSICAL pixels.
                # page.mouse.click() expects CSS pixels → divide by devicePixelRatio.
                try:
                    dpr = float(self.page.evaluate("window.devicePixelRatio"))
                except:
                    dpr = 1.0
                
                css_x = x / dpr
                css_y = y / dpr
                
                # --- VISUAL DEBUGGER & CLICK INJECTION ---
                frames = self.page.frames
                target_frame = self.page.main_frame
                
                for f in frames:
                    try:
                        has_canvas = f.evaluate("document.querySelectorAll('canvas').length > 0")
                        if has_canvas:
                            target_frame = f
                            break
                    except:
                        pass
                
                # --- VISUAL DEBUGGER (chỉ vẽ khi toggle bật) ---
                show_dot = self.debug_visual_var.get() if self.debug_visual_var else False
                if show_dot:
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
                
                # [SAFETY] Kiểm tra tọa độ trước khi click
                try:
                    viewport_size = self.page.evaluate("({w: window.innerWidth, h: window.innerHeight})")
                    vw = viewport_size['w']
                    vh = viewport_size['h']
                    if css_x < 0 or css_x > vw or css_y < 0 or css_y > vh:
                        print(f"[BotAction] BLOCKED CLICK: ({css_x:.0f},{css_y:.0f}) outside viewport ({vw}x{vh})")
                        return
                except:
                    pass
                
                # --- THỰC THI CLICK ---
                if self.cdp:
                    # Use _cdp_send_safe for auto-retry on session errors
                    ok = self._cdp_send_safe("Input.dispatchMouseEvent", {
                        "type": "mouseMoved",
                        "x": css_x, "y": css_y,
                        "button": "none",
                    })
                    if ok:
                        time.sleep(random.uniform(0.015, 0.03))
                        
                        ok = self._cdp_send_safe("Input.dispatchMouseEvent", {
                            "type": "mousePressed",
                            "x": css_x, "y": css_y,
                            "button": "left",
                            "clickCount": 1,
                        })
                    if ok:
                        time.sleep(random.uniform(0.04, 0.08))
                        
                        self._cdp_send_safe("Input.dispatchMouseEvent", {
                            "type": "mouseReleased",
                            "x": css_x, "y": css_y,
                            "button": "left",
                            "clickCount": 1,
                        })
                    
                    if not ok:
                        # All CDP attempts failed, fallback to Playwright mouse
                        print(f"[BotAction] CDP failed completely, using page.mouse.click")
                        self.page.mouse.click(css_x, css_y, delay=random.randint(80, 180))
                else:
                    self.page.mouse.click(css_x, css_y, delay=random.randint(80, 180))
                    
                time.sleep(random.uniform(0.05, 0.10))
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
            try:
                playwright_key = keys_str.replace("ctrl", "Control").replace("shift", "Shift").replace("alt", "Alt")
                self.page.keyboard.press(playwright_key)
            except Exception as e:
                print(f"[BotAction] Lỗi Key Background: {str(e)}")
        else:
            if len(parts) == 1:
                pyautogui.press(parts[0])
            else:
                pyautogui.hotkey(*parts)
