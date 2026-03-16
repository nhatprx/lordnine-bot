"""
Node Features — Meta storage and position tracking for nodes.

Storage format:
  trackers/Home.png              ← template image
  trackers/Home.meta.json        ← position, stats
"""
import os
import json
import logging
import threading

logger = logging.getLogger(__name__)

# Lock for meta.json writes
_meta_lock = threading.Lock()


# ── Meta JSON ─────────────────────────────────────────────────


def _meta_path(template_path):
    """Get .meta.json path for a template."""
    base, _ = os.path.splitext(template_path)
    return base + ".meta.json"


def load_meta(template_path):
    """Load metadata for a template. Returns dict or empty dict."""
    path = _meta_path(template_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_meta(template_path, meta):
    """Save metadata for a template. Thread-safe."""
    path = _meta_path(template_path)
    with _meta_lock:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save meta {path}: {e}")


def save_capture_position(template_path, x, y, frame_w, frame_h):
    """Save the capture position after a user capture."""
    meta = load_meta(template_path)
    meta["capture_position"] = {"x": int(x), "y": int(y)}
    meta["capture_resolution"] = [int(frame_w), int(frame_h)]
    save_meta(template_path, meta)


def update_learned_position(template_path, x, y, score):
    """Update learned position via EMA after high-confidence detection."""
    meta = load_meta(template_path)
    lp = meta.get("learned_position")

    if lp is None:
        meta["learned_position"] = {
            "x": int(x), "y": int(y),
            "score": float(score), "count": 1
        }
    else:
        count = lp.get("count", 1)
        alpha = min(0.3, 2.0 / (count + 1))
        lp["x"] = int(lp["x"] * (1 - alpha) + x * alpha)
        lp["y"] = int(lp["y"] * (1 - alpha) + y * alpha)
        lp["score"] = float(lp["score"] * (1 - alpha) + score * alpha)
        lp["count"] = count + 1

    meta["total_detections"] = meta.get("total_detections", 0) + 1
    save_meta(template_path, meta)


def reset_learned_position(template_path, x, y, score):
    """Replace learned_position entirely with fresh detection coordinates.

    Unlike update_learned_position (EMA), this RESETS the position
    to exact coordinates. Use when the user explicitly tests/confirms
    a position (e.g. Test Node), so stale data is wiped out.

    x, y must be in CDP screenshot pixel space.
    """
    meta = load_meta(template_path)
    meta["learned_position"] = {
        "x": int(x), "y": int(y),
        "score": float(score), "count": 3
    }
    meta["total_detections"] = meta.get("total_detections", 0) + 1
    save_meta(template_path, meta)


def save_hard_click_position(template_path, x, y, frame_w=0, frame_h=0):
    """Save the hard click position (CDP screenshot pixel space).

    This is set once at capture/snip time by template-matching the
    snipped image against a CDP screenshot. Hard click uses ONLY this.
    """
    meta = load_meta(template_path)
    meta["hard_click_position"] = {
        "x": int(x), "y": int(y)
    }
    if frame_w and frame_h:
        meta["hard_click_resolution"] = [int(frame_w), int(frame_h)]
    save_meta(template_path, meta)


def get_search_position(template_path):
    """
    Get best known position for position-first search.
    Returns (x, y) or None. Priority: learned > capture.
    """
    meta = load_meta(template_path)
    lp = meta.get("learned_position")
    if lp and lp.get("count", 0) >= 3:
        return (lp["x"], lp["y"])
    cp = meta.get("capture_position")
    if cp:
        return (cp["x"], cp["y"])
    return None


# ── Stubs (for backward compatibility) ────────────────────────


def get_click_zone(template_path):
    """
    Get click zone for hard click: (cx, cy, w, h).
    Returns tuple or None if no suitable position exists.

    Uses ONLY `hard_click_position` — set at capture time by matching
    the snipped template against a CDP screenshot.
    This is independent from the detection pipeline.
    """
    meta = load_meta(template_path)
    hcp = meta.get("hard_click_position")
    if not hcp:
        return None
    cx, cy = hcp["x"], hcp["y"]
    try:
        from PIL import Image as _PILImage
        img = _PILImage.open(template_path)
        w, h = img.size
        return (cx, cy, w, h)
    except Exception:
        return None


def precompute_features(template_path):
    """Stub — no feature extraction."""
    return True


def load_features(template_path):
    """Stub — no features."""
    return None


def batch_precompute(trackers_dir="trackers"):
    """Stub — no batch feature extraction."""
    return 0, 0, 0


def extract_and_store_features(template_path):
    """Stub — no feature extraction."""
    return True


def add_variant(template_path, variant_image, screen_x=0, screen_y=0,
                frame_w=0, frame_h=0):
    """Stub — no variant support."""
    return None


def get_variant_count(template_path):
    """Stub — returns 0."""
    return 0


def add_negative_sample(template_path, frame_bytes, cx, cy):
    """Stub — no negative samples."""
    return False


def get_negative_count(template_path):
    """Stub — returns 0."""
    return 0
