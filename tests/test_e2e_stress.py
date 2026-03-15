"""
🔥 E2E Stress Test — Mô phỏng 150 accounts chạy loop đồng thời.

Simulate toàn bộ pipeline của mỗi account worker:
  connect → screenshot → vision.find_template_direct → bot.click_at 
  → state_db.log_action → next node → lặp lại

Tất cả Playwright, Vision, BotAction đều được mock để test logic + tải.
Mục tiêu: kiểm tra hệ thống có chịu nổi 150 accounts cùng chạy không.

Run: python -m pytest tests/test_e2e_stress.py -v -s
"""
import pytest
import os
import sys
import threading
import time
import json
import queue
import random
import tempfile
import shutil
from unittest.mock import MagicMock, patch, PropertyMock
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from state_db import StateDB
from tests.conftest import generate_bulk_accounts

# ============================================================
# Simulated Components (Mocked)
# ============================================================

class FakeVision:
    """Mock Vision — trả về kết quả detect ngẫu nhiên.
    70% chance tìm thấy template (giống thực tế).
    Simulate CPU work bằng sleep nhẹ.
    """
    def __init__(self, find_rate=0.7, latency_ms=20):
        self.find_rate = find_rate
        self.latency_ms = latency_ms
        self.call_count = 0
        self._lock = threading.Lock()
    
    def find_template_direct(self, filepath, threshold=0.85, debug=False, frame_bytes=None):
        with self._lock:
            self.call_count += 1
        time.sleep(self.latency_ms / 1000.0)  # Simulate CV processing
        if random.random() < self.find_rate:
            # Trả về tọa độ giả (center_x, center_y, score)
            return (random.randint(100, 800), random.randint(100, 600), 0.92)
        return None


class FakePage:
    """Mock Playwright Page — trả bytes screenshot giả."""
    def __init__(self, latency_ms=10):
        self.latency_ms = latency_ms
        self.screenshot_count = 0
        self._lock = threading.Lock()
        self._closed = False
        # Giả lập DPR
        self.mouse = MagicMock()
        self.keyboard = MagicMock()
        self.frames = [MagicMock()]
        self.main_frame = self.frames[0]
        self.context = MagicMock()
    
    def screenshot(self):
        with self._lock:
            self.screenshot_count += 1
        if self._closed:
            raise Exception("Page is closed")
        time.sleep(self.latency_ms / 1000.0)
        # Return 100 bytes giả (vision sẽ mock nên ko cần ảnh thật)
        return b'\x89PNG' + os.urandom(96)
    
    def evaluate(self, script, *args, **kwargs):
        if "devicePixelRatio" in str(script):
            return 1.0
        if "innerWidth" in str(script):
            return {"w": 1280, "h": 720}
        if "canvas" in str(script):
            return False
        return None


class FakeBotAction:
    """Mock BotAction — ghi nhận clicks và key presses."""
    def __init__(self, page=None, debug_visual_var=None):
        self.page = page
        self.click_count = 0
        self.key_count = 0
        self._lock = threading.Lock()
    
    def click_at(self, x, y, randomize=True):
        with self._lock:
            self.click_count += 1
        time.sleep(0.005)  # Simulate CDP dispatch
    
    def press_key(self, key):
        with self._lock:
            self.key_count += 1


# ============================================================
# Simulated Loop Graph (like the real tab_accounts worker)
# ============================================================

