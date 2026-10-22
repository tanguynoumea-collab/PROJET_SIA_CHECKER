"""Logo de SIA Check Viewer : le bilan par niveau (élément signature) et une coche de contrôle.

Trois dalles empilées, chacune remplie aux couleurs SIA (SUP, SUS, SD, SI) avec son résidu en
creux ; une pastille pervenche (accent de l'app) coche le contrôle. Fond graphite de l'app.
Les petites tailles (≤ 32 px) gardent seulement les dalles et la coche, sans segments fins.

    .venv/Scripts/python scripts/make_logo.py

Écrit app/SiaCheck.Viewer/Assets/SiaCheck.ico (16 à 256 px) et SiaCheck.png (512 px), docs/logo.png.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "SiaCheck.Viewer" / "Assets"

GRAPHITE = "#1E2128"
RIM = "#2C3039"
ACCENT = "#8B83FF"
WHITE = "#FFFFFF"
SIA = ["#D5003B", "#F0A900", "#F2E900", "#0C9DDA"]   # SUP, SUS, SD, SI
# Parts de chaque dalle (SUP, SUS, SD, SI) ; le reste est le résidu, laissé en creux.
LEVELS = [(0.50, 0.14, 0.14, 0.08), (0.56, 0.10, 0.13, 0.09), (0.46, 0.18, 0.15, 0.10)]
S = 1024   # dessin à 1024, réduit ensuite (anticrénelage)


def draw(detail: bool) -> Image.Image:
    big = S * 4
    k = big / S
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=220 * k, fill=GRAPHITE, outline=RIM, width=int(12 * k))

    x0, x1, h, gap = 176, 848, 128 if detail else 150, 52 if detail else 46
    y = 236 if detail else 200
    for parts in LEVELS:
        top, bot = y * k, (y + h) * k
        # contour du niveau = la SP ; le résidu reste vide
        d.rounded_rectangle([x0 * k, top, x1 * k, bot], radius=26 * k, outline="#8A90A0", width=int(8 * k))
        x = x0 + 14
        inner = x1 - x0 - 28
        for share, color in zip(parts, SIA):
            w = inner * share
            seg_gap = 10 if detail else 0
            d.rounded_rectangle([x * k, top + 14 * k, (x + w - seg_gap) * k, bot - 14 * k],
                                radius=12 * k, fill=color)
            x += w
        y += h + gap

    # pastille de contrôle (accent pervenche), cerclée de graphite pour se détacher des dalles
    cx, cy, r = (792, 792, 168) if detail else (770, 770, 214)
    d.ellipse([(cx - r - 34) * k, (cy - r - 34) * k, (cx + r + 34) * k, (cy + r + 34) * k], fill=GRAPHITE)
    d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=ACCENT)
    pts = [(cx - r * 0.48, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.36), (cx + r * 0.50, cy - r * 0.34)]
    d.line([(px * k, py * k) for px, py in pts], fill=WHITE, width=int(r * 0.22 * k), joint="curve")
    for px, py in (pts[0], pts[-1]):   # extrémités arrondies
        rr = r * 0.11
        d.ellipse([(px - rr) * k, (py - rr) * k, (px + rr) * k, (py + rr) * k], fill=WHITE)
    return im.resize((S, S), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    full, simple = draw(detail=True), draw(detail=False)
    full.resize((512, 512), Image.LANCZOS).save(ASSETS / "SiaCheck.png")
    full.resize((512, 512), Image.LANCZOS).save(ROOT / "docs" / "logo.png")
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [(simple if s <= 32 else full).resize((s, s), Image.LANCZOS) for s in sizes]
    frames[-1].save(ASSETS / "SiaCheck.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    # planche de contrôle (non versionnée)
    sheet = Image.new("RGBA", (sum(sizes) + 10 * len(sizes) + 532, 532), "#F3F4F6")
    x = 10
    for f in frames:
        sheet.paste(f, (x, 532 - f.height - 10), f)
        x += f.width + 10
    sheet.paste(full.resize((512, 512), Image.LANCZOS), (x, 10), full.resize((512, 512), Image.LANCZOS))
    sheet.save(ROOT / "report" / "logo_sheet.png")
    print("ok", ASSETS)


if __name__ == "__main__":
    main()
