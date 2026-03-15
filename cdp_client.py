"""
CDPClient — Lightweight Chrome DevTools Protocol client.

Replaces Playwright for 500+ account scale by connecting directly
to Chrome tabs via WebSocket, eliminating Node.js process overhead.

Each CDPClient instance connects to ONE Chrome tab via its
webSocketDebuggerUrl. No external dependencies beyond stdlib + websocket.

Usage:
    client = CDPClient.connect(port=9222, tab_index=0)
    screenshot_bytes = client.screenshot(format="jpeg", quality=80)
    result = client.evaluate("document.title")
    client.click(100, 200)
    client.press_key("Enter")
    client.close()
"""

import json
import urllib.request
import base64
import threading
import time


class CDPClient:
    """Lightweight CDP client using WebSocket connection to a Chrome tab."""
    
    def __init__(self, ws_url, tab_info=None):
        """
        Initialize with a WebSocket URL to a specific Chrome tab.
        Use CDPClient.connect() factory method instead.
        """
        self._ws_url = ws_url
        self._ws = None
        self._msg_id = 0
        self._lock = threading.Lock()
        self._responses = {}
        self._event_callbacks = {}
        self._closed = False
        self.tab_info = tab_info or {}
        self.url = tab_info.get("url", "") if tab_info else ""
        self.title = tab_info.get("title", "") if tab_info else ""
        self._connect_ws()

    def _connect_ws(self):
        """Establish WebSocket connection."""
        import websocket
        self._ws = websocket.create_connection(
            self._ws_url,
            timeout=10,
            enable_multithread=True,
            suppress_origin=True,  # Chrome rejects non-localhost Origin headers with 403
        )
    
    @staticmethod
    def list_tabs(port=9222):
        """List all page tabs on a Chrome instance."""
        try:
            resp = urllib.request.urlopen(
                f"http://localhost:{port}/json",
                timeout=5
            )
            targets = json.loads(resp.read().decode())
            return [t for t in targets if t.get("type") == "page"]
        except Exception as e:
            return []
    
    @staticmethod
    def connect(port=9222, tab_index=0):
        """
        Connect to a Chrome tab by visual index.
        Returns CDPClient instance or raises ConnectionError.
        """
        tabs = CDPClient.list_tabs(port)
        if not tabs:
            raise ConnectionError(f"No tabs found on port {port}")
        if tab_index >= len(tabs):
            raise ConnectionError(
                f"Tab {tab_index} out of range (only {len(tabs)} tabs on port {port})"
            )
        
        tab = tabs[tab_index]
        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            raise ConnectionError(
                f"Tab {tab_index} has no webSocketDebuggerUrl — "
                "is another debugger already attached?"
            )
        
        return CDPClient(ws_url, tab_info=tab)
    
    def _send(self, method, params=None, timeout=15):
        """Send CDP command and wait for response."""
        if self._closed:
            raise ConnectionError("CDPClient is closed")
        
        with self._lock:
            self._msg_id += 1
            msg_id = self._msg_id
        
        msg = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params
        
        try:
            self._ws.send(json.dumps(msg))
        except Exception as e:
            raise ConnectionError(f"WebSocket send failed: {e}")
        
        # Wait for response with matching id
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._ws.settimeout(min(1.0, deadline - time.time()))
                raw = self._ws.recv()
                if not raw:
                    continue
                data = json.loads(raw)
                
                if data.get("id") == msg_id:
                    if "error" in data:
                        err = data["error"]
                        raise RuntimeError(
                            f"CDP error {err.get('code', '?')}: {err.get('message', '?')}"
                        )
                    return data.get("result", {})
                    
                # Not our response — could be an event, discard
            except Exception as e:
                if "timed out" in str(e).lower():
                    continue
                if "CDPClient is closed" in str(e) or "WebSocket" in str(e):
                    raise
                raise
        
        raise TimeoutError(f"CDP command {method} timed out after {timeout}s")
    
    def screenshot(self, format="jpeg", quality=80):
        """
        Capture screenshot of the tab.
        Returns bytes (JPEG or PNG).
        """
        params = {"format": format}
        if format == "jpeg":
            params["quality"] = quality
        
        result = self._send("Page.captureScreenshot", params)
        data_b64 = result.get("data", "")
        return base64.b64decode(data_b64)
    
    def evaluate(self, expression):
        """
        Evaluate JavaScript in the tab's main frame.
        Returns the result value.
        """
        result = self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        
        remote_obj = result.get("result", {})
        if result.get("exceptionDetails"):
            exc = result["exceptionDetails"]
            raise RuntimeError(f"JS Error: {exc.get('text', str(exc))}")
        
        return remote_obj.get("value")
    
    def evaluate_in_frame(self, expression, args=None):
        """
        Evaluate JS with args (like Playwright's page.evaluate(fn, arg)).
        Wraps expression to accept args via IIFE.
        """
        if args is not None:
            # Wrap as IIFE: (expression)(args)
            js = f"({expression})({json.dumps(args)})"
        else:
            js = expression
        return self.evaluate(js)
    
    def call_function_on(self, expression, args=None):
        """
        Call a function expression with arguments.
        Similar to evaluate_in_frame but uses Runtime.callFunctionOn.
        """
        params = {
            "functionDeclaration": expression,
            "returnByValue": True,
        }
        if args is not None:
            params["arguments"] = [{"value": args}]
        
        # Need a global execution context
        result = self._send("Runtime.evaluate", {
            "expression": "this",
            "returnByValue": False
        })
        obj_id = result.get("result", {}).get("objectId")
        if obj_id:
            params["objectId"] = obj_id
        
        result = self._send("Runtime.callFunctionOn", params)
        return result.get("result", {}).get("value")
    
    def click(self, x, y, delay_ms=None):
        """
        Click at (x, y) coordinates using CDP Input events.
        Coordinates are in CSS pixels.
        """
        import random
        
        # mouseMove
        self._send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": x, "y": y,
            "button": "none",
        })
        time.sleep(random.uniform(0.015, 0.03))
        
        # mousePressed
        self._send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x, "y": y,
            "button": "left",
            "clickCount": 1,
        })
        
        if delay_ms:
            time.sleep(delay_ms / 1000)
        else:
            time.sleep(random.uniform(0.04, 0.08))
        
        # mouseReleased
        self._send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x, "y": y,
            "button": "left",
            "clickCount": 1,
        })
    
    def press_key(self, key_str):
        """
        Press a key or key combination.
        Supports: "Enter", "Tab", "Escape", "Control+a", etc.
        """
        # Parse key combination
        parts = key_str.split("+")
        modifiers = 0
        key = parts[-1] if parts else key_str
        
        for mod in parts[:-1]:
            mod_lower = mod.strip().lower()
            if mod_lower in ("ctrl", "control"):
                modifiers |= 2
            elif mod_lower in ("shift",):
                modifiers |= 8
            elif mod_lower in ("alt",):
                modifiers |= 1
            elif mod_lower in ("meta", "cmd"):
                modifiers |= 4
        
        # Map common key names
        key_map = {
            "enter": ("Enter", "\r", 13),
            "tab": ("Tab", "\t", 9),
            "escape": ("Escape", "\x1b", 27),
            "backspace": ("Backspace", "\b", 8),
            "delete": ("Delete", "", 46),
            "arrowup": ("ArrowUp", "", 38),
            "arrowdown": ("ArrowDown", "", 40),
            "arrowleft": ("ArrowLeft", "", 37),
            "arrowright": ("ArrowRight", "", 39),
            "space": (" ", " ", 32),
            "f1": ("F1", "", 112),
            "f2": ("F2", "", 113),
            "f5": ("F5", "", 116),
        }
        
        key_lower = key.strip().lower()
        if key_lower in key_map:
            key_name, text, code = key_map[key_lower]
        else:
            key_name = key
            text = key if len(key) == 1 else ""
            code = ord(key.upper()) if len(key) == 1 else 0
        
        # keyDown
        params = {
            "type": "keyDown",
            "key": key_name,
            "modifiers": modifiers,
            "windowsVirtualKeyCode": code,
        }
        if text:
            params["text"] = text
        self._send("Input.dispatchKeyEvent", params)
        
        time.sleep(0.02)
        
        # keyUp
        self._send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key_name,
            "modifiers": modifiers,
            "windowsVirtualKeyCode": code,
        })
    
    def get_frames(self):
        """Get frame tree. Returns list of frame info dicts."""
        result = self._send("Page.getFrameTree")
        frames = []
        
        def _collect(node):
            frame = node.get("frame", {})
            frames.append(frame)
            for child in node.get("childFrames", []):
                _collect(child)
        
        _collect(result.get("frameTree", {}))
        return frames
    
    def evaluate_in_specific_frame(self, frame_id, expression):
        """Evaluate JS in a specific frame by frameId."""
        # Create isolated world in the frame
        result = self._send("Page.createIsolatedWorld", {
            "frameId": frame_id,
            "worldName": "cdp_eval",
            "grantUniveralAccess": True,
        })
        context_id = result.get("executionContextId")
        if not context_id:
            return self.evaluate(expression)
        
        result = self._send("Runtime.evaluate", {
            "expression": expression,
            "contextId": context_id,
            "returnByValue": True,
        })
        return result.get("result", {}).get("value")
    
    def find_canvas_frame(self):
        """Find the frame that contains a canvas element (game frame)."""
        frames = self.get_frames()
        if not frames:
            return None
        
        # Main frame is always first
        main_frame_id = frames[0].get("id")
        
        for frame in frames:
            frame_id = frame.get("id")
            try:
                has_canvas = self.evaluate_in_specific_frame(
                    frame_id,
                    "document.querySelectorAll('canvas').length > 0"
                )
                if has_canvas:
                    return frame_id
            except:
                continue
        
        return main_frame_id
    
    def reconnect(self):
        """Reconnect the WebSocket (e.g., after page navigation)."""
        try:
            if self._ws:
                self._ws.close()
        except:
            pass
        self._connect_ws()
    
    def is_alive(self):
        """Check if the connection is still alive."""
        try:
            self.evaluate("1")
            return True
        except:
            return False
    
    def close(self):
        """Close the WebSocket connection."""
        self._closed = True
        try:
            if self._ws:
                self._ws.close()
        except:
            pass
        self._ws = None
    
    def __del__(self):
        self.close()
    
    def __repr__(self):
        return f"CDPClient(url={self.url[:60]}, title={self.title[:30]})"
