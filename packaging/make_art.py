"""Draw the installer's art from Clawd's 12x8 pixel grid (the same one pet.py draws):
claude-pet.ico (16 to 256 px) and the wizard's corner logo at 1x and 2x. Standard library only.
"""
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).parent
BODY, EYE, BG = (0xD9, 0x77, 0x57), (0, 0, 0), (0x15, 0x14, 0x1A)
CLAWD = (
    "..########..",
    "..#e####e#..",
    "############",
    "############",
    "..########..",
    "..########..",
    "..#.#..#.#..",
    "..#.#..#.#..",
)


def pixels(size, bg=None):
    """RGBA rows of Clawd centered in a size x size square (transparent unless bg is given)."""
    cell = max(1, size * 10 // 12 // 12)
    w, h = 12 * cell, 8 * cell
    x0, y0 = (size - w) // 2, (size - h) // 2
    fill = (*bg, 255) if bg else (0, 0, 0, 0)
    rows = [[fill] * size for _ in range(size)]
    for r, line in enumerate(CLAWD):
        for c, ch in enumerate(line):
            if ch == ".":
                continue
            color = (*(EYE if ch == "e" else BODY), 255)
            for y in range(y0 + r * cell, y0 + (r + 1) * cell):
                for x in range(x0 + c * cell, x0 + (c + 1) * cell):
                    rows[y][x] = color
    return rows


def png(rows):
    raw = b"".join(b"\0" + bytes(v for px in row for v in px) for row in rows)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", len(rows[0]), len(rows), 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    images = [png(pixels(s)) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(head + entries + b"".join(images))


def bmp(path, size):
    """24-bit BMP on the wizard's dark background (Inno Setup wants BMPs)."""
    rows = pixels(size, BG)
    pad = (4 - size * 3 % 4) % 4
    body = b"".join(bytes(v for px in row for v in (px[2], px[1], px[0])) + b"\0" * pad for row in reversed(rows))
    header = struct.pack("<2sIHHI", b"BM", 54 + len(body), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, size, size, 1, 24, 0, len(body), 2835, 2835, 0, 0)
    path.write_bytes(header + info + body)


if __name__ == "__main__":
    ico(HERE / "claude-pet.ico")
    bmp(HERE / "wizard-small-1x.bmp", 58)
    bmp(HERE / "wizard-small-2x.bmp", 116)
    (HERE / "claude-pet.png").write_bytes(png(pixels(256)))
