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
    
    def launch(self, port=9222, proxy=None):
        """
        Launch a Chrome instance with remote debugging on the given port.
        
        Args:
            port: Debug port number
            proxy: Optional proxy string (e.g. "socks5://1.2.3.4:1080")
            
        Returns:
            (success: bool, message: str)
        """
        # Check if already running
        if port in self.processes and self.processes[port].poll() is None:
            return True, f"Chrome already running on port {port}"
        
        # Also check if port is externally occupied
        if self._is_port_reachable(port):
            # Port is occupied by external Chrome — register it
            self.processes[port] = None  # Mark as external
            return True, f"Chrome already active on port {port} (external)"
        
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
        
        try:
            proc = subprocess.Popen(cmd, shell=False, 
                                     stdout=subprocess.DEVNULL, 
                                     stderr=subprocess.DEVNULL)
            self.processes[port] = proc
            
            # Wait for Chrome to start accepting connections
            for attempt in range(15):  # 3 seconds max
                time.sleep(0.2)
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
                    proc.terminate()
                    proc.wait(timeout=5)
                except:
                    try:
                        proc.kill()
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
            resp = urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=0.3)
            return resp.status == 200
        except:
            return False
    
    def get_next_available_port(self):
        """Find the next unused port in the default range."""
        active = self.get_active_ports()
        for port in self.DEFAULT_PORT_RANGE:
            if port not in active:
                return port
        return None
