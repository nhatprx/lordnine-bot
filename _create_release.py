"""Create GitHub Release and upload update.zip — uses git credential manager for auth."""
import subprocess, json, os, sys, glob

REPO = "nhatpse/lordnine-bot"

# Get version from version.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from version import APP_VERSION

TAG = f"v{APP_VERSION}"
ZIP_PATTERN = f"dist/LordNineBot_v{APP_VERSION}_update.zip"

# Find zip
zips = glob.glob(ZIP_PATTERN)
if not zips:
    print(f"❌ No zip found matching {ZIP_PATTERN}")
    sys.exit(1)
zip_path = zips[0]
print(f"📦 Zip: {zip_path} ({os.path.getsize(zip_path):,} bytes)")

# Get token from git credential manager
try:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, timeout=10
    )
    token = None
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1]
            break
    if not token:
        print("❌ Could not get GitHub token from git credential manager")
        sys.exit(1)
except Exception as e:
    print(f"❌ Error getting credentials: {e}")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
}

import urllib.request, urllib.error

# Create release
print(f"🏷️  Creating release {TAG}...")
release_data = json.dumps({
    "tag_name": TAG,
    "name": TAG,
    "body": f"## {TAG}\n\n- Phone death logging: logs/deaths.log with phone name, timestamp, node context\n- Death events tracked at all failure points (connection, screenshot, health check, crash)\n- ⚡ Hard Click for Loops Click nodes\n- Click node configure dialog with toggle",
    "draft": False,
    "prerelease": False,
}).encode()

req = urllib.request.Request(
    f"https://api.github.com/repos/{REPO}/releases",
    data=release_data,
    headers={**headers, "Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req) as resp:
        release = json.loads(resp.read())
    upload_url = release["upload_url"].replace("{?name,label}", "")
    release_id = release["id"]
    print(f"✅ Release created: {release['html_url']}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if "already_exists" in body:
        # Get existing release
        print(f"⚠️  Release {TAG} already exists, fetching...")
        req2 = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}",
            headers=headers,
        )
        with urllib.request.urlopen(req2) as resp:
            release = json.loads(resp.read())
        upload_url = release["upload_url"].replace("{?name,label}", "")
        release_id = release["id"]
        print(f"✅ Using existing release: {release['html_url']}")
    else:
        print(f"❌ Failed to create release: {e.code} {body}")
        sys.exit(1)

# Upload zip
zip_name = os.path.basename(zip_path)
print(f"📤 Uploading {zip_name}...")

with open(zip_path, "rb") as f:
    zip_data = f.read()

upload_req = urllib.request.Request(
    f"{upload_url}?name={zip_name}",
    data=zip_data,
    headers={**headers, "Content-Type": "application/zip"},
    method="POST",
)

try:
    with urllib.request.urlopen(upload_req) as resp:
        asset = json.loads(resp.read())
    print(f"✅ Uploaded: {asset['browser_download_url']}")
    print(f"\n{'='*60}")
    print(f"📋 Release URL: {release['html_url']}")
    print(f"📋 Download URL: https://github.com/{REPO}/releases/download/{TAG}/{zip_name}")
    print(f"{'='*60}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"❌ Upload failed: {e.code} {body[:300]}")
    sys.exit(1)
