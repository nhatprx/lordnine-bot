"""
Unit tests for constants.py — get_page_by_visual_index function.
Tests tab matching strategies: unique URL, duplicate URL, and index fallback.
"""
import pytest
import os
import sys
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import get_page_by_visual_index, COLOR, FONT, PAD


class TestColorPalette:
    """Verify design system constants are defined."""

    def test_all_critical_colors_defined(self):
        required = ["bg", "surface", "primary", "success", "danger", "warning",
                     "text", "text_dim", "text_muted", "border", "sidebar"]
        for key in required:
            assert key in COLOR, f"Missing color: {key}"

    def test_colors_are_hex_strings(self):
        for key, val in COLOR.items():
            assert isinstance(val, str), f"{key} is not a string"
            assert val.startswith("#"), f"{key} doesn't start with #"

    def test_font_system_defined(self):
        assert "family" in FONT
        assert "mono" in FONT

    def test_pad_system_defined(self):
        for key in ["xs", "sm", "md", "lg", "xl"]:
            assert key in PAD


class TestGetPageByVisualIndex:
    """Test get_page_by_visual_index tab matching strategies."""

    def _make_page(self, url):
        p = MagicMock()
        p.url = url
        return p

    def _mock_cdp_response(self, targets):
        """Create a mock response for /json endpoint."""
        data = json.dumps(targets).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = data
        mock_resp.decode = lambda: data.decode()
        return mock_resp

    @patch('urllib.request.urlopen')
    def test_strategy1_unique_url_match(self, mock_urlopen):
        """Strategy 1: Match by unique URL."""
        targets = [
            {"type": "page", "id": "t1", "url": "http://game.com/play", "title": "Game"},
            {"type": "page", "id": "t2", "url": "http://game.com/settings", "title": "Settings"},
        ]
        mock_urlopen.return_value = self._mock_cdp_response(targets)

        page1 = self._make_page("http://game.com/play")
        page2 = self._make_page("http://game.com/settings")
        ctx = MagicMock()
        ctx.pages = [page2, page1]  # different order from CDP

        result, info = get_page_by_visual_index(ctx, 0)
        assert result is page1

    @patch('urllib.request.urlopen')
    def test_strategy2_duplicate_url_position_match(self, mock_urlopen):
        """Strategy 2: Duplicate URLs matched by position."""
        targets = [
            {"type": "page", "id": "t1", "url": "http://cloud.com/phone", "title": "Phone 1"},
            {"type": "page", "id": "t2", "url": "http://cloud.com/phone", "title": "Phone 2"},
            {"type": "page", "id": "t3", "url": "http://cloud.com/phone", "title": "Phone 3"},
        ]
        mock_urlopen.return_value = self._mock_cdp_response(targets)

        p1 = self._make_page("http://cloud.com/phone")
        p2 = self._make_page("http://cloud.com/phone")
        p3 = self._make_page("http://cloud.com/phone")
        ctx = MagicMock()
        ctx.pages = [p1, p2, p3]

        result, info = get_page_by_visual_index(ctx, 1)
        assert result is p2

    @patch('urllib.request.urlopen')
    def test_strategy3_index_fallback(self, mock_urlopen):
        """Strategy 3: Index-based fallback."""
        targets = [
            {"type": "page", "id": "t1", "url": "http://a.com", "title": "A"},
            {"type": "page", "id": "t2", "url": "http://b.com", "title": "B"},
        ]
        mock_urlopen.return_value = self._mock_cdp_response(targets)

        pa = self._make_page("http://different.com")
        pb = self._make_page("http://other.com")
        ctx = MagicMock()
        ctx.pages = [pa, pb]

        result, info = get_page_by_visual_index(ctx, 0)
        assert result is pa

    @patch('urllib.request.urlopen')
    def test_out_of_range_index(self, mock_urlopen):
        targets = [
            {"type": "page", "id": "t1", "url": "http://a.com", "title": "A"},
        ]
        mock_urlopen.return_value = self._mock_cdp_response(targets)

        ctx = MagicMock()
        ctx.pages = [self._make_page("http://a.com")]

        result, info = get_page_by_visual_index(ctx, 5)
        assert result is None
        assert "out of range" in info

    @patch('urllib.request.urlopen')
    def test_no_page_targets(self, mock_urlopen):
        targets = [
            {"type": "background_page", "id": "bg1", "url": "chrome-extension://abc"},
        ]
        mock_urlopen.return_value = self._mock_cdp_response(targets)

        ctx = MagicMock()
        ctx.pages = []

        result, info = get_page_by_visual_index(ctx, 0)
        assert result is None
        assert "No page" in info

    @patch('urllib.request.urlopen')
    def test_cdp_connection_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")

        ctx = MagicMock()
        ctx.pages = [self._make_page("http://a.com")]

        result, info = get_page_by_visual_index(ctx, 0)
        assert result is None
        assert "Cannot reach" in info

    @patch('urllib.request.urlopen')
    def test_returns_tab_list_info(self, mock_urlopen):
        targets = [
            {"type": "page", "id": "t1", "url": "http://game.com", "title": "Game Tab"},
            {"type": "page", "id": "t2", "url": "http://settings.com", "title": "Settings"},
        ]
        mock_urlopen.return_value = self._mock_cdp_response(targets)

        p1 = self._make_page("http://game.com")
        p2 = self._make_page("http://settings.com")
        ctx = MagicMock()
        ctx.pages = [p1, p2]

        result, info = get_page_by_visual_index(ctx, 0)
        assert isinstance(info, list)
        assert len(info) == 2
        assert info[0][1] == "Game Tab"
