"""Draw the pixel-art firefly app icon: assets/icon.png (1024 px), icon.icns (macOS), icon.ico (Windows).

Run: python tools/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# 16×16 sprite, same as the one in the app's header. Legend: w wing, b body, a antenna, l lamp.
SPRITE = [
    "....a......a....",
    ".....a....a.....",
    "......bbbb......",
    "..www.bbbb.www..",
    ".wwwwwbbbbwwwww.",
    ".wwwwwbbbbwwwww.",
    "..www.bbbb.www..",
    "......bbbb......",
    ".....llllll.....",
    ".....llllll.....",
    "....llllllll....",
    "....llllllll....",
    ".....llllll.....",
    ".....llllll.....",
    "......llll......",
    ".......ll.......",
]
COLORS = {"w": (62, 240, 255, 200), "b": (143, 134, 255, 255), "a": (143, 134, 255, 255), "l": (216, 255, 62, 255)}


def draw(size: int = 1024) -> Image.Image:
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # macOS-style tile: 824 px rounded square centred in 1024, dark night sky.
    margin, radius = int(size * 0.0977), int(size * 0.18)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle(
        [margin, margin, size - margin, size - margin], radius, fill=(14, 12, 34, 255), outline=(43, 39, 102, 255),
        width=max(2, size // 128),
    )
    icon.alpha_composite(tile)

    cell = (size - 2 * margin) // 20  # sprite occupies 16 of 20 cells
    origin = (size - 16 * cell) // 2
    sprite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    lamp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd, ld = ImageDraw.Draw(sprite), ImageDraw.Draw(lamp)
    for y, row in enumerate(SPRITE):
        for x, key in enumerate(row):
            if key in COLORS:
                box = [origin + x * cell, origin + y * cell, origin + (x + 1) * cell - 1, origin + (y + 1) * cell - 1]
                sd.rectangle(box, fill=COLORS[key])
                if key == "l":
                    ld.rectangle(box, fill=COLORS[key])
    glow = lamp.filter(ImageFilter.GaussianBlur(size // 22))
    icon.alpha_composite(glow)
    icon.alpha_composite(glow)
    icon.alpha_composite(sprite)
    # Keep the glow inside the tile.
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, size - margin, size - margin], radius, fill=255)
    clipped = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    clipped.paste(icon, (0, 0), mask)
    return clipped


def main():
    ASSETS.mkdir(exist_ok=True)
    icon = draw()
    icon.save(ASSETS / "icon.png")
    icon.save(ASSETS / "icon.icns")
    icon.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.resize((64, 64), Image.LANCZOS).save(ASSETS / "favicon.png")
    print("wrote", ", ".join(p.name for p in sorted(ASSETS.iterdir())))


if __name__ == "__main__":
    main()
