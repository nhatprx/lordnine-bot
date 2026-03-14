"""
Chrome Manager — Manages multiple Chrome browser instances on different debug ports.

Each Chrome instance handles a group of tabs (recommended: max 10 tabs per instance).
For scaling to 100+ accounts, use 10+ Chrome instances on ports 9222-9232+.

Usage:
    manager = ChromeManager()
    manager.launch(port=9222)         # Launch Chrome on port 9222
    manager.launch(port=9223, proxy="socks5://1.2.3.4:1080")
    ports = manager.get_active_ports() # [9222, 9223]
    info  = manager.get_port_info(9222) # {port, pid, tab_count, tabs: [...]}
    manager.kill(port=9223)            # Kill Chrome on port 9223
"""

import subprocess
import os
import time
import json
import urllib.request
import urllib.parse
import signal


class ChromeManager:
    """Manages multiple Chrome instances with remote debugging ports."""
    
    DEFAULT_PORT_RANGE = range(9222, 9242)  # 20 possible Chrome instances
    
    def __init__(self, base_user_data_dir=None):
        """
        Args:
            base_user_data_dir: Base folder for Chrome user data dirs.
                Each port gets its own subfolder to isolate sessions.
        """
        self.processes = {}  # port -> subprocess.Popen
        self.proxies = {}    # port -> proxy string
        
        if base_user_data_dir:
            self.base_user_data_dir = base_user_data_dir
        else:
            self.base_user_data_dir = os.path.join(os.path.expanduser("~"), ".lordnine_chrome")
        
        os.makedirs(self.base_user_data_dir, exist_ok=True)
    
    def _find_chrome_path(self):
        """Find Chrome executable on Windows."""
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None
    
    def launch(self, port=9222, proxy=None, startup_url=None):
        """
        Launch a Chrome instance with remote debugging on the given port.
        
        Args:
            port: Debug port number
            proxy: Optional proxy string (e.g. "socks5://1.2.3.4:1080")
            
        Returns:
            (success: bool, message: str)
        """
        # Check if already running (managed process)
        if port in self.processes:
            proc = self.processes[port]
            if proc is not None and proc.poll() is None:
                return True, f"Chrome already running on port {port}"
        
        chrome_path = self._find_chrome_path()
        if not chrome_path:
            return False, "Chrome not found. Install Chrome or provide path."
        
        user_data_dir = os.path.join(self.base_user_data_dir, f"profile_port_{port}")
        os.makedirs(user_data_dir, exist_ok=True)
        
        cmd = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        
        if proxy:
            cmd.append(f"--proxy-server={proxy}")
            self.proxies[port] = proxy
        
        if startup_url:
            cmd.append(startup_url)
        
        try:
            proc = subprocess.Popen(cmd, shell=False, 
                                     stdout=subprocess.DEVNULL, 
                                     stderr=subprocess.DEVNULL)
            self.processes[port] = proc
            
            # Wait for Chrome to start accepting connections
            for attempt in range(10):  # 1 second max
                time.sleep(0.1)
                if self._is_port_reachable(port):
                    return True, f"Chrome launched on port {port} (PID: {proc.pid})"
            
            return True, f"Chrome launched on port {port} (PID: {proc.pid}, slow start)"
            
        except Exception as e:
            return False, f"Failed to launch Chrome: {e}"
    
    def kill(self, port):
        """Kill Chrome instance on the given port."""
        if port in self.processes:
            proc = self.processes[port]
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except:
                    pass
            del self.processes[port]
            if port in self.proxies:
                del self.proxies[port]
            return True, f"Chrome on port {port} terminated"
        return False, f"No Chrome managed on port {port}"
    
    def kill_all(self):
        """Kill all managed Chrome instances."""
        ports = list(self.processes.keys())
        for port in ports:
            self.kill(port)
    
    def get_active_ports(self):
        """Return list of ports with reachable Chrome instances."""
        active = []
        # Check managed processes
        for port in list(self.processes.keys()):
            if self._is_port_reachable(port):
                active.append(port)
            else:
                # Process died, clean up
                if self.processes[port] is not None:
                    del self.processes[port]
        
        # Also scan for externally launched Chrome
        for port in self.DEFAULT_PORT_RANGE:
            if port not in active and self._is_port_reachable(port):
                active.append(port)
                self.processes[port] = None  # Mark as external
        
        return sorted(active)
    
    def get_port_info(self, port):
        """
        Get info about a Chrome instance on the given port.
        
        Returns:
            dict with {port, status, tab_count, tabs: [{index, title, url, id}], proxy}
            or None if port is not reachable
        """
        try:
            resp = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=0.5)
            targets = json.loads(resp.read().decode())
            page_targets = [t for t in targets if t.get("type") == "page"]
            
            tabs = []
            for i, t in enumerate(page_targets):
                tabs.append({
                    "index": i,
                    "title": t.get("title", "(untitled)")[:50],
                    "url": t.get("url", "")[:80],
                    "id": t.get("id", ""),
                })
            
            pid = None
            if port in self.processes and self.processes[port] is not None:
                pid = self.processes[port].pid
            
            return {
                "port": port,
                "status": "running",
                "pid": pid,
                "tab_count": len(page_targets),
                "tabs": tabs,
                "proxy": self.proxies.get(port, ""),
            }
        except:
            return None
    
    def get_all_ports_info(self):
        """Get info for all active ports."""
        result = []
        for port in self.get_active_ports():
            info = self.get_port_info(port)
            if info:
                result.append(info)
        return result
    
    def _is_port_reachable(self, port):
        """Check if Chrome is reachable on the given port."""
        try:
            resp = urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=0.15)
            return resp.status == 200
        except:
            return False
    
    def get_next_available_port(self):
        """Find the next unused port in the default range."""
        for port in self.DEFAULT_PORT_RANGE:
            if port not in self.processes:
                return port
        return None
    
    def open_tabs(self, port, url, count=1):
        """
        Open new tabs on an existing Chrome instance via CDP.
        
        Args:
            port: Chrome debug port
            url: URL to open in each tab
            count: Number of tabs to open
            
        Returns:
            (opened_count, error_msg or None)
        """
        opened = 0
        for i in range(count):
            try:
                encoded_url = urllib.parse.quote(url, safe=':/')
                req_url = f"http://localhost:{port}/json/new?{encoded_url}"
                req = urllib.request.Request(req_url, method='PUT', data=b'')
                resp = urllib.request.urlopen(req, timeout=5)
                if resp.status == 200:
                    opened += 1
            except Exception as e:
                print(f"[open_tabs] Tab {i+1} FAILED: {e}")
                return opened, f"Failed at tab {i+1}: {e}"
        return opened, None
    
    def launch_with_tabs(self, port, url, tab_count, proxy=None):
        """
        Launch Chrome on a port and open multiple tabs to the given URL.
        
        Args:
            port: Debug port
            url: URL to open in all tabs
            tab_count: Total number of tabs to have
            proxy: Optional proxy string
            
        Returns:
            (success, message, actual_tab_count)
        """
        # Launch Chrome with URL as startup arg (first tab opens URL directly)
        success, msg = self.launch(port=port, proxy=proxy, startup_url=url)
        if not success:
            return False, msg, 0
        
        # Brief wait (launch() already polls for port readiness)
        time.sleep(0.5)
        
        # Open remaining tabs (tab_count - 1, since first tab already has URL)
        remaining = tab_count - 1
        if remaining > 0:
            opened, err = self.open_tabs(port, url, remaining)
            if err:
                return True, f"Chrome port {port}: opened {opened + 1}/{tab_count} tabs. {err}", opened + 1
        
        # Verify final tab count
        info = self.get_port_info(port)
        actual = info["tab_count"] if info else tab_count
        
        return True, f"Chrome port {port}: {actual} tabs ready", actual
    
    def auto_open_cloud_phones(self, port, phone_indices, timeout=15):
        """
        Auto-click cloud phone cards on the Redfinger page.
        
        Uses Playwright to connect to Chrome via CDP, find cloud phone cards,
        and click on the specified indices. Each tab clicks a different phone.
        
        Args:
            port: Chrome debug port
            phone_indices: list of 0-based indices, one per tab
                e.g. [0, 1, 2] = click phone 1, 2, 3
            timeout: max seconds to wait for page load
            
        Returns:
            (opened_count, errors_list)
        """
        from playwright.sync_api import sync_playwright
        
        pw = sync_playwright().start()
        opened = 0
        errors = []
        phone_names = {}  # tab_idx -> phone_name
        
        try:
            browser = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
            pages = browser.contexts[0].pages
            
            # Filter to Redfinger pages only
            rf_pages = [p for p in pages if "cloudemulator" in p.url or "redfinger" in p.url]
            
            if not rf_pages:
                errors.append("No Redfinger pages found")
                return opened, errors
            
            for tab_idx, page in enumerate(rf_pages):
                if tab_idx >= len(phone_indices):
                    break
                
                phone_idx = phone_indices[tab_idx]
                
                try:
                    # Wait for phone cards to load
                    page.wait_for_selector('div.phone-col.grid-item', timeout=timeout * 1000)
                    
                    # Find all phone cards
                    cards = page.query_selector_all('div.phone-col.grid-item')
                    
                    if phone_idx >= len(cards):
                        errors.append(f"Tab {tab_idx}: phone #{phone_idx+1} not found (only {len(cards)} phones)")
                        continue
                    
                    # Get phone name for logging
                    name_el = cards[phone_idx].query_selector('div.single-line')
                    phone_name = name_el.inner_text() if name_el else f"Phone #{phone_idx+1}"
                    
                    # Click the phone card to open it
                    cards[phone_idx].click()
                    opened += 1
                    phone_names[tab_idx] = phone_name
                    print(f"[auto_open] Tab {tab_idx}: opened {phone_name}")
                    
                except Exception as e:
                    errors.append(f"Tab {tab_idx}: {e}")
            
        except Exception as e:
            errors.append(f"Connection error: {e}")
        finally:
            try:
                pw.stop()
            except:
                pass
        
        return opened, errors, phone_names
