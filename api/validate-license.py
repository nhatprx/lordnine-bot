"""
Vercel Serverless Function — License Validation API Proxy.

Hides the GitHub Gist URL from clients. Validates license key + HWID binding.
Deploy to Vercel with environment variable:
  GIST_URL = https://gist.githubusercontent.com/nhatpse/.../raw/licenses.json
"""

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler


# Read Gist URL from Vercel environment variable (never exposed to client)
GIST_URL = os.environ.get("GIST_URL", "")


def _fetch_gist_licenses():
    """Fetch license data from GitHub Gist (server-side only)."""
    if not GIST_URL:
        return None
    try:
        req = urllib.request.Request(
            GIST_URL,
            headers={"Cache-Control": "no-cache", "User-Agent": "LordNineBot-Server/1.0"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("licenses", {})
    except Exception:
        return None


def _validate(key, hwid, licenses):
    """Validate license key and check HWID binding."""
    if key not in licenses:
        return {"valid": False, "message": "Invalid license key."}

    info = licenses[key]
    status = info.get("status", "locked")

    if status == "locked":
        return {"valid": False, "message": "This license has been revoked by admin."}
    if status == "expired":
        return {"valid": False, "message": "This license has expired."}

    # Check expiry date
    expires = info.get("expires")
    if expires:
        try:
            from datetime import datetime
            if datetime.now() > datetime.strptime(expires, "%Y-%m-%d"):
                return {"valid": False, "message": f"License expired on {expires}."}
        except Exception:
            pass

    if status != "active":
        return {"valid": False, "message": "Unknown license status."}

    # HWID binding check
    stored_hwid = info.get("hwid")
    if stored_hwid is None:
        # First activation — bind HWID (in a real setup, update the Gist via API)
        # For now, accept any HWID on first use
        pass
    elif stored_hwid and stored_hwid != hwid:
        return {
            "valid": False,
            "message": "This license is bound to another machine. Contact admin."
        }

    client = info.get("client", "")
    return {
        "valid": True,
        "message": f"Welcome, {client}!" if client else "License verified.",
        "client": client
    }


class handler(BaseHTTPRequestHandler):
    """Vercel serverless handler for POST /api/validate-license"""

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self._respond(400, {"valid": False, "message": "Invalid request body."})
            return

        key = data.get("key", "").strip()
        hwid = data.get("hwid", "").strip()

        if not key:
            self._respond(400, {"valid": False, "message": "License key is required."})
            return
        if not hwid:
            self._respond(400, {"valid": False, "message": "Machine ID is required."})
            return

        licenses = _fetch_gist_licenses()
        if licenses is None:
            self._respond(503, {"valid": False, "message": "License server unavailable."})
            return

        result = _validate(key, hwid, licenses)
        self._respond(200, result)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
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
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
