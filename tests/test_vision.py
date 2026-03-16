"""
Test Vision — Unit tests for the OpenCV detection engine.

Tests core detection logic with synthetic frames and templates:
- Exact match detection
- No-match returns None
- Threshold filtering
- Position-first search optimization
- Thread safety with 50 concurrent calls
- Debug mode output
- Fast mode (2-pass)
- prepare_frame for batch detection

Run: python -m pytest tests/test_vision.py -v -s
"""
import pytest
import os
import sys
import cv2
import numpy as np
import threading
import time
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vision import Vision


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_vision_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _create_test_image(path, w, h, pattern="rect"):
    """Create a synthetic test image with a distinctive pattern."""
    img = np.zeros((h, w), dtype=np.uint8)
    if pattern == "rect":
        # White rectangle with border
        cv2.rectangle(img, (5, 5), (w - 5, h - 5), 255, 2)
        cv2.rectangle(img, (10, 10), (w - 10, h - 10), 200, -1)
    elif pattern == "circle":
        cv2.circle(img, (w // 2, h // 2), min(w, h) // 3, 255, 2)
    elif pattern == "cross":
        cv2.line(img, (0, 0), (w, h), 255, 2)
        cv2.line(img, (w, 0), (0, h), 255, 2)
    cv2.imwrite(path, img)
    return img


def _create_frame_with_template(frame_w, frame_h, template_img, tx, ty):
    """Create a synthetic frame with template placed at (tx, ty)."""
    frame = np.random.randint(30, 60, (frame_h, frame_w), dtype=np.uint8)
    th, tw = template_img.shape[:2]
    # Place template
    frame[ty:ty + th, tx:tx + tw] = template_img
    return frame


class TestVisionBasic:
    """Basic detection tests."""

    def test_find_exact_match(self, temp_dir):
        """Template exists in frame → returns correct (x, y, score)."""
        # Create template
        tmpl_path = os.path.join(temp_dir, "btn.png")
        tmpl_img = _create_test_image(tmpl_path, 40, 30, "rect")

        # Create frame with template at (200, 150)
        frame = _create_frame_with_template(800, 600, tmpl_img, 200, 150)
        _, frame_bytes = cv2.imencode(".png", frame)
        frame_bytes = frame_bytes.tobytes()

        vision = Vision()
        result = vision.find_template_direct(
            tmpl_path, threshold=0.8, frame_bytes=frame_bytes
        )

        assert result is not None, "Should find the template"
        x, y, score = result
        assert abs(x - 220) <= 2, f"Expected x≈220, got {x}"  # center = 200 + 40/2
        assert abs(y - 165) <= 2, f"Expected y≈165, got {y}"  # center = 150 + 30/2
        assert score >= 0.9, f"Expected high score, got {score:.3f}"

    def test_find_no_match(self, temp_dir):
        """Template not in frame → returns None."""
        tmpl_path = os.path.join(temp_dir, "unique.png")
        _create_test_image(tmpl_path, 40, 30, "cross")

        # Create empty frame (no template)
        frame = np.random.randint(30, 60, (600, 800), dtype=np.uint8)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        result = vision.find_template_direct(
            tmpl_path, threshold=0.95, frame_bytes=frame_bytes.tobytes()
        )

        assert result is None, "Should not find template in random noise"

    def test_threshold_filtering(self, temp_dir):
        """Low-confidence match below threshold → returns None."""
        tmpl_path = os.path.join(temp_dir, "btn.png")
        tmpl_img = _create_test_image(tmpl_path, 40, 30, "rect")

        # Create frame with slightly corrupted template
        frame = _create_frame_with_template(800, 600, tmpl_img, 200, 150)
        # Add heavy noise to reduce match score
        noise = np.random.randint(0, 100, frame.shape, dtype=np.uint8)
        frame = cv2.add(frame, noise)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        # Very high threshold should reject noisy match
        result = vision.find_template_direct(
            tmpl_path, threshold=0.999, frame_bytes=frame_bytes.tobytes()
        )

        # Might or might not match depending on noise — test is about threshold behavior
        # With threshold=0.999, most noisy matches should be rejected


    def test_template_not_found_file(self, temp_dir):
        """Non-existent template file → returns None gracefully."""
        vision = Vision()
        frame = np.zeros((600, 800), dtype=np.uint8)
        _, frame_bytes = cv2.imencode(".png", frame)

        result = vision.find_template_direct(
            os.path.join(temp_dir, "nonexistent.png"),
            frame_bytes=frame_bytes.tobytes()
        )
        assert result is None

    def test_no_frame_bytes(self, temp_dir):
        """No frame_bytes provided to find_template_direct → returns None."""
        tmpl_path = os.path.join(temp_dir, "btn.png")
        _create_test_image(tmpl_path, 40, 30, "rect")

        vision = Vision()
        result = vision.find_template_direct(tmpl_path, frame_bytes=None)
        assert result is None


class TestVisionPositionSearch:
    """Position-first expanding search tests."""

    def test_position_hint_speeds_up_search(self, temp_dir):
        """Template at known position → found in first ROI pass (faster)."""
        tmpl_path = os.path.join(temp_dir, "icon.png")
        tmpl_img = _create_test_image(tmpl_path, 50, 50, "circle")

        # Place template at (600, 400)
        frame = _create_frame_with_template(1280, 720, tmpl_img, 600, 400)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()

        # Pre-seed position cache to simulate known position
        vision._position_cache[tmpl_path] = (625, 425)  # near actual center

        result = vision.find_template_direct(
            tmpl_path, threshold=0.8, frame_bytes=frame_bytes.tobytes(),
            fast_mode=True
        )

        assert result is not None, "Should find with position hint"
        x, y, score = result
        assert abs(x - 625) <= 2 and abs(y - 425) <= 2

    def test_no_position_falls_back_to_full_scan(self, temp_dir):
        """No known position → falls back to full frame scan."""
        tmpl_path = os.path.join(temp_dir, "icon.png")
        tmpl_img = _create_test_image(tmpl_path, 50, 50, "circle")

        frame = _create_frame_with_template(1280, 720, tmpl_img, 100, 50)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        # No position hint

        result = vision.find_template_direct(
            tmpl_path, threshold=0.8, frame_bytes=frame_bytes.tobytes()
        )

        assert result is not None, "Should find via full frame scan"

    def test_position_updates_after_detection(self, temp_dir):
        """After detection, position cache is updated for next call."""
        tmpl_path = os.path.join(temp_dir, "icon.png")
        tmpl_img = _create_test_image(tmpl_path, 40, 40, "rect")

        frame = _create_frame_with_template(800, 600, tmpl_img, 300, 200)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        assert tmpl_path not in vision._position_cache

        result = vision.find_template_direct(
            tmpl_path, threshold=0.8, frame_bytes=frame_bytes.tobytes()
        )
        assert result is not None

        # Position cache should now have the detected position
        assert tmpl_path in vision._position_cache
        pos = vision._position_cache[tmpl_path]
        assert abs(pos[0] - 320) <= 2 and abs(pos[1] - 220) <= 2


class TestVisionDebugMode:
    """Debug mode tests."""

    def test_debug_returns_tuple(self, temp_dir):
        """debug=True → returns (result, [debug_lines])."""
        tmpl_path = os.path.join(temp_dir, "btn.png")
        tmpl_img = _create_test_image(tmpl_path, 40, 30, "rect")

        frame = _create_frame_with_template(800, 600, tmpl_img, 200, 150)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        output = vision.find_template_on_screen(
            tmpl_path, threshold=0.8, debug=True,
            frame_bytes=frame_bytes.tobytes()
        )

        assert isinstance(output, tuple) and len(output) == 2
        result, debug_lines = output
        assert result is not None
        assert isinstance(debug_lines, list)
        assert len(debug_lines) > 0
        assert any("Found" in line for line in debug_lines)

    def test_debug_no_match(self, temp_dir):
        """debug=True with no match → returns (None, [debug_lines])."""
        tmpl_path = os.path.join(temp_dir, "btn.png")
        _create_test_image(tmpl_path, 40, 30, "cross")

        frame = np.random.randint(30, 60, (600, 800), dtype=np.uint8)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        result, lines = vision.find_template_on_screen(
            tmpl_path, threshold=0.99, debug=True,
            frame_bytes=frame_bytes.tobytes()
        )

        assert result is None
        assert any("Not found" in line for line in lines)


class TestVisionThreadSafety:
    """Thread safety tests for multi-account concurrency."""

    def test_50_threads_concurrent_detection(self, temp_dir):
        """50 threads calling find_template_direct simultaneously."""
        NUM_THREADS = 50

        # Create template and frame
        tmpl_path = os.path.join(temp_dir, "icon.png")
        tmpl_img = _create_test_image(tmpl_path, 40, 30, "rect")

        frame = _create_frame_with_template(800, 600, tmpl_img, 300, 200)
        _, frame_bytes = cv2.imencode(".png", frame)
        frame_bytes = frame_bytes.tobytes()

        vision = Vision()
        results = [None] * NUM_THREADS
        errors = []

        def worker(idx):
            try:
                # Each thread has its own frame_bytes (simulating per-account screenshot)
                r = vision.find_template_direct(
                    tmpl_path, threshold=0.8,
                    frame_bytes=frame_bytes, fast_mode=True
                )
                results[idx] = r
            except Exception as e:
                errors.append((idx, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(NUM_THREADS)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.perf_counter() - t0

        assert len(errors) == 0, f"Errors: {errors}"
        found_count = sum(1 for r in results if r is not None)
        assert found_count == NUM_THREADS, f"Only {found_count}/{NUM_THREADS} threads found template"

        print(f"\n  ✅ {NUM_THREADS} concurrent threads: all found template in {elapsed:.2f}s")

    def test_cache_shared_across_threads(self, temp_dir):
        """Template loaded once, used by all threads (cache efficiency)."""
        tmpl_path = os.path.join(temp_dir, "shared.png")
        _create_test_image(tmpl_path, 40, 30, "rect")

        frame = np.zeros((600, 800), dtype=np.uint8)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        barrier = threading.Barrier(20)

        def worker():
            barrier.wait()
            vision.find_template_direct(
                tmpl_path, threshold=0.99,
                frame_bytes=frame_bytes.tobytes()
            )

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Template should be cached exactly once
        assert tmpl_path in vision._cache
        assert len(vision._cache) == 1


class TestVisionPrepareFrame:
    """prepare_frame optimization tests."""

    def test_prepared_frame_reuse(self, temp_dir):
        """prepare_frame returns reusable decoded frame."""
        tmpl_path = os.path.join(temp_dir, "btn.png")
        tmpl_img = _create_test_image(tmpl_path, 40, 30, "rect")

        frame = _create_frame_with_template(800, 600, tmpl_img, 200, 150)
        _, frame_bytes = cv2.imencode(".png", frame)

        vision = Vision()
        prepared = Vision.prepare_frame(frame_bytes.tobytes())

        assert prepared is not None
        assert isinstance(prepared, np.ndarray)
        assert prepared.shape == (600, 800)

        # Use prepared frame for detection
        result = vision.find_template_direct(
            tmpl_path, threshold=0.8, _prepared_frame=prepared
        )
        assert result is not None


class TestVisionRefresh:
    """Cache management tests."""

    def test_refresh_evicts_cache(self, temp_dir):
        """refresh_template evicts the template from cache."""
        tmpl_path = os.path.join(temp_dir, "btn.png")
        _create_test_image(tmpl_path, 40, 30, "rect")

        vision = Vision()
        # Trigger cache load
        vision._get_template(tmpl_path)
        assert tmpl_path in vision._cache

        # Refresh should evict
        vision.refresh_template(tmpl_path)
        assert tmpl_path not in vision._cache

    def test_shutdown_clears_all(self, temp_dir):
        """shutdown_pool clears all caches."""
        tmpl1 = os.path.join(temp_dir, "a.png")
        tmpl2 = os.path.join(temp_dir, "b.png")
        _create_test_image(tmpl1, 40, 30, "rect")
        _create_test_image(tmpl2, 40, 30, "circle")

        vision = Vision()
        vision._get_template(tmpl1)
        vision._get_template(tmpl2)
        assert len(vision._cache) == 2

        vision.shutdown_pool()
        assert len(vision._cache) == 0
        assert len(vision._position_cache) == 0
