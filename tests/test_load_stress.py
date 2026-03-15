"""
Load/Stress tests — Simulating hundreds of concurrent accounts.
Focus: StateDB throughput, PlaywrightPool concurrency, worker thread scaling,
GUI queue saturation, JSON persistence performance, and memory baseline.

Run with: python -m pytest tests/test_load_stress.py -v --tb=short -s
"""
import pytest
import os
import sys
import threading
import time
import json
import queue
import tempfile
import shutil
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from state_db import StateDB
from tests.conftest import generate_bulk_accounts


# ============================================================
# StateDB Load Tests
# ============================================================

class TestStateDBLoad:
    """Stress test StateDB with hundreds of concurrent accounts."""

    def test_500_accounts_concurrent_write(self, temp_dir):
        """500 threads each saving their own account state simultaneously.
        Uses retry-on-lock to handle SQLite contention realistically.
        """
        db = StateDB(db_path=os.path.join(temp_dir, "load_test.db"))
        errors = []
        start_event = threading.Event()
        
        def worker(acc_id):
            start_event.wait()  # Synchronize start
            name = f"LoadAcc_{acc_id:04d}"
            for attempt in range(10):
                try:
                    db.save_account_state(name, status="running",
                                           current_node=f"node_{acc_id}",
                                           port=9222 + (acc_id // 10),
                                           tab_index=acc_id % 10)
                    return  # Success
                except Exception as e:
                    if "locked" in str(e).lower() and attempt < 9:
                        time.sleep(0.05 * (attempt + 1))  # Backoff
                        continue
                    errors.append((acc_id, str(e)))
                    return
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(500)]
        for t in threads:
            t.start()
        
        t0 = time.perf_counter()
        start_event.set()  # Release all threads at once
        
        for t in threads:
            t.join(timeout=60)
        elapsed = time.perf_counter() - t0
        
        assert not errors, f"Errors ({len(errors)}): {errors[:5]}"
        
        states = db.get_all_account_states()
        assert len(states) == 500, f"Expected 500, got {len(states)}"
        
        print(f"\n  ✅ 500 accounts concurrent write: {elapsed:.2f}s ({500/elapsed:.0f} ops/sec)")
        db.close()

    def test_100_accounts_concurrent_read_write(self, temp_dir):
        """100 accounts: each thread writes then reads back, 5 iterations."""
        db = StateDB(db_path=os.path.join(temp_dir, "rw_test.db"))
        errors = []
        
        def worker(acc_id):
            try:
                name = f"RW_Acc_{acc_id:04d}"
                for iteration in range(5):
                    db.save_account_state(name, status=f"iter_{iteration}",
                                           current_node=f"n_{iteration}")
                    state = db.get_account_state(name)
                    if state is None:
                        errors.append((acc_id, "State is None"))
                        return
                    if state["status"] != f"iter_{iteration}":
                        errors.append((acc_id, f"Status mismatch: {state['status']}"))
                        return
            except Exception as e:
                errors.append((acc_id, str(e)))
        
        t0 = time.perf_counter()
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.perf_counter() - t0
        
        assert not errors, f"Errors: {errors[:5]}"
        
        total_ops = 100 * 5 * 2  # 100 accounts × 5 iters × (write + read)
        print(f"\n  ✅ 100 accounts R/W (5 iters): {elapsed:.2f}s ({total_ops/elapsed:.0f} ops/sec)")
        db.close()

    def test_log_action_under_load(self, temp_dir):
        """100 accounts × 50 log entries each, concurrently."""
        db = StateDB(db_path=os.path.join(temp_dir, "log_load.db"))
        errors = []
        
        def worker(acc_id):
            try:
                name = f"Log_Acc_{acc_id:04d}"
                for i in range(50):
                    db.log_action(name, f"action_{i}", f"detail_{i}", "OK")
            except Exception as e:
                errors.append((acc_id, str(e)))
        
        t0 = time.perf_counter()
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        elapsed = time.perf_counter() - t0
        
        assert not errors, f"Errors: {errors[:5]}"
        
        total_logs = 100 * 50
        print(f"\n  ✅ {total_logs} log entries from 100 threads: {elapsed:.2f}s ({total_logs/elapsed:.0f} ops/sec)")
        db.close()

    def test_get_all_states_performance_500(self, temp_dir):
        """Measure time to retrieve all 500 account states at once."""
        db = StateDB(db_path=os.path.join(temp_dir, "perf_test.db"))
        
        for i in range(500):
            db.save_account_state(f"Perf_Acc_{i:04d}", status="idle", port=9222 + (i // 10))
        
        t0 = time.perf_counter()
        states = db.get_all_account_states()
        elapsed = time.perf_counter() - t0
        
        assert len(states) == 500
        assert elapsed < 1.0, f"get_all_account_states took {elapsed:.3f}s (> 1s threshold)"
        print(f"\n  ✅ get_all_account_states(500): {elapsed*1000:.1f}ms")
        db.close()


# ============================================================
# PlaywrightPool Load Tests
# ============================================================

class TestPlaywrightPoolLoad:
    """Stress test PlaywrightPool with many ports."""

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_100_ports_concurrent_acquire_release(self, mock_get_page, mock_sp):
        """100 different ports, each acquired and released concurrently."""
        from connection_pool import PlaywrightPool
        
        mock_page = MagicMock()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = MagicMock()
        mock_pw.chromium.connect_over_cdp.return_value = MagicMock(
            contexts=[MagicMock(pages=[mock_page])]
        )
        mock_sp.return_value.start.return_value = mock_pw
        
        pool = PlaywrightPool()
        errors = []
        
        def worker(port):
            try:
                page, info = pool.acquire(port, 0)
                time.sleep(0.01)
                pool.release(port)
            except Exception as e:
                errors.append((port, str(e)))
        
        t0 = time.perf_counter()
        threads = [threading.Thread(target=worker, args=(9222 + i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.perf_counter() - t0
        
        assert not errors, f"Errors: {errors[:5]}"
        assert pool.get_connection_count() == 0
        print(f"\n  ✅ 100 ports acquire/release: {elapsed:.2f}s")

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_same_port_50_concurrent_users(self, mock_get_page, mock_sp):
        """50 accounts sharing a single port — tests ref_count under contention."""
        from connection_pool import PlaywrightPool
        
        mock_page = MagicMock()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = MagicMock()
        mock_pw.chromium.connect_over_cdp.return_value = MagicMock(
            contexts=[MagicMock(pages=[mock_page])]
        )
        mock_sp.return_value.start.return_value = mock_pw
        
        pool = PlaywrightPool()
        errors = []
        barrier = threading.Barrier(50)
        
        def worker(tab_idx):
            try:
                barrier.wait(timeout=5)
                page, info = pool.acquire(9222, tab_idx % 10)
                time.sleep(0.02)
                pool.release(9222)
            except Exception as e:
                errors.append((tab_idx, str(e)))
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        
        assert not errors, f"Errors: {errors[:5]}"
        assert pool.get_connection_count() == 0


# ============================================================
# Worker Thread Scaling Tests
# ============================================================

class TestWorkerScaling:
    """Simulate account_running dict under heavy concurrent access."""

    def test_account_running_dict_consistency_200_workers(self):
        """200 workers reading/writing account_running concurrently."""
        account_running = {}
        lock = threading.Lock()
        errors = []
        
        def worker(acc_id):
            name = f"Worker_{acc_id:04d}"
            try:
                # Start
                with lock:
                    account_running[name] = True
                
                # Simulate work loop
                for _ in range(10):
                    with lock:
                        running = account_running.get(name, False)
                    if not running:
                        break
                    time.sleep(0.001)
                
                # Stop
                with lock:
                    account_running[name] = False
            except Exception as e:
                errors.append((acc_id, str(e)))
        
        t0 = time.perf_counter()
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.perf_counter() - t0
        
        assert not errors, f"Errors: {errors[:5]}"
        
        # All should be stopped
        with lock:
            still_running = [k for k, v in account_running.items() if v]
        assert len(still_running) == 0, f"Still running: {still_running[:5]}"
        print(f"\n  ✅ 200 workers start/stop: {elapsed:.2f}s")

    def test_account_running_without_lock_race_detection(self):
        """Verify that plain dict access without lock is 'safe enough' under GIL.
        This test demonstrates the issue but shouldn't crash due to GIL.
        """
        account_running = {}
        
        def writer(acc_id):
            name = f"RaceAcc_{acc_id:04d}"
            account_running[name] = True
            for _ in range(100):
                account_running[name] = not account_running[name]
            account_running[name] = False
        
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(500)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        
        # With GIL, dict operations are atomic so this should work
        assert len(account_running) == 500
        still_running = sum(1 for v in account_running.values() if v)
        assert still_running == 0


# ============================================================
# GUI Queue Saturation Test
# ============================================================

class TestGUIQueueSaturation:
    """Test queue.Queue behavior under heavy producer load."""

    def test_1000_messages_queued_rapidly(self):
        """1000 messages from 50 producers — simulates 50 accounts sending logs."""
        gui_queue = queue.Queue()
        errors = []
        
        def producer(producer_id, count):
            try:
                for i in range(count):
                    gui_queue.put(("log", f"[Acc_{producer_id:03d}] Message {i}"))
            except Exception as e:
                errors.append(e)
        
        # 50 producers × 20 messages = 1000 total
        t0 = time.perf_counter()
        threads = [threading.Thread(target=producer, args=(i, 20)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        elapsed_produce = time.perf_counter() - t0
        
        assert not errors
        assert gui_queue.qsize() == 1000
        
        # Consume all (simulates GUI tick)
        consumed = 0
        t0 = time.perf_counter()
        while not gui_queue.empty():
            try:
                gui_queue.get_nowait()
                consumed += 1
            except queue.Empty:
                break
        elapsed_consume = time.perf_counter() - t0
        
        assert consumed == 1000
        print(f"\n  ✅ 1000 msgs: produce={elapsed_produce*1000:.1f}ms, consume={elapsed_consume*1000:.1f}ms")

    def test_5000_messages_no_deadlock(self):
        """5000 messages from 100 producers — checks for no deadlocks."""
        gui_queue = queue.Queue()
        barrier = threading.Barrier(100)
        
        def producer(producer_id):
            barrier.wait(timeout=5)
            for i in range(50):
                gui_queue.put(("run", lambda: None))
        
        threads = [threading.Thread(target=producer, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        
        assert gui_queue.qsize() == 5000


# ============================================================
# JSON Persistence Load Test
# ============================================================

class TestJSONPersistenceLoad:
    """Test save/load performance with large account lists."""

    def test_500_accounts_save_load_time(self, temp_dir):
        """Save and load 500 accounts, measure timing."""
        accounts = generate_bulk_accounts(500)
        path = os.path.join(temp_dir, "multi_load.json")
        
        # Save timing
        t0 = time.perf_counter()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=4)
        save_time = time.perf_counter() - t0
        
        # Load timing
        t0 = time.perf_counter()
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        load_time = time.perf_counter() - t0
        
        assert len(loaded) == 500
        assert save_time < 1.0, f"Save took {save_time:.3f}s"
        assert load_time < 0.5, f"Load took {load_time:.3f}s"
        
        file_size_kb = os.path.getsize(path) / 1024
        print(f"\n  ✅ 500 accounts: save={save_time*1000:.1f}ms, load={load_time*1000:.1f}ms, size={file_size_kb:.1f}KB")

    def test_1000_accounts_save_load(self, temp_dir):
        """Extreme: 1000 accounts."""
        accounts = generate_bulk_accounts(1000)
        path = os.path.join(temp_dir, "multi_extreme.json")
        
        t0 = time.perf_counter()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=4)
        save_time = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        load_time = time.perf_counter() - t0
        
        assert len(loaded) == 1000
        file_size_kb = os.path.getsize(path) / 1024
        print(f"\n  ✅ 1000 accounts: save={save_time*1000:.1f}ms, load={load_time*1000:.1f}ms, size={file_size_kb:.1f}KB")

    def test_concurrent_save_load_safety(self, temp_dir):
        """Multiple threads trying to save/load simultaneously."""
        accounts = generate_bulk_accounts(200)
        path = os.path.join(temp_dir, "concurrent_multi.json")
        lock = threading.Lock()
        errors = []
        
        with open(path, "w") as f:
            json.dump(accounts, f)
        
        def save_worker(worker_id):
            try:
                data = list(accounts)
                data.append({"name": f"Extra_{worker_id}", "port": 9999, "target": "0", "loop": ""})
                with lock:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f)
            except Exception as e:
                errors.append(e)
        
        def load_worker(worker_id):
            try:
                with lock:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                assert len(data) >= 200
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(20):
            threads.append(threading.Thread(target=save_worker, args=(i,)))
            threads.append(threading.Thread(target=load_worker, args=(i,)))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        
        assert not errors, f"Errors: {errors[:5]}"


# ============================================================
# Memory Baseline Test
# ============================================================

class TestMemoryBaseline:
    """Measure memory footprint of core data structures."""

    def test_500_account_dict_memory(self):
        """Estimate memory for account_running + account_workers dicts."""
        account_running = {}
        account_workers = {}
        
        for i in range(500):
            name = f"Account_{i:04d}"
            account_running[name] = False
            account_workers[name] = MagicMock()  # Mock thread
        
        # Basic size check
        assert len(account_running) == 500
        assert len(account_workers) == 500
        
        import sys as _sys
        running_size = _sys.getsizeof(account_running)
        # Dict overhead + keys + values
        total_size = running_size + sum(
            _sys.getsizeof(k) + _sys.getsizeof(v)
            for k, v in account_running.items()
        )
        
        print(f"\n  ✅ 500 account_running dict: ~{total_size/1024:.1f}KB")
        assert total_size < 500_000, "Dict too large for 500 accounts"

    def test_state_db_500_accounts_disk_size(self, temp_dir):
        """Measure SQLite DB size with 500 accounts + logs."""
        db_path = os.path.join(temp_dir, "size_test.db")
        db = StateDB(db_path=db_path)
        
        for i in range(500):
            name = f"Size_Acc_{i:04d}"
            db.save_account_state(name, status="idle", port=9222 + (i // 10), tab_index=i % 10)
            db.log_action(name, "init", "started")
        
        db.close()
        
        db_size_kb = os.path.getsize(db_path) / 1024
        print(f"\n  ✅ DB with 500 accounts + 500 logs: {db_size_kb:.1f}KB")
        assert db_size_kb < 1024, f"DB too large: {db_size_kb:.1f}KB"


# ============================================================
# Health Monitor Stress Test
# ============================================================

class TestHealthMonitorStress:
    """Simulate health monitor detecting and restarting dead workers."""

    def test_200_workers_crash_restart_cycle(self):
        """200 workers, 20% die randomly, verify restart logic detects them."""
        import random
        
        account_running = {}
        account_workers = {}
        crash_detected = []
        restart_count = [0]
        lock = threading.Lock()
        
        class FakeThread:
            def __init__(self, acc_name, should_crash=False):
                self.acc_name = acc_name
                self.should_crash = should_crash
                self._alive = True
                if should_crash:
                    self._alive = False
            
            def is_alive(self):
                return self._alive
        
        # Setup 200 workers, 40 will "crash"
        crash_indices = set(random.sample(range(200), 40))
        for i in range(200):
            name = f"Worker_{i:04d}"
            account_running[name] = True
            account_workers[name] = FakeThread(name, should_crash=(i in crash_indices))
        
        # Health monitor logic (simplified from tab_accounts.py)
        for acc_name, thread in list(account_workers.items()):
            if account_running.get(acc_name, False) and not thread.is_alive():
                crash_detected.append(acc_name)
                account_running[acc_name] = False
                # Simulate restart
                account_workers[acc_name] = FakeThread(acc_name, should_crash=False)
                account_running[acc_name] = True
                restart_count[0] += 1
        
        assert len(crash_detected) == 40
        assert restart_count[0] == 40
        
        # After restart, all should be alive
        still_dead = [
            name for name, thread in account_workers.items()
            if not thread.is_alive()
        ]
        assert len(still_dead) == 0
        
        print(f"\n  ✅ 200 workers, 40 crashed, all restarted successfully")
