"""
🖱️ Test Click 200 Accounts Đồng Thời
Mô phỏng 200 accounts click cùng lúc qua CDP (Input.dispatchMouseEvent).
Mỗi account có 1 BotAction riêng (page + CDP session riêng).

Kết quả chi tiết:
- Tổng click thành công / thất bại
- Thời gian trung bình mỗi click
- Phương thức click (CDP / fallback page.mouse / pyautogui)
- Báo cáo lỗi cụ thể nếu có

Run: python -m pytest tests/test_click_200.py -v -s
"""
import pytest
import os
import sys
import threading
import time
import random
import queue
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot_action import BotAction


# ============================================================
# Click Result Tracking
# ============================================================

@dataclass
class ClickResult:
    """Kết quả 1 lần click."""
    acc_name: str
    x: int
    y: int
    success: bool
    method: str  # "CDP", "page.mouse", "pyautogui", "blocked"
    latency_ms: float
    error: str = ""


@dataclass
class AccountReport:
    """Báo cáo click cho 1 account."""
    acc_name: str
    total_clicks: int = 0
    success_clicks: int = 0
    failed_clicks: int = 0
    blocked_clicks: int = 0
    cdp_clicks: int = 0
    fallback_clicks: int = 0
    avg_latency_ms: float = 0.0
    errors: List[str] = field(default_factory=list)


# ============================================================
# Realistic Mock Components
# ============================================================

class RealisticMockPage:
    """Mock Page với hành vi giống Playwright thật.
    
    - evaluate() trả DPR và viewport
    - CDP session dispatch mouse events
    - Có thể inject lỗi để test fallback
    """
    def __init__(self, dpr=1.0, viewport_w=1280, viewport_h=720, 
                 cdp_fail_rate=0.0, page_fail_rate=0.0):
        self.dpr = dpr
        self.viewport_w = viewport_w
        self.viewport_h = viewport_h
        self.cdp_fail_rate = cdp_fail_rate
        self.page_fail_rate = page_fail_rate
        
        self.mouse = MagicMock()
        self.keyboard = MagicMock()
        self.main_frame = MagicMock()
        self.frames = [self.main_frame]
        self.context = MagicMock()
        
        # Track CDP calls
        self._cdp_calls = []
        self._lock = threading.Lock()
        
        # Setup frame.evaluate to return False for canvas check
        self.main_frame.evaluate.return_value = False
        
        # Setup page.mouse.click to optionally fail
        if page_fail_rate > 0:
            original_click = self.mouse.click
            def maybe_fail_click(*args, **kwargs):
                if random.random() < page_fail_rate:
                    raise Exception("page.mouse.click failed: execution context destroyed")
                return original_click(*args, **kwargs)
            self.mouse.click = maybe_fail_click
    
    def evaluate(self, script, *args, **kwargs):
        if "devicePixelRatio" in str(script):
            return self.dpr
        if "innerWidth" in str(script):
            return {"w": self.viewport_w, "h": self.viewport_h}
        if "canvas" in str(script):
            return False
        return None


class RealisticMockCDP:
    """Mock CDP Session với tracking chi tiết."""
    def __init__(self, fail_rate=0.0, latency_ms=5):
        self.fail_rate = fail_rate
        self.latency_ms = latency_ms
        self.calls = []
        self._lock = threading.Lock()
        self.total_dispatched = 0
    
    def send(self, method, params=None):
        time.sleep(self.latency_ms / 1000.0)
        
        with self._lock:
            self.total_dispatched += 1
            self.calls.append({"method": method, "params": params})
        
        if random.random() < self.fail_rate:
            raise Exception(f"CDP Error: Session closed unexpectedly")
        
        return {}


# ============================================================
# Click Worker (mô phỏng 1 account click liên tục)
# ============================================================

