"""
Vercel Serverless Function — Download Proxy for Private GitHub Releases.

Since the repo is private, direct download URLs return 404.
This endpoint uses GITHUB_TOKEN to get a temporary download URL
from GitHub API and redirects the client there.

Endpoint: GET /api/download
"""

import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
DOWNLOAD_URL = os.environ.get("DOWNLOAD_URL", "").strip()

# Parse owner/repo and tag from DOWNLOAD_URL
# e.g. https://github.com/nhatpse/lordnine-bot/releases/download/v3.19.2/LordNineBot_v3.19.2_update.zip

def _get_asset_url():
    """Use GitHub API to get a temporary S3 download URL for the release asset."""
    if not GITHUB_TOKEN or not DOWNLOAD_URL:
        return None, "Not configured"
    
    # Parse the download URL to extract owner, repo, tag, filename
    # Format: https://github.com/{owner}/{repo}/releases/download/{tag}/{filename}
    parts = DOWNLOAD_URL.replace("https://github.com/", "").split("/")
    if len(parts) < 5:
        return None, "Invalid DOWNLOAD_URL format"
    
    owner = parts[0]
    repo = parts[1]
    tag = parts[4]  # e.g. v3.19.2
    filename = parts[5] if len(parts) > 5 else ""
    
    try:
        # Step 1: Get release by tag
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        req = Request(api_url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        resp = urlopen(req, timeout=10)
        release = json.loads(resp.read().decode())
        
        # Step 2: Find the matching asset
        for asset in release.get("assets", []):
            if asset["name"] == filename:
                # Step 3: Get the asset download URL with auth
                # GitHub API returns a 302 redirect to a temp S3 URL
                # when we request the asset with Accept: application/octet-stream
                asset_api_url = asset["url"]
                req2 = Request(asset_api_url, headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/octet-stream",
                    "X-GitHub-Api-Version": "2022-11-28",
                })
                # Don't actually download — just get the redirect URL
                import urllib.request
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        return None
                
                opener = urllib.request.build_opener(NoRedirect)
                try:
                    opener.open(req2, timeout=10)
                except HTTPError as e:
                    if e.code in (301, 302, 303, 307):
                        redirect_url = e.headers.get("Location")
                        if redirect_url:
                            return redirect_url, None
                    return None, f"GitHub redirect failed: {e.code}"
                
                return None, "No redirect received"
        
        return None, f"Asset '{filename}' not found in release {tag}"
        
    except HTTPError as e:
        return None, f"GitHub API error: {e.code}"
    except Exception as e:
        return None, f"Error: {str(e)}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url, error = _get_asset_url()
        if url:
            # Redirect client to temp S3 URL (no auth needed)
            self.send_response(302)
            self.send_header("Location", url)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": error}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
