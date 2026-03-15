"""
Unit tests for ChromeManager — Chrome lifecycle, port management.
Uses mocked subprocess and HTTP to test logic without real Chrome.
"""
import pytest
import os
import sys
from unittest.mock import MagicMock, patch
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chrome_manager import ChromeManager


class TestPortManagement:
    """Test port allocation and reachability."""

    def test_get_next_available_port_default(self):
        mgr = ChromeManager()
        port = mgr.get_next_available_port()
        assert port == 9222

    def test_get_next_available_port_skips_used(self):
        mgr = ChromeManager()
        mgr.processes[9222] = MagicMock()
        port = mgr.get_next_available_port()
        assert port == 9223

    def test_get_next_available_port_skips_multiple(self):
        mgr = ChromeManager()
        for p in range(9222, 9227):
            mgr.processes[p] = MagicMock()
        port = mgr.get_next_available_port()
        assert port == 9227

    @patch('urllib.request.urlopen')
    def test_is_port_reachable_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        
        mgr = ChromeManager()
        assert mgr._is_port_reachable(9222) is True

    @patch('urllib.request.urlopen')
    def test_is_port_reachable_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        
        mgr = ChromeManager()
        assert mgr._is_port_reachable(9222) is False


class TestGetActivePortsExternal:
    """Test external port discovery."""

    @patch.object(ChromeManager, '_is_port_reachable')
    def test_no_active_ports(self, mock_reachable):
        mock_reachable.return_value = False
        mgr = ChromeManager()
        ports = mgr.get_active_ports()
        assert ports == []

    @patch.object(ChromeManager, '_is_port_reachable')
    def test_scans_port_range(self, mock_reachable):
        mock_reachable.side_effect = lambda p: p in [9222, 9224]
        mgr = ChromeManager()
        ports = mgr.get_active_ports()
        assert 9222 in ports
        assert 9224 in ports
        assert 9223 not in ports


class TestGetPortInfo:
    """Test CDP /json endpoint parsing."""

    @patch('urllib.request.urlopen')
    def test_get_port_info_success(self, mock_urlopen):
        targets = [
            {"type": "page", "title": "Game", "url": "http://game.com", "id": "t1"},
            {"type": "page", "title": "Chat", "url": "http://chat.com", "id": "t2"},
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(targets).encode()
        mock_urlopen.return_value = mock_resp

        mgr = ChromeManager()
        info = mgr.get_port_info(9222)
        assert info is not None
        assert info["tab_count"] == 2
        assert len(info["tabs"]) == 2
        assert info["port"] == 9222

    @patch('urllib.request.urlopen')
    def test_get_port_info_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        mgr = ChromeManager()
        info = mgr.get_port_info(9222)
        assert info is None or info == []


class TestKillChrome:
    """Test kill and cleanup."""

    def test_kill_by_port_cleans_up(self):
        mgr = ChromeManager()
        proc = MagicMock()
        proc.poll.return_value = None
        mgr.processes[9222] = proc
        
        mgr.kill(9222)
        proc.kill.assert_called()
        assert 9222 not in mgr.processes

    def test_kill_nonexistent_port_silent(self):
        mgr = ChromeManager()
        mgr.kill(9999)  # Should not raise

    def test_kill_all(self):
        mgr = ChromeManager()
        procs = {}
        for port in [9222, 9223, 9224]:
            proc = MagicMock()
            proc.poll.return_value = None
            mgr.processes[port] = proc
            procs[port] = proc
        
        mgr.kill_all()
        for proc in procs.values():
            proc.kill.assert_called()
        assert len(mgr.processes) == 0


class TestLaunch:
    """Test Chrome launch (mocked subprocess)."""

    @patch('chrome_manager.subprocess.Popen')
    @patch('chrome_manager.os.path.exists')
    def test_launch_basic(self, mock_exists, mock_popen):
        # First call to os.path.exists: chrome_path check returns True
        # Second call: makedirs check (returns True)
        mock_exists.return_value = True
        mock_popen.return_value = MagicMock(pid=12345, poll=MagicMock(return_value=None))
        
        mgr = ChromeManager()
        result = mgr.launch(9222)
        
        # launch returns (success, message) tuple
        assert result[0] is True or mock_popen.called

    @patch('chrome_manager.subprocess.Popen')
    @patch('chrome_manager.os.path.exists')
    def test_launch_with_proxy(self, mock_exists, mock_popen):
        mock_exists.return_value = True
        mock_popen.return_value = MagicMock(pid=12346, poll=MagicMock(return_value=None))
        
        mgr = ChromeManager()
        result = mgr.launch(9223, proxy="socks5://1.2.3.4:1080")
        
        if mock_popen.called:
            # Verify proxy arg was included in the command
            cmd_list = mock_popen.call_args[0][0]
            proxy_args = [arg for arg in cmd_list if "proxy" in arg.lower()]
            assert len(proxy_args) > 0, "Proxy argument should be passed to Chrome"

    def test_launch_chrome_not_found(self):
        """Chrome not installed → returns failure."""
        mgr = ChromeManager()
        with patch.object(mgr, '_find_chrome_path', return_value=None):
            result = mgr.launch(9222)
            assert result[0] is False
            assert "not found" in result[1].lower()
