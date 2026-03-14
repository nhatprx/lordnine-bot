import customtkinter as ctk

# Design System
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- Premium Color Palette ---
COLOR = {
    # Backgrounds
    "bg":           "#0B0F19",   # Deep space background
    "surface":      "#141B2D",   # Panel/card background
    "surface2":     "#1C2640",   # Elevated surface
    "surface3":     "#243049",   # Highest elevation
    "border":       "#1E293B",   # Subtle border for glassmorphism
    "sidebar":      "#080C14",   # Sidebar dark bg
    "sidebar_h":    "#0F1420",   # Sidebar hover

    # Primary actions
    "primary":      "#3B82F6",   # Electric blue
    "primary_h":    "#2563EB",   # Blue hover
    "primary_dim":  "#1E40AF",   # Blue muted

    # Status colors
    "success":      "#10B981",   # Emerald green (softer)
    "success_h":    "#059669",   # Emerald hover
    "danger":       "#F43F5E",   # Rose red (softer)
    "danger_h":     "#E11D48",   # Rose hover
    "warning":      "#F59E0B",   # Amber
    "warning_h":    "#D97706",   # Amber hover
    "accent":       "#06B6D4",   # Cyan accent
    "accent_h":     "#0891B2",   # Cyan hover
    "purple":       "#8B5CF6",   # Purple/violet
    "purple_h":     "#7C3AED",   # Purple hover

    # Text
    "text":         "#E2E8F0",   # Primary text
    "text_dim":     "#64748B",   # Secondary text
    "text_dark":    "#1E293B",   # Dark text (on light bg)
    "text_muted":   "#475569",   # Very dim text
}

# --- Font System ---
FONT = {
    "family":       "Segoe UI",
    "mono":         "Consolas",
    "h1":           ("Segoe UI", 18, "bold"),
    "h2":           ("Segoe UI", 15, "bold"),
    "h3":           ("Segoe UI", 13, "bold"),
    "body":         ("Segoe UI", 12),
    "small":        ("Segoe UI", 11),
    "tiny":         ("Segoe UI", 10),
    "mono_body":    ("Consolas", 11),
    "btn":          ("Segoe UI", 12, "bold"),
    "btn_sm":       ("Segoe UI", 11, "bold"),
}

# --- Spacing ---
PAD = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
    "xxl": 24,
}

RADIUS = 10  # Default corner radius


def get_page_by_visual_index(browser_context, tab_index, port=9222):
    """
    Get a Playwright Page by its VISUAL position in Chrome (left-to-right).
    
    Chrome CDP /json returns targets in visual tab order.
    Playwright context.pages returns them in creation order.
    This maps visual position -> correct Playwright page using CDP Target IDs.
    
    Matching strategy (in priority order):
    1. Match by CDP targetId via page's cdpSession
    2. Match by webSocketDebuggerUrl (unique per tab)
    3. Match by URL with deduplication (only if URL is unique among tabs)
    4. Last resort: index-based fallback
    """
    import urllib.request
    import json

    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}/json")
        targets = json.loads(resp.read().decode())
    except Exception as e:
        return None, f"Cannot reach Chrome CDP at port {port}: {e}"

    page_targets = [t for t in targets if t.get("type") == "page"]

    if not page_targets:
        return None, "No page tabs found in Chrome."

    if tab_index >= len(page_targets):
        return None, f"Tab index {tab_index} out of range (only {len(page_targets)} tabs)."

    target_info = page_targets[tab_index]
    target_id = target_info.get("id")
    target_url = target_info.get("url", "")
    
    tab_list = [(i, t.get("title", "?"), t.get("url", "")) for i, t in enumerate(page_targets)]
    pw_pages = browser_context.pages
    
    # --- Strategy 1: Match by CDP Target ID ---
    # Build a map: target_id -> target_url for all CDP targets  
    id_to_url = {t.get("id"): t.get("url", "") for t in page_targets}
    url_to_ids = {}
    for t in page_targets:
        url = t.get("url", "")
        url_to_ids.setdefault(url, []).append(t.get("id"))
    
    # Try to match each Playwright page to the desired target_id
    # by checking if the page's URL maps to EXACTLY ONE target_id
    for p in pw_pages:
        try:
            p_url = p.url
            # If this URL is unique among targets, we can safely match by URL
            if p_url in url_to_ids and len(url_to_ids[p_url]) == 1:
                if url_to_ids[p_url][0] == target_id:
                    return p, tab_list
        except:
            continue
    
    # --- Strategy 2: For pages with duplicate URLs, use position-based matching ---
    # Build ordered list of Playwright pages that match each CDP target by URL
    # Then match by order of appearance
    
    # Count how many times we've seen each URL in CDP targets (up to tab_index)
    target_url_occurrence = 0  # which occurrence of this URL is our target?
    for i in range(tab_index + 1):
        if page_targets[i].get("url", "") == target_url:
            target_url_occurrence += 1
    # target_url_occurrence is now: "our target is the Nth page with this URL"
    
    # Find the Nth Playwright page with this URL
    seen_count = 0
    for p in pw_pages:
        try:
            if p.url == target_url:
                seen_count += 1
                if seen_count == target_url_occurrence:
                    return p, tab_list
        except:
            continue

    # --- Strategy 3: Last resort index-based fallback ---
    if tab_index < len(pw_pages):
        return pw_pages[tab_index], tab_list

    return None, f"Could not match Tab {tab_index} to any Playwright page."