def create_test_loop():
    """Tạo một loop graph mô phỏng thực tế:
    Start → Condition(hp_bar) → [true] Click(potion) → Delay(500ms) → Macro → End
                               → [false] → Delay(1000ms) → End
    """
    return {
        "nodes": {
            "start":  {"id": "start",  "type": "Start",     "data": {"title": "Start"}},
            "cond1":  {"id": "cond1",  "type": "Condition",  "data": {"image_name": "hp_bar"}},
            "click1": {"id": "click1", "type": "Click",      "data": {"image_name": "potion"}},
            "delay1": {"id": "delay1", "type": "Delay",      "data": {"time": 500}},
            "macro1": {"id": "macro1", "type": "Macro",      "data": {"macro_name": "HealMacro"}},
            "delay2": {"id": "delay2", "type": "Delay",      "data": {"time": 1000}},
            "end":    {"id": "end",    "type": "End",        "data": {}},
        },
        "edges": [
            {"from": "start",  "from_pin": "out",   "to": "cond1"},
            {"from": "cond1",  "from_pin": "true",  "to": "click1"},
            {"from": "cond1",  "from_pin": "false", "to": "delay2"},
            {"from": "click1", "from_pin": "out",   "to": "delay1"},
            {"from": "delay1", "from_pin": "out",   "to": "macro1"},
            {"from": "macro1", "from_pin": "true",  "to": "end"},
            {"from": "macro1", "from_pin": "false", "to": "end"},
            {"from": "delay2", "from_pin": "out",   "to": "end"},
        ]
    }


# ============================================================
# Account Worker Simulator (mirrors _account_worker_thread)
# ============================================================

