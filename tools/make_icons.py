"""Write the PWA icons (web/icons/*.png) with the stdlib only: a white ball on dark green.

Run from anywhere:  python tools/make_icons.py
"""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
BG = (20, 83, 45)       # #14532d
FG = (255, 255, 255)
PENT = (20, 83, 45)
SS = 3                  # supersampling per axis (anti-aliasing)


def pentagon(r):
    return [(r * math.sin(2 * math.pi * k / 5), -r * math.cos(2 * math.pi * k / 5)) for k in range(5)]


def inside(poly, x, y):
    n, c = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def colour_at(u, v, maskable):
    """u, v in [-0.5, 0.5]; returns RGBA."""
    if not maskable:  # rounded square, transparent corners
        r, e = 0.18, 0.5
        dx, dy = max(abs(u) - (e - r), 0), max(abs(v) - (e - r), 0)
        if dx * dx + dy * dy > r * r:
            return (0, 0, 0, 0)
    ball = 0.27 if maskable else 0.33   # maskable keeps content inside the 40% safe circle
    d = math.hypot(u, v)
    if d > ball:
        return BG + (255,)
    if inside(pentagon(ball * 0.42), u, v):
        return PENT + (255,)
    return FG + (255,)


def render(size, maskable):
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    u = (x + (sx + 0.5) / SS) / size - 0.5
                    v = (y + (sy + 0.5) / SS) / size - 0.5
                    c = colour_at(u, v, maskable)
                    for i in range(3):
                        acc[i] += c[i] * c[3]
                    acc[3] += c[3]
            a = acc[3] / (SS * SS)
            rgb = [round(acc[i] / acc[3]) if acc[3] else 0 for i in range(3)]
            row += bytes(rgb + [round(a)])
        rows.append(bytes(row))
    return b"".join(rows)


def png(size, raw):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, maskable in [("icon-192.png", 192, False), ("icon-512.png", 512, False),
                                 ("icon-maskable-512.png", 512, True)]:
        (OUT / name).write_bytes(png(size, render(size, maskable)))
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
