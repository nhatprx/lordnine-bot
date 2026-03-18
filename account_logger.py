"""
Account Logger — Per-account structured logging for scale debugging.

Each account gets its own log file in `logs/{name}.log` with rotation.
Structured event categories make it easy to filter and analyze.

Usage:
    from account_logger import AccountLogger
    log = AccountLogger("Ace")
    log.loop("Starting loop iteration #5")
    log.scan("Supplies", result=True, latency_ms=120)
    log.shot(success=True, latency_ms=95)
    log.macro("Home", "Step 1/2 Hard Click → OK", latency_ms=50)
    log.cdp("Connected to port 9222, tab 3")
    log.error("Screenshot timeout after 25s")
    log.summary()  # Write session summary
"""

import os
import time
import logging
from logging.handlers import RotatingFileHandler

from metrics import metrics

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


class AccountLogger:
    """Per-account structured logger with metrics integration."""
    
    def __init__(self, acc_name: str, port: int = 0, tab_index: int = 0):
        self.acc_name = acc_name
        self.port = port
        self.tab_index = tab_index
        self._start_time = time.time()
        
        # Create logs directory
        os.makedirs(_LOG_DIR, exist_ok=True)
        
        # Per-account file logger
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in acc_name)
        log_path = os.path.join(_LOG_DIR, f"{safe_name}.log")
        
        self._logger = logging.getLogger(f"acc.{safe_name}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        
        # Remove old handlers (in case of restart)
        for h in self._logger.handlers[:]:
            self._logger.removeHandler(h)
        
        handler = RotatingFileHandler(
            log_path, maxBytes=1 * 1024 * 1024, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(message)s", datefmt="%H:%M:%S"
        ))
        self._logger.addHandler(handler)
        
        # Initialize metrics session
        metrics.start_session(acc_name, port=port, tab_index=tab_index)
        
        # Write session header
        self._logger.info(f"{'='*60}")
        self._logger.info(f"SESSION START — {acc_name} (port:{port} tab:{tab_index})")
        self._logger.info(f"{'='*60}")
    
    def loop(self, msg: str):
        """Log loop event."""
        self._logger.info(f"[LOOP] {msg}")
    
    def loop_complete(self):
        """Log loop iteration completion."""
        metrics.record_loop(self.acc_name)
        self._logger.info("[LOOP] ── Loop iteration complete ──")
    
    def scan(self, image_name: str, result: bool, latency_ms: float = 0):
        """Log condition scan result."""
        tag = "TRUE" if result else "FALSE"
        self._logger.info(f"[SCAN] {image_name} → {tag} ({latency_ms:.0f}ms)")
    
    def shot(self, success: bool, latency_ms: float = 0, fail_count: int = 0):
        """Log screenshot result and update metrics."""
        metrics.record_screenshot(self.acc_name, success=success, latency_ms=latency_ms)
        if success:
            self._logger.debug(f"[SHOT] OK ({latency_ms:.0f}ms)")
        else:
            self._logger.info(f"[SHOT] FAIL #{fail_count} ({latency_ms:.0f}ms)")
    
    def macro(self, macro_name: str, detail: str, latency_ms: float = 0):
        """Log macro step or result."""
        self._logger.info(f"[MACRO] {macro_name}: {detail} ({latency_ms:.0f}ms)")
    
    def macro_result(self, macro_name: str, success: bool, total_ms: float = 0):
        """Log macro completion."""
        metrics.record_macro(self.acc_name, success=success)
        tag = "PASSED" if success else "FAILED"
        self._logger.info(f"[MACRO] {macro_name}: {tag} ({total_ms:.0f}ms total)")
    
    def cdp(self, msg: str):
        """Log CDP connection event."""
        self._logger.info(f"[CDP] {msg}")
    
    def node(self, node_name: str, node_type: str):
        """Log node transition."""
        metrics.record_node(self.acc_name, node_name)
        self._logger.info(f"[NODE] → {node_type}: {node_name}")
    
    def error(self, msg: str):
        """Log error and update metrics."""
        metrics.record_error(self.acc_name, msg)
        self._logger.error(f"[ERR] {msg}")
    
    def phone_dead(self, reason: str, node_type: str = "", node_name: str = "", loop_name: str = ""):
        """Log phone death event with full context.
        
        Args:
            reason: Why the phone died (e.g. 'screenshot_timeout', 'connection_lost', 'health_check_failed')
            node_type: Current flowchart node type (Click, Condition, Macro, Delay)
            node_name: Current node target (image name, macro name)
            loop_name: Which loop/function was running
        """
        import datetime
        uptime_min = (time.time() - self._start_time) / 60.0
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Structured death line
        at_node = f" at {node_type}:{node_name}" if node_type else ""
        in_loop = f" in '{loop_name}'" if loop_name else ""
        death_line = f"[DEAD] {self.acc_name} — {reason}{at_node}{in_loop} (uptime {uptime_min:.1f}min, port:{self.port} tab:{self.tab_index})"
        
        # Log to per-account file
        self._logger.error(death_line)
        
        # Log to shared deaths.log for easy cross-account export
        try:
            deaths_path = os.path.join(_LOG_DIR, "deaths.log")
            with open(deaths_path, "a", encoding="utf-8") as f:
                f.write(f"{ts} {death_line}\n")
        except Exception:
            pass
        
        # Record in metrics
        metrics.record_error(self.acc_name, f"DEAD: {reason}{at_node}")
    
    def info(self, msg: str):
        """General info log (replaces flog)."""
        self._logger.info(msg)
    
    def summary(self):
        """Write session summary on worker stop."""
        m = metrics.get_one(self.acc_name)
        if not m:
            return
        
        duration = time.time() - self._start_time
        mins = duration / 60
        
        self._logger.info(f"{'='*60}")
        self._logger.info(f"SESSION END — {self.acc_name} ({mins:.1f} min)")
        self._logger.info(f"  Loops: {m.loops_completed}")
        self._logger.info(f"  Screenshots: {m.shots_ok} ok / {m.shots_fail} fail ({m.shot_fail_rate:.1f}%)")
        self._logger.info(f"  Avg latency: {m.avg_latency_ms:.0f}ms")
        self._logger.info(f"  Macros: {m.macros_ok} ok / {m.macros_fail} fail")
        self._logger.info(f"  Errors: {len(m.errors)}")
        self._logger.info(f"{'='*60}")
        
        metrics.end_session(self.acc_name)
    
    def close(self):
        """Clean up handlers."""
        for h in self._logger.handlers[:]:
            h.close()
            self._logger.removeHandler(h)