def _db_retry(fn, *args, max_retries=5, **kwargs):
    """Retry DB operation on 'database is locked' errors."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(0.05 * (attempt + 1))
                continue
            raise


def simulate_account_worker(
    acc_name, loop_graph, vision, state_db, gui_queue,
    account_running, stats, max_loops=3
):
    """
    Mô phỏng _account_worker_thread thật trong tab_accounts.py.
    
    Pipeline mỗi vòng loop:
    1. Kết nối (mock) → screenshot → vision detect → click/delay → next node
    2. Lặp lại max_loops lần rồi dừng
    """
    page = FakePage(latency_ms=random.randint(5, 20))
    bot = FakeBotAction(page=page)
    
    nodes = loop_graph["nodes"]
    edges = loop_graph["edges"]
    
    def get_next(nid, pin):
        for e in edges:
            if e["from"] == nid and e["from_pin"] == pin:
                return e["to"]
        return None
    
    def get_start():
        for nid, n in nodes.items():
            if n["type"] == "Start":
                return nid
        return None
    
    # Phase 1: Connect
    _db_retry(state_db.save_account_state, acc_name, status="connecting", port=9222)
    time.sleep(random.uniform(0.01, 0.05))  # Simulated stagger
    _db_retry(state_db.save_account_state, acc_name, status="connected")
    
    loop_count = 0
    total_screenshots = 0
    total_detects = 0
    total_clicks = 0
    
    # Phase 2: Run loop graph
    while account_running.get(acc_name, False) and loop_count < max_loops:
        current_nid = get_start()
        
        while current_nid and current_nid in nodes and account_running.get(acc_name, False):
            n = nodes[current_nid]
            ntype = n["type"]
            ndata = n.get("data", {})
            next_nid = None
            
            _db_retry(state_db.save_account_state, acc_name, status="running", current_node=current_nid)
            
            if ntype == "Start":
                next_nid = get_next(current_nid, "out")
                time.sleep(0.01)
            
            elif ntype == "Delay":
                delay_ms = float(ndata.get("time", 500))
                # Giảm delay thực tế để test nhanh hơn (1/50 thời gian thật)
                time.sleep(delay_ms / 50000.0)
                _db_retry(state_db.log_action, acc_name, "delay", f"{delay_ms:.0f}ms")
                next_nid = get_next(current_nid, "out")
            
            elif ntype == "Condition":
                img_name = ndata.get("image_name", "unknown")
                
                # Screenshot + detect
                frame_bytes = page.screenshot()
                total_screenshots += 1
                
                res = vision.find_template_direct(
                    f"icons/{img_name}.png", threshold=0.85,
                    debug=False, frame_bytes=frame_bytes
                )
                total_detects += 1
                
                if res:
                    next_nid = get_next(current_nid, "true")
                    _db_retry(state_db.log_action, acc_name, "condition", img_name, "TRUE")
                else:
                    next_nid = get_next(current_nid, "false")
                    _db_retry(state_db.log_action, acc_name, "condition", img_name, "FALSE")
                
                time.sleep(0.01)
            
            elif ntype == "Click":
                img_name = ndata.get("image_name", "unknown")
                frame_bytes = page.screenshot()
                total_screenshots += 1
                
                res = vision.find_template_direct(
                    f"icons/{img_name}.png", threshold=0.85,
                    debug=False, frame_bytes=frame_bytes
                )
                total_detects += 1
                
                if res:
                    x, y, score = res
                    bot.click_at(x, y, randomize=True)
                    total_clicks += 1
                    _db_retry(state_db.log_action, acc_name, "click", img_name, "OK")
                else:
                    _db_retry(state_db.log_action, acc_name, "click", img_name, "NOT_VISIBLE")
                time.sleep(0.01)
                next_nid = get_next(current_nid, "out")
            
            elif ntype == "Macro":
                # Macro = chuỗi nhỏ: 3 screenshot + 2 click
                mac_name = ndata.get("macro_name", "?")
                _db_retry(state_db.log_action, acc_name, "macro_start", mac_name)
                
                macro_ok = True
                for step in range(3):
                    frame_bytes = page.screenshot()
                    total_screenshots += 1
                    res = vision.find_template_direct(
                        f"icons/macro_step_{step}.png", threshold=0.85,
                        frame_bytes=frame_bytes
                    )
                    total_detects += 1
                    if res:
                        bot.click_at(res[0], res[1])
                        total_clicks += 1
                    else:
                        macro_ok = False
                    time.sleep(0.005)
                
                _db_retry(state_db.log_action, acc_name, "macro_done", mac_name,
                          "OK" if macro_ok else "FAIL")
                next_nid = get_next(current_nid, "true" if macro_ok else "false")
            
            elif ntype == "End":
                _db_retry(state_db.log_action, acc_name, "end", "Loop finished")
                break
            
            current_nid = next_nid
        
        loop_count += 1
        gui_queue.put(("log", f"[{acc_name}] Loop {loop_count}/{max_loops} done"))
    
    # Phase 3: Cleanup
    _db_retry(state_db.save_account_state, acc_name, status="idle", current_node="")
    account_running[acc_name] = False
    
    with stats["lock"]:
        stats["screenshots"] += total_screenshots
        stats["detects"] += total_detects
        stats["clicks"] += total_clicks
        stats["loops_completed"] += loop_count
        stats["workers_done"] += 1


# ============================================================
# TESTS
# ============================================================

class TestE2EStress150Accounts:
    """Mô phỏng 150 accounts chạy loop đồng thời."""

    def test_150_accounts_full_pipeline(self, temp_dir):
        """
        🔥 TEST CHÍNH: 150 accounts × 3 loops mỗi account.

        Mỗi account chạy pipeline đầy đủ:
        - Screenshot (mock) → Vision detect (mock 20ms) → Click (mock)
        - StateDB ghi trạng thái + log mỗi bước
        - GUI queue nhận log messages
        - Tất cả chạy song song 150 threads
        """
        NUM_ACCOUNTS = 150
        MAX_LOOPS = 3
        
        # Setup
        db = StateDB(db_path=os.path.join(temp_dir, "e2e_stress.db"))
        vision = FakeVision(find_rate=0.7, latency_ms=20)
        gui_queue = queue.Queue()
        account_running = {}
        loop_graph = create_test_loop()
        
        stats = {
            "screenshots": 0, "detects": 0, "clicks": 0,
            "loops_completed": 0, "workers_done": 0,
            "lock": threading.Lock()
        }
        
        # Kích hoạt tất cả accounts
        for i in range(NUM_ACCOUNTS):
            account_running[f"Acc_{i:04d}"] = True
        
        # Launch
        t0 = time.perf_counter()
        threads = []
        for i in range(NUM_ACCOUNTS):
            acc_name = f"Acc_{i:04d}"
            t = threading.Thread(
                target=simulate_account_worker,
                args=(acc_name, loop_graph, vision, db, gui_queue,
                      account_running, stats, MAX_LOOPS),
                daemon=True
            )
            threads.append(t)
            t.start()
            # Stagger launch (2ms giữa mỗi account)
            if i % 10 == 0:
                time.sleep(0.02)
        
        # Wait
        for t in threads:
            t.join(timeout=120)
        elapsed = time.perf_counter() - t0
        
        # Collect results
        alive = sum(1 for t in threads if t.is_alive())
        gui_msgs = gui_queue.qsize()
        
        # Assertions
        assert alive == 0, f"{alive} threads still alive!"
        assert stats["workers_done"] == NUM_ACCOUNTS, \
            f"Only {stats['workers_done']}/{NUM_ACCOUNTS} workers completed"
        assert stats["loops_completed"] == NUM_ACCOUNTS * MAX_LOOPS, \
            f"Only {stats['loops_completed']}/{NUM_ACCOUNTS * MAX_LOOPS} loops completed"
        
        # Verify DB state
        all_states = db.get_all_account_states()
        assert len(all_states) == NUM_ACCOUNTS
        idle_count = sum(1 for s in all_states if s["status"] == "idle")
        assert idle_count == NUM_ACCOUNTS, \
            f"Only {idle_count}/{NUM_ACCOUNTS} accounts returned to idle"
        
        print(f"\n{'='*60}")
        print(f"  🔥 E2E STRESS TEST: {NUM_ACCOUNTS} ACCOUNTS × {MAX_LOOPS} LOOPS")
        print(f"{'='*60}")
        print(f"  ⏱  Tổng thời gian:    {elapsed:.2f}s")
        print(f"  📸 Tổng screenshots:   {stats['screenshots']:,}")
        print(f"  🔍 Tổng vision detect: {stats['detects']:,}")
        print(f"  🖱  Tổng clicks:        {stats['clicks']:,}")
        print(f"  🔄 Loops hoàn thành:   {stats['loops_completed']:,}")
        print(f"  📩 GUI messages:       {gui_msgs:,}")
        print(f"  📊 Vision call count:  {vision.call_count:,}")
        print(f"  ✅ Tất cả {NUM_ACCOUNTS} accounts về idle")
        print(f"{'='*60}")
        
        db.close()

    def test_150_accounts_graceful_stop_midway(self, temp_dir):
        """
        Test dừng 150 accounts giữa chừng (simulate user bấm Stop All).
        Verify: không thread nào bị treo, tất cả cleanup đúng.
        """
        NUM_ACCOUNTS = 150
        
        db = StateDB(db_path=os.path.join(temp_dir, "e2e_stop.db"))
        vision = FakeVision(find_rate=0.7, latency_ms=15)
        gui_queue = queue.Queue()
        account_running = {}
        loop_graph = create_test_loop()
        
        stats = {
            "screenshots": 0, "detects": 0, "clicks": 0,
            "loops_completed": 0, "workers_done": 0,
            "lock": threading.Lock()
        }
        
        for i in range(NUM_ACCOUNTS):
            account_running[f"Stop_{i:04d}"] = True
        
        threads = []
        for i in range(NUM_ACCOUNTS):
            acc_name = f"Stop_{i:04d}"
            t = threading.Thread(
                target=simulate_account_worker,
                args=(acc_name, loop_graph, vision, db, gui_queue,
                      account_running, stats, 999),  # Many loops
                daemon=True
            )
            threads.append(t)
            t.start()
        
        # Đợi 2 giây rồi stop all
        time.sleep(2.0)
        t0_stop = time.perf_counter()
        for key in list(account_running.keys()):
            account_running[key] = False
        
        for t in threads:
            t.join(timeout=15)
        stop_elapsed = time.perf_counter() - t0_stop
        
        alive = sum(1 for t in threads if t.is_alive())
        
        assert alive == 0, f"{alive} threads still alive after stop!"
        assert stop_elapsed < 10.0, f"Stop took {stop_elapsed:.1f}s (too slow!)"
        assert stats["workers_done"] == NUM_ACCOUNTS
        
        # All should be idle
        all_states = db.get_all_account_states()
        idle_count = sum(1 for s in all_states if s["status"] == "idle")
        assert idle_count == NUM_ACCOUNTS
        
        print(f"\n  ✅ 150 accounts stopped gracefully in {stop_elapsed:.2f}s")
        print(f"     Loops completed before stop: {stats['loops_completed']}")
        print(f"     Screenshots taken: {stats['screenshots']:,}")
        
        db.close()

    def test_150_accounts_with_random_crashes(self, temp_dir):
        """
        10% accounts gặp lỗi random (simulate page crash).
        Verify: lỗi được xử lý, không crash hệ thống.
        """
        NUM_ACCOUNTS = 150
        CRASH_RATE = 0.10
        
        db = StateDB(db_path=os.path.join(temp_dir, "e2e_crash.db"))
        
        # Vision thỉnh thoảng raise exception
        class CrashyVision(FakeVision):
            def find_template_direct(self, *args, **kwargs):
                if random.random() < CRASH_RATE:
                    raise Exception("Simulated vision crash!")
                return super().find_template_direct(*args, **kwargs)
        
        vision = CrashyVision(find_rate=0.7, latency_ms=15)
        gui_queue = queue.Queue()
        account_running = {}
        loop_graph = create_test_loop()
        
        stats = {
            "screenshots": 0, "detects": 0, "clicks": 0,
            "loops_completed": 0, "workers_done": 0,
            "lock": threading.Lock()
        }
        
        errors_caught = []
        
        def resilient_worker(acc_name, *worker_args):
            """Worker with error handling (like the real code)."""
            try:
                simulate_account_worker(acc_name, *worker_args)
            except Exception as e:
                errors_caught.append((acc_name, str(e)))
                account_running[acc_name] = False
                _db_retry(db.save_account_state, acc_name, status="error", error_msg=str(e)[:100])
                with stats["lock"]:
                    stats["workers_done"] += 1
        
        for i in range(NUM_ACCOUNTS):
            account_running[f"Crash_{i:04d}"] = True
        
        threads = []
        for i in range(NUM_ACCOUNTS):
            acc_name = f"Crash_{i:04d}"
            t = threading.Thread(
                target=resilient_worker,
                args=(acc_name, loop_graph, vision, db, gui_queue,
                      account_running, stats, 3),
                daemon=True
            )
            threads.append(t)
            t.start()
            if i % 10 == 0:
                time.sleep(0.02)
        
        for t in threads:
            t.join(timeout=120)
        
        alive = sum(1 for t in threads if t.is_alive())
        assert alive == 0, f"{alive} threads still alive!"
        assert stats["workers_done"] == NUM_ACCOUNTS, \
            f"Only {stats['workers_done']}/{NUM_ACCOUNTS} workers finished"
        
        # Some may have errored, that's expected
        all_states = db.get_all_account_states()
        error_count = sum(1 for s in all_states if s["status"] == "error")
        idle_count = sum(1 for s in all_states if s["status"] == "idle")
        
        print(f"\n  ✅ 150 accounts with {CRASH_RATE*100:.0f}% crash rate:")
        print(f"     Completed normally: {idle_count}")
        print(f"     Crashed (handled):  {error_count}")
        print(f"     Errors caught:      {len(errors_caught)}")
        print(f"     Total detects:      {stats['detects']:,}")
        
        assert idle_count + error_count == NUM_ACCOUNTS
        db.close()

    def test_gui_queue_throughput_under_150_accounts(self):
        """
        Test GUI queue xử lý messages từ 150 accounts.
        Mô phỏng: mỗi account gửi ~20 messages trong 1 loop.
        """
        NUM_ACCOUNTS = 150
        MSGS_PER_ACCOUNT = 20
        gui_queue = queue.Queue()
        
        def producer(acc_id):
            for i in range(MSGS_PER_ACCOUNT):
                gui_queue.put(("log", f"[Acc_{acc_id:04d}] Step {i}"))
                gui_queue.put(("status", f"Acc_{acc_id:04d}", "running"))
                time.sleep(0.001)
        
        t0 = time.perf_counter()
        threads = [threading.Thread(target=producer, args=(i,)) for i in range(NUM_ACCOUNTS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        produce_time = time.perf_counter() - t0
        
        total_expected = NUM_ACCOUNTS * MSGS_PER_ACCOUNT * 2  # log + status
        actual = gui_queue.qsize()
        
        # Consume (simulate GUI after() tick — process 50 per tick at 60fps)
        t0 = time.perf_counter()
        consumed = 0
        ticks = 0
        while not gui_queue.empty():
            batch = 0
            while batch < 50 and not gui_queue.empty():
                try:
                    gui_queue.get_nowait()
                    consumed += 1
                    batch += 1
                except queue.Empty:
                    break
            ticks += 1
            # Simulate 16ms frame time (60fps)
            time.sleep(0.001)  # Reduced for test speed
        consume_time = time.perf_counter() - t0
        
        assert consumed == total_expected, f"Lost messages: {total_expected - consumed}"
        
        print(f"\n  ✅ GUI Queue: {total_expected:,} messages")
        print(f"     Produce: {produce_time*1000:.0f}ms")
        print(f"     Consume: {consume_time*1000:.0f}ms ({ticks} ticks)")

    def test_state_db_consistency_after_150_accounts(self, temp_dir):
        """
        Verify StateDB data integrity sau khi 150 accounts chạy xong.
        Kiểm tra: không mất dữ liệu, logs đầy đủ, trạng thái đúng.
        """
        NUM_ACCOUNTS = 150
        
        db = StateDB(db_path=os.path.join(temp_dir, "e2e_consistency.db"))
        vision = FakeVision(find_rate=0.8, latency_ms=10)
        gui_queue = queue.Queue()
        account_running = {}
        loop_graph = create_test_loop()
        
        stats = {
            "screenshots": 0, "detects": 0, "clicks": 0,
            "loops_completed": 0, "workers_done": 0,
            "lock": threading.Lock()
        }
        
        for i in range(NUM_ACCOUNTS):
            account_running[f"Con_{i:04d}"] = True
        
        threads = []
        for i in range(NUM_ACCOUNTS):
            acc_name = f"Con_{i:04d}"
            t = threading.Thread(
                target=simulate_account_worker,
                args=(acc_name, loop_graph, vision, db, gui_queue,
                      account_running, stats, 2),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=120)
        
        # Verify consistency
        all_states = db.get_all_account_states()
        assert len(all_states) == NUM_ACCOUNTS
        
        # Every account should have some logs
        accounts_with_logs = 0
        for i in range(NUM_ACCOUNTS):
            logs = db.get_recent_logs(f"Con_{i:04d}", limit=5)
            if len(logs) > 0:
                accounts_with_logs += 1
        
        assert accounts_with_logs == NUM_ACCOUNTS, \
            f"Only {accounts_with_logs}/{NUM_ACCOUNTS} have logs"
        
        # Most recent logs should contain "end" for each account
        end_count = 0
        for i in range(NUM_ACCOUNTS):
            logs = db.get_recent_logs(f"Con_{i:04d}", limit=10)
            actions = [l["action"] for l in logs]
            if "end" in actions:
                end_count += 1
        
        assert end_count == NUM_ACCOUNTS, \
            f"Only {end_count}/{NUM_ACCOUNTS} accounts have 'end' in logs"
        
        print(f"\n  ✅ DB Consistency: {NUM_ACCOUNTS} accounts")
        print(f"     All have logs: YES")
        print(f"     All ended correctly: YES")
        print(f"     Total vision calls: {vision.call_count:,}")
        
        db.close()
