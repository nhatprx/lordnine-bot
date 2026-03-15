"""
Unit tests for BotAction — Mouse clicks, keyboard presses, coordinate scaling.
Uses mocked Playwright page/CDP to test logic without a real browser.
"""
import pytest
import os
import sys
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot_action import BotAction


def _make_mock_page(dpr=1.0):
    """Create a mock Playwright page with configurable DPR.
    
    BotAction.__init__ calls page.context.new_cdp_session(page) to create
    a CDP session. We must mock this chain properly.
    """
    page = MagicMock()
    # DPR evaluation returns the configured value
    page.evaluate.return_value = dpr
    # Frames chain
    page.frames = [page.main_frame]
    page.main_frame.evaluate.return_value = False  # no canvas in frame
    
    cdp_session = MagicMock()
    page.context.new_cdp_session.return_value = cdp_session
    
    return page, cdp_session


class TestClickAt:
    """Test click_at coordinate translation and dispatch."""

    def test_basic_click_dispatches_cdp_events(self):
        page, cdp = _make_mock_page()
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        bot.click_at(100, 200, randomize=False)
        
        cdp_calls = cdp.send.call_args_list
        assert len(cdp_calls) >= 2
        event_names = [c[0][0] for c in cdp_calls]
        assert "Input.dispatchMouseEvent" in event_names

    def test_click_with_dpr_scaling(self):
        """With DPR=2.0 and no randomize, pixel (200,400) → CSS (100,200)."""
        page, cdp = _make_mock_page(dpr=2.0)
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        # The click_at function:
        # 1. If randomize, adds ±3 (we disable this)
        # 2. Gets DPR from page.evaluate
        # 3. Divides by DPR: css_x = x / dpr, css_y = y / dpr
        # 4. Checks viewport (mocked) 
        # 5. Dispatches CDP events with css_x, css_y
        
        # Override page.evaluate to return DPR=2.0 for the first call,
        # and viewport info for subsequent calls
        def evaluate_side_effect(script, *args, **kwargs):
            if "devicePixelRatio" in str(script):
                return 2.0
            if "innerWidth" in str(script):
                return {"w": 1280, "h": 720}
            if "canvas" in str(script):
                return False
            return None
        
        page.evaluate.side_effect = evaluate_side_effect
        page.main_frame.evaluate.side_effect = evaluate_side_effect
        
        bot.click_at(200, 400, randomize=False)
        
        # Check that CDP received CSS coordinates (divided by DPR)
        mouse_events = [
            c for c in cdp.send.call_args_list
            if c[0][0] == "Input.dispatchMouseEvent"
        ]
        assert len(mouse_events) >= 2  # mouseMoved, mousePressed, mouseReleased
        
        # The first mousePressed event should have x=100, y=200
        for c in mouse_events:
            params = c[0][1]
            if params.get("type") == "mousePressed":
                assert params["x"] == 100.0, f"Expected CSS x=100, got {params['x']}"
                assert params["y"] == 200.0, f"Expected CSS y=200, got {params['y']}"
                break

    def test_click_with_randomize_varies_coords(self):
        page, cdp = _make_mock_page()
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        coords = set()
        for _ in range(30):
            cdp.reset_mock()
            # Reset page.evaluate to return fresh values
            page.evaluate.return_value = 1.0
            page.main_frame.evaluate.return_value = False
            
            bot.click_at(500, 500, randomize=True)
            for c in cdp.send.call_args_list:
                if c[0][0] == "Input.dispatchMouseEvent":
                    params = c[0][1]
                    coords.add((params["x"], params["y"]))
                    break
        
        assert len(coords) > 1, "Randomize should produce different coordinates"

    def test_click_negative_coords_handled(self):
        page, cdp = _make_mock_page()
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        # Should not raise
        bot.click_at(-10, -20, randomize=False)

    def test_click_fallback_on_cdp_error(self):
        """When CDP errors, BotAction falls back to page.mouse.click."""
        page, cdp = _make_mock_page()
        cdp.send.side_effect = Exception("CDP session closed")
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        bot.click_at(100, 200, randomize=False)
        
        page.mouse.click.assert_called()

    def test_click_at_zero_zero(self):
        page, cdp = _make_mock_page()
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        bot.click_at(0, 0, randomize=False)
        assert cdp.send.called

    def test_click_without_page_uses_pyautogui(self):
        """When page is None, fallback to pyautogui."""
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=None, debug_visual_var=debug_var)
        
        with patch('bot_action.pyautogui') as mock_pag:
            bot.click_at(100, 200, randomize=False)
            mock_pag.click.assert_called()


class TestPressKey:
    """Test keyboard press actions."""

    def test_press_key_basic(self):
        page, cdp = _make_mock_page()
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        bot.press_key("Enter")
        page.keyboard.press.assert_called_with("Enter")

    def test_press_key_with_modifier(self):
        page, cdp = _make_mock_page()
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        
        bot.press_key("Control+c")
        page.keyboard.press.assert_called_with("Control+c")


class TestBotActionInit:
    """Test BotAction initialization."""

    def test_init_with_page(self):
        page, _ = _make_mock_page()
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=page, debug_visual_var=debug_var)
        assert bot.page is page

    def test_init_without_page(self):
        debug_var = MagicMock()
        debug_var.get.return_value = False
        bot = BotAction(page=None, debug_visual_var=debug_var)
        assert bot.page is None
        assert bot.cdp is None
