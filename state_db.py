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


class StateDB:
    """Thread-safe SQLite state persistence."""
    
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.db")
        
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
    
    def _get_conn(self):
        """Get thread-local connection (SQLite connections are not thread-safe)."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
        return self._local.conn
    
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
        """Save or update account execution state."""
        conn = self._get_conn()
        
        # Build SET clause dynamically (only update provided fields)
        fields = {"last_active": time.time()}
        if current_node is not None: fields["current_node_id"] = current_node
        if loop_name is not None: fields["loop_name"] = loop_name
        if status is not None: fields["status"] = status
        if error_msg is not None: fields["error_msg"] = error_msg
        if port is not None: fields["port"] = port
        if tab_index is not None: fields["tab_index"] = tab_index
        
        # Upsert
        set_clause = ", ".join(f"{k}=?" for k in fields.keys())
        values = list(fields.values())
        
        conn.execute(f"""
            INSERT INTO account_state (name, {', '.join(fields.keys())})
            VALUES (?, {', '.join('?' * len(fields))})
            ON CONFLICT(name) DO UPDATE SET {set_clause}
        """, [name] + values + values)
        conn.commit()
    
    def get_account_state(self, name):
        """Get account state. Returns dict or None."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM account_state WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None
    
    def get_all_account_states(self):
        """Get all account states."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM account_state ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    
    def clear_account_state(self, name):
        """Reset account state to idle."""
        self.save_account_state(name, current_node="", status="idle", error_msg="")
    
    def clear_all_states(self):
        """Reset all accounts to idle."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE account_state 
            SET status='idle', current_node_id='', error_msg=''
        """)
        conn.commit()
    
    # --- Execution Log ---
    
    def log_action(self, account, action, detail="", result=""):
        """Log an execution action."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO execution_log (timestamp, account, action, detail, result) VALUES (?, ?, ?, ?, ?)",
            (time.time(), account, action, detail, result)
        )
        conn.commit()
        
        # Auto-cleanup: batch prune only every ~100 inserts (not every call)
        if not hasattr(self._local, '_log_count'):
            self._local._log_count = 0
        self._local._log_count += 1
        if self._local._log_count >= 100:
            self._local._log_count = 0
            try:
                conn.execute("""
                    DELETE FROM execution_log 
                    WHERE account = ? AND id NOT IN (
                        SELECT id FROM execution_log 
                        WHERE account = ? 
                        ORDER BY timestamp DESC 
                        LIMIT 2000
                    )
                """, (account, account))
                conn.commit()
            except:
                pass
    
    def get_recent_logs(self, account=None, limit=100):
        """Get recent log entries."""
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
        """Close the database connection for the current thread."""
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
