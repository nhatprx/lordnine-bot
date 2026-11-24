"""
Cross-platform crisp vector-style monochrome icons rendered via Pillow + CTkImage.
Works identically on macOS, Windows, and Linux without relying on Windows-only fonts
like Segoe MDL2 Assets or emoji glyphs.
"""

import math
import customtkinter as ctk
from PIL import Image, ImageDraw

_ICON_CACHE = {}


def _hex_to_rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _draw_icon(name, color_hex, size=18):
    """Render a 4x supersampled anti-aliased monochrome line icon as PIL.Image."""
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = _hex_to_rgba(color_hex)
    w = max(2, int(round(1.7 * scale)))  # ~1.7px stroke at 1x

    def pt(x, y):
        """Map 0..24 viewBox coordinates to pixel coordinates."""
        return (x / 24.0 * s, y / 24.0 * s)

    def box(x1, y1, x2, y2):
        return [x1 / 24.0 * s, y1 / 24.0 * s, x2 / 24.0 * s, y2 / 24.0 * s]

    def line(x1, y1, x2, y2, width=w):
        d.line([pt(x1, y1), pt(x2, y2)], fill=c, width=width, joint="curve")

    def rrect(x1, y1, x2, y2, r=2.0, width=w, fill=None):
        d.rounded_rectangle(
            box(x1, y1, x2, y2),
            radius=r / 24.0 * s,
            outline=c,
            fill=fill,
            width=width,
        )

    if name == "nodes":
        # 2x2 grid of rounded squares (Lucide layout-grid)
        rrect(3, 3, 10, 10, r=1.8)
        rrect(14, 3, 21, 10, r=1.8)
        rrect(3, 14, 10, 21, r=1.8)
        rrect(14, 14, 21, 21, r=1.8)

    elif name == "macros":
        # Lightning bolt (Lucide zap)
        pts = [
            pt(13.5, 2.5),
            pt(4.5, 13.5),
            pt(11.5, 13.5),
            pt(10.5, 21.5),
            pt(19.5, 10.5),
            pt(12.5, 10.5),
            pt(13.5, 2.5),
        ]
        d.line(pts, fill=c, width=w, joint="curve")

    elif name == "automation":
        # Loop / repeat arrows (Lucide repeat / sync)
        # Top horizontal + right arrow
        line(4, 9, 19, 9)
        line(15.5, 5.5, 19.5, 9)
        line(15.5, 12.5, 19.5, 9)
        # Bottom horizontal + left arrow
        line(20, 16, 5, 16)
        line(8.5, 12.5, 4.5, 16)
        line(8.5, 19.5, 4.5, 16)

    elif name == "accounts":
        # Users icon (Lucide user)
        d.ellipse(box(8, 3.5, 16, 11.5), outline=c, width=w)
        d.arc(box(4, 13.5, 20, 27), start=195, end=345, fill=c, width=w)

    elif name == "output":
        # Document / list lines (Lucide file-text)
        rrect(4, 3, 20, 21, r=2.2)
        line(8, 8.5, 16, 8.5)
        line(8, 12.5, 16, 12.5)
        line(8, 16.5, 13, 16.5)

    elif name == "lock":
        # Closed padlock (Lucide lock)
        rrect(5, 11, 19, 21, r=2.2)
        d.arc(box(8, 4, 16, 14), start=180, end=360, fill=c, width=w)
        line(8, 9, 8, 11)
        line(16, 9, 16, 11)
        d.ellipse(box(11, 15, 13, 17), fill=c)

    elif name == "unlock":
        # Open padlock (Lucide lock-open)
        rrect(5, 11, 19, 21, r=2.2)
        d.arc(box(8, 4, 16, 14), start=180, end=330, fill=c, width=w)
        line(8, 9, 8, 11)
        d.ellipse(box(11, 15, 13, 17), fill=c)

    elif name == "refresh":
        # Circular refresh arrow (Lucide rotate-cw)
        d.arc(box(4, 4, 20, 20), start=35, end=325, fill=c, width=w)
        # Arrowhead near top-right (~325 deg)
        line(19.2, 4.8, 19.2, 9.8)
        line(14.2, 9.8, 19.2, 9.8)

    elif name == "quit":
        # Power symbol (Lucide power)
        d.arc(box(4.5, 5, 19.5, 20), start=305, end=235, fill=c, width=w)
        line(12, 3, 12, 11.5)

    elif name == "key":
        # Key icon (Lucide key-round)
        d.ellipse(box(3.5, 9, 11.5, 17), outline=c, width=w)
        line(11.5, 13, 20.5, 13)
        line(17, 13, 17, 16.5)
        line(20, 13, 20, 16.5)

    elif name == "error":
        # X inside circle
        d.ellipse(box(3.5, 3.5, 20.5, 20.5), outline=c, width=w)
        line(9, 9, 15, 15)
        line(15, 9, 9, 15)

    else:
        # Fallback circle
        d.ellipse(box(5, 5, 19, 19), outline=c, width=w)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def get_icon(name, color_hex, size=18):
    """Return a cached CTkImage for the given icon name, color, and size."""
    key = (name, color_hex, size)
    if key not in _ICON_CACHE:
        pil_img = _draw_icon(name, color_hex, size=size)
        _ICON_CACHE[key] = ctk.CTkImage(
            light_image=pil_img, dark_image=pil_img, size=(size, size)
        )
    return _ICON_CACHE[key]
