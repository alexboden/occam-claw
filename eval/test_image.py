"""Generate a test PNG image using only stdlib (no Pillow).

Creates a 200x200 PNG with a red rectangle and blue circle on white background.
Used by the vision eval case.
"""

import base64
import struct
import zlib


def _make_png(width: int, height: int, pixels: list[list[tuple[int, int, int]]]) -> bytes:
    """Create a minimal RGB PNG from a 2D pixel array."""

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    raw = b""
    for row in pixels:
        raw += b"\x00"  # filter byte
        for r, g, b in row:
            raw += bytes([r, g, b])

    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return header + ihdr + idat + iend


def generate_test_image() -> bytes:
    """Generate a 200x200 test PNG: white background, red rectangle, blue circle."""
    w, h = 200, 200
    white = (255, 255, 255)
    red = (255, 0, 0)
    blue = (0, 0, 255)

    pixels = [[white] * w for _ in range(h)]

    # Red rectangle: top-left (20,20) to bottom-right (100,80)
    for y in range(20, 80):
        for x in range(20, 100):
            pixels[y][x] = red

    # Blue filled circle: center (140,130), radius 40
    cx, cy, radius = 140, 130, 40
    for y in range(h):
        for x in range(w):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                pixels[y][x] = blue

    return _make_png(w, h, pixels)


def generate_test_image_base64() -> str:
    """Return the test image as a base64-encoded string."""
    return base64.b64encode(generate_test_image()).decode()


if __name__ == "__main__":
    import sys
    data = generate_test_image()
    if len(sys.argv) > 1:
        with open(sys.argv[1], "wb") as f:
            f.write(data)
        print(f"Wrote {len(data)} bytes to {sys.argv[1]}")
    else:
        print(f"Generated {len(data)} byte PNG")
