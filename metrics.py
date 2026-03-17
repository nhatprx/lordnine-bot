"""
Metrics Collector — Lightweight in-memory metrics for 100+ accounts.

Thread-safe, O(1) updates, zero disk I/O. Used by Health Dashboard
and Analysis Report to give instant overview of all accounts.

Usage:
    from metrics import metrics
    metrics.record_screenshot(acc_name, success=True, latency_ms=120)
    metrics.record_loop(acc_name)
    metrics.record_error(acc_name, "Screenshot timeout")
    
    # Get all metrics for dashboard
    all_stats = metrics.get_all()
    
    # Get analysis report
    report = metrics.generate_report()
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional


@dataclass
class AccountMetrics:
    """Per-account metrics — updated atomically by worker threads."""
    # Screenshot stats
    shots_ok: int = 0
    shots_fail: int = 0
    shot_latency_sum: float = 0.0  # cumulative ms for averaging
    
    # Loop stats
    loops_completed: int = 0
    current_node: str = ""
    current_status: str = "idle"
    
    # Macro stats
    macros_ok: int = 0
    macros_fail: int = 0
    
    # Error tracking (last 10)
    errors: List[Tuple[float, str]] = field(default_factory=list)
    
    # Timing
    start_time: float = 0.0
    last_activity: float = 0.0
    
    # Port info
    port: int = 0
    tab_index: int = 0
    
    @property
    def shot_total(self) -> int:
        return self.shots_ok + self.shots_fail
    
    @property
    def shot_fail_rate(self) -> float:
        total = self.shot_total
        return (self.shots_fail / total * 100) if total > 0 else 0.0
    
    @property
    def avg_latency_ms(self) -> float:
        return (self.shot_latency_sum / self.shots_ok) if self.shots_ok > 0 else 0.0
    
    @property
    def uptime_min(self) -> float:
        if self.start_time <= 0:
            return 0.0
        return (time.time() - self.start_time) / 60.0


class MetricsCollector:
    """Global metrics store — singleton, thread-safe."""
    
    def __init__(self):
        self._metrics: Dict[str, AccountMetrics] = {}
        self._lock = threading.Lock()
    
    def _get(self, acc_name: str) -> AccountMetrics:
        m = self._metrics.get(acc_name)
        if m is None:
            m = AccountMetrics()
            self._metrics[acc_name] = m
        return m
    
    def start_session(self, acc_name: str, port: int = 0, tab_index: int = 0):
        """Call when worker starts."""
        with self._lock:
            m = self._get(acc_name)
            m.start_time = time.time()
            m.last_activity = time.time()
            m.current_status = "starting"
            m.port = port
            m.tab_index = tab_index
            # Reset counters for new session
            m.shots_ok = 0
            m.shots_fail = 0
            m.shot_latency_sum = 0.0
            m.loops_completed = 0
            m.macros_ok = 0
            m.macros_fail = 0
            m.errors.clear()
    
    def end_session(self, acc_name: str):
        """Call when worker stops."""
        with self._lock:
            m = self._get(acc_name)
            m.current_status = "stopped"
            m.last_activity = time.time()
    
    def record_screenshot(self, acc_name: str, success: bool, latency_ms: float = 0):
        with self._lock:
            m = self._get(acc_name)
            if success:
                m.shots_ok += 1
                m.shot_latency_sum += latency_ms
            else:
                m.shots_fail += 1
            m.last_activity = time.time()
    
    def record_loop(self, acc_name: str):
        with self._lock:
            m = self._get(acc_name)
            m.loops_completed += 1
            m.last_activity = time.time()
    
    def record_macro(self, acc_name: str, success: bool):
        with self._lock:
            m = self._get(acc_name)
            if success:
                m.macros_ok += 1
            else:
                m.macros_fail += 1
            m.last_activity = time.time()
    
    def record_node(self, acc_name: str, node_name: str, status: str = ""):
        with self._lock:
            m = self._get(acc_name)
            m.current_node = node_name
            if status:
                m.current_status = status
            m.last_activity = time.time()
    
    def record_error(self, acc_name: str, error_msg: str):
        with self._lock:
            m = self._get(acc_name)
            m.errors.append((time.time(), error_msg))
            if len(m.errors) > 10:
                m.errors.pop(0)
            m.last_activity = time.time()
    
    def get_all(self) -> Dict[str, AccountMetrics]:
        """Thread-safe snapshot of all metrics."""
        with self._lock:
            return dict(self._metrics)
    
    def get_one(self, acc_name: str) -> Optional[AccountMetrics]:
        with self._lock:
            return self._metrics.get(acc_name)
    
    def clear(self, acc_name: str = None):
        with self._lock:
            if acc_name:
                self._metrics.pop(acc_name, None)
            else:
                self._metrics.clear()
    
    def generate_report(self) -> str:
        """Generate analysis report across all accounts."""
        with self._lock:
            snapshot = dict(self._metrics)
        
        if not snapshot:
            return "No metrics collected yet."
        
        lines = []
        now = time.time()
        
        # Header
        running = [n for n, m in snapshot.items() if m.current_status not in ("stopped", "idle")]
        lines.append(f"=== ANALYSIS REPORT ({time.strftime('%Y-%m-%d %H:%M')}) ===")
        lines.append(f"Accounts: {len(running)} running / {len(snapshot)} total\n")
        
        # ── Port-level screenshot health ──
        port_stats: Dict[int, dict] = {}
        for name, m in snapshot.items():
            if m.port <= 0 or m.shot_total == 0:
                continue
            ps = port_stats.setdefault(m.port, {"ok": 0, "fail": 0, "latency_sum": 0.0, "tabs": 0})
            ps["ok"] += m.shots_ok
            ps["fail"] += m.shots_fail
            ps["latency_sum"] += m.shot_latency_sum
            ps["tabs"] += 1
        
        if port_stats:
            lines.append("📊 SCREENSHOT HEALTH (by port)")
            for port in sorted(port_stats):
                ps = port_stats[port]
                total = ps["ok"] + ps["fail"]
                rate = (ps["ok"] / total * 100) if total > 0 else 0
                avg_lat = (ps["latency_sum"] / ps["ok"]) if ps["ok"] > 0 else 0
                flag = "  ⚠ BOTTLENECK" if rate < 80 else ""
                lines.append(f"  Port {port} ({ps['tabs']} tabs): {rate:.0f}% success, avg {avg_lat:.0f}ms{flag}")
            lines.append("")
        
        # ── Top errors ──
        all_errors: Dict[str, int] = {}
        for name, m in snapshot.items():
            for _, err in m.errors:
                # Normalize error messages
                key = err[:50]
                all_errors[key] = all_errors.get(key, 0) + 1
        
        if all_errors:
            lines.append("❌ TOP ERRORS (by frequency)")
            for i, (err, count) in enumerate(sorted(all_errors.items(), key=lambda x: -x[1])[:5]):
                lines.append(f"  {i+1}. {err} ({count} times)")
            lines.append("")
        
        # ── Loop health ──
        loop_accounts = [(n, m) for n, m in snapshot.items() if m.loops_completed > 0]
        if loop_accounts:
            avg_loops = sum(m.loops_completed for _, m in loop_accounts) / len(loop_accounts)
            slowest = sorted(loop_accounts, key=lambda x: x[1].loops_completed)[:3]
            fastest = sorted(loop_accounts, key=lambda x: -x[1].loops_completed)[:3]
            
            lines.append("🔄 LOOP HEALTH")
            lines.append(f"  Avg loops/account: {avg_loops:.1f}")
            lines.append(f"  Slowest: {', '.join(f'{n} ({m.loops_completed})' for n, m in slowest)}")
            lines.append(f"  Fastest: {', '.join(f'{n} ({m.loops_completed})' for n, m in fastest)}")
            lines.append("")
        
        # ── Accounts needing attention ──
        problem_accounts = []
        for name, m in snapshot.items():
            if m.current_status in ("stopped", "idle"):
                continue
            reasons = []
            if m.shot_total > 10 and m.shot_fail_rate > 30:
                reasons.append(f"{m.shot_fail_rate:.0f}% screenshot fail")
            if m.avg_latency_ms > 500:
                reasons.append(f"avg latency {m.avg_latency_ms:.0f}ms")
            if len(m.errors) >= 5:
                reasons.append(f"{len(m.errors)} recent errors")
            if reasons:
                problem_accounts.append((name, m, reasons))
        
        if problem_accounts:
            lines.append("⚠ ACCOUNTS NEEDING ATTENTION")
            for name, m, reasons in sorted(problem_accounts, key=lambda x: -x[1].shot_fail_rate):
                node_info = f", at node '{m.current_node}'" if m.current_node else ""
                lines.append(f"  {name} — {', '.join(reasons)}{node_info}")
            lines.append("")
        
        if not port_stats and not all_errors and not loop_accounts:
            lines.append("Not enough data yet. Run accounts for a few minutes.")
        
        return "\n".join(lines)


# ── Global singleton ──
metrics = MetricsCollector()
