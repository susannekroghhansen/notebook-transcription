#!/usr/bin/env python3
"""Generate a 1024x1024 notebook app icon."""

from PIL import Image, ImageDraw
import math

SIZE = 1024
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# ── Background rounded rect (warm off-white) ──────────────────────────
def rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2*radius, y0 + 2*radius], fill=fill)
    draw.ellipse([x1 - 2*radius, y0, x1, y0 + 2*radius], fill=fill)
    draw.ellipse([x0, y1 - 2*radius, x0 + 2*radius, y1], fill=fill)
    draw.ellipse([x1 - 2*radius, y1 - 2*radius, x1, y1], fill=fill)
    if outline:
        draw.arc([x0, y0, x0 + 2*radius, y0 + 2*radius], 180, 270, fill=outline, width=width)
        draw.arc([x1 - 2*radius, y0, x1, y0 + 2*radius], 270, 360, fill=outline, width=width)
        draw.arc([x0, y1 - 2*radius, x0 + 2*radius, y1], 90, 180, fill=outline, width=width)
        draw.arc([x1 - 2*radius, y1 - 2*radius, x1, y1], 0, 90, fill=outline, width=width)
        draw.line([x0 + radius, y0, x1 - radius, y0], fill=outline, width=width)
        draw.line([x0 + radius, y1, x1 - radius, y1], fill=outline, width=width)
        draw.line([x0, y0 + radius, x0, y1 - radius], fill=outline, width=width)
        draw.line([x1, y0 + radius, x1, y1 - radius], fill=outline, width=width)

# App background (macOS-style rounded square)
bg_color = (245, 245, 240, 255)
rounded_rect(draw, (0, 0, SIZE-1, SIZE-1), 200, bg_color)

# ── Notebook body ─────────────────────────────────────────────────────
NX0, NY0, NX1, NY1 = 200, 130, 824, 894
coral = (220, 80, 70)
shadow = (180, 55, 50)

# Drop shadow
rounded_rect(draw, (NX0+14, NY0+14, NX1+14, NY1+14), 28, (0, 0, 0, 60))

# Back cover (slightly darker)
rounded_rect(draw, (NX0, NY0+12, NX1, NY1+12), 28, shadow)

# Front cover
rounded_rect(draw, (NX0, NY0, NX1, NY1), 28, coral)

# ── Cover shine / highlight ───────────────────────────────────────────
shine_color = (240, 110, 95, 120)
rounded_rect(draw, (NX0+20, NY0+20, NX0+200, NY0+260), 18, shine_color)

# ── Ruled lines on the page (cream area) ─────────────────────────────
PAGE_X0, PAGE_Y0, PAGE_X1, PAGE_Y1 = NX0+80, NY0+60, NX1-40, NY1-40
page_color = (255, 252, 240)
rounded_rect(draw, (PAGE_X0, PAGE_Y0, PAGE_X1, PAGE_Y1), 12, page_color)

# Ruled lines
line_color = (200, 210, 230, 200)
line_start_y = PAGE_Y0 + 90
line_spacing = 58
for i in range(9):
    y = line_start_y + i * line_spacing
    if y < PAGE_Y1 - 30:
        draw.line([(PAGE_X0+30, y), (PAGE_X1-30, y)], fill=line_color, width=4)

# Red margin line
draw.line([(PAGE_X0+90, PAGE_Y0+30), (PAGE_X0+90, PAGE_Y1-30)],
          fill=(220, 150, 150, 180), width=4)

# ── Spiral binding (white circles on left) ───────────────────────────
BIND_X = NX0 + 38
spiral_color = (255, 255, 255)
spiral_shadow = (180, 180, 180)
ring_r = 22
ring_spacing = 72
first_ring_y = NY0 + 100

