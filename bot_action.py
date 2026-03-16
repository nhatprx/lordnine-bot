import pyautogui
import time
import random

class BotAction:
    def __init__(self, page=None, cdp_client=None, debug_visual_var=None):
        """
        page: Legacy Playwright Page instance (for backward compat)
        cdp_client: CDPClient instance (preferred for 500 acc scale)
        debug_visual_var: BooleanVar to toggle debug click dots
        
        If cdp_client is provided, it's used directly.
        If only page is provided, legacy Playwright CDP session is created.
        If neither, falls back to PyAutoGUI system clicks.
        """
        self.page = page
        self.cdp_client = cdp_client
        self.debug_visual_var = debug_visual_var
        self.cdp = None
        
        # Only create legacy CDP session if using Playwright page
        if page and not cdp_client:
            self._create_cdp_session()

    def _create_cdp_session(self):
        """Create a fresh CDP session for the current Playwright page (legacy)."""
        self._detach_cdp()
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
        if self.cdp_client:
            try: self.cdp_client.reconnect()
            except: pass
        else:
            self._create_cdp_session()
    
    def _cdp_send_safe(self, method, params):
        """Send CDP command with 1 retry on session error."""
        if self.cdp_client:
            try:
                self.cdp_client._send(method, params)
                return True
            except Exception as e:
                try:
                    self.cdp_client.reconnect()
                    self.cdp_client._send(method, params)
                    return True
                except:
                    return False
        
        # Legacy Playwright CDP
        try:
            self.cdp.send(method, params)
            return True
        except Exception as e:
            err_str = str(e).lower()
            if "session" in err_str or "detach" in err_str or "closed" in err_str:
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
        Click at coordinate (x, y).
        randomize: Add slight randomness to bypass anti-cheat.
        """
        if randomize:
            x += random.randint(-3, 3)
            y += random.randint(-3, 3)

        if self.cdp_client or self.page:
            # BACKGROUND CLICK
            try:
                # Get devicePixelRatio for coordinate conversion
                try:
                    if self.cdp_client:
                        dpr = float(self.cdp_client.evaluate("window.devicePixelRatio"))
                    else:
                        dpr = float(self.page.evaluate("window.devicePixelRatio"))
                except:
                    dpr = 1.0
                
                css_x = x / dpr
                css_y = y / dpr
                
                # --- VISUAL DEBUGGER & CLICK INJECTION ---
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
                        if self.cdp_client:
                            # Find canvas frame and draw dot
                            canvas_frame = self.cdp_client.find_canvas_frame()
                            if canvas_frame:
                                self.cdp_client.evaluate_in_specific_frame(
                                    canvas_frame,
                                    f"({js_draw_dot})({{x: {css_x}, y: {css_y}}})"
                                )
                            else:
                                self.cdp_client.evaluate(
                                    f"({js_draw_dot})({{x: {css_x}, y: {css_y}}})"
                                )
                        else:
                            # Legacy: use Playwright frames
                            frames = self.page.frames
                            target_frame = self.page.main_frame
                            for f in frames:
                                try:
                                    if f.evaluate("document.querySelectorAll('canvas').length > 0"):
                                        target_frame = f
                                        break
                                except:
                                    pass
                            target_frame.evaluate(js_draw_dot, {'x': css_x, 'y': css_y})
                    except:
                        pass
                
                # [SAFETY] Bound check
                try:
                    if self.cdp_client:
                        viewport_size = self.cdp_client.evaluate("({w: window.innerWidth, h: window.innerHeight})")
                    else:
                        viewport_size = self.page.evaluate("({w: window.innerWidth, h: window.innerHeight})")
                    vw = viewport_size['w']
                    vh = viewport_size['h']
                    if css_x < 0 or css_x > vw or css_y < 0 or css_y > vh:
                        print(f"[BotAction] BLOCKED CLICK: ({css_x:.0f},{css_y:.0f}) outside viewport ({vw}x{vh})")
                        return
                except:
                    pass
                
                # --- EXECUTE CLICK ---
                if self.cdp_client:
                    # Direct CDPClient click
                    self.cdp_client.click(css_x, css_y)
                elif self.cdp:
                    # Legacy: use Playwright CDP session
                    ok = self._cdp_send_safe("Input.dispatchMouseEvent", {
                        "type": "mouseMoved", "x": css_x, "y": css_y, "button": "none",
                    })
                    if ok:
                        time.sleep(random.uniform(0.015, 0.03))
                        ok = self._cdp_send_safe("Input.dispatchMouseEvent", {
                            "type": "mousePressed", "x": css_x, "y": css_y,
                            "button": "left", "clickCount": 1,
                        })
                    if ok:
                        time.sleep(random.uniform(0.04, 0.08))
                        self._cdp_send_safe("Input.dispatchMouseEvent", {
                            "type": "mouseReleased", "x": css_x, "y": css_y,
                            "button": "left", "clickCount": 1,
                        })
                    if not ok:
                        print(f"[BotAction] CDP failed completely, using page.mouse.click")
                        self.page.mouse.click(css_x, css_y, delay=random.randint(80, 180))
                else:
                    self.page.mouse.click(css_x, css_y, delay=random.randint(80, 180))
                    
                time.sleep(random.uniform(0.05, 0.10))
            except Exception as e:
                print(f"[BotAction] Click Error: {str(e)}")
        else:
            # SYSTEM CLICK (PyAutoGUI)
            duration = random.uniform(0.1, 0.3)
            pyautogui.moveTo(x, y, duration=duration)
            time.sleep(random.uniform(0.05, 0.15))
            pyautogui.click()

    def press_key(self, keys_str):
        """Send hotkey or key sequence."""
        parts = [p.strip().lower() for p in keys_str.split('+')]
        if not parts or parts == [""]:
            return

        time.sleep(random.uniform(0.1, 0.3))
        
        if self.cdp_client:
            try:
                # Map key names for CDPClient
                key_mapped = keys_str.replace("ctrl", "Control").replace("shift", "Shift").replace("alt", "Alt")
                self.cdp_client.press_key(key_mapped)
            except Exception as e:
                print(f"[BotAction] Key Error (CDP): {str(e)}")
        elif self.page:
            try:
                playwright_key = keys_str.replace("ctrl", "Control").replace("shift", "Shift").replace("alt", "Alt")
                self.page.keyboard.press(playwright_key)
            except Exception as e:
                print(f"[BotAction] Key Error (Playwright): {str(e)}")
        else:
            if len(parts) == 1:
                pyautogui.press(parts[0])
            else:
                pyautogui.hotkey(*parts)
