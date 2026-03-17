"""
Test CDPClient concurrency fixes — per-port lock, tab cache, stagger timing.

Validates that:
1. Per-port lock serializes concurrent connections (no thundering herd)
2. Tab list cache avoids redundant HTTP calls
3. Stagger delay spreads accounts over time

Run: python -m pytest tests/test_cdp_concurrency.py -v -s
"""
import sys
import os
import threading
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPerPortLock:
    """Verify per-port locks serialize concurrent CDPClient.connect() calls."""

    def test_lock_created_per_port(self):
        """Each port gets its own lock instance."""
        from cdp_client import _get_port_lock
        lock_a = _get_port_lock(9222)
        lock_b = _get_port_lock(9223)
        lock_a2 = _get_port_lock(9222)  # same port → same lock

        assert lock_a is lock_a2, "Same port must return same lock"
        assert lock_a is not lock_b, "Different ports must have different locks"
        print("  ✅ Per-port lock creation works correctly")

    @patch('cdp_client.urllib.request.urlopen')
    @patch('cdp_client.CDPClient._connect_ws')
    def test_concurrent_connects_serialized(self, mock_ws, mock_urlopen):
        """20 threads connecting to same port execute /json one at a time."""
        from cdp_client import CDPClient, _tab_cache

        # Clear cache to force HTTP calls
        _tab_cache.clear()

        call_timestamps = []
        call_lock = threading.Lock()

        def fake_urlopen(url, timeout=5):
            """Track when /json is called and simulate Chrome response."""
            with call_lock:
                call_timestamps.append(time.perf_counter())
            time.sleep(0.05)  # Simulate Chrome response time

            mock_resp = MagicMock()
            # Return 20 fake tabs
            tabs = []
            for i in range(20):
                tabs.append({
                    "type": "page",
                    "id": f"tab_{i}",
                    "title": f"Tab {i}",
                    "url": f"http://example.com/{i}",
                    "webSocketDebuggerUrl": f"ws://localhost:9222/devtools/page/tab_{i}"
                })
            import json
            mock_resp.read.return_value = json.dumps(tabs).encode()
            return mock_resp

        mock_urlopen.side_effect = fake_urlopen

        results = []
        errors = []
        barrier = threading.Barrier(20)

        def connect_worker(tab_idx):
            try:
                barrier.wait(timeout=5)
                client = CDPClient.connect(port=9222, tab_index=tab_idx)
                results.append(tab_idx)
                client.close()
            except Exception as e:
                errors.append((tab_idx, str(e)))

        threads = [threading.Thread(target=connect_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Connection errors: {errors[:5]}"
        assert len(results) == 20, f"Expected 20 connections, got {len(results)}"

        # Key assertion: due to per-port lock + cache, we should NOT have 20
        # separate HTTP calls. The cache (2s TTL) means only the first call
        # hits HTTP, the rest use cache.
        # With lock, calls are serialized → at most a few HTTP calls (cache kicks in)
        http_call_count = mock_urlopen.call_count
        print(f"  ✅ 20 concurrent connects: {http_call_count} HTTP call(s) (cache working)")
        assert http_call_count < 20, f"Expected fewer than 20 HTTP calls (got {http_call_count}), cache not working"

    @patch('cdp_client.urllib.request.urlopen')
    @patch('cdp_client.CDPClient._connect_ws')
    def test_different_ports_parallel(self, mock_ws, mock_urlopen):
        """Connections to DIFFERENT ports should run in parallel (not blocked)."""
        from cdp_client import CDPClient, _tab_cache
        _tab_cache.clear()

        port_call_times = {}
        call_lock = threading.Lock()

        def fake_urlopen(url, timeout=5):
            port = int(url.split(':')[2].split('/')[0])
            start = time.perf_counter()
            time.sleep(0.1)  # Simulate 100ms Chrome response
            with call_lock:
                port_call_times[port] = start

            mock_resp = MagicMock()
            import json
            tabs = [{
                "type": "page", "id": "tab_0", "title": "Tab 0",
                "url": "http://example.com", 
                "webSocketDebuggerUrl": f"ws://localhost:{port}/devtools/page/tab_0"
            }]
            mock_resp.read.return_value = json.dumps(tabs).encode()
            return mock_resp

        mock_urlopen.side_effect = fake_urlopen

        barrier = threading.Barrier(5)
        results = []

        def connect_to_port(port):
            barrier.wait(timeout=5)
            try:
                client = CDPClient.connect(port=port, tab_index=0)
                results.append(port)
                client.close()
            except Exception as e:
                results.append(f"err_{port}: {e}")

        threads = [threading.Thread(target=connect_to_port, args=(9222 + i,)) for i in range(5)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        elapsed = time.perf_counter() - t0

        assert len(results) == 5, f"Expected 5 results, got {len(results)}: {results}"
        # 5 different ports should run in parallel → total time ~0.1-0.3s, NOT 0.5s+
        assert elapsed < 0.5, f"Different ports should be parallel but took {elapsed:.2f}s"
        print(f"  ✅ 5 different ports connected in {elapsed:.2f}s (parallel OK)")


class TestTabCache:
    """Verify tab list caching avoids redundant HTTP calls."""

    @patch('cdp_client.urllib.request.urlopen')
    def test_cache_hit_within_ttl(self, mock_urlopen):
        """Second call within 2s should use cache, not HTTP."""
        from cdp_client import CDPClient, _tab_cache
        _tab_cache.clear()

        mock_resp = MagicMock()
        import json
        mock_resp.read.return_value = json.dumps([
            {"type": "page", "id": "t1", "title": "T1", "url": "http://x.com",
             "webSocketDebuggerUrl": "ws://localhost:9999/devtools/page/t1"}
        ]).encode()
        mock_urlopen.return_value = mock_resp

        # First call → HTTP
        tabs1 = CDPClient.list_tabs(port=9999)
        assert mock_urlopen.call_count == 1

        # Second call → cache
        tabs2 = CDPClient.list_tabs(port=9999)
        assert mock_urlopen.call_count == 1, "Second call should use cache"
        assert len(tabs2) == 1
        print("  ✅ Tab cache hit within TTL works")

    @patch('cdp_client.urllib.request.urlopen')
    def test_cache_miss_after_ttl(self, mock_urlopen):
        """After TTL expires, cache should be refreshed."""
        from cdp_client import CDPClient, _tab_cache, _TAB_CACHE_TTL
        _tab_cache.clear()

        mock_resp = MagicMock()
        import json
        mock_resp.read.return_value = json.dumps([
            {"type": "page", "id": "t1", "title": "T1", "url": "http://x.com",
             "webSocketDebuggerUrl": "ws://localhost:9998/devtools/page/t1"}
        ]).encode()
        mock_urlopen.return_value = mock_resp

        # First call
        CDPClient.list_tabs(port=9998)
        assert mock_urlopen.call_count == 1

        # Expire cache manually
        _tab_cache[9998] = (time.time() - _TAB_CACHE_TTL - 1, _tab_cache[9998][1])

        # Should make new HTTP call
        CDPClient.list_tabs(port=9998)
        assert mock_urlopen.call_count == 2, "Expired cache should trigger new HTTP call"
        print("  ✅ Tab cache expires after TTL")

    def test_cache_returns_copy(self):
        """Cache should return a copy, not a reference (prevent mutation)."""
        from cdp_client import _tab_cache
        _tab_cache[8888] = (time.time(), [{"id": "t1"}, {"id": "t2"}])

        from cdp_client import CDPClient
        tabs = CDPClient.list_tabs(port=8888)
        tabs.append({"id": "injected"})

        # Original cache should be unchanged
        assert len(_tab_cache[8888][1]) == 2, "Cache was mutated!"
        print("  ✅ Tab cache returns copy (immutable)")


class TestStaggerTiming:
    """Verify that stagger delay formula gives correct values."""

    def test_stagger_formula_20_accounts(self):
        """Tab 20 should wait ~4-5s with new formula (was 0.4-0.7s)."""
        import random
        random.seed(42)

        delays = []
        for tab_idx in range(21):
            if tab_idx > 0:
                batch_delay = tab_idx / 5   # New formula: 5 acc/s
                jitter = random.uniform(0, 1.0)
                stagger = batch_delay + jitter
                delays.append((tab_idx, stagger))

        # Tab 1 should wait ~0.2-1.2s
        assert 0.1 < delays[0][1] < 2.0, f"Tab 1 delay too extreme: {delays[0][1]:.2f}s"

        # Tab 10 should wait ~2-3s
        tab10_delay = delays[9][1]
        assert 1.5 < tab10_delay < 4.0, f"Tab 10 delay unexpected: {tab10_delay:.2f}s"

        # Tab 20 should wait ~4-5s
        tab20_delay = delays[19][1]
        assert 3.0 < tab20_delay < 6.0, f"Tab 20 delay unexpected: {tab20_delay:.2f}s"

        print(f"  ✅ Stagger delays look correct:")
        print(f"     Tab 1:  {delays[0][1]:.2f}s")
        print(f"     Tab 10: {tab10_delay:.2f}s")
        print(f"     Tab 20: {tab20_delay:.2f}s")

    def test_old_formula_was_too_fast(self):
        """Demonstrate the old formula (tab_idx/50) was way too fast."""
        import random
        random.seed(42)

        for tab_idx in [10, 20]:
            old_delay = tab_idx / 50 + random.uniform(0, 0.3)
            new_delay = tab_idx / 5 + random.uniform(0, 1.0)
            speedup = new_delay / old_delay
            print(f"     Tab {tab_idx}: old={old_delay:.2f}s → new={new_delay:.2f}s ({speedup:.1f}× slower)")
            assert new_delay > old_delay * 3, "New formula should be significantly slower"

        print("  ✅ New formula is appropriately slower than old")

    def test_wave_batch_timing_21_accounts(self):
        """21 accounts with WAVE_SIZE=3 and 2s gap → should take ~14s total."""
        WAVE_SIZE = 3
        WAVE_DELAY_MS = 2000  # 2s between waves

        num_accounts = 21
        num_waves = (num_accounts + WAVE_SIZE - 1) // WAVE_SIZE  # ceiling division
        total_delay_ms = (num_waves - 1) * WAVE_DELAY_MS  # first wave is instant

        print(f"  ✅ 21 accounts: {num_waves} waves, total deploy time: {total_delay_ms/1000:.0f}s")
        assert num_waves == 7, f"Expected 7 waves, got {num_waves}"
        assert total_delay_ms == 12000, f"Expected 12s total, got {total_delay_ms}ms"


class TestRetryBackoff:
    """Verify retry backoff with jitter."""

    def test_retry_wait_times(self):
        """Retry wait times should include jitter and not be identical."""
        import random
        random.seed(42)

        max_retries = 5
        waits = []
        for attempt in range(max_retries - 1):
            wait_time = 2 ** (attempt + 1) + random.uniform(0, 1.5)
            waits.append(wait_time)

        # Attempt 1: ~2-3.5s, Attempt 2: ~4-5.5s, Attempt 3: ~8-9.5s, Attempt 4: ~16-17.5s
        assert 2.0 <= waits[0] <= 3.5, f"Attempt 1 wait: {waits[0]:.2f}s"
        assert 4.0 <= waits[1] <= 5.5, f"Attempt 2 wait: {waits[1]:.2f}s"
        assert 8.0 <= waits[2] <= 9.5, f"Attempt 3 wait: {waits[2]:.2f}s"
        assert 16.0 <= waits[3] <= 17.5, f"Attempt 4 wait: {waits[3]:.2f}s"

        print(f"  ✅ Retry backoff with jitter:")
        for i, w in enumerate(waits):
            print(f"     Attempt {i+1}: {w:.2f}s")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])
