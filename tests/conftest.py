"""
Shared test fixtures for the lordnine-bot test suite.
"""
import pytest
import os
import sys
import json
import tempfile
import shutil

# Add project root to path so tests can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    d = tempfile.mkdtemp(prefix="lordnine_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_db(temp_dir):
    """Create a StateDB instance in a temp directory."""
    from state_db import StateDB
    db_path = os.path.join(temp_dir, "test_bot_state.db")
    db = StateDB(db_path=db_path)
    yield db
    db.close()


@pytest.fixture
def sample_accounts():
    """Generate sample account data."""
    return [
        {
            "name": f"Account_{i:03d}",
            "target": str(i % 10),
            "port": 9222 + (i // 10),
            "loop": "TestLoop",
            "proxy": "",
            "enabled": True,
            "group": "default",
        }
        for i in range(20)
    ]


@pytest.fixture
def sample_combos():
    """Sample macro/combo data."""
    return {
        "TestMacro1": {
            "steps": [
                {"node": "hp_bar"},
                {"type": "delay", "time": 500},
                {"node": "potion"},
            ],
            "success_capture": "None",
            "failure_capture": "None",
        },
        "TestMacro2": {
            "steps": [
                {"node": "settings"},
                {"type": "marker", "marker": "confirm_btn", "mode": "Wait until Appear", "time": "0"},
                {"node": "ok_button"},
            ],
        },
    }


@pytest.fixture
def sample_loops():
    """Sample loop/flowchart data."""
    return {
        "BotFarm": {
            "nodes": {
                "start1": {"id": "start1", "type": "Start", "x": 50, "y": 50, "w": 140, "h": 60, "data": {"title": "Start"}},
                "macro1": {"id": "macro1", "type": "Macro", "x": 50, "y": 130, "w": 140, "h": 60, "data": {"macro_name": "TestMacro1"}},
                "delay1": {"id": "delay1", "type": "Delay", "x": 50, "y": 210, "w": 140, "h": 60, "data": {"time": 2000}},
                "end1":   {"id": "end1",   "type": "End",   "x": 50, "y": 290, "w": 140, "h": 60, "data": {}},
            },
            "edges": [
                {"from": "start1", "from_pin": "out", "to": "macro1", "to_pin": "in"},
                {"from": "macro1", "from_pin": "true", "to": "delay1", "to_pin": "in"},
                {"from": "delay1", "from_pin": "out", "to": "end1", "to_pin": "in"},
            ],
        }
    }


@pytest.fixture
def json_file(temp_dir):
    """Create a helper for writing JSON test fixtures."""
    def _write(filename, data):
        path = os.path.join(temp_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return path
    return _write


def generate_bulk_accounts(count):
    """Generate a large number of accounts for load testing."""
    return [
        {
            "name": f"LoadAcc_{i:04d}",
            "target": str(i % 10),
            "port": 9222 + (i // 10),
            "loop": f"Loop_{i % 5}",
            "proxy": f"socks5://proxy{i % 20}.test:1080" if i % 3 == 0 else "",
            "enabled": True,
            "group": f"group_{i % 10}",
        }
        for i in range(count)
    ]
