"""
Vision — Template matching engine.

STUB: Detection logic has been removed for a complete rewrite.
All methods return None (no match) to keep the app running.

API contract (for callers):
    find_template_on_screen(path, threshold, ...) → (x, y, score) | None
    find_template_direct(path, threshold, ...)    → (x, y, score) | None
    find_text_on_screen(text, frame_bytes, ...)   → (x, y, conf)  | None
"""
import logging

logger = logging.getLogger(__name__)


class Vision:
    def __init__(self, pool_workers=None):
        logger.info("[Vision] Stub loaded — detection disabled, awaiting reimplementation.")

    def find_template_on_screen(self, template_path, threshold=0.8,
                                debug=False, region=None,
                                frame_bytes=None, write_debug=False):
        """Template matching — TODO: reimplement."""
        return None

    def find_template_direct(self, template_path, threshold=0.8,
                             debug=False, region=None,
                             frame_bytes=None, fast_mode=False):
        """Direct template matching (no pool) — TODO: reimplement."""
        return None

    def find_text_on_screen(self, search_text, frame_bytes=None,
                            region=None, lang='eng'):
        """OCR text detection — TODO: reimplement."""
        return None

    def shutdown_pool(self):
        """Cleanup — no-op in stub."""
        pass
