"""One-time script to convert logo.svg geometry to logo.png using PIL drawing."""
from PIL import Image, ImageDraw
import os

size = 128
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Color matching the mockup's muted style
color = (180, 190, 210)  # light blue-gray for dark theme

# Outer ring (from SVG path: circle at 256,256 radius ~224)
pad = 8
draw.ellipse([pad, pad, size - pad, size - pad], outline=color, width=5)

# Center filled circle (from SVG: cx=256, cy=256, r=102)
cx, cy = size // 2, size // 2
r_inner = 25
draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=color)

# Small dot top-right (from SVG: cx=402.59, cy=116.45, r=46.52)
# Proportionally: (402/512)*128 = ~100, (116/512)*128 = ~29
dx = int((402.59 / 512) * size)
dy = int((116.45 / 512) * size)
r_dot = int((46.52 / 512) * size)
draw.ellipse([dx - r_dot, dy - r_dot, dx + r_dot, dy + r_dot], fill=color)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
img.save(out_path)
print(f"Saved logo.png ({size}x{size}) to {out_path}")
