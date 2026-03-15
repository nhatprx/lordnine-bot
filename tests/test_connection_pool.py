"""
Unit tests for PlaywrightPool — Thread-safe connection pool.
Tests: acquire/release lifecycle, ref counting, reconnect, shutdown.
Uses mocked Playwright to avoid requiring a real browser.
"""
import pytest
import os
import sys
import threading
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from connection_pool import PlaywrightPool


def _make_mock_page(url="http://example.com"):
    page = MagicMock()
    page.url = url
    return page


def _make_mock_context(pages=None):
    ctx = MagicMock()
    ctx.pages = pages or [_make_mock_page()]
    return ctx


def _make_mock_browser(contexts=None):
    browser = MagicMock()
    browser.contexts = contexts or [_make_mock_context()]
    return browser


def _make_mock_pw(browser=None):
    pw = MagicMock()
    if browser is None:
        browser = _make_mock_browser()
    pw.chromium.connect_over_cdp.return_value = browser
    return pw


class TestAcquireRelease:
    """Test basic acquire/release lifecycle."""

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_acquire_creates_connection(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        page, info = pool.acquire(9222, 0)

        assert page is mock_page
        assert pool.get_connection_count() == 1

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_acquire_reuses_connection_same_port(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        pool.acquire(9222, 0)
        pool.acquire(9222, 1)

        assert pool.get_connection_count() == 1
        # sync_playwright should only be called once for same port
        assert mock_sp.return_value.start.call_count == 1

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_acquire_creates_separate_connections_different_ports(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        pool.acquire(9222, 0)
        pool.acquire(9223, 0)

        assert pool.get_connection_count() == 2

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_release_decrements_ref_count(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        pool.acquire(9222, 0)
        pool.acquire(9222, 1)  # ref_count = 2
        pool.release(9222)      # ref_count = 1

        assert pool.get_connection_count() == 1  # Still alive

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_release_destroys_at_ref_count_zero(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        pool.acquire(9222, 0)
        pool.release(9222)

        assert pool.get_connection_count() == 0

    def test_release_nonexistent_port_silent(self):
        pool = PlaywrightPool()
        pool.release(9999)  # Should not raise

    @patch('connection_pool.sync_playwright')
    def test_acquire_connection_failure_returns_none(self, mock_sp):
        mock_sp.return_value.start.return_value.chromium.connect_over_cdp.side_effect = \
            Exception("Connection refused")

        pool = PlaywrightPool()
        page, info = pool.acquire(9222, 0)

        assert page is None
        assert "Cannot connect" in info

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_acquire_page_failure_releases_ref(self, mock_get_page, mock_sp):
        mock_get_page.side_effect = Exception("Tab not found")
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        page, info = pool.acquire(9222, 0)

        assert page is None
        # Connection should be cleaned up since ref_count drops to 0
        assert pool.get_connection_count() == 0


class TestShutdown:
    """Test shutdown and cleanup."""

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_shutdown_closes_all(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        pool.acquire(9222, 0)
        pool.acquire(9223, 0)
        pool.shutdown()

        assert pool.get_connection_count() == 0


class TestGetStats:
    """Test stats reporting."""

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_get_stats_returns_port_info(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        pool.acquire(9222, 0)
        pool.acquire(9222, 1)

        stats = pool.get_stats()
        assert 9222 in stats
        assert stats[9222]['ref_count'] == 2


class TestConcurrentAccess:
    """Test thread safety of the pool."""

    @patch('connection_pool.sync_playwright')
    @patch('connection_pool.get_page_by_visual_index')
    def test_concurrent_acquire_release(self, mock_get_page, mock_sp):
        mock_page = _make_mock_page()
        mock_get_page.return_value = (mock_page, [])
        mock_pw = _make_mock_pw()
        mock_sp.return_value.start.return_value = mock_pw

        pool = PlaywrightPool()
        errors = []
        
        def acquire_release(port):
            try:
                page, info = pool.acquire(port, 0)
                import time
                time.sleep(0.01)
                pool.release(port)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=acquire_release, args=(9222 + (i % 5),))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        
        assert not errors, f"Thread errors: {errors}"
        # All released, count should be 0
        assert pool.get_connection_count() == 0
