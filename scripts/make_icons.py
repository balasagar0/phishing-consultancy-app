"""Draws the app icons (frontend/public/icon-192.png and icon-512.png) with the standard library only: a blue rounded square and a white shield
with three linked dots, the same design as icon.svg.  python scripts/make_icons.py"""
import math, struct, zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public"
BLUE, WHITE = (0x1c, 0x5c, 0xab), (255, 255, 255)


def shield(x, y):
    """Inside the shield outline, in a 64-unit box (see icon.svg)."""
    if y < 10 or y > 55: return False
    top = 10 + 7 * (abs(x - 32) / 18)
    if y < top or x < 14 or x > 50: return False
    if y <= 31: return True
    t = (y - 31) / 24                                   # the lower curve narrows to the point at (32, 55)
    half = 18 * math.sqrt(max(0.0, 1 - t * t))
    return abs(x - 32) <= half


def ring(x, y):
    inner = lambda x, y: shield(32 + (x - 32) * 1.22, 31 + (y - 31) * 1.22) and shield(32 + (x - 32) * 1.12, 31 + (y - 31) * 1.12)
    return shield(x, y) and not inner(x, y)


def pixel(x, y):
    r = 14
    if (x < r and y < r and math.hypot(x - r, y - r) > r) or (x > 64 - r and y < r and math.hypot(x - 64 + r, y - r) > r) or \
       (x < r and y > 64 - r and math.hypot(x - r, y - 64 + r) > r) or (x > 64 - r and y > 64 - r and math.hypot(x - 64 + r, y - 64 + r) > r):
        return None
    pts = ((25, 30), (39, 30), (32, 41))
    for cx, cy in pts:
        if math.hypot(x - cx, y - cy) <= 3.5: return WHITE
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):           # the links between the dots
        t = max(0, min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
        if math.hypot(x - ax - t * (bx - ax), y - ay - t * (by - ay)) <= 1.0: return WHITE
    if ring(x, y): return WHITE
    return BLUE


def png(size, path):
    ss = 4; rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    c = pixel((px + (sx + .5) / ss) * 64 / size, (py + (sy + .5) / ss) * 64 / size)
                    if c: acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]; acc[3] += 255
            n = ss * ss; a = acc[3] / n
            row += bytes([int(acc[0] / max(1, acc[3] / 255)), int(acc[1] / max(1, acc[3] / 255)), int(acc[2] / max(1, acc[3] / 255)), int(a)]) if a else bytes(4)
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


if __name__ == "__main__":
    for s in (192, 512): png(s, OUT / f"icon-{s}.png"); print("wrote", OUT / f"icon-{s}.png")
