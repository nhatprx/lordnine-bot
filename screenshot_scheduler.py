"""
Screenshot Scheduler — Central coordinator for CDP screenshots at scale.

Replaces the old semaphore-based throttling with a fair round-robin scheduler
that prevents Chrome from being overwhelmed by concurrent screenshot requests.

Design decisions:
  - Adaptive concurrency: 1-2 worker threads per Chrome port based on demand
  - Workers submit requests and block until result is delivered
  - Round-robin ensures fairness — no tab starves
  - Circuit breaker pauses a port after consecutive failures
  - Frame cache (2s TTL) prevents redundant shots in tight loops
  - Periodic cache cleanup prevents memory growth over 24h+ operation

Usage:
    scheduler = ScreenshotScheduler()
    frame = scheduler.request_screenshot(cdp_client, quality=70, timeout=25)
    # frame is bytes (JPEG) or None on failure

    # At shutdown:
    scheduler.shutdown()
"""

import time
import threading
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)


class _ScreenshotRequest:
    """Internal request object — one per worker call."""
    __slots__ = ('cdp_client', 'quality', 'result', 'error', 'event')

    def __init__(self, cdp_client, quality):
        self.cdp_client = cdp_client
        self.quality = quality
        self.result = None      # bytes on success
        self.error = None       # str on failure
        self.event = threading.Event()


class PortScheduler:
    """Scheduler for a single Chrome port.

    Runs one background thread that processes screenshot requests
    in round-robin order across tabs on that port.
    """

    def __init__(self, port):
        self.port = port
        self._lock = threading.Lock()

        # Pending requests: tab_index → latest _ScreenshotRequest
        # Using OrderedDict for round-robin insertion-order iteration
        self._pending = OrderedDict()

        # Signal that new work is available
        self._work_event = threading.Event()

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0  # timestamp when circuit reopens

        # Frame cache: tab_index → (timestamp, bytes)
        self._frame_cache = {}
        self._CACHE_TTL = 3.0  # seconds — longer TTL for 37+ account scenarios

        # Rate limiting
        self._MIN_GAP = 0.15  # minimum 150ms between screenshots (reduce Chrome pressure)
        self._last_shot_time = 0.0

        # Periodic cache cleanup (prevent memory growth over 24h+)
        self._last_cache_cleanup = time.time()
        self._CACHE_CLEANUP_INTERVAL = 60.0  # every 60 seconds

        # Adaptive concurrency: start with 1 worker, scale to 2 if needed
        self._running = True
        self._active_workers = 1
        self._worker_threads = []
        t = threading.Thread(
            target=self._worker_loop,
            name=f"ShotSched-{port}-0",
            daemon=True
        )
        t.start()
        self._worker_threads.append(t)

    def request(self, cdp_client, tab_index, quality=70, timeout=25):
        """Submit a screenshot request.

        Blocks until the result is ready or timeout expires.
        Returns frame_bytes (bytes) or None on failure.

        Thread-safe — multiple workers call this concurrently.
        """
        # Check frame cache first — avoids queueing entirely
        cached = self._get_cached(tab_index)
        if cached is not None:
            return cached

        req = _ScreenshotRequest(cdp_client, quality)

        with self._lock:
            # Request coalescing: replace any existing pending request
            # for this tab (only the latest caller gets the result)
            old = self._pending.get(tab_index)
            if old is not None:
                # Wake the old waiter with None so it doesn't hang forever
                old.result = None
                old.error = "coalesced"
                old.event.set()

            self._pending[tab_index] = req

        # Signal the worker thread
        self._work_event.set()

        # Block until result is ready
        if not req.event.wait(timeout=timeout):
            # Timeout — remove from pending if still there
            with self._lock:
                if self._pending.get(tab_index) is req:
                    del self._pending[tab_index]
            logger.warning(f"[ShotSched:{self.port}] Tab {tab_index} request timed out ({timeout}s)")
            return None

        if req.error and req.error != "coalesced":
            logger.debug(f"[ShotSched:{self.port}] Tab {tab_index} error: {req.error}")

        return req.result

    def get_cached(self, tab_index, max_age=None):
        """Get cached frame if fresh enough. Returns bytes or None."""
        return self._get_cached(tab_index, max_age)

    def _get_cached(self, tab_index, max_age=None):
        """Internal cache lookup."""
        ttl = max_age if max_age is not None else self._CACHE_TTL
        entry = self._frame_cache.get(tab_index)
        if entry and (time.time() - entry[0]) < ttl:
            return entry[1]
        return None

    def _maybe_scale_workers(self):
        """Adaptive concurrency: add a second worker if demand is high.
        
        With 10+ tabs and complex loops, a single worker can't keep up.
        Two workers per port ~doubles throughput without overwhelming Chrome.
        Max 2 workers (Chrome struggles with more concurrent renders).
        """
        with self._lock:
            pending_count = len(self._pending)
        
        if pending_count >= 5 and self._active_workers < 2:
            self._active_workers = 2
            t = threading.Thread(
                target=self._worker_loop,
                name=f"ShotSched-{self.port}-1",
                daemon=True
            )
            t.start()
            self._worker_threads.append(t)
            logger.info(f"[ShotSched:{self.port}] Scaled UP to 2 workers ({pending_count} pending)")

    def _cleanup_stale_cache(self):
        """Remove expired cache entries to prevent memory growth over days."""
        now = time.time()
        if (now - self._last_cache_cleanup) < self._CACHE_CLEANUP_INTERVAL:
            return
        self._last_cache_cleanup = now
        stale_keys = [k for k, (ts, _) in self._frame_cache.items()
                      if (now - ts) > self._CACHE_TTL * 5]
        for k in stale_keys:
            del self._frame_cache[k]
        if stale_keys:
            logger.debug(f"[ShotSched:{self.port}] Cleaned {len(stale_keys)} stale cache entries")

    def _worker_loop(self):
        """Background thread: process requests round-robin."""
        while self._running:
            # Wait for work (with 1s timeout to allow clean shutdown)
            self._work_event.wait(timeout=1.0)
            self._work_event.clear()

            # Check if we need more workers
            self._maybe_scale_workers()

            # Periodic cache cleanup (memory safety for 24h+ runs)
            self._cleanup_stale_cache()

            while self._running:
                # Circuit breaker check
                now = time.time()
                if now < self._circuit_open_until:
                    # Circuit is open — sleep until it closes
                    sleep_time = self._circuit_open_until - now
                    logger.debug(f"[ShotSched:{self.port}] Circuit open, sleeping {sleep_time:.1f}s")
                    time.sleep(min(sleep_time, 1.0))
                    break  # Re-check after sleep

                # Grab next request (round-robin via OrderedDict pop-first)
                req = None
                tab_index = None
                with self._lock:
                    if not self._pending:
                        break  # No more work

                    # Pop the first (oldest) request
                    tab_index, req = self._pending.popitem(last=False)

                if req is None:
                    break

                # Rate limit: ensure minimum gap between shots
                elapsed = time.time() - self._last_shot_time
                if elapsed < self._MIN_GAP:
                    time.sleep(self._MIN_GAP - elapsed)

                # Execute screenshot
                frame_bytes = None
                error = None
                try:
                    frame_bytes = req.cdp_client.screenshot(quality=req.quality)
                    self._consecutive_failures = 0
                except Exception as e:
                    error = str(e)
                    self._consecutive_failures += 1

                    # Circuit breaker: open after 5 consecutive failures
                    if self._consecutive_failures >= 5:
                        self._circuit_open_until = time.time() + 5.0
                        logger.warning(
                            f"[ShotSched:{self.port}] Circuit breaker OPEN — "
                            f"{self._consecutive_failures} consecutive failures, "
                            f"pausing for 5s"
                        )

                self._last_shot_time = time.time()

                # Cache successful frame
                if frame_bytes is not None:
                    self._frame_cache[tab_index] = (time.time(), frame_bytes)

                # Deliver result to waiting worker
                req.result = frame_bytes
                req.error = error
                req.event.set()

    def shutdown(self):
        """Stop all worker threads and wake all waiters."""
        self._running = False
        self._work_event.set()

        # Wake all pending requests so they don't block forever
        with self._lock:
            for tab_index, req in self._pending.items():
                req.result = None
                req.error = "scheduler shutdown"
                req.event.set()
            self._pending.clear()

        for t in self._worker_threads:
            t.join(timeout=5)
        
        # Clear cache to free memory
        self._frame_cache.clear()


