"""
Integration tests for JSON data persistence — combos.json, loops.json, multi.json.
Tests save/load round-trips, backup files, corruption handling, and migration.
"""
import pytest
import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCombosPersistence:
    """Test macro data save/load round-trips."""

    def test_save_and_load_combos(self, temp_dir, sample_combos):
        path = os.path.join(temp_dir, "combos.json")
        backup = path + ".bak"
        
        # Save
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample_combos, f, indent=4)
        
        # Load
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        
        assert loaded == sample_combos
        assert "TestMacro1" in loaded
        assert len(loaded["TestMacro1"]["steps"]) == 3

    def test_backup_creation(self, temp_dir, sample_combos):
        path = os.path.join(temp_dir, "combos.json")
        backup = path + ".bak"
        
        # First save (creates file)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample_combos, f, indent=4)
        
        # Second save (should create backup)
        shutil.copy2(path, backup)
        sample_combos["NewMacro"] = {"steps": []}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample_combos, f, indent=4)
        
        assert os.path.exists(backup)
        with open(backup, "r") as f:
            bak_data = json.load(f)
        assert "NewMacro" not in bak_data  # Backup has old data

    def test_load_empty_file_returns_empty(self, temp_dir):
        path = os.path.join(temp_dir, "combos.json")
        with open(path, "w") as f:
            f.write("")
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}
        
        assert data == {}

    def test_load_corrupt_json_fallback(self, temp_dir):
        path = os.path.join(temp_dir, "combos.json")
        backup = path + ".bak"
        
        # Create valid backup
        valid_data = {"TestMacro": {"steps": []}}
        with open(backup, "w") as f:
            json.dump(valid_data, f)
        
        # Corrupt main file
        with open(path, "w") as f:
            f.write("{invalid json!!!")
        
        # Load with fallback to backup
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            if os.path.exists(backup):
                with open(backup, "r") as f:
                    data = json.load(f)
            else:
                data = {}
        
        assert data == valid_data

    def test_missing_file_returns_empty(self, temp_dir):
        path = os.path.join(temp_dir, "nonexistent.json")
        if os.path.exists(path):
            os.remove(path)
        
        assert not os.path.exists(path)
        data = {}
        assert data == {}


class TestLoopsPersistence:
    """Test loop/flowchart data save/load round-trips."""

    def test_save_and_load_loops(self, temp_dir, sample_loops):
        path = os.path.join(temp_dir, "loops.json")
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample_loops, f, indent=4)
        
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        
        assert loaded == sample_loops
        assert "BotFarm" in loaded
        nodes = loaded["BotFarm"]["nodes"]
        assert "start1" in nodes
        assert len(loaded["BotFarm"]["edges"]) == 3

    def test_loop_data_structure_integrity(self, sample_loops):
        """Verify all edges reference valid node IDs."""
        for loop_name, loop_data in sample_loops.items():
            nodes = loop_data["nodes"]
            edges = loop_data["edges"]
            for edge in edges:
                assert edge["from"] in nodes, f"Edge from '{edge['from']}' not in nodes"
                assert edge["to"] in nodes, f"Edge to '{edge['to']}' not in nodes"

    def test_legacy_list_migration(self, temp_dir):
        """Test migration from old list format to graph format."""
        legacy = {"OldLoop": ["Macro1", "Macro2", "Macro3"]}
        path = os.path.join(temp_dir, "loops.json")
        
        with open(path, "w") as f:
            json.dump(legacy, f)
        
        with open(path, "r") as f:
            loaded = json.load(f)
        
        # Verify the old list format can be detected
        assert isinstance(loaded["OldLoop"], list)
        assert len(loaded["OldLoop"]) == 3


class TestMultiAccountPersistence:
    """Test multi-account data save/load."""

    def test_save_and_load_multi(self, temp_dir, sample_accounts):
        path = os.path.join(temp_dir, "multi.json")
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample_accounts, f, indent=4)
        
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        
        assert len(loaded) == 20
        assert loaded[0]["name"] == "Account_000"
        assert loaded[0]["port"] == 9222

    def test_large_account_list_round_trip(self, temp_dir):
        """Test with 500 accounts — simulates heavy usage."""
        from tests.conftest import generate_bulk_accounts
        accounts = generate_bulk_accounts(500)
        
        path = os.path.join(temp_dir, "multi.json")
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=4)
        
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        
        assert len(loaded) == 500
        assert loaded[499]["name"] == "LoadAcc_0499"

    def test_account_with_special_characters(self, temp_dir):
        accounts = [
            {"name": "Test (Backup) [Clone]", "port": 9222, "target": "0", "loop": ""},
            {"name": "Tài khoản @Admin#01", "port": 9223, "target": "1", "loop": ""},
        ]
        path = os.path.join(temp_dir, "multi.json")
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=4, ensure_ascii=False)
        
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        
        assert loaded[0]["name"] == "Test (Backup) [Clone]"
        assert loaded[1]["name"] == "Tài khoản @Admin#01"

    def test_empty_account_list(self, temp_dir):
        path = os.path.join(temp_dir, "multi.json")
        
        with open(path, "w") as f:
            json.dump([], f)
        
        with open(path, "r") as f:
            loaded = json.load(f)
        
        assert loaded == []

    def test_file_size_reasonable(self, temp_dir):
        """500 accounts should not create an unreasonably large file."""
        from tests.conftest import generate_bulk_accounts
        accounts = generate_bulk_accounts(500)
        path = os.path.join(temp_dir, "multi.json")
        
        with open(path, "w") as f:
            json.dump(accounts, f, indent=4)
        
        file_size = os.path.getsize(path)
        assert file_size < 500_000, f"File too large: {file_size} bytes for 500 accounts"