for i in range(11):
    cy = first_ring_y + i * ring_spacing
    if cy > NY1 - 60:
        break
    # Shadow
    draw.ellipse([BIND_X - ring_r + 4, cy - ring_r + 4,
                  BIND_X + ring_r + 4, cy + ring_r + 4],
                 outline=spiral_shadow, width=6)
    # Ring
    draw.ellipse([BIND_X - ring_r, cy - ring_r,
                  BIND_X + ring_r, cy + ring_r],
                 outline=spiral_color, width=8)
    # Inner fill to look like a real ring
    draw.ellipse([BIND_X - ring_r + 10, cy - ring_r + 10,
                  BIND_X + ring_r - 10, cy + ring_r - 10],
                 fill=spiral_color)

# Vertical spine line behind rings
draw.line([(BIND_X, NY0+40), (BIND_X, NY1-40)],
          fill=(200, 200, 200, 80), width=14)

# ── Pencil ────────────────────────────────────────────────────────────
# Pencil drawn at angle in bottom-right area of the page
px, py = PAGE_X1 - 110, PAGE_Y0 + 80  # tip anchor
angle = -38  # degrees

def rot(cx, cy, x, y, deg):
    r = math.radians(deg)
    dx, dy = x - cx, y - cy
    nx = cx + dx * math.cos(r) - dy * math.sin(r)
    ny = cy + dx * math.sin(r) + dy * math.cos(r)
    return (nx, ny)

pencil_len = 320
body_w = 28

# Pencil body (yellow)
body_pts = [
    rot(px, py, px - body_w//2, py, angle),
    rot(px, py, px + body_w//2, py, angle),
    rot(px, py, px + body_w//2, py + pencil_len, angle),
    rot(px, py, px - body_w//2, py + pencil_len, angle),
]
draw.polygon(body_pts, fill=(255, 210, 60))
draw.line([body_pts[0], body_pts[1]], fill=(200, 160, 40), width=3)
draw.line([body_pts[2], body_pts[3]], fill=(200, 160, 40), width=3)
draw.line([body_pts[0], body_pts[3]], fill=(200, 160, 40), width=2)
draw.line([body_pts[1], body_pts[2]], fill=(200, 160, 40), width=2)

# Eraser (pink)
eraser_h = 38
eraser_pts = [
    rot(px, py, px - body_w//2, py + pencil_len, angle),
    rot(px, py, px + body_w//2, py + pencil_len, angle),
    rot(px, py, px + body_w//2, py + pencil_len + eraser_h, angle),
    rot(px, py, px - body_w//2, py + pencil_len + eraser_h, angle),
]
draw.polygon(eraser_pts, fill=(255, 160, 160))

# Metal ferrule (gray band between eraser and body)
ferrule_pts = [
    rot(px, py, px - body_w//2 - 2, py + pencil_len - 10, angle),
    rot(px, py, px + body_w//2 + 2, py + pencil_len - 10, angle),
    rot(px, py, px + body_w//2 + 2, py + pencil_len + 8, angle),
    rot(px, py, px - body_w//2 - 2, py + pencil_len + 8, angle),
]
draw.polygon(ferrule_pts, fill=(180, 185, 190))

# Tip cone (wood triangle)
tip_h = 44
tip_pts = [
    rot(px, py, px - body_w//2, py, angle),
    rot(px, py, px + body_w//2, py, angle),
    rot(px, py, px, py - tip_h, angle),
]
draw.polygon(tip_pts, fill=(200, 155, 100))

# Graphite tip
graphite_h = 12
graphite_pts = [
    rot(px, py, px - 5, py - tip_h + 4, angle),
    rot(px, py, px + 5, py - tip_h + 4, angle),
    rot(px, py, px, py - tip_h - graphite_h, angle),
]
draw.polygon(graphite_pts, fill=(60, 60, 60))

# ── Save ──────────────────────────────────────────────────────────────
out = "/Users/dkSusKro/Documents/claude-projects/notebook-transcription/notebook-webapp/Notebook App.app/Contents/Resources/AppIcon_1024.png"
img.save(out, "PNG")
print(f"Saved: {out}")