class ScreenshotScheduler:
    """Top-level scheduler managing per-port PortSchedulers.

    Usage:
        scheduler = ScreenshotScheduler()

        # In worker thread:
        frame = scheduler.request_screenshot(cdp_client, quality=70)

        # At shutdown:
        scheduler.shutdown()
    """

    def __init__(self):
        self._schedulers = {}  # port → PortScheduler
        self._lock = threading.Lock()

    def _get_port_scheduler(self, port):
        """Get or create a PortScheduler for the given port."""
        sched = self._schedulers.get(port)
        if sched is not None:
            return sched

        with self._lock:
            # Double-check after acquiring lock
            sched = self._schedulers.get(port)
            if sched is not None:
                return sched

            sched = PortScheduler(port)
            self._schedulers[port] = sched
            logger.info(f"[ShotSched] Created scheduler for port {port}")
            return sched

    def request_screenshot(self, cdp_client, quality=70, timeout=25):
        """Request a screenshot from the appropriate port scheduler.

        Args:
            cdp_client: CDPClient instance (has _port and _tab_index)
            quality:    JPEG quality (1-100)
            timeout:    Max seconds to wait for result

        Returns:
            bytes (JPEG) or None on failure
        """
        port = getattr(cdp_client, '_port', 9222)
        tab_index = getattr(cdp_client, '_tab_index', 0)

        sched = self._get_port_scheduler(port)
        return sched.request(cdp_client, tab_index, quality, timeout)

    def get_cached_frame(self, cdp_client, max_age=1.0):
        """Get cached frame if fresh enough.

        Returns bytes or None.
        Useful for multiple find_template calls in the same loop iteration.
        """
        port = getattr(cdp_client, '_port', 9222)
        tab_index = getattr(cdp_client, '_tab_index', 0)

        sched = self._schedulers.get(port)
        if sched is None:
            return None

        return sched.get_cached(tab_index, max_age)

    def shutdown(self):
        """Stop all port schedulers."""
        with self._lock:
            for port, sched in self._schedulers.items():
                logger.info(f"[ShotSched] Shutting down scheduler for port {port}")
                sched.shutdown()
            self._schedulers.clear()

    def get_stats(self):
        """Get scheduler stats for debugging.

        Returns dict: {port: {pending: N, cache_size: N, circuit_open: bool}}
        """
        stats = {}
        for port, sched in self._schedulers.items():
            with sched._lock:
                pending = len(sched._pending)
            stats[port] = {
                "pending": pending,
                "cache_size": len(sched._frame_cache),
                "circuit_open": time.time() < sched._circuit_open_until,
                "consecutive_failures": sched._consecutive_failures,
            }
        return stats
