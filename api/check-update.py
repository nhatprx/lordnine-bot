"""
Vercel Serverless Function — Update Check API.

Client sends current version, server responds with latest version info.

Configuration via Vercel environment variables:
    LATEST_VERSION  = "3.16.0"
    DOWNLOAD_URL    = "https://github.com/nhatpse/lordnine-releases/releases/download/v3.16.0/LordNineBot_v3.16.0_update.zip"
    CHANGELOG       = "• Fix connection 20+ accounts\\n• Thêm auto-update"
    UPDATE_SIZE     = "47185920"  (bytes, optional)
    UPDATE_SHA256   = "abc123..."  (optional, for integrity check)

Endpoint: GET /api/check-update?v=3.15.6
"""

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# Read config from Vercel environment variables
LATEST_VERSION = os.environ.get("LATEST_VERSION", "").strip()
DOWNLOAD_URL = os.environ.get("DOWNLOAD_URL", "").strip()
CHANGELOG = os.environ.get("CHANGELOG", "Bug fixes and improvements.").strip().replace("\\n", "\n")
UPDATE_SIZE = int(os.environ.get("UPDATE_SIZE", "0").strip() or "0")
UPDATE_SHA256 = os.environ.get("UPDATE_SHA256", "").strip()


def _parse_version(v):
    """Parse version string to tuple: '3.15.6' → (3, 15, 6)"""
    v = v.strip().lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


class handler(BaseHTTPRequestHandler):
    """Vercel serverless handler for GET /api/check-update"""

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        client_version = params.get("v", ["0.0.0"])[0].strip()

        if not LATEST_VERSION or not DOWNLOAD_URL:
            self._respond(200, {
                "update_available": False,
                "message": "Update server not configured."
            })
            return

        client_v = _parse_version(client_version)
        latest_v = _parse_version(LATEST_VERSION)

        if latest_v > client_v:
            # Use our download proxy (/api/download) since repo is private
            # Direct GitHub URLs return 404 for private repos
            proxy_url = "https://lordnine-update.vercel.app/api/download"
            self._respond(200, {
                "update_available": True,
                "latest_version": LATEST_VERSION,
                "download_url": proxy_url,
                "changelog": CHANGELOG,
                "size": UPDATE_SIZE,
                "sha256": UPDATE_SHA256,
            })
        else:
            self._respond(200, {
                "update_available": False,
                "latest_version": LATEST_VERSION,
                "message": "You are up to date."
            })

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _respond(self, status_code, data):
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
