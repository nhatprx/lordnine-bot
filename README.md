# LordNine Bot — Developer Guide

> **Current Version:** 3.19.8 · **Last Updated:** 2026-03-17
>
> Bot automation tool for LordNine game, running on cloud phones (Redfinger) via Chrome DevTools Protocol.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Core Concepts](#core-concepts)
- [Code Conventions](#code-conventions)
- [Build & Release Pipeline](#build--release-pipeline)
- [Infrastructure](#infrastructure)
- [Known Issues & Design Decisions](#known-issues--design-decisions)
- [Performance Notes](#performance-notes)
- [Logging & Debugging](#logging--debugging)
- [Version History](#version-history)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    LordNine Bot (main.py)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Accounts │ │  Loops   │ │  Macros  │ │  Nodes   │   │
│  │   Tab    │ │   Tab    │ │   Tab    │ │   Tab    │   │
│  └────┬─────┘ └──────────┘ └──────────┘ └──────────┘   │
│       │                                                  │
│  ┌────▼─────────────────────────────────────────────┐   │
│  │  Worker Threads (1 per account, daemon=True)     │   │
│  │  ├─ CDPClient.connect(port, tab_index)           │   │
│  │  ├─ BotAction (click, screenshot, OCR)           │   │
│  │  └─ Loop/Macro execution engine                  │   │
│  └────┬─────────────────────────────────────────────┘   │
│       │ gui_queue (thread-safe)                          │
│  ┌────▼─────────────────────────────────────────────┐   │
│  │  GUI Queue Processor (100ms tick, max 30/tick)   │   │
│  │  Coalesces dash_status, batches log lines        │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │
         │ WebSocket (CDP)
         ▼
┌───────────────────┐     ┌───────────────────┐
│  Chrome Profile 1 │     │  Chrome Profile 2 │
│  Port 9222        │     │  Port 9223        │
│  ├─ Tab 0 (Phone) │     │  ├─ Tab 0         │
│  ├─ Tab 1 (Phone) │     │  ├─ Tab 1         │
│  └─ ...           │     │  └─ ...           │
└───────────────────┘     └───────────────────┘
         │ Redfinger Cloud Phone
         ▼
    ┌──────────┐
    │ LordNine │
    │   Game   │
    └──────────┘
```

### Data Flow

1. **User** configures accounts (phone + loop/macro) in Accounts tab
2. **Quick Launch** opens Chrome with N tabs, auto-opens cloud phones per tab
3. **Start All** spawns 1 daemon thread per account
4. Each **worker thread** connects to its tab via CDP WebSocket
5. Worker executes the **flowchart loop** or **macro** — scan → click → delay → repeat
6. Status updates flow through `gui_queue` to main thread (throttled 1/sec)
7. Detailed logs go to **file** (`lordnine_debug.log`), errors only to GUI

---

## Project Structure

```
detect-lordnine/
├── main.py                 # App entry point, CTk root, GUI queue processor, sidebar
├── tab_accounts.py         # Accounts tab: multi-account coordinator, workers, Quick Launch
├── tab_loops.py            # Loops tab: flowchart editor for loop logic
├── tab_macros.py           # Macros tab: combo/macro editor
├── tab_nodes.py            # Nodes tab: image tracker management (learn, test, delete)
├── flowchart_ui.py         # Visual flowchart canvas (node drag, edge routing)
├── graph_engine.py         # Graph traversal logic for flowchart execution
├── macro_runner.py         # Macro step executor (click, wait, scan)
│
├── cdp_client.py           # Chrome DevTools Protocol client (WebSocket, screenshot, click)
├── chrome_manager.py       # Chrome process launcher, tab manager, phone name scanner
├── connection_pool.py      # (Legacy) Connection pool — mostly unused
├── bot_action.py           # High-level bot actions (click_at, screenshot, mouse_move)
├── vision.py               # Template matching, OCR, HSV color detection
├── screencapture.py        # Screen capture utilities
├── node_features.py        # Node metadata (color detect flags, text node helpers)
│
├── state_db.py             # SQLite state persistence (account states, action log)
├── constants.py            # Design system: colors, fonts, padding, radius
├── version.py              # Single source of truth: APP_VERSION = "3.19.8"
├── license_manager.py      # License key validation (HWID binding, Vercel API)
├── updater.py              # Auto-update system (check, download, apply, restart)
├── ui_dialogs.py           # Reusable dialog/modal helpers
│
├── api/                    # Vercel serverless functions
│   ├── check-update.py     # GET /api/check-update?v=X.Y.Z → update info
│   ├── download.py         # GET /api/download → proxy for private repo assets
│   └── validate-license.py # POST /api/validate-license → license check + HWID
├── vercel.json             # Vercel routing config (builds + routes)
│
├── build_exe.py            # PyInstaller build script → dist/LordNineBot/
├── protect_and_build.py    # PyArmor + PyInstaller protected build
├── installer.iss           # Inno Setup installer script
├── LordNineBot.spec        # PyInstaller spec file
│
├── trackers/               # User data: saved node images (.png)
├── config.json             # User preferences
├── combos.json             # Saved macros/combos
├── loops.json              # Saved loop flowcharts
├── multi.json              # Account list (names, ports, targets, loops)
│
├── lordnine_debug.log      # Runtime debug log (rotated 5MB × 3)
└── tests/                  # Stress tests, E2E tests
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| GUI | CustomTkinter (CTk) on Python 3.13 |
| Browser Control | CDP over WebSocket (`websocket-client`) |
| Image Detection | OpenCV (`cv2`) template matching + HSV histograms |
| OCR | (built into vision.py) |
| Database | SQLite via `sqlite3` (batched writes) |
| Packaging | PyInstaller (frozen .exe) |
| Installer | Inno Setup (.iss → .exe) |
| Update Server | Vercel (Python serverless) |
| Hosting | GitHub (private repo) + Vercel |
| Code Protection | PyArmor (optional) |

---

## Core Concepts

### CDPClient (cdp_client.py)
- **Lightweight** Chrome DevTools Protocol client (~1KB per instance vs ~100MB Playwright)
- Connects via WebSocket to `ws://localhost:{port}/devtools/page/{id}`
- **Per-port lock** prevents concurrent `/json` calls crashing Chrome
- **Tab cache** (2s TTL) avoids redundant HTTP calls
- **Retry logic** (3 attempts with cache clear) for high-load reliability
- Key methods: `screenshot()`, `evaluate()`, `mouse_move()`, `click()`

### Worker Threads (tab_accounts.py)
- 1 daemon thread per account, spawned by `_start_account()`
- **Stagger start**: 5 accounts/second + random jitter to avoid CDP overload
- Each worker has its own `CDPClient` instance
- **Keep-alive**: sends `mouse_move(1,1)` every 4.5 minutes to prevent Redfinger timeout
- **Auto-reconnect**: 5 retries with exponential backoff on connection loss

### GUI Queue (main.py)
- Thread-safe `queue.Queue` bridges worker threads → main thread
- Processed every 100ms, max 30 messages per tick
- **Coalescing**: `dash_status` keeps only latest per account
- **Batch logging**: multiple log lines inserted in single widget operation
- Message types: `log`, `dash_status`, `conn_status`, `test_notif`, `run`

### Flowchart Engine
- Nodes: `Start`, `End`, `Condition`, `Click`, `Delay`, `Macro`
- Edges connect output pins to input pins
- `Condition` node: screenshot → template match → TRUE/FALSE branch
- `Click` node: screenshot → find → click at coordinates
- `Macro` node: runs a saved macro sequence inline

### Auto-Update System (updater.py)
- Check: `GET /api/check-update?v={current}` → Vercel API
- Download: `GET /api/download` → Vercel proxy → GitHub release asset (private repo)
- Apply: extract zip → create `_update.bat` with xcopy
- Restart: `os._exit(0)` to force-terminate → batch waits for PID exit → xcopy files → start exe
- **Important**: uses `.bat` (not PowerShell) for reliability across all Windows versions

---

## Code Conventions

### General Rules
- **Python 3.13+**, no type hints enforced but encouraged
- **Imports**: stdlib → third-party → local, separated by blank lines
- **Thread safety**: always use `gui_queue.put()` to update UI from worker threads, **NEVER** call Tk widgets directly from threads
- **Logging**: errors → `self.log_gui()` (shows in GUI), verbose → `flog()` or `_file_logger` (file only)

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase` (e.g., `CDPClient`, `BotAction`)
- Functions/methods: `snake_case` with leading `_` for private
- Constants: `UPPER_SNAKE_CASE`
- GUI callbacks: `_on_event_name` or `_handle_event_name`

### Status Updates (Worker → GUI)
```python
# ✅ DO: throttled update (max 1/sec per account)
throttled_dash("Scanning: icon...", COLOR["warning"])

# ❌ DON'T: direct update floods GUI queue
self.update_dash_status(acc_name, "Scanning...", COLOR["warning"])

# ✅ DO: file-only logging for verbose info
flog(f"Condition {img_name} → TRUE")

# ❌ DON'T: log every step to GUI
self.log_gui(f"[{acc_name}] Condition {img_name} → TRUE")
```

### Version Bumping
- **Single source of truth**: `version.py` → `APP_VERSION = "X.Y.Z"`
- Also update `installer.iss`: `AppVersion` and `OutputBaseFilename`
- Semantic versioning: `major.minor.patch`

---

## Build & Release Pipeline

### Prerequisites
- Python 3.13 with PyInstaller
- Inno Setup 6 (for installer)
- Vercel CLI (`npm i -g vercel`)
- GitHub credentials in git credential store

### Build Steps

```bash
# 1. Bump version
# Edit version.py → APP_VERSION = "X.Y.Z"
# Edit installer.iss → AppVersion and OutputBaseFilename

# 2. Build exe + update zip
python build_exe.py
# Output: dist/LordNineBot_vX.Y.Z_update.zip
# Prints: UPDATE_SIZE, UPDATE_SHA256

# 3. Build installer (optional, for manual distribution)
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
# Output: installer_output/LordNineBotSetup_vX.Y.Z.exe

# 4. Commit and push
git add -A
git commit -m "vX.Y.Z: description"
git push origin master

# 5. Create GitHub release + upload asset
# Use GitHub API or web UI to create release with tag vX.Y.Z
# Upload dist/LordNineBot_vX.Y.Z_update.zip as release asset

# 6. Update Vercel env vars (use Python subprocess, NOT PowerShell echo)
# LATEST_VERSION = "X.Y.Z"
# DOWNLOAD_URL = "https://github.com/nhatpse/lordnine-bot/releases/download/vX.Y.Z/..."
# UPDATE_SIZE = "<bytes>"
# UPDATE_SHA256 = "<hash>"

# 7. Deploy Vercel
vercel --prod --yes
```

> **⚠️ IMPORTANT**: Never use PowerShell `echo "value" | vercel env add` — it appends newlines to values, causing 404 errors. Always use Python `subprocess.run(..., input=value)` with `shell=True`.

### Automated Release Script Pattern

```python
# See _release.py pattern used in development
import subprocess
envs = {"KEY": "value"}
for k, v in envs.items():
    subprocess.run(f"vercel env add {k} production --force",
                   input=v, capture_output=True, text=True, shell=True)
```

---

## Infrastructure

### Vercel Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/check-update?v=X.Y.Z` | Returns update info (version, download URL, changelog) |
| `GET /api/download` | Proxy for private GitHub release assets (uses `GITHUB_TOKEN`) |
| `POST /api/validate-license` | License key + HWID validation |

### Vercel Environment Variables

| Variable | Example | Notes |
|----------|---------|-------|
| `LATEST_VERSION` | `3.19.8` | Current release version |
| `DOWNLOAD_URL` | `https://github.com/.../update.zip` | Direct GitHub URL (proxy resolves auth) |
| `UPDATE_SIZE` | `72365839` | Bytes, for progress bar |
| `UPDATE_SHA256` | `7dca778b...` | Integrity check |
| `CHANGELOG` | `Fix: ...` | Shown in update dialog |
| `GITHUB_TOKEN` | `gho_...` | For `/api/download` proxy (private repo) |
| `GIST_ID` | `...` | License key storage |
| `GIST_TOKEN` | `...` | Gist API access |

### Why Download Proxy?

The GitHub repo is **private**. Direct release asset URLs return 404 without auth. The `/api/download` endpoint:
1. Uses `GITHUB_TOKEN` to call GitHub API
2. Gets the release asset's temporary S3 URL via redirect
3. Returns 302 redirect to client → client downloads from S3 (no auth needed)

---

## Known Issues & Design Decisions

### Bootstrap Update Problem
Users on versions ≤ v3.19.1 cannot auto-update because the updater itself was broken (PowerShell + SSL issues). **Solution**: distribute installer manually for first upgrade. After installing v3.19.4+, auto-update works via batch file.

### Auto-Update Mechanism
- **PowerShell** (v3.17–v3.19.3): unreliable — execution policy blocks, silent failures, process not exiting
- **Batch file** (v3.19.4+): `_update.bat` with `xcopy /E /Y` — works on all Windows
- **Critical**: `os._exit(0)` is used (not `root.destroy()`) to ensure the Python process actually terminates so the batch script can detect PID exit and proceed

### Multi-Profile Chrome
- Quick Launch distributes accounts across multiple Chrome instances (max tabs per Chrome configurable)
- Each Chrome runs on a different debug port: 9222, 9223, 9224...
- **Phone indices are offset per profile** — profile 1 opens phones [0-6], profile 2 opens [7-13], etc.
- Phone names can collide across profiles → port suffix appended (e.g., "Alcoholic (9224)")

### SSL in PyInstaller Builds
PyInstaller bundles don't include system CA certificates. The updater detects frozen mode (`sys._MEIPASS`) and falls back to unverified SSL context (`ssl.CERT_NONE`) for update downloads.

---

## Performance Notes

### Scaling to 20+ Accounts
With 20+ concurrent worker threads, these optimizations prevent UI freeze:

| Optimization | Impact |
|-------------|--------|
| **Throttled dash_status** (1/sec per account) | ~90% reduction in GUI queue messages |
| **Throttled state_db saves** (5s interval) | ~95% reduction in SQLite writes during loops |
| **File-only macro/loop logs** | GUI queue only receives errors, not every step |
| **GUI queue coalescing** | Keeps only latest status per account per tick |
| **Batch log insertion** | Single widget op instead of N |
| **Per-port CDP lock** | Prevents concurrent `/json` calls crashing Chrome |
| **CDPClient retry** (3 attempts) | Handles transient failures under load |
| **Stagger start** (5 acc/sec + jitter) | Prevents CDP connection storm |

### Memory
- Each `CDPClient` instance: ~1KB (vs ~100MB per Playwright instance)
- 30 accounts ≈ 30KB CDPClient overhead
- Main memory consumers: screenshot buffers (JPEG, ~50-100KB each), OpenCV template matching

---

## Logging & Debugging

### File Logger
- Path: `lordnine_debug.log` (in app directory)
- Rotation: 5MB × 3 backup files
- Format: `HH:MM:SS [LEVEL] [AccName] message`
- Contents: every condition result, click result, macro step, connection attempt, reconnect

### GUI Logger
Only shows:
- Connection errors (screenshot fail, WebSocket disconnect)
- Macro errors (crash, not found)
- Loop restart warnings (3+ consecutive restarts)
- System messages (update check, Quick Launch progress)

### Debugging a User Issue
1. Ask user to send `lordnine_debug.log` from their install directory
2. Look for `Connection failed`, `Screenshot Error`, `Macro error` patterns
3. Check `_update_log.txt` for auto-update failures
4. Check `bot_state.db` (SQLite) for account state history

---

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| 3.19.8 | 2026-03-17 | Throttled GUI updates, file logger, macro logs → file only |
| 3.19.7 | 2026-03-17 | CDPClient.connect() retry logic (3 attempts) |
| 3.19.6 | 2026-03-17 | `os._exit(0)` for update, hidden batch terminal |
| 3.19.5 | 2026-03-17 | Fix duplicate phone opens across Chrome profiles |
| 3.19.4 | 2026-03-17 | Fix PRESERVE_FILES NameError crash in updater |
| 3.19.3 | 2026-03-17 | Batch file updater (replaces PowerShell) |
| 3.19.2 | 2026-03-17 | Download proxy for private repo, duplicate name fix |
| 3.19.1 | 2026-03-17 | SSL fix for PyInstaller builds |
| 3.19.0 | 2026-03-17 | Refresh button, multi-profile Chrome merge |
| 3.18.0 | 2026-03-16 | Keep-alive, HSV color detect, auto-update, DB batching |
| 3.17.0 | 2026-03-15 | CDPClient (replaces Playwright), Quick Launch, multi-account |

---

## User Data Files (Preserved During Update)

These files are **never overwritten** by auto-update:
- `config.json` — User preferences
- `combos.json` / `combos.json.bak` — Saved macros
- `loops.json` / `loops.json.bak` — Saved loop flowcharts
- `multi.json` / `multi.json.bak` — Account list
- `bot_state.db` — SQLite state database
- `license.key` — License key
- `trackers/` — Node images
