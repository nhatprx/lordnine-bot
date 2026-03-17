"""
State DB — SQLite-based persistence for bot state.

Tracks account execution state, allows resuming after app restart,
and keeps an execution log for debugging.

Usage:
    db = StateDB()
    db.save_account_state("Acc001", current_node="abc123", status="running")
    state = db.get_account_state("Acc001")
    db.log_action("Acc001", "macro_exec", "Clicked Revive button")
    recent = db.get_recent_logs("Acc001", limit=50)
"""

import sqlite3
import os
import time
import threading
import queue


class StateDB:
    """Thread-safe SQLite state persistence with batched writes.
    
    Write batching: instead of commit per call (300 writes/sec with 30 threads),
    buffers writes in memory and flushes every 2 seconds in a single transaction.
    """
    
    _FLUSH_INTERVAL = 2.0  # seconds between flush cycles
    
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.db")
        
        self.db_path = db_path
        self._local = threading.local()
        
        # Write buffers (thread-safe via locks)
        self._state_buffer = {}     # acc_name → {fields dict}
        self._state_lock = threading.Lock()
        self._log_buffer = []       # list of (timestamp, account, action, detail, result)
        self._log_lock = threading.Lock()
        
        # Dedicated writer connection (only used by flush thread)
        self._writer_conn = None
        self._writer_lock = threading.Lock()  # Protects writer conn access
        
        self._init_db()
        
        # Start background flush thread
        self._flush_stop = threading.Event()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True, name="StateDB-flush")
        self._flush_thread.start()
    
    def _get_conn(self):
        """Get thread-local connection for READS only."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn
    
    def _get_writer(self):
        """Get the dedicated writer connection (flush thread + reads after flush)."""
        if self._writer_conn is None:
            self._writer_conn = sqlite3.connect(
                self.db_path, timeout=15, check_same_thread=False
            )
            self._writer_conn.execute("PRAGMA journal_mode=WAL")
            self._writer_conn.execute("PRAGMA synchronous=NORMAL")
            self._writer_conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
            self._writer_conn.execute("PRAGMA mmap_size=67108864")  # 64MB mmap
        return self._writer_conn
    
    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS account_state (
                name TEXT PRIMARY KEY,
                current_node_id TEXT DEFAULT '',
                loop_name TEXT DEFAULT '',
                status TEXT DEFAULT 'idle',
                last_active REAL DEFAULT 0,
                error_msg TEXT DEFAULT '',
                port INTEGER DEFAULT 9222,
                tab_index INTEGER DEFAULT 0,
                extra_json TEXT DEFAULT '{}'
            );
            
            CREATE TABLE IF NOT EXISTS execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                account TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                result TEXT DEFAULT ''
            );
            
            CREATE INDEX IF NOT EXISTS idx_log_account 
                ON execution_log(account, timestamp DESC);
                
            CREATE TABLE IF NOT EXISTS chrome_instances (
                port INTEGER PRIMARY KEY,
                pid INTEGER DEFAULT 0,
                proxy TEXT DEFAULT '',
                launched_at REAL DEFAULT 0,
                status TEXT DEFAULT 'unknown'
            );
        """)
        conn.commit()
    
    # --- Account State ---
    
    def save_account_state(self, name, current_node=None, loop_name=None,
                           status=None, error_msg=None, port=None, tab_index=None):
        """Buffer account state update. Flushed to DB every 2 seconds."""
        fields = {"last_active": time.time()}
        if current_node is not None: fields["current_node_id"] = current_node
        if loop_name is not None: fields["loop_name"] = loop_name
        if status is not None: fields["status"] = status
        if error_msg is not None: fields["error_msg"] = error_msg
        if port is not None: fields["port"] = port
        if tab_index is not None: fields["tab_index"] = tab_index
        
        with self._state_lock:
            if name in self._state_buffer:
                self._state_buffer[name].update(fields)  # Merge with pending
            else:
                self._state_buffer[name] = fields
    
    def get_account_state(self, name):
        """Get account state. Returns dict or None.
        
        Flushes pending writes and reads from writer connection
        for consistent read-your-own-writes semantics.
        """
        self.flush()
        # Read from writer connection — it always sees its own committed data
        with self._writer_lock:
            writer = self._get_writer()
            writer.row_factory = sqlite3.Row
            row = writer.execute(
                "SELECT * FROM account_state WHERE name = ?", (name,)
            ).fetchone()
            result = dict(row) if row else None
        
        # Also overlay any pending buffer (race between flush and new writes)
        with self._state_lock:
            pending = self._state_buffer.get(name)
            if pending:
                if result is None:
                    result = {
                        "name": name, "current_node_id": "",
                        "loop_name": "", "status": "idle",
                        "last_active": 0, "error_msg": "",
                        "port": 9222, "tab_index": 0, "extra_json": "{}",
                    }
                result.update(pending)
        
        return result
    
    def get_all_account_states(self):
        """Get all account states. Reads from writer for consistency."""
        self.flush()
        with self._writer_lock:
            writer = self._get_writer()
            writer.row_factory = sqlite3.Row
            rows = writer.execute("SELECT * FROM account_state ORDER BY name").fetchall()
        results = {dict(r)["name"]: dict(r) for r in rows}
        
        # Overlay pending buffer entries (race between flush and new writes)
        with self._state_lock:
            for name, fields in self._state_buffer.items():
                if name in results:
                    results[name].update(fields)
                else:
                    entry = {
                        "name": name, "current_node_id": "",
                        "loop_name": "", "status": "idle",
                        "last_active": 0, "error_msg": "",
                        "port": 9222, "tab_index": 0, "extra_json": "{}",
                    }
                    entry.update(fields)
                    results[name] = entry
        
        return sorted(results.values(), key=lambda s: s["name"])
    
    def clear_account_state(self, name):
        """Reset account state to idle."""
        self.save_account_state(name, current_node="", status="idle", error_msg="")
    
    def clear_all_states(self):
        """Reset all accounts to idle."""
        # Flush pending writes first, then overwrite everything
        self.flush()
        conn = self._get_conn()
        conn.execute("""
            UPDATE account_state 
            SET status='idle', current_node_id='', error_msg=''
        """)
        conn.commit()
    
    # --- Execution Log ---
    
    def log_action(self, account, action, detail="", result=""):
        """Buffer a log entry. Flushed to DB every 2 seconds."""
        with self._log_lock:
            # Cap buffer to prevent OOM under heavy load (100+ accounts)
            if len(self._log_buffer) > 5000:
                self._log_buffer = self._log_buffer[-2000:]
            self._log_buffer.append((time.time(), account, action, detail, result))
    
    # ── Background Flush ──
    
    def _flush_loop(self):
        """Background thread: flush buffered writes every 2 seconds."""
        while not self._flush_stop.is_set():
            self._flush_stop.wait(self._FLUSH_INTERVAL)
            self._flush_now()
    
    def _flush_now(self):
        """Flush all pending state + log writes in a single transaction."""
        # Grab pending data
        with self._state_lock:
            states = dict(self._state_buffer)
            self._state_buffer.clear()
        with self._log_lock:
            logs = list(self._log_buffer)
            self._log_buffer.clear()
        
        if not states and not logs:
            return
        
        with self._writer_lock:
            try:
                conn = self._get_writer()
                
                # Batch state upserts
                for name, fields in states.items():
                    set_clause = ", ".join(f"{k}=?" for k in fields.keys())
                    values = list(fields.values())
                    conn.execute(f"""
                        INSERT INTO account_state (name, {', '.join(fields.keys())})
                        VALUES (?, {', '.join('?' * len(fields))})
                        ON CONFLICT(name) DO UPDATE SET {set_clause}
                    """, [name] + values + values)
                
                # Batch log inserts
                if logs:
                    conn.executemany(
                        "INSERT INTO execution_log (timestamp, account, action, detail, result) VALUES (?, ?, ?, ?, ?)",
                        logs
                    )
                    
                    # Auto-prune old logs every 500 buffered inserts
                    if len(logs) >= 50:
                        # Delete logs older than 24h
                        cutoff = time.time() - 86400
                        conn.execute("DELETE FROM execution_log WHERE timestamp < ?", (cutoff,))
                        # Also cap total to 5000 most recent
                        conn.execute("""
                            DELETE FROM execution_log
                            WHERE id NOT IN (
                                SELECT id FROM execution_log
                                ORDER BY timestamp DESC
                                LIMIT 5000
                            )
                        """)
                
                conn.commit()
            except Exception:
                pass  # Best-effort persistence
    
    def flush(self):
        """Force immediate flush of all buffered writes to disk.
        
        Call this when you need read-your-own-writes consistency.
        In production, the background thread flushes every 2s automatically.
        """
        self._flush_now()
        # Close the thread-local reader so the next read opens a fresh
        # connection that sees the writer's latest committed data.
        # (In SQLite WAL mode, each connection holds its own read snapshot.)
        if hasattr(self._local, 'conn') and self._local.conn:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
    
    def shutdown(self):
        """Flush remaining writes and stop background thread. Idempotent."""
        if getattr(self, '_shutdown_done', False):
            return
        self._shutdown_done = True
        self._flush_stop.set()
        self.flush()  # Final flush
        if self._writer_conn:
            try: self._writer_conn.close()
            except: pass
    
    def get_recent_logs(self, account=None, limit=100):
        """Get recent log entries."""
        self.flush()
        conn = self._get_conn()
        if account:
            rows = conn.execute(
                "SELECT * FROM execution_log WHERE account = ? ORDER BY timestamp DESC LIMIT ?",
                (account, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM execution_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    
    # --- Chrome Instances ---
    
    def save_chrome_instance(self, port, pid=0, proxy="", status="running"):
        """Save Chrome instance info."""
        conn = self._get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO chrome_instances (port, pid, proxy, launched_at, status)
            VALUES (?, ?, ?, ?, ?)
        """, (port, pid, proxy, time.time(), status))
        conn.commit()
    
    def remove_chrome_instance(self, port):
        """Remove Chrome instance record."""
        conn = self._get_conn()
        conn.execute("DELETE FROM chrome_instances WHERE port = ?", (port,))
        conn.commit()
    
    def get_chrome_instances(self):
        """Get all Chrome instance records."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM chrome_instances ORDER BY port").fetchall()
        return [dict(r) for r in rows]
    
    def close(self):
        """Close the database — flushes pending writes first."""
        self.shutdown()
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
    
    def checkpoint(self):
        """Force WAL checkpoint to compact the database file.
        Call periodically to prevent WAL file from growing unbounded."""
        try:
            conn = self._get_conn()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except:
            pass
    
    def cleanup_old_logs(self, max_per_account=2000):
        """Batch cleanup of old logs for all accounts."""
        try:
            conn = self._get_conn()
            conn.execute(f"""
                DELETE FROM execution_log
                WHERE id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (PARTITION BY account ORDER BY timestamp DESC) as rn
                        FROM execution_log
                    ) WHERE rn <= {max_per_account}
                )
            """)
            conn.commit()
        except:
            pass
