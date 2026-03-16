"""
Vision — Template detection engine using OpenCV matchTemplate.

Thread-safe detection engine designed for 100+ concurrent account workers.
Each worker calls find_template_direct(path, frame_bytes=...) independently.

Architecture:
  - Template cache: loaded once, shared read-only across all threads
  - Detection: pure function on (template, frame_bytes) — no shared mutable state
  - Position-first search: ROI at saved coords → expand → full frame

Performance:
  - matchTemplate on 1280×720 grayscale: ~10-15ms
  - Position-first hit: ~2-5ms (searches small ROI first)
  - Cache miss (load template): ~1ms disk read
"""
import os
import cv2
import numpy as np
import threading
import logging

logger = logging.getLogger(__name__)

# Search radii for position-first expanding search (pixels)
# 0 = exact position (tight ROI), -1 = full frame
SEARCH_RADII = [0, 50, 100, 200, -1]

# Padding around template for ROI extraction
ROI_PAD_FACTOR = 1.5  # ROI = template_size * factor on each side


class Vision:
    """OpenCV-based template detection engine.

    Thread-safe: template cache uses a lock only on cache miss.
    Detection calls are pure functions on cached data + frame_bytes.
    """

    def __init__(self, pool_workers=None):
        self._cache = {}          # path → {gray, w, h, edges}
        self._cache_lock = threading.Lock()
        self._position_cache = {}  # path → (x, y) last known position
        self._pos_lock = threading.Lock()
        logger.info("[Vision] OpenCV detection engine initialized (matchTemplate + position-first search)")

    # ── Template Cache ─────────────────────────────────────────

    def _get_template(self, template_path):
        """Get cached template data. Thread-safe, loads on first access."""
        # Fast path: already cached (no lock needed for read)
        cached = self._cache.get(template_path)
        if cached is not None:
            return cached

        # Slow path: load and cache (lock only for writes)
        with self._cache_lock:
            # Double-check after acquiring lock
            cached = self._cache.get(template_path)
            if cached is not None:
                return cached

            if not os.path.exists(template_path):
                logger.warning(f"[Vision] Template not found: {template_path}")
                return None

            img = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                logger.warning(f"[Vision] Failed to read template: {template_path}")
                return None

            h, w = img.shape[:2]
            edges = cv2.Canny(img, 50, 150)

            entry = {
                "gray": img,
                "w": w,
                "h": h,
                "edges": edges,
            }
            self._cache[template_path] = entry
            return entry

    def _get_position(self, template_path):
        """Get last known position for this template (for ROI search)."""
        # Check local position cache first
        pos = self._position_cache.get(template_path)
        if pos:
            return pos

        # Fall back to node_features metadata
        try:
            from node_features import get_search_position
            return get_search_position(template_path)
        except Exception:
            return None

    def _update_position(self, template_path, x, y):
        """Update in-memory position cache (fast, no disk I/O)."""
        with self._pos_lock:
            self._position_cache[template_path] = (x, y)

    # ── Core Detection ─────────────────────────────────────────

    def _decode_frame(self, frame_bytes):
        """Decode JPEG/PNG bytes to grayscale numpy array."""
        if frame_bytes is None:
            return None
        arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        return frame

    def _match_in_region(self, frame_gray, template_entry, roi=None, threshold=0.8):
        """Run matchTemplate in a region. Returns (x, y, score) or None.

        Coordinates returned are in full-frame space (not ROI-local).
        """
        tmpl = template_entry["gray"]
        tw, th = template_entry["w"], template_entry["h"]

        if roi:
            x1, y1, x2, y2 = roi
            # Clamp to frame bounds
            fh, fw = frame_gray.shape[:2]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(fw, x2)
            y2 = min(fh, y2)

            # ROI must be at least as large as template
            if (x2 - x1) < tw or (y2 - y1) < th:
                return None

            search_region = frame_gray[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1
        else:
            search_region = frame_gray
            offset_x, offset_y = 0, 0
            fh, fw = frame_gray.shape[:2]
            if fw < tw or fh < th:
                return None

        # matchTemplate
        result = cv2.matchTemplate(search_region, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            # Convert to full-frame center coordinates
            cx = offset_x + max_loc[0] + tw // 2
            cy = offset_y + max_loc[1] + th // 2
            return (cx, cy, float(max_val))

        return None

    def _detect(self, frame_gray, template_path, template_entry, threshold=0.8):
        """Position-first expanding search.

        1. Search at last known position (tight ROI)
        2. Expand outward: +50px, +100px, +200px
        3. Full frame scan
        """
        tw, th = template_entry["w"], template_entry["h"]
        fh, fw = frame_gray.shape[:2]
        position = self._get_position(template_path)

        for radius in SEARCH_RADII:
            if radius == -1:
                # Full frame scan
                result = self._match_in_region(frame_gray, template_entry,
                                                roi=None, threshold=threshold)
            elif position:
                cx, cy = position
                # Build ROI around known position + radius
                pad_x = int(tw * ROI_PAD_FACTOR) + radius
                pad_y = int(th * ROI_PAD_FACTOR) + radius
                roi = (cx - pad_x, cy - pad_y, cx + pad_x, cy + pad_y)
                result = self._match_in_region(frame_gray, template_entry,
                                                roi=roi, threshold=threshold)
            else:
                # No known position and radius != -1 → skip to full scan
                continue

            if result:
                # Update position cache for next detection
                self._update_position(template_path, result[0], result[1])
                return result

        return None

    # ── Public API ─────────────────────────────────────────────

    def find_template_on_screen(self, template_path, threshold=0.8,
                                debug=False, region=None,
                                frame_bytes=None, write_debug=False):
        """Find template in screenshot. Used by single-tab workflows.

        Args:
            template_path: path to template image
            threshold: match confidence threshold (0.0-1.0)
            debug: if True, returns (result, [debug_lines])
            region: (x1, y1, x2, y2) restrict search area
            frame_bytes: pre-captured screenshot bytes (JPEG/PNG)
            write_debug: unused (backward compat)

        Returns:
            (x, y, score) or None
            If debug=True: ((x,y,score)|None, [debug_lines])
        """
        debug_lines = []

        # Load template
        tmpl = self._get_template(template_path)
        if tmpl is None:
            if debug:
                return None, ["[Vision] Template file not found or unreadable"]
            return None

        # Decode frame
        if frame_bytes:
            frame_gray = self._decode_frame(frame_bytes)
        else:
            # Fallback: capture screen via mss
            try:
                import mss
                with mss.mss() as sct:
                    monitor = sct.monitors[1]  # primary monitor
                    screenshot = sct.grab(monitor)
                    img = np.array(screenshot)
                    frame_gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
            except Exception as e:
                if debug:
                    return None, [f"[Vision] Screen capture failed: {e}"]
                return None

        if frame_gray is None:
            if debug:
                return None, ["[Vision] Failed to decode frame"]
            return None

        fh, fw = frame_gray.shape[:2]
        if debug:
            debug_lines.append(f"[Vision] Frame: {fw}×{fh}, Template: {tmpl['w']}×{tmpl['h']}")

        # Apply region constraint if specified
        if region:
            rx1, ry1, rx2, ry2 = region
            rx1, ry1 = max(0, rx1), max(0, ry1)
            rx2, ry2 = min(fw, rx2), min(fh, ry2)
            if (rx2 - rx1) >= tmpl['w'] and (ry2 - ry1) >= tmpl['h']:
                frame_gray = frame_gray[ry1:ry2, rx1:rx2]
                region_offset = (rx1, ry1)
                if debug:
                    debug_lines.append(f"[Vision] Region: ({rx1},{ry1})-({rx2},{ry2})")
            else:
                region_offset = (0, 0)
        else:
            region_offset = (0, 0)

        # Detect
        position = self._get_position(template_path)
        if debug and position:
            debug_lines.append(f"[Vision] Position hint: ({position[0]},{position[1]})")

        result = self._detect(frame_gray, template_path, tmpl, threshold)

        if result and region_offset != (0, 0):
            # Adjust coordinates back to full frame
            result = (result[0] + region_offset[0],
                      result[1] + region_offset[1],
                      result[2])

        if debug:
            if result:
                debug_lines.append(f"[Vision] Found at ({result[0]},{result[1]}) score={result[2]:.3f}")
            else:
                debug_lines.append(f"[Vision] Not found (threshold={threshold:.2f})")
            return result, debug_lines

        return result

    def find_template_direct(self, template_path, threshold=0.8,
                             debug=False, region=None,
                             frame_bytes=None, fast_mode=False,
                             _prepared_frame=None):
        """Find template in provided frame bytes. Hot path for multi-account.

        Designed for high concurrency: no global state mutation, no disk I/O
        (after initial template cache), no screen capture.

        Args:
            template_path: path to template image
            threshold: match confidence threshold
            debug: unused for direct path
            region: (x1, y1, x2, y2) restrict search
            frame_bytes: screenshot bytes (required for multi-account)
            fast_mode: if True, skip expanding search — do ROI + full only
            _prepared_frame: pre-decoded grayscale frame (from prepare_frame)

        Returns:
            (x, y, score) or None
        """
        # Load template (cache hit = no lock, no I/O)
        tmpl = self._get_template(template_path)
        if tmpl is None:
            return None

        # Decode frame
        if _prepared_frame is not None:
            frame_gray = _prepared_frame
        elif frame_bytes is not None:
            frame_gray = self._decode_frame(frame_bytes)
        else:
            return None

        if frame_gray is None:
            return None

        # Apply region constraint
        region_offset = (0, 0)
        if region:
            rx1, ry1, rx2, ry2 = region
            fh, fw = frame_gray.shape[:2]
            rx1, ry1 = max(0, rx1), max(0, ry1)
            rx2, ry2 = min(fw, rx2), min(fh, ry2)
            if (rx2 - rx1) >= tmpl['w'] and (ry2 - ry1) >= tmpl['h']:
                frame_gray = frame_gray[ry1:ry2, rx1:rx2]
                region_offset = (rx1, ry1)

        if fast_mode:
            # Fast mode: ROI at known position → full frame (skip expanding)
            result = self._detect_fast(frame_gray, template_path, tmpl, threshold)
        else:
            result = self._detect(frame_gray, template_path, tmpl, threshold)

        if result and region_offset != (0, 0):
            result = (result[0] + region_offset[0],
                      result[1] + region_offset[1],
                      result[2])

        return result

    def _detect_fast(self, frame_gray, template_path, template_entry, threshold):
        """Fast detection: position ROI → full frame (2 passes only)."""
        tw, th = template_entry["w"], template_entry["h"]
        position = self._get_position(template_path)

        # Pass 1: ROI at known position
        if position:
            cx, cy = position
            pad_x = int(tw * ROI_PAD_FACTOR) + 50
            pad_y = int(th * ROI_PAD_FACTOR) + 50
            roi = (cx - pad_x, cy - pad_y, cx + pad_x, cy + pad_y)
            result = self._match_in_region(frame_gray, template_entry,
                                            roi=roi, threshold=threshold)
            if result:
                self._update_position(template_path, result[0], result[1])
                return result

        # Pass 2: full frame
        result = self._match_in_region(frame_gray, template_entry,
                                        roi=None, threshold=threshold)
        if result:
            self._update_position(template_path, result[0], result[1])
        return result

    def find_text_on_screen(self, search_text, frame_bytes=None,
                            region=None, lang='eng'):
        """Find text on screen via OCR. Currently a stub.

        Returns:
            (x, y, score) or None
        """
        # OCR implementation deferred
        return None

    # ── Utilities ──────────────────────────────────────────────

    def refresh_template(self, template_path):
        """Evict template from cache (e.g. after re-capture)."""
        with self._cache_lock:
            self._cache.pop(template_path, None)
        with self._pos_lock:
            self._position_cache.pop(template_path, None)

    def refresh_features(self, template_path):
        """Same as refresh_template (backward compat)."""
        self.refresh_template(template_path)

    @staticmethod
    def prepare_frame(frame_bytes):
        """Pre-decode frame bytes to grayscale numpy array.

        Useful when multiple templates need to be searched in the same frame:
            prepared = Vision.prepare_frame(frame_bytes)
            result1 = vision.find_template_direct(tmpl1, _prepared_frame=prepared)
            result2 = vision.find_template_direct(tmpl2, _prepared_frame=prepared)
        """
        if frame_bytes is None:
            return None
        arr = np.frombuffer(frame_bytes, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)

    def shutdown_pool(self):
        """Cleanup resources."""
        with self._cache_lock:
            self._cache.clear()
        with self._pos_lock:
            self._position_cache.clear()
        logger.info("[Vision] Engine shut down, caches cleared")