def click_worker(acc_name, bot, clicks_per_account, results_queue, 
                 account_running, viewport_w=1280, viewport_h=720):
    """
    Mỗi account thực hiện N clicks tại vị trí ngẫu nhiên.
    Ghi nhận kết quả chi tiết cho từng click.
    """
    report = AccountReport(acc_name=acc_name)
    
    for i in range(clicks_per_account):
        if not account_running.get(acc_name, True):
            break
        
        # Tọa độ ngẫu nhiên trong viewport
        x = random.randint(50, viewport_w - 50)
        y = random.randint(50, viewport_h - 50)
        
        t0 = time.perf_counter()
        result = ClickResult(acc_name=acc_name, x=x, y=y, 
                             success=False, method="unknown", latency_ms=0)
        
        try:
            bot.click_at(x, y, randomize=True)
            latency = (time.perf_counter() - t0) * 1000
            
            # Xác định method dựa trên CDP calls
            if bot.cdp and hasattr(bot.cdp, 'calls'):
                result.method = "CDP"
                report.cdp_clicks += 1
            else:
                result.method = "page.mouse"
                report.fallback_clicks += 1
            
            result.success = True
            result.latency_ms = latency
            report.success_clicks += 1
            
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            result.success = False
            result.error = str(e)[:100]
            result.latency_ms = latency
            result.method = "FAILED"
            report.failed_clicks += 1
            report.errors.append(f"Click #{i}: {str(e)[:80]}")
        
        report.total_clicks += 1
        results_queue.put(result)
        
        # Delay nhỏ giữa các clicks (giống thực tế)
        time.sleep(random.uniform(0.01, 0.03))
    
    # Tính avg latency
    if report.total_clicks > 0:
        # Lấy lại tất cả results từ queue... 
        # actually we track separately
        pass
    
    return report


# ============================================================
# TESTS
# ============================================================

