"""
Unit tests for StateDB — SQLite-based persistence for bot state.
Tests: CRUD for account state, execution log, chrome instances, thread safety.
"""
import pytest
import os
import threading
import time
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from state_db import StateDB


class TestAccountStateCRUD:
    """Test basic account state operations."""

    def test_save_and_get_account_state(self, temp_db):
        temp_db.save_account_state("Acc001", current_node="node_a", status="running")
        state = temp_db.get_account_state("Acc001")
        assert state is not None
        assert state["name"] == "Acc001"
        assert state["current_node_id"] == "node_a"
        assert state["status"] == "running"

    def test_get_nonexistent_account_returns_none(self, temp_db):
        result = temp_db.get_account_state("DoesNotExist")
        assert result is None

    def test_upsert_updates_existing_fields(self, temp_db):
        temp_db.save_account_state("Acc001", status="idle", port=9222)
        temp_db.save_account_state("Acc001", status="running")
        state = temp_db.get_account_state("Acc001")
        assert state["status"] == "running"
        assert state["port"] == 9222  # unchanged field preserved

    def test_partial_update_preserves_other_fields(self, temp_db):
        temp_db.save_account_state("Acc001", current_node="n1", status="running",
                                    port=9223, tab_index=3)
        temp_db.save_account_state("Acc001", current_node="n2")
        state = temp_db.get_account_state("Acc001")
        assert state["current_node_id"] == "n2"
        assert state["port"] == 9223
        assert state["tab_index"] == 3

    def test_last_active_is_updated(self, temp_db):
        before = time.time()
        temp_db.save_account_state("Acc001", status="running")
        after = time.time()
        state = temp_db.get_account_state("Acc001")
        assert before <= state["last_active"] <= after

    def test_get_all_account_states(self, temp_db):
        for i in range(5):
            temp_db.save_account_state(f"Acc{i:03d}", status="idle")
        states = temp_db.get_all_account_states()
        assert len(states) == 5
        names = [s["name"] for s in states]
        assert sorted(names) == [f"Acc{i:03d}" for i in range(5)]

    def test_clear_account_state(self, temp_db):
        temp_db.save_account_state("Acc001", current_node="n1", status="running",
                                    error_msg="some error")
        temp_db.clear_account_state("Acc001")
        state = temp_db.get_account_state("Acc001")
        assert state["status"] == "idle"
        assert state["current_node_id"] == ""
        assert state["error_msg"] == ""

    def test_clear_all_states(self, temp_db):
        for i in range(5):
            temp_db.save_account_state(f"Acc{i}", status="running",
                                        current_node="n1", error_msg="err")
        temp_db.clear_all_states()
        for i in range(5):
            state = temp_db.get_account_state(f"Acc{i}")
            assert state["status"] == "idle"
            assert state["current_node_id"] == ""
            assert state["error_msg"] == ""

    def test_save_with_error_msg(self, temp_db):
        temp_db.save_account_state("Acc001", status="error",
                                    error_msg="Connection timeout after 30s")
        state = temp_db.get_account_state("Acc001")
        assert state["error_msg"] == "Connection timeout after 30s"


class TestExecutionLog:
    """Test execution logging functionality."""

    def test_log_action_inserts(self, temp_db):
        temp_db.log_action("Acc001", "click", "hp_bar", "OK")
        logs = temp_db.get_recent_logs("Acc001")
        assert len(logs) == 1
        assert logs[0]["action"] == "click"
        assert logs[0]["detail"] == "hp_bar"
        assert logs[0]["result"] == "OK"

    def test_log_action_ordering(self, temp_db):
        for i in range(5):
            temp_db.log_action("Acc001", f"action_{i}", f"detail_{i}")
        logs = temp_db.get_recent_logs("Acc001")
        assert len(logs) == 5
        # Newest first
        assert logs[0]["action"] == "action_4"
        assert logs[4]["action"] == "action_0"

    def test_log_action_limit(self, temp_db):
        for i in range(20):
            temp_db.log_action("Acc001", f"action_{i}", "")
        logs = temp_db.get_recent_logs("Acc001", limit=5)
        assert len(logs) == 5

    def test_log_action_per_account(self, temp_db):
        for i in range(3):
            temp_db.log_action("Acc001", f"a_{i}", "")
            temp_db.log_action("Acc002", f"b_{i}", "")
        logs1 = temp_db.get_recent_logs("Acc001")
        logs2 = temp_db.get_recent_logs("Acc002")
        assert len(logs1) == 3
        assert len(logs2) == 3
        assert all(l["action"].startswith("a_") for l in logs1)

    def test_get_all_logs_no_account_filter(self, temp_db):
        temp_db.log_action("Acc001", "a", "")
        temp_db.log_action("Acc002", "b", "")
        logs = temp_db.get_recent_logs()
        assert len(logs) == 2


