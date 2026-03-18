"""
Graph Engine — Flowchart execution engine.

Extracted from tab_loops._loop_engine_worker() and
tab_accounts._account_worker_thread() to eliminate duplication.

Implements the Start → Macro → Delay → Condition → Click → End
node traversal logic that was previously duplicated across both files.
"""
import time
import os
import logging

from macro_runner import run_macro
from node_features import get_color_detect

logger = logging.getLogger(__name__)


class GraphEngine:
    """
    Executes a flowchart graph node-by-node.

    Args:
        graph:          dict with "nodes" and "edges"
        vision:         Vision instance for template matching
        tracked_icons:  dict mapping node_name -> image path
        combos:         dict mapping macro_name -> macro_data
        bot_instance:   BotAction instance for clicking
        cdp_client:     CDPClient (or None for screen capture)
        threshold_fn:   callable() -> float, returns current threshold
        log_fn:         callable(str) for log output
        status_fn:      callable(str, str) for UI status updates (msg, color)
        is_running_fn:  callable() -> bool, checked each iteration
        highlight_fn:   callable(str) to highlight active node on UI
        use_direct_vision: if True, uses find_template_direct
    """

    def __init__(self, graph, vision, tracked_icons, combos,
                 bot_instance, cdp_client=None,
                 threshold_fn=None, log_fn=None, status_fn=None,
                 is_running_fn=None, highlight_fn=None,
                 use_direct_vision=False):
        self.nodes = graph.get("nodes", {})
        self.edges = graph.get("edges", [])
        self.vision = vision
        self.tracked_icons = tracked_icons
        self.combos = combos
        self.bot_instance = bot_instance
        self.cdp_client = cdp_client
        self.threshold_fn = threshold_fn or (lambda: 0.54)
        self.log_fn = log_fn or logger.info
        self.status_fn = status_fn or (lambda msg, color: None)
        self.is_running_fn = is_running_fn or (lambda: True)
        self.highlight_fn = highlight_fn or (lambda nid: None)
        self.use_direct_vision = use_direct_vision

    def get_start_node(self):
        """Find the Start node ID."""
        for nid, n in self.nodes.items():
            if n.get("type") == "Start":
                return nid
        return None

    def get_next_node(self, node_id, pin_name):
        """Follow an edge from node_id's pin_name to the target node."""
        for e in self.edges:
            if e["from"] == node_id and e["from_pin"] == pin_name:
                return e["to"]
        return None

    def _capture_frame(self):
        """Take a screenshot via CDP."""
        if not self.cdp_client:
            return None
        try:
            return self.cdp_client.screenshot(quality=70)
        except Exception:
            return None

    def run(self, start_node_id=None):
        """
        Execute the graph from the start node until End or stop signal.

        Args:
            start_node_id: override start node (default: auto-detect Start node)

        Returns:
            "ended"   – reached End node
            "stopped" – is_running_fn returned False
            "error"   – start node missing or fatal error
        """
        current = start_node_id or self.get_start_node()
        if not current:
            self.log_fn("[FLOWCHART] ERROR: No Start node found.")
            return "error"

        while self.is_running_fn():
            if not current or current not in self.nodes:
                self.log_fn("[FLOWCHART] End of path reached. Restarting from Start in 1s...")
                time.sleep(1.0)
                current = start_node_id or self.get_start_node()
                continue

            n = self.nodes[current]
            ntype = n["type"]
            ndata = n.get("data", {})
            threshold_val = self.threshold_fn()

            self.highlight_fn(current)

            if ntype == "Start":
                self.status_fn("START → Following entry path", "success")
                self.log_fn("[FLOWCHART] ---> START")
                current = self.get_next_node(current, "out")
                time.sleep(0.5)

            elif ntype == "Macro":
                current = self._exec_macro(current, ndata, threshold_val)

            elif ntype == "Delay":
                current = self._exec_delay(current, ndata)

            elif ntype == "Condition":
                current = self._exec_condition(current, ndata, threshold_val)

            elif ntype == "Click":
                current = self._exec_click(current, ndata, threshold_val)

            elif ntype == "End":
                self.status_fn("END — Loop finished", "success")
                self.log_fn("[FLOWCHART] Reached END node.")
                return "ended"

        return "stopped"

    # ── Node handlers ─────────────────────────────────────────────

    def _exec_macro(self, node_id, ndata, threshold_val):
        mac_name = ndata.get("macro_name")
        if not mac_name or mac_name not in self.combos:
            self.status_fn(f"Macro [{mac_name}] → INVALID", "danger")
            self.log_fn(f"[FLOWCHART] Warning: Invalid Macro '{mac_name}'.")
            return self.get_next_node(node_id, "false")

        self.status_fn(f"Running Macro: {mac_name}", "accent")
        self.log_fn(f"[FLOWCHART] Executing Macro: {mac_name}")

        macro_data = self.combos[mac_name]
        result = run_macro(
            macro_data, self.bot_instance, self.vision,
            self.tracked_icons, threshold_val,
            cdp_client=self.cdp_client,
            log_fn=self.log_fn,
            is_running_fn=self.is_running_fn,
            use_direct_vision=self.use_direct_vision,
        )
        if result:
            self.status_fn(f"Macro [{mac_name}] → OK", "success")
            self.log_fn("[FLOWCHART] -> Macro OK. Following success path.")
            return self.get_next_node(node_id, "true")
        else:
            self.status_fn(f"Macro [{mac_name}] → FAILED", "danger")
            self.log_fn("[FLOWCHART] -> Macro FAILED. Following failure path.")
            return self.get_next_node(node_id, "false")

    def _exec_delay(self, node_id, ndata):
        delay_ms = float(ndata.get("time", 1000))
        delay_sec = delay_ms / 1000.0
        self.status_fn(f"Waiting {delay_ms:.0f}ms...", "warning")
        self.log_fn(f"[FLOWCHART] Waiting {delay_ms:.0f}ms ({delay_sec:.1f}s)...")

        steps = int(delay_sec * 10)
        for i in range(steps):
            if not self.is_running_fn():
                break
            if i % 10 == 0:
                remaining_ms = delay_ms - (i * 100)
                self.status_fn(f"Delay: {remaining_ms:.0f}ms remaining", "warning")
            time.sleep(0.1)

        return self.get_next_node(node_id, "out")

    def _exec_condition(self, node_id, ndata, threshold_val):
        img_name = ndata.get("image_name")
        filepath = self.tracked_icons.get(img_name)

        if not filepath or not os.path.exists(filepath):
            self.status_fn(f"Condition [{img_name}] → NOT FOUND", "danger")
            self.log_fn(f"[FLOWCHART] Image condition '{img_name}' not found. Defaulting to False.")
            time.sleep(0.5)
            return self.get_next_node(node_id, "false")

        self.status_fn(f"Checking: {img_name}...", "warning")
        self.log_fn(f"[FLOWCHART] Checking: Is '{img_name}' on screen?")

        found = False
        use_color = get_color_detect(filepath) if filepath else False
        for _ in range(3):
            frame_bytes = self._capture_frame()
            res = self.vision.find_template_on_screen(
                filepath, threshold=threshold_val,
                debug=False, frame_bytes=frame_bytes,
                use_color=use_color,
            )
            if res:
                found = True
                break
            time.sleep(0.5)

        if found:
            self.status_fn(f"Condition [{img_name}] → TRUE", "success")
            self.log_fn(f"[FLOWCHART] -> TRUE (Found '{img_name}')")
            time.sleep(0.5)
            return self.get_next_node(node_id, "true")
        else:
            self.status_fn(f"Condition [{img_name}] → FALSE", "danger")
            self.log_fn(f"[FLOWCHART] -> FALSE (Not Found)")
            time.sleep(0.5)
            return self.get_next_node(node_id, "false")

    def _exec_click(self, node_id, ndata, threshold_val):
        import random

        img_name = ndata.get("image_name")
        filepath = self.tracked_icons.get(img_name)

        if not filepath or not os.path.exists(filepath):
            self.status_fn(f"Click [{img_name}] → NOT FOUND", "danger")
            self.log_fn(f"[FLOWCHART] Click target '{img_name}' image not found. Skipping.")
        elif ndata.get("hard_click"):
            # ── HARD CLICK: skip detection, click at learned position ──
            from node_features import get_click_zone
            zone = get_click_zone(filepath)
            if zone:
                cx, cy, w, h = zone
                rx = cx + random.randint(-w * 35 // 100, w * 35 // 100)
                ry = cy + random.randint(-h * 35 // 100, h * 35 // 100)
                self.bot_instance.click_at(rx, ry, randomize=False)
                self.status_fn(f"⚡ Click [{img_name}] → OK", "success")
                self.log_fn(f"[FLOWCHART] ⚡ Hard Click '{img_name}' at ({rx},{ry})")
            else:
                # No learned position yet — fall back to detection
                self.log_fn(f"[FLOWCHART] ⚡ Hard Click: No learned position for '{img_name}'. Falling back to detection.")
                self._click_by_detection(img_name, filepath, threshold_val)
        else:
            # ── Normal detect-then-click ──
            self._click_by_detection(img_name, filepath, threshold_val)

        time.sleep(0.3)
        return self.get_next_node(node_id, "out")

    def _click_by_detection(self, img_name, filepath, threshold_val):
        """Detect image on screen and click at found position."""
        self.status_fn(f"Clicking: {img_name}...", "warning")
        self.log_fn(f"[FLOWCHART] Looking for '{img_name}' to click...")

        use_color = get_color_detect(filepath)
        frame_bytes = self._capture_frame()
        res = self.vision.find_template_on_screen(
            filepath, threshold=threshold_val,
            debug=False, frame_bytes=frame_bytes,
            use_color=use_color,
        )

        if res:
            cx, cy = res[0], res[1]
            self.log_fn(f"[FLOWCHART] Found '{img_name}' at ({cx}, {cy}). Clicking...")
            self.bot_instance.click_at(cx, cy)
            self.status_fn(f"Click [{img_name}] → OK", "success")
            self.log_fn(f"[FLOWCHART] Clicked '{img_name}'")
            # Update learned position for future hard clicks
            try:
                from node_features import update_learned_position
                update_learned_position(filepath, cx, cy, res[2])
            except Exception:
                pass
        else:
            self.status_fn(f"Click [{img_name}] → NOT VISIBLE", "warning")
            self.log_fn(f"[FLOWCHART] '{img_name}' not on screen. Skipping click.")