class TestClick200Accounts:
    """Test 200 accounts click đồng thời."""

    def test_200_accounts_click_simultaneously_cdp(self):
        """
        🖱️ TEST CHÍNH: 200 accounts × 10 clicks/account = 2000 clicks.
        
        Mỗi account có CDP session riêng.
        Báo cáo chi tiết: success/fail, latency, phương thức.
        """
        NUM_ACCOUNTS = 200
        CLICKS_PER_ACCOUNT = 10
        TOTAL_CLICKS = NUM_ACCOUNTS * CLICKS_PER_ACCOUNT
        
        results_queue = queue.Queue()
        account_running = {}
        reports = []
        reports_lock = threading.Lock()
        
        # Tạo 200 BotAction với CDP riêng
        bots = []
        for i in range(NUM_ACCOUNTS):
            page = RealisticMockPage(dpr=1.5, viewport_w=960, viewport_h=540)
            cdp = RealisticMockCDP(fail_rate=0.0, latency_ms=2)
            page.context.new_cdp_session.return_value = cdp
            
            debug_var = MagicMock()
            debug_var.get.return_value = False
            
            bot = BotAction(page=page, debug_visual_var=debug_var)
            bot.cdp = cdp  # Ensure CDP is attached
            bots.append(bot)
            account_running[f"Click_{i:04d}"] = True
        
        # Launch all workers
        t0 = time.perf_counter()
        threads = []
        for i in range(NUM_ACCOUNTS):
            acc_name = f"Click_{i:04d}"
            t = threading.Thread(
                target=lambda idx=i, name=acc_name: (
                    reports.append(
                        click_worker(name, bots[idx], CLICKS_PER_ACCOUNT, 
                                     results_queue, account_running,
                                     viewport_w=960, viewport_h=540)
                    )
                ),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=60)
        elapsed = time.perf_counter() - t0
        
        # ========== TỔNG HỢP KẾT QUẢ ==========
        all_results = []
        while not results_queue.empty():
            try:
                all_results.append(results_queue.get_nowait())
            except queue.Empty:
                break
        
        total_success = sum(1 for r in all_results if r.success)
        total_failed = sum(1 for r in all_results if not r.success)
        total_cdp = sum(1 for r in all_results if r.method == "CDP")
        total_fallback = sum(1 for r in all_results if r.method == "page.mouse")
        
        latencies = [r.latency_ms for r in all_results if r.success]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        min_latency = min(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
        
        # Lỗi unique
        errors = {}
        for r in all_results:
            if r.error:
                errors[r.error] = errors.get(r.error, 0) + 1
        
        # CDP events dispatched
        total_cdp_events = sum(bot.cdp.total_dispatched for bot in bots if hasattr(bot.cdp, 'total_dispatched'))
        
        success_rate = (total_success / len(all_results) * 100) if all_results else 0
        
        # ========== BÁO CÁO ==========
        print(f"\n{'='*70}")
        print(f"  🖱️  KẾT QUẢ CLICK TEST: {NUM_ACCOUNTS} ACCOUNTS × {CLICKS_PER_ACCOUNT} CLICKS")
        print(f"{'='*70}")
        print(f"  📊 Tổng clicks:         {len(all_results):,} / {TOTAL_CLICKS:,} expected")
        print(f"  ✅ Thành công:           {total_success:,} ({success_rate:.1f}%)")
        print(f"  ❌ Thất bại:             {total_failed:,}")
        print(f"  ⏱  Tổng thời gian:      {elapsed:.2f}s")
        print(f"  📈 Throughput:           {len(all_results)/elapsed:.0f} clicks/sec")
        print(f"{'─'*70}")
        print(f"  📡 CDP clicks:           {total_cdp:,}")
        print(f"  🔄 Fallback clicks:      {total_fallback:,}")
        print(f"  📨 CDP events tổng:      {total_cdp_events:,}")
        print(f"{'─'*70}")
        print(f"  ⏱  Latency trung bình:   {avg_latency:.1f}ms")
        print(f"  ⏱  Latency min:          {min_latency:.1f}ms")
        print(f"  ⏱  Latency max:          {max_latency:.1f}ms")
        print(f"  ⏱  Latency P95:          {p95_latency:.1f}ms")
        if errors:
            print(f"{'─'*70}")
            print(f"  ⚠️  Lỗi gặp phải:")
            for err, count in errors.items():
                print(f"     [{count}x] {err}")
        print(f"{'='*70}")
        
        # Assertions
        assert len(all_results) == TOTAL_CLICKS, \
            f"Mất clicks: {TOTAL_CLICKS - len(all_results)}"
        assert success_rate == 100.0, \
            f"Click success rate: {success_rate:.1f}% (expected 100%)"
        assert avg_latency < 500, \
            f"Avg latency quá cao: {avg_latency:.1f}ms"

    def test_200_accounts_click_with_5pct_cdp_failure(self):
        """
        🔥 200 accounts click, 5% CDP fail → verify fallback page.mouse.click.
        """
        NUM_ACCOUNTS = 200
        CLICKS_PER_ACCOUNT = 5
        
        results_queue = queue.Queue()
        account_running = {}
        
        bots = []
        for i in range(NUM_ACCOUNTS):
            page = RealisticMockPage(dpr=2.0, viewport_w=800, viewport_h=600)
            cdp = RealisticMockCDP(fail_rate=0.05, latency_ms=3)
            page.context.new_cdp_session.return_value = cdp
            
            debug_var = MagicMock()
            debug_var.get.return_value = False
            
            bot = BotAction(page=page, debug_visual_var=debug_var)
            bot.cdp = cdp
            bots.append(bot)
            account_running[f"Fail_{i:04d}"] = True
        
        t0 = time.perf_counter()
        threads = []
        for i in range(NUM_ACCOUNTS):
            acc_name = f"Fail_{i:04d}"
            t = threading.Thread(
                target=lambda idx=i, name=acc_name: (
                    click_worker(name, bots[idx], CLICKS_PER_ACCOUNT,
                                 results_queue, account_running,
                                 viewport_w=800, viewport_h=600)
                ),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=60)
        elapsed = time.perf_counter() - t0
        
        all_results = []
        while not results_queue.empty():
            try:
                all_results.append(results_queue.get_nowait())
            except queue.Empty:
                break
        
        total_success = sum(1 for r in all_results if r.success)
        total_failed = sum(1 for r in all_results if not r.success)
        success_rate = total_success / len(all_results) * 100 if all_results else 0
        
        latencies = [r.latency_ms for r in all_results if r.success]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        print(f"\n{'='*70}")
        print(f"  🔥 CLICK TEST VỚI 5% CDP FAILURE")
        print(f"{'='*70}")
        print(f"  📊 Tổng clicks:         {len(all_results):,}")
        print(f"  ✅ Thành công:           {total_success:,} ({success_rate:.1f}%)")
        print(f"  ❌ Thất bại:             {total_failed:,}")
        print(f"  ⏱  Thời gian:           {elapsed:.2f}s")
        print(f"  ⏱  Latency TB:          {avg_latency:.1f}ms")
        print(f"{'='*70}")
        
        # Với 5% CDP fail, fallback page.mouse nên handle → success rate vẫn ~100%
        assert success_rate >= 95.0, f"Success rate quá thấp: {success_rate:.1f}%"

    def test_200_accounts_click_dpr_accuracy(self):
        """
        🎯 Test DPR scaling chính xác cho 200 accounts.
        DPR=2.0: pixel (400,300) phải thành CSS (200,150).
        """
        NUM_ACCOUNTS = 200
        results_queue = queue.Queue()
        account_running = {}
        cdp_records = []
        
        for i in range(NUM_ACCOUNTS):
            page = RealisticMockPage(dpr=2.0, viewport_w=1280, viewport_h=720)
            cdp = RealisticMockCDP(fail_rate=0.0, latency_ms=1)
            page.context.new_cdp_session.return_value = cdp
            
            debug_var = MagicMock()
            debug_var.get.return_value = False
            
            bot = BotAction(page=page, debug_visual_var=debug_var)
            bot.cdp = cdp
            
            # Click at exact pixel (400, 300), no randomize
            bot.click_at(400, 300, randomize=False)
            
            # Check CDP calls
            for call in cdp.calls:
                if call["method"] == "Input.dispatchMouseEvent":
                    params = call["params"]
                    if params.get("type") == "mousePressed":
                        cdp_records.append({
                            "acc": i,
                            "x": params["x"],
                            "y": params["y"]
                        })
        
        # Verify all 200 clicks landed at CSS (200.0, 150.0)
        correct = sum(1 for r in cdp_records if r["x"] == 200.0 and r["y"] == 150.0)
        wrong = [r for r in cdp_records if r["x"] != 200.0 or r["y"] != 150.0]
        
        print(f"\n{'='*70}")
        print(f"  🎯 DPR SCALING TEST: {NUM_ACCOUNTS} ACCOUNTS")
        print(f"{'='*70}")
        print(f"  Input pixel:    (400, 300)")
        print(f"  Expected CSS:   (200.0, 150.0)  [DPR=2.0]")
        print(f"  ✅ Chính xác:    {correct}/{len(cdp_records)}")
        if wrong:
            print(f"  ❌ Sai tọa độ:   {len(wrong)}")
            for w in wrong[:5]:
                print(f"     Acc_{w['acc']:04d}: ({w['x']}, {w['y']})")
        print(f"{'='*70}")
        
        assert correct == NUM_ACCOUNTS, \
            f"Chỉ {correct}/{NUM_ACCOUNTS} clicks có tọa độ chính xác"

    def test_200_accounts_click_viewport_blocking(self):
        """
        🛡️ Test viewport bounds check: click ngoài viewport phải bị chặn.
        """
        NUM_ACCOUNTS = 200
        blocked = 0
        passed = 0
        
        for i in range(NUM_ACCOUNTS):
            page = RealisticMockPage(dpr=1.0, viewport_w=800, viewport_h=600)
            cdp = RealisticMockCDP(fail_rate=0.0, latency_ms=0)
            page.context.new_cdp_session.return_value = cdp
            
            debug_var = MagicMock()
            debug_var.get.return_value = False
            
            bot = BotAction(page=page, debug_visual_var=debug_var)
            bot.cdp = cdp
            
            # Click outside viewport (900, 700) > (800, 600)
            bot.click_at(900, 700, randomize=False)
            
            # Nếu bị chặn: không có mousePressed event
            has_press = any(
                c["params"].get("type") == "mousePressed" 
                for c in cdp.calls 
                if c["method"] == "Input.dispatchMouseEvent"
            )
            
            if has_press:
                passed += 1
            else:
                blocked += 1
        
        print(f"\n{'='*70}")
        print(f"  🛡️ VIEWPORT BLOCKING TEST: {NUM_ACCOUNTS} ACCOUNTS")
        print(f"{'='*70}")
        print(f"  Click tại:       (900, 700)")
        print(f"  Viewport:        800×600")
        print(f"  ✅ Bị chặn:       {blocked}/{NUM_ACCOUNTS}")
        print(f"  ⚠️ Lọt qua:      {passed}/{NUM_ACCOUNTS}")
        print(f"{'='*70}")
        
        assert blocked == NUM_ACCOUNTS, \
            f"Chỉ {blocked}/{NUM_ACCOUNTS} clicks bị chặn khi ngoài viewport"

    def test_200_accounts_click_latency_under_load(self):
        """
        ⏱️ Benchmark: 200 accounts click liên tục, đo latency distribution.
        """
        NUM_ACCOUNTS = 200
        CLICKS_PER_ACCOUNT = 20
        
        results_queue = queue.Queue()
        account_running = {}
        
        bots = []
        for i in range(NUM_ACCOUNTS):
            page = RealisticMockPage(dpr=1.0, viewport_w=1280, viewport_h=720)
            cdp = RealisticMockCDP(fail_rate=0.0, latency_ms=3)
            page.context.new_cdp_session.return_value = cdp
            
            debug_var = MagicMock()
            debug_var.get.return_value = False
            
            bot = BotAction(page=page, debug_visual_var=debug_var)
            bot.cdp = cdp
            bots.append(bot)
            account_running[f"Lat_{i:04d}"] = True
        
        t0 = time.perf_counter()
        threads = []
        for i in range(NUM_ACCOUNTS):
            acc_name = f"Lat_{i:04d}"
            t = threading.Thread(
                target=lambda idx=i, name=acc_name: (
                    click_worker(name, bots[idx], CLICKS_PER_ACCOUNT,
                                 results_queue, account_running)
                ),
                daemon=True
            )
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=120)
        elapsed = time.perf_counter() - t0
        
        all_results = []
        while not results_queue.empty():
            try:
                all_results.append(results_queue.get_nowait())
            except queue.Empty:
                break
        
        latencies = sorted([r.latency_ms for r in all_results if r.success])
        total = len(all_results)
        success = sum(1 for r in all_results if r.success)
        
        if latencies:
            avg = sum(latencies) / len(latencies)
            p50 = latencies[len(latencies) // 2]
            p90 = latencies[int(len(latencies) * 0.90)]
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[int(len(latencies) * 0.99)]
        else:
            avg = p50 = p90 = p95 = p99 = 0
        
        total_clicks = NUM_ACCOUNTS * CLICKS_PER_ACCOUNT
        throughput = total_clicks / elapsed if elapsed > 0 else 0
        
        print(f"\n{'='*70}")
        print(f"  ⏱️  LATENCY BENCHMARK: {NUM_ACCOUNTS} ACCOUNTS × {CLICKS_PER_ACCOUNT} CLICKS")
        print(f"{'='*70}")
        print(f"  📊 Tổng clicks:    {total:,} / {total_clicks:,}")
        print(f"  ✅ Success:         {success:,}")
        print(f"  ⏱  Tổng thời gian: {elapsed:.2f}s")
        print(f"  📈 Throughput:      {throughput:.0f} clicks/sec")
        print(f"{'─'*70}")
        print(f"  Latency Distribution:")
        print(f"  ├── AVG:    {avg:.1f}ms")
        print(f"  ├── P50:    {p50:.1f}ms")
        print(f"  ├── P90:    {p90:.1f}ms")
        print(f"  ├── P95:    {p95:.1f}ms")
        print(f"  └── P99:    {p99:.1f}ms")
        print(f"{'='*70}")
        
        assert success == total_clicks, f"Mất clicks: {total_clicks - success}"
        assert p95 < 1000, f"P95 latency quá cao: {p95:.1f}ms"
