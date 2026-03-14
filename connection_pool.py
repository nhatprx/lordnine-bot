"""
Playwright Connection Pool — Thread-safe pool for sharing browser connections.

Accounts on the SAME port share ONE Playwright instance + ONE browser connection.
This reduces resource usage from N Playwright processes (1 per account) to M (1 per port).

Usage:
    pool = PlaywrightPool()
    page, release = pool.acquire(port=9222, tab_index=0)
    # ... use page ...
    release()  # When done
    pool.shutdown()  # Cleanup all
"""

import threading
from playwright.sync_api import sync_playwright
from constants import get_page_by_visual_index


class PlaywrightPool:
    """Thread-safe pool: 1 Playwright + 1 browser connection per Chrome port."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._connections = {}  # port -> {pw, browser, context, ref_count, lock}
    
    def acquire(self, port, tab_index):
        """
        Get a Playwright Page for the given port + tab_index.
        
        Returns:
            (page, tab_list_info) or (None, error_string)
        
        Call release(port) when done with this connection.
        """
        with self._lock:
            if port not in self._connections:
                # Create new connection for this port
                try:
                    pw = sync_playwright().start()
                    browser = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
                    context = browser.contexts[0]
                    self._connections[port] = {
                        'pw': pw,
                        'browser': browser,
                        'context': context,
                        'ref_count': 0,
                        'lock': threading.Lock(),
                    }
                except Exception as e:
                    return None, f"Cannot connect to Chrome on port {port}: {e}"
            
            conn = self._connections[port]
            conn['ref_count'] += 1
        
        # Get page outside the global lock (but still thread-safe per port)
        try:
            page, info = get_page_by_visual_index(conn['context'], tab_index, port=port)
            return page, info
        except Exception as e:
            self.release(port)
            return None, f"Failed to get tab {tab_index} on port {port}: {e}"
    
    def release(self, port):
        """Release one reference to the connection on this port."""
        with self._lock:
            if port not in self._connections:
                return
            
            conn = self._connections[port]
            conn['ref_count'] -= 1
            
            if conn['ref_count'] <= 0:
                # Last user — close everything
                try:
                    conn['browser'].close()
                except:
                    pass
                try:
                    conn['pw'].stop()
                except:
                    pass
                del self._connections[port]
    
    def reconnect(self, port, tab_index):
        """
        Force reconnect to a port (e.g. after connection drop).
        Closes existing connection and creates a new one.
        
        Returns:
            (page, info) or (None, error_string)
        """
        with self._lock:
            if port in self._connections:
                conn = self._connections[port]
                old_ref_count = conn['ref_count']
                try:
                    conn['browser'].close()
                except:
                    pass
                try:
                    conn['pw'].stop()
                except:
                    pass
                del self._connections[port]
            else:
                old_ref_count = 1
        
        # Re-acquire with the same ref count
        page, info = self.acquire(port, tab_index)
        if page:
            with self._lock:
                if port in self._connections:
                    self._connections[port]['ref_count'] = old_ref_count
        return page, info
    
    def get_connection_count(self):
        """Return number of active port connections."""
        with self._lock:
            return len(self._connections)
    
    def get_stats(self):
        """Return stats for all connections."""
        with self._lock:
            stats = {}
            for port, conn in self._connections.items():
                stats[port] = {
                    'ref_count': conn['ref_count'],
                    'pages': len(conn['context'].pages) if conn['context'] else 0,
                }
            return stats
    
    def shutdown(self):
        """Close ALL connections. Call on app exit."""
        with self._lock:
            for port, conn in list(self._connections.items()):
                try:
                    conn['browser'].close()
                except:
                    pass
                try:
                    conn['pw'].stop()
                except:
                    pass
            self._connections.clear()
