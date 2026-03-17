"""
Macro Runner — Standalone macro step execution engine.

Extracted from tab_loops.py to eliminate code duplication between
the single-tab loop engine and the multi-account coordinator.

Both `tab_loops._loop_engine_worker()` and `tab_accounts._account_worker_thread()`
now import and call `run_macro()` instead of maintaining separate copies.
"""
import time
import os
import random
import logging

from node_features import get_color_detect

logger = logging.getLogger(__name__)


def _capture_frame(cdp_client, screenshot_fn=None):
    """Take a screenshot via CDP or ScreenshotScheduler.
    
    Args:
        cdp_client: CDPClient instance (fallback)
        screenshot_fn: callable() → bytes, from ScreenshotScheduler
    
    Returns bytes or None.
    """
    try:
        if screenshot_fn:
            return screenshot_fn()
        if cdp_client:
            return cdp_client.screenshot(quality=70)
    except Exception:
        pass
    return None


def run_macro(macro_data, bot_instance, vision, tracked_icons,
              threshold_val=0.54, cdp_client=None,
              log_fn=None, is_running_fn=None,
              use_direct_vision=False, screenshot_fn=None):
    """
    Execute a macro's step list.

    Args:
        macro_data:       dict with "steps", "success_capture", "failure_capture"
        bot_instance:     BotAction instance for clicking
        vision:           Vision instance for template matching
        tracked_icons:    dict mapping node_name -> image file path
        threshold_val:    matching threshold (0.0 – 1.0)
        cdp_client:       CDPClient for screenshots (fallback if no screenshot_fn)
        log_fn:           callable(str) for logging, defaults to logger.info
        is_running_fn:    callable() -> bool, checked before each step
        use_direct_vision: if True, uses find_template_direct (multi-account)
        screenshot_fn:    callable() -> bytes from ScreenshotScheduler.
                          Preferred for multi-account; falls back to cdp_client.

    Returns:
        True if macro succeeded, False otherwise.
    """
    if log_fn is None:
        log_fn = logger.info

    if is_running_fn is None:
        is_running_fn = lambda: True

    steps = macro_data.get("steps", [])

    def _find(path, threshold, frame_bytes=None, use_color=False):
        if use_direct_vision:
            return vision.find_template_direct(
                path, threshold=threshold, debug=False,
                frame_bytes=frame_bytes, fast_mode=True,
                use_color=use_color,
            )
        return vision.find_template_on_screen(
            path, threshold=threshold, debug=False,
            frame_bytes=frame_bytes, use_color=use_color,
        )

    for idx, step_data in enumerate(steps):
        if not is_running_fn():
            log_fn(f"[Macro] Stopped at step {idx+1}/{len(steps)} (worker stopped)")
            return False

        if isinstance(step_data, str):
            step_data = {"node": step_data}

        step_type = step_data.get("type", "click")

        # ── DELAY step (interruptible) ──────────────────────────
        if step_type == "delay":
            delay_ms = float(step_data.get("time", 1000))
            delay_sec = delay_ms / 1000.0
            log_fn(f"[Macro] ({idx+1}/{len(steps)}) Delay: {delay_ms:.0f}ms ({delay_sec:.1f}s)...")
            chunks = int(delay_sec * 10)
            for _ in range(max(1, chunks)):
                if not is_running_fn():
                    return False
                time.sleep(0.1)
            log_fn("[Macro] Delay completed.")
            continue

        # ── MARKER step (wait for image appear/disappear) ───────
        if step_type == "marker":
            ok = _run_marker_step(
                step_data, idx, len(steps),
                tracked_icons, threshold_val,
                cdp_client, _find, log_fn, is_running_fn,
                screenshot_fn=screenshot_fn,
            )
            if not ok:
                return False
            continue

        # ── CLICK step (find + click) ───────────────────────────
        node_name = step_data.get("node", "")
        if not node_name:
            continue

        filepath = tracked_icons.get(node_name)
        if not filepath or not os.path.exists(filepath):
            log_fn(f"    - Step FAILED: Node '{node_name}' image file missing.")
            return False

        # ── HARD CLICK: skip detection, click at saved coordinates ──
        if step_data.get("hard_click"):
            from node_features import get_click_zone
            zone = get_click_zone(filepath)
            if zone:
                cx, cy, w, h = zone
                rx = cx + random.randint(-w * 35 // 100, w * 35 // 100)
                ry = cy + random.randint(-h * 35 // 100, h * 35 // 100)
                bot_instance.click_at(rx, ry, randomize=False)
                log_fn(f"    - Step OK: ⚡ Hard Click '{node_name}' at ({rx},{ry})")
                time.sleep(random.uniform(0.3, 0.5))
                continue
            else:
                log_fn(f"    - ⚡ Hard Click: No learned position yet (need ≥3 detections). Falling back to detection.")

        # ── Normal detect-then-click ──
        found = False
        for attempt in range(5):
            frame_bytes = _capture_frame(cdp_client, screenshot_fn)
            try:
                res = _find(filepath, threshold_val, frame_bytes=frame_bytes,
                            use_color=get_color_detect(filepath))
            finally:
                # Explicit cleanup — 37 accounts × 100-200KB per frame
                if not res:
                    del frame_bytes
            if res:
                x, y, _ = res
                bot_instance.click_at(x, y, randomize=True)
                log_fn(f"    - Step OK: Clicked '{node_name}'")
                found = True
                # Update learned position for future hard clicks
                try:
                    from node_features import update_learned_position
                    update_learned_position(filepath, x, y, _)
                except Exception:
                    pass
                time.sleep(random.uniform(0.3, 0.5))
                break
            time.sleep(0.3)

        if not found:
            log_fn(f"    - Step FAILED: Could not find '{node_name}' after 5 attempts.")
            return False

    log_fn("[Macro] Steps completed. Checking result...")

    # ── Result verification via success/failure capture ─────────
    return _verify_result(
        macro_data, tracked_icons, threshold_val,
        cdp_client, _find, log_fn,
        screenshot_fn=screenshot_fn,
    )


def _run_marker_step(step_data, idx, total,
                     tracked_icons, threshold_val,
                     cdp_client, _find, log_fn, is_running_fn,
                     screenshot_fn=None):
    """Execute a single marker (wait-for-image) step. Returns True on success."""
    marker = step_data.get("marker", "")
    marker_mode = step_data.get("mode", "Wait until Appear")

    try:
        marker_time = float(step_data.get("time", "0")) / 1000.0
    except (ValueError, TypeError):
        marker_time = 0
    try:
        marker_timeout = float(step_data.get("timeout", "0")) / 1000.0
    except (ValueError, TypeError):
        marker_timeout = 0

    fail_image = step_data.get("fail_image", "None")
    mode_str = "APPEAR" if marker_mode == "Wait until Appear" else "DISAPPEAR"
    timeout_str = f", timeout {marker_timeout:.0f}s" if marker_timeout > 0 else ""

    log_fn(
        f"[Macro] ({idx+1}/{total}) Waiting: '{marker}' to {mode_str} "
        f"(hold {marker_time:.1f}s{timeout_str})..."
    )

    marker_path = tracked_icons.get(marker)
    if not marker_path or not os.path.exists(marker_path):
        log_fn(f"    - Step FAILED: Marker '{marker}' image missing.")
        return False

    fail_path = None
    if fail_image and fail_image != "None":
        fail_path = tracked_icons.get(fail_image)

    hold_start = None
    last_log_time = 0
    start_time = time.time()

    while True:
        # Timeout check
        if marker_timeout > 0 and (time.time() - start_time) > marker_timeout:
            log_fn(f"    - Marker TIMEOUT ({marker_timeout:.0f}s): '{marker}'. Macro FAILED.")
            return False

        if not is_running_fn():
            return False

        frame_bytes = _capture_frame(cdp_client, screenshot_fn)

        # CRITICAL: If screenshot failed, do NOT evaluate condition.
        # A None frame causes _find() to return None, which in
        # "Wait until Disappear" mode is falsely treated as "disappeared".
        if frame_bytes is None:
            time.sleep(0.5)
            continue

        # Fail image check
        if fail_path and os.path.exists(fail_path):
            fail_res = _find(fail_path, threshold_val, frame_bytes=frame_bytes,
                             use_color=get_color_detect(fail_path))
            fail_mode = step_data.get("fail_mode", "Fail if Appear")
            fail_triggered = (
                (fail_mode == "Fail if Appear" and fail_res)
                or (fail_mode == "Fail if Disappear" and not fail_res)
            )
            if fail_triggered:
                log_fn(f"    - CANCEL: Fail image '{fail_image}' ({fail_mode})! Macro FAILED.")
                return False

        res = _find(marker_path, threshold_val, frame_bytes=frame_bytes,
                    use_color=get_color_detect(marker_path))
        is_condition_met = (
            (marker_mode == "Wait until Appear" and res)
            or (marker_mode == "Wait until Disappear" and not res)
        )

        if is_condition_met:
            if hold_start is None:
                hold_start = time.time()
                if marker_time > 0:
                    log_fn(f"    - Marker triggered. Holding {marker_time:.1f}s...")
            elapsed = time.time() - hold_start
            current_sec = int(elapsed)
            if marker_time > 0 and current_sec > last_log_time + 2:
                log_fn(f"    - Holding... {current_sec}/{marker_time:.0f}s")
                last_log_time = current_sec
            if elapsed >= marker_time:
                log_fn(f"    - Marker OK: '{marker}' confirmed {mode_str}.")
                return True
        else:
            if hold_start is not None:
                log_fn("    - Marker interrupted. Resetting hold timer.")
                hold_start = None
                last_log_time = 0

        time.sleep(random.uniform(0.3, 1.2))  # Jitter to stagger multi-account polling


def _verify_result(macro_data, tracked_icons, threshold_val,
                   cdp_client, _find, log_fn,
                   screenshot_fn=None):
    """Verify macro result via success/failure capture images."""
    success_capture = macro_data.get("success_capture", "None")
    failure_capture = macro_data.get("failure_capture", "None")

    if success_capture == "None" and failure_capture == "None":
        log_fn("[Macro] Finished (no capture check configured).")
        return True

    time.sleep(1.0)
    frame_bytes = _capture_frame(cdp_client, screenshot_fn)

    if success_capture != "None":
        s_path = tracked_icons.get(success_capture)
        if s_path and os.path.exists(s_path):
            res = _find(s_path, threshold_val, frame_bytes=frame_bytes,
                        use_color=get_color_detect(s_path))
            if res:
                log_fn(f"[Macro] Result: SUCCESS (found '{success_capture}')")
                return True
            else:
                log_fn(f"[Macro] Result: FAILURE ('{success_capture}' not found)")
                return False

    if failure_capture != "None":
        f_path = tracked_icons.get(failure_capture)
        if f_path and os.path.exists(f_path):
            res = _find(f_path, threshold_val, frame_bytes=frame_bytes,
                        use_color=get_color_detect(f_path))
            if res:
                log_fn(f"[Macro] Result: FAILURE (found '{failure_capture}')")
                return False
            else:
                log_fn(f"[Macro] Result: SUCCESS ('{failure_capture}' not found)")
                return True

    log_fn("[Macro] Finished (capture images not available).")
    return True