class TestChromeInstances:
    """Test Chrome instance record operations."""

    def test_save_and_get_chrome_instance(self, temp_db):
        temp_db.save_chrome_instance(9222, pid=1234, proxy="socks5://1.2.3.4:1080")
        instances = temp_db.get_chrome_instances()
        assert len(instances) == 1
        assert instances[0]["port"] == 9222
        assert instances[0]["pid"] == 1234
        assert instances[0]["proxy"] == "socks5://1.2.3.4:1080"

    def test_remove_chrome_instance(self, temp_db):
        temp_db.save_chrome_instance(9222, pid=1234)
        temp_db.save_chrome_instance(9223, pid=5678)
        temp_db.remove_chrome_instance(9222)
        instances = temp_db.get_chrome_instances()
        assert len(instances) == 1
        assert instances[0]["port"] == 9223

    def test_replace_existing_chrome_instance(self, temp_db):
        temp_db.save_chrome_instance(9222, pid=1234, status="running")
        temp_db.save_chrome_instance(9222, pid=5678, status="restarted")
        instances = temp_db.get_chrome_instances()
        assert len(instances) == 1
        assert instances[0]["pid"] == 5678
        assert instances[0]["status"] == "restarted"


class TestThreadSafety:
    """Test thread-local connections work correctly."""

    def test_concurrent_writes_from_different_threads(self, temp_db):
        errors = []
        
        def write_states(start, count):
            try:
                for i in range(start, start + count):
                    temp_db.save_account_state(f"Thread_Acc_{i}", status="running")
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=write_states, args=(i * 10, 10))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        
        assert not errors, f"Thread errors: {errors}"
        states = temp_db.get_all_account_states()
        assert len(states) == 50

    def test_concurrent_log_writes(self, temp_db):
        errors = []
        
        def log_entries(acc_name, count):
            try:
                for i in range(count):
                    temp_db.log_action(acc_name, f"action_{i}", f"detail_{i}")
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=log_entries, args=(f"Acc{i}", 20))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        
        assert not errors
        total_logs = temp_db.get_recent_logs(limit=200)
        assert len(total_logs) == 100  # 5 accounts × 20 entries


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_name(self, temp_db):
        temp_db.save_account_state("", status="idle")
        state = temp_db.get_account_state("")
        assert state is not None
        assert state["status"] == "idle"

    def test_special_characters_in_name(self, temp_db):
        name = "Acc_001 (Test) [Group-1] @#$"
        temp_db.save_account_state(name, status="running")
        state = temp_db.get_account_state(name)
        assert state is not None
        assert state["name"] == name

    def test_unicode_name(self, temp_db):
        name = "Tài_khoản_001_🎮"
        temp_db.save_account_state(name, status="idle")
        state = temp_db.get_account_state(name)
        assert state is not None

    def test_close_and_reopen(self, temp_dir):
        db_path = os.path.join(temp_dir, "test.db")
        db1 = StateDB(db_path=db_path)
        db1.save_account_state("Acc001", status="running")
        db1.close()

        db2 = StateDB(db_path=db_path)
        state = db2.get_account_state("Acc001")
        assert state is not None
        assert state["status"] == "running"
        db2.close()
