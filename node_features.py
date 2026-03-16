"""
Node Features — Precompute template features for detection.

STUB: Feature precomputation has been removed alongside the detection engine.
All functions are no-ops to keep the app running.
"""
import os


def precompute_features(template_path):
    """Precompute detection features — TODO: reimplement."""
    return True


def load_features(template_path):
    """Load precomputed features — TODO: reimplement."""
    return None


def batch_precompute(trackers_dir="trackers"):
    """Batch precompute all templates — TODO: reimplement."""
    return (0, 0, 0)


def get_feature_status(trackers_dir="trackers"):
    """Get learning status for all templates — returns stub status."""
    status = []
    if not os.path.exists(trackers_dir):
        return status
    for filename in sorted(os.listdir(trackers_dir)):
        if filename.endswith(".png"):
            name = filename[:-4]
            status.append((name, False, False))
    return status
