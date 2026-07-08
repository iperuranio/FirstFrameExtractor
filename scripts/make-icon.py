#!/usr/bin/env python3
"""Genera l'icona di First Frame Extractor.

Disegna un master 1024x1024 (squircle scuro coerente col tema dell'app, con una
pellicola il cui PRIMO fotogramma è evidenziato in blu accent + un play) ed
esporta:
  - assets/icon.png    master 1024
  - assets/icon.icns   (macOS, via iconutil)
  - assets/icon.ico    (Windows, multi-size)
"""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
ACCENT = (91, 140, 255)       # #5b8cff
ACCENT_HI = (124, 163, 255)   # #7ca3ff
BG_TOP = (26, 34, 51)         # #1a2233
BG_BOT = (15, 17, 21)         # #0f1115
STRIP = (7, 9, 16)            # quasi nero (pellicola)
HOLE = (54, 62, 80)           # fori di trascinamento
CELL_DARK = (18, 21, 29)      # fotogrammi non evidenziati


def rrect(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def render() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # --- Sfondo squircle con gradiente verticale ---------------------------
    grad = Image.new("RGB", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line(
            [(0, y), (S, y)],
            fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)),
        )
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((84, 84, 940, 940), radius=196, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)

    # --- Pellicola ---------------------------------------------------------
    sx0, sy0, sx1, sy1 = 176, 384, 848, 640
    rrect(d, (sx0, sy0, sx1, sy1), 30, STRIP)

    # Fori di trascinamento (righe alto/basso).
    hole_w, hole_h = 34, 24
    n = 7
    span0, span1 = sx0 + 26, sx1 - 26 - hole_w
    step = (span1 - span0) / (n - 1)
    for i in range(n):
        hx = span0 + step * i
        rrect(d, (hx, sy0 + 20, hx + hole_w, sy0 + 20 + hole_h), 7, HOLE)
        rrect(d, (hx, sy1 - 20 - hole_h, hx + hole_w, sy1 - 20), 7, HOLE)

    # Tre fotogrammi; il primo è evidenziato in accent (con gradiente).
    cy0, cy1 = 452, 572
    xs = [(214, 404), (416, 606), (620, 810)]
    for idx, (cx0, cx1) in enumerate(xs):
        if idx == 0:
            cell = Image.new("RGB", (cx1 - cx0, cy1 - cy0))
            cdr = ImageDraw.Draw(cell)
            for y in range(cy1 - cy0):
                t = y / (cy1 - cy0 - 1)
                cdr.line(
                    [(0, y), (cx1 - cx0, y)],
                    fill=tuple(int(ACCENT_HI[i] + (ACCENT[i] - ACCENT_HI[i]) * t)
                               for i in range(3)),
                )
            cmask = Image.new("L", (cx1 - cx0, cy1 - cy0), 0)
            ImageDraw.Draw(cmask).rounded_rectangle(
                (0, 0, cx1 - cx0 - 1, cy1 - cy0 - 1), radius=12, fill=255)
            img.paste(cell, (cx0, cy0), cmask)
            # Play bianco nel primo fotogramma.
            pcx, pcy, ph = (cx0 + cx1) / 2 + 6, (cy0 + cy1) / 2, 40
            d.polygon([(pcx - 26, pcy - ph), (pcx - 26, pcy + ph), (pcx + 34, pcy)],
                      fill=(255, 255, 255))
        else:
            rrect(d, (cx0, cy0, cx1, cy1), 12, CELL_DARK)

    return img


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    master = render()

    png = assets / "icon.png"
    master.save(png)

    # --- .ico (Windows) ----------------------------------------------------
    master.save(assets / "icon.ico",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                       (128, 128), (256, 256)])

    # --- .icns (macOS) via iconutil ---------------------------------------
    iconset = assets / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    specs = [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]
    for size, name in specs:
        master.resize((size, size), Image.LANCZOS).save(iconset / name)
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(assets / "icon.icns")],
        check=True,
    )
    for p in iconset.iterdir():
        p.unlink()
    iconset.rmdir()

    print("Creati: assets/icon.png, assets/icon.ico, assets/icon.icns")


if __name__ == "__main__":
    main()
