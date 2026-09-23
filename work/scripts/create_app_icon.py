from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "work" / "build_assets"
OUTPUT.mkdir(parents=True, exist_ok=True)
scale = 4
size = 256
canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
draw = ImageDraw.Draw(canvas)
draw.rounded_rectangle((4 * scale, 4 * scale, 252 * scale, 252 * scale), radius=52 * scale,
                       fill=(11, 17, 23, 255), outline=(62, 91, 102, 255), width=4 * scale)

center = size * scale // 2
blade_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
blade_draw = ImageDraw.Draw(blade_layer)
blade_draw.ellipse((center + 3 * scale, center - 20 * scale, center + 94 * scale, center + 20 * scale),
                   fill=(24, 68, 73, 255), outline=(84, 214, 199, 255), width=5 * scale)
blade_draw.ellipse((center + 56 * scale, center - 11 * scale, center + 85 * scale, center + 11 * scale),
                   fill=(35, 132, 124, 255))
for angle in (0, 120, 240):
    rotated = blade_layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(center, center))
    canvas.alpha_composite(rotated)

draw = ImageDraw.Draw(canvas)
draw.ellipse((center - 29 * scale, center - 29 * scale, center + 29 * scale, center + 29 * scale),
             fill=(33, 50, 60, 255), outline=(111, 211, 202, 255), width=5 * scale)
draw.ellipse((center - 17 * scale, center - 17 * scale, center + 17 * scale, center + 17 * scale),
             fill=(215, 230, 234, 255), outline=(20, 168, 151, 255), width=4 * scale)
for index in range(6):
    angle = index * math.pi / 3
    x = center + math.cos(angle) * 10 * scale
    y = center + math.sin(angle) * 10 * scale
    draw.ellipse((x - 2 * scale, y - 2 * scale, x + 2 * scale, y + 2 * scale), fill=(16, 53, 60, 255))
draw.ellipse((center - 4 * scale, center - 4 * scale, center + 4 * scale, center + 4 * scale), fill=(11, 17, 23, 255))

icon = canvas.resize((size, size), Image.Resampling.LANCZOS)
icon.save(OUTPUT / "propcalc.png")
icon.save(OUTPUT / "propcalc.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(OUTPUT / "propcalc.ico")
