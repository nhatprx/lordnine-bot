"""
Test updater module — version parsing, comparison, download, apply logic.

Run: python -m pytest tests/test_updater.py -v -s
"""
import sys
import os
import json
import time
import zipfile
import hashlib
import tempfile
import shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from updater import (
    _parse_version, is_newer, check_for_update,
    download_update, apply_update, _get_app_dir
)


class TestVersionParsing:
    def test_basic_parse(self):
        assert _parse_version("3.15.6") == (3, 15, 6)
        assert _parse_version("v3.16.0") == (3, 16, 0)
        assert _parse_version("1.0.0") == (1, 0, 0)
        print("  ✅ Version parsing works")

    def test_is_newer(self):
        assert is_newer("3.16.0", "3.15.6") is True
        assert is_newer("3.15.7", "3.15.6") is True
        assert is_newer("4.0.0", "3.99.99") is True
        assert is_newer("3.15.6", "3.15.6") is False
        assert is_newer("3.15.5", "3.15.6") is False
        assert is_newer("3.14.0", "3.15.6") is False
        print("  ✅ Version comparison works")


class TestCheckForUpdate:
    @patch('updater.urllib.request.urlopen')
    def test_update_available(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "update_available": True,
            "latest_version": "3.16.0",
            "download_url": "https://example.com/update.zip",
            "changelog": "Fix bugs",
            "size": 47000000,
            "sha256": "abc123"
        }).encode()
        mock_urlopen.return_value = mock_resp

        result = check_for_update("3.15.6")
        assert result is not None
        assert result["latest"] == "3.16.0"
        assert result["download_url"] == "https://example.com/update.zip"
        assert result["sha256"] == "abc123"
        print("  ✅ Update check: new version detected")

    @patch('updater.urllib.request.urlopen')
    def test_no_update(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "update_available": False,
            "latest_version": "3.15.6"
        }).encode()
        mock_urlopen.return_value = mock_resp

        result = check_for_update("3.15.6")
        assert result is None
        print("  ✅ Update check: up to date")

    @patch('updater.urllib.request.urlopen')
    def test_network_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("timeout")

        result = check_for_update("3.15.6")
        assert result is None
        print("  ✅ Update check: network error handled gracefully")


class TestDownloadUpdate:
    def test_download_with_hash_verify(self):
        """Simulate download with file on disk and verify SHA-256."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake zip to "download"
            fake_zip = os.path.join(tmpdir, "source.zip")
            with zipfile.ZipFile(fake_zip, 'w') as zf:
                zf.writestr("test.txt", "hello world")

            # Calculate expected hash
            sha = hashlib.sha256()
            with open(fake_zip, 'rb') as f:
                sha.update(f.read())
            expected_hash = sha.hexdigest()

            # Mock urlopen to serve the fake zip
            dest_path = os.path.join(tmpdir, "downloaded.zip")

            with patch('updater.urllib.request.urlopen') as mock_urlopen:
                with open(fake_zip, 'rb') as f:
                    content = f.read()

                mock_resp = MagicMock()
                mock_resp.headers = {"Content-Length": str(len(content))}
                mock_resp.read.side_effect = [content, b'']
                mock_urlopen.return_value = mock_resp

                progress_calls = []
                success, error = download_update(
                    "https://example.com/update.zip",
                    dest_path,
                    progress_cb=lambda d, t: progress_calls.append((d, t)),
                    sha256_expected=expected_hash
                )

            assert success, f"Download should succeed but got: {error}"
            assert os.path.exists(dest_path)
            assert len(progress_calls) > 0
            print(f"  ✅ Download with SHA-256 verification works ({len(progress_calls)} progress calls)")

    def test_hash_mismatch_rejected(self):
        """File with wrong hash should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_zip = os.path.join(tmpdir, "source.zip")
            with zipfile.ZipFile(fake_zip, 'w') as zf:
                zf.writestr("test.txt", "hello world")

            dest_path = os.path.join(tmpdir, "bad.zip")

            with patch('updater.urllib.request.urlopen') as mock_urlopen:
                with open(fake_zip, 'rb') as f:
                    content = f.read()

                mock_resp = MagicMock()
                mock_resp.headers = {"Content-Length": str(len(content))}
                mock_resp.read.side_effect = [content, b'']
                mock_urlopen.return_value = mock_resp

                success, error = download_update(
                    "https://example.com/update.zip",
                    dest_path,
                    sha256_expected="0000000000000000wrong_hash"
                )

            assert not success
            assert "Hash mismatch" in error
            assert not os.path.exists(dest_path), "Bad file should be deleted"
            print("  ✅ Hash mismatch properly rejected")


class TestApplyUpdate:
    def test_update_script_generated(self):
        """apply_update should create the batch swap script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake update zip
            zip_path = os.path.join(tmpdir, "update.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr("LordNineBot/LordNineBot.exe", "fake exe")
                zf.writestr("LordNineBot/version.txt", "3.16.0")

            with patch('updater._get_app_dir', return_value=tmpdir):
                success, error = apply_update(zip_path)

            assert success, f"Apply should succeed: {error}"

            # Check script was created (batch file, not PowerShell)
            script_path = os.path.join(tmpdir, "_update.bat")
            assert os.path.exists(script_path), "Update batch script not found"

            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()

            assert "LordNineBot.exe" in script_content
            assert "xcopy" in script_content  # Batch copy command
            assert "waitloop" in script_content  # Wait for PID loop
            print("  OK: Update batch script generated correctly")

    def test_extracted_content_correct(self):
        """Verify zip is extracted to the correct temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "update.zip")
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr("LordNineBot/test_file.txt", "updated content")

            with patch('updater._get_app_dir', return_value=tmpdir):
                success, error = apply_update(zip_path)

            assert success
            extract_dir = os.path.join(tmpdir, "_update_temp", "extracted", "LordNineBot")
            assert os.path.exists(extract_dir), "Extracted content not found"
            test_file = os.path.join(extract_dir, "test_file.txt")
            assert os.path.exists(test_file)
            print("  ✅ Zip extracted correctly")


class TestCheckUpdateAPI:
    """Test the Vercel API handler logic (offline)."""

    def test_api_response_format(self):
        """Verify api/check-update.py can be imported and has correct handler."""
        # Add api/ to path
        api_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api")
        sys.path.insert(0, api_dir)

        try:
            import importlib
            spec = importlib.util.spec_from_file_location(
                "check_update_api",
                os.path.join(api_dir, "check-update.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            assert hasattr(mod, 'handler'), "API module must have 'handler' class"
            assert hasattr(mod, '_parse_version'), "API module must have _parse_version"
            assert mod._parse_version("3.15.6") == (3, 15, 6)
            print("  ✅ API module loads and parses versions correctly")
        finally:
            sys.path.remove(api_dir)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])
