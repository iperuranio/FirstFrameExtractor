#!/usr/bin/env python3
"""Genera lo sfondo del DMG di First Frame Extractor.

Produce tre file in scripts/:
  - dmg-background.png       (1x, WxH)
  - dmg-background@2x.png    (2x, Retina)
  - dmg-background.tiff      TIFF multi-risoluzione (1x+2x) via tiffutil

Il TIFF combinato è ciò che build-dmg.sh passa a create-dmg: Finder sceglie la
rappresentazione giusta e lo sfondo resta nitido anche sui display Retina.

Il layout è pensato per NON sovrapporsi alle etichette che Finder disegna sotto
le icone (app, Applications, "Open if blocked.txt"). Le coordinate delle icone
sono definite in build-dmg.sh e devono restare coerenti con quelle qui sotto.
"""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- Geometria (in punti, 1x) ----------------------------------------------
W, H = 620, 480

HN = "/System/Library/Fonts/HelveticaNeue.ttc"  # 0=Regular 1=Bold 10=Medium


def font(index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(HN, size, index=index)


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def render(scale: int) -> Image.Image:
    s = scale
    img = Image.new("RGB", (W * s, H * s), "#0f1115")
    d = ImageDraw.Draw(img)

    # Sfondo: gradiente verticale scuro coerente col tema dell'app.
    top = (0x0F, 0x11, 0x15)
    bot = (0x16, 0x19, 0x22)
    for y in range(H * s):
        t = y / (H * s - 1)
        d.line(
            [(0, y), (W * s, y)],
            fill=(lerp(top[0], bot[0], t), lerp(top[1], bot[1], t),
                  lerp(top[2], bot[2], t)),
        )

    def text(cx, cy, string, f, fill):
        d.text((cx * s, cy * s), string, font=f, fill=fill, anchor="mm")

    # Title + subtitle (top area, clear of the icon labels).
    text(W / 2, 46, "First Frame Extractor", font(1, 27 * s), "#ffffff")
    text(W / 2, 86, "Drag the app to the Applications folder",
         font(0, 14 * s), "#9aa0aa")

    # Freccia app → Applications, all'altezza del centro delle icone (y=195),
    # nello spazio vuoto fra le due (le icone sono a x=165 e x=455).
    ay = 195 * s
    x0, x1 = 252 * s, 368 * s
    th = max(2, 5 * s)
    d.line([(x0, ay), (x1, ay)], fill="#5b8cff", width=th)
    hh = 15 * s  # semi-altezza punta
    d.polygon([(x1, ay - hh), (x1 + 22 * s, ay), (x1, ay + hh)], fill="#5b8cff")

    # Hint pointing to the instructions file, above its icon (y=392).
    text(W / 2, 322, 'macOS blocking the app?  Open  "Open if blocked.txt"  below',
         font(10, 13 * s), "#c4c9d4")

    return img


def main() -> None:
    out = Path(__file__).resolve().parent
    p1 = out / "dmg-background.png"
    p2 = out / "dmg-background@2x.png"
    tiff = out / "dmg-background.tiff"

    render(1).save(p1)
    render(2).save(p2)
    subprocess.run(
        ["tiffutil", "-cathidpicheck", str(p1), str(p2), "-out", str(tiff)],
        check=True,
    )
    print(f"Creati: {p1.name}, {p2.name}, {tiff.name}")


if __name__ == "__main__":
    main()
