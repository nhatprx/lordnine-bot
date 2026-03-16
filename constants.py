import customtkinter as ctk

# Design System
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- Premium Color Palette (Refined) ---
COLOR = {
    # Backgrounds
    "bg":             "#0F1117",   # Deep dark bg
    "bg_subtle":      "#13151C",   # Slightly lighter bg
    "surface":        "#181B23",   # Panel/card background
    "surface2":       "#1E2130",   # Elevated surface (hover)
    "surface3":       "#222530",   # Highest elevation
    "border":         "#2A2D38",   # Standard border
    "border_subtle":  "#1F222C",   # Subtle border
    "sidebar":        "#0C0E14",   # Sidebar dark bg
    "sidebar_h":      "#14161E",   # Sidebar hover

    # Primary actions
    "primary":        "#5B8DEF",   # Softer blue
    "primary_h":      "#4A7DE0",   # Blue hover
    "primary_dim":    "#3A5A9E",   # Blue muted

    # Status colors
    "success":        "#4CAF82",   # Muted green
    "success_h":      "#3D9B70",   # Green hover
    "success_dim":    "#2D5A44",   # Green bg
    "danger":         "#D4626C",   # Muted rose
    "danger_h":       "#C4525C",   # Rose hover
    "danger_dim":     "#5A2D32",   # Rose bg
    "warning":        "#D4A24C",   # Muted amber
    "warning_h":      "#C4923C",   # Amber hover
    "accent":         "#5BB8CF",   # Muted cyan
    "accent_h":       "#4BA8BF",   # Cyan hover
    "purple":         "#9B7DCF",   # Muted purple
    "purple_h":       "#8B6DBF",   # Purple hover

    # Text
    "text":           "#D1D5DE",   # Primary text
    "text_dim":       "#8B90A0",   # Secondary text
    "text_dark":      "#1E293B",   # Dark text (on light bg)
    "text_muted":     "#555A68",   # Very dim text

    # Flowchart node colors
    "node_macro":     "#2563EB",
    "node_cond":      "#D97706",
    "node_delay":     "#8B5CF6",
    "node_start":     "#059669",
    "node_click":     "#E11D48",
    "node_end":       "#6B7280",
    "node_default":   "#475569",
    "wire":           "#64748B",
    "wire_true":      "#10B981",
    "wire_false":     "#F43F5E",
    "wire_drag":      "#F59E0B",
    "pin_in":         "#64748B",
    "pin_out":        "#F59E0B",
}

# --- Font System ---
FONT = {
    "family":       "Inter",
    "mono":         "Consolas",
    "h1":           ("Inter", 18, "bold"),
    "h2":           ("Inter", 15, "bold"),
    "h3":           ("Inter", 13, "bold"),
    "body":         ("Inter", 12),
    "small":        ("Inter", 11),
    "tiny":         ("Inter", 10),
    "mono_body":    ("Consolas", 11),
    "btn":          ("Inter", 12, "bold"),
    "btn_sm":       ("Inter", 11, "bold"),
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
