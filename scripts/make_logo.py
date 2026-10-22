"""Logo de SIA Check Viewer : les niveaux d'un bâtiment en vue isométrique, éclatés comme dans la 3D de l'app.

Des dalles carrées empilées, un angle face à l'observateur (isométrie vraie, 30°), chacune aux couleurs
SIA : SI, SD, SUS, SUP de bas en haut, puis la SP au sommet, découpée en locaux. Les faces latérales
sont des teintes assombries de la même couleur. Fond graphite de l'app.
Les petites tailles (≤ 32 px) gardent trois dalles plus épaisses, sans les locaux.

    .venv/Scripts/python scripts/make_logo.py

Écrit app/SiaCheck.Viewer/Assets/SiaCheck.ico (16 à 256 px) et SiaCheck.png (512 px), docs/logo.png.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "SiaCheck.Viewer" / "Assets"

GRAPHITE = "#1E2128"
RIM = "#2C3039"
SP, SUP, SUS, SD, SI = "#B1005D", "#D5003B", "#F0A900", "#F2E900", "#0C9DDA"
S = 1024   # dessin à 1024, réduit ensuite (anticrénelage)
COS, SIN = math.cos(math.radians(30)), math.sin(math.radians(30))


def _rgb(hex_: str) -> tuple[int, int, int]:
    return tuple(int(hex_[i:i + 2], 16) for i in (1, 3, 5))


def _shade(hex_: str, f: float) -> tuple[int, int, int]:
    return tuple(round(c * f) for c in _rgb(hex_))


def _mix(hex_: str, other: str, t: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * t) for a, b in zip(_rgb(hex_), _rgb(other)))


def draw(detail: bool) -> Image.Image:
    big = S * 4
    k = big / S
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=220 * k, fill=GRAPHITE, outline=RIM, width=int(12 * k))

    layers = [SI, SD, SUS, SUP, SP] if detail else [SUS, SUP, SP]
    t, g = (0.08, 0.15) if detail else (0.16, 0.14)   # épaisseur et vide entre dalles, en côtés de dalle
    span = 2 * COS                                       # largeur à l'écran d'une dalle de côté 1
    height = 1 + len(layers) * t + (len(layers) - 1) * g
    a = min((S - 2 * 150) / span, (S - 2 * 140) / height)
    top_z = (len(layers) - 1) * (t + g) + t
    ox, oy = S / 2, (S - height * a) / 2 + top_z * a     # origine (0, 0, 0) : angle arrière de la dalle du bas

    def p(x: float, y: float, z: float) -> tuple[float, float]:
        """(x, y) sur la dalle de côté 1, z vers le haut (côtés de dalle) → pixels du dessin agrandi."""
        return ((ox + (x - y) * COS * a) * k, (oy + ((x + y) * SIN - z) * a) * k)

    for i, color in enumerate(layers):
        z1 = top_z - (len(layers) - 1 - i) * (t + g)
        z0 = z1 - t
        d.polygon([p(1, 0, z1), p(1, 1, z1), p(1, 1, z0), p(1, 0, z0)], fill=_shade(color, 0.62))   # face droite
        d.polygon([p(0, 1, z1), p(1, 1, z1), p(1, 1, z0), p(0, 1, z0)], fill=_shade(color, 0.80))   # face gauche
        d.polygon([p(0, 0, z1), p(1, 0, z1), p(1, 1, z1), p(0, 1, z1)], fill=_mix(color, "#FFFFFF", 0.10))
        if detail and i == len(layers) - 1:
            # locaux de la SP : cloisons sur la face supérieure, comme les surfaces Treegram d'un étage
            line = _shade(color, 0.55)
            w = int(10 * k)
            for (x0, y0), (x1, y1) in [((0.42, 0), (0.42, 1)), ((0.42, 0.55), (1, 0.55)), ((0, 0.36), (0.42, 0.36)),
                                       ((0.72, 0.55), (0.72, 1)), ((0.42, 0.24), (1, 0.24))]:
                d.line([p(x0, y0, z1), p(x1, y1, z1)], fill=line, width=w)
            # un local mis en évidence (SUP), comme une sélection dans la visionneuse
            d.polygon([p(0.72, 0.55, z1), p(1, 0.55, z1), p(1, 1, z1), p(0.72, 1, z1)], fill=_mix(SUP, "#FFFFFF", 0.05))
            for (x0, y0), (x1, y1) in [((0.72, 0.55), (1, 0.55)), ((0.72, 0.55), (0.72, 1))]:
                d.line([p(x0, y0, z1), p(x1, y1, z1)], fill=line, width=w)
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
    (ROOT / "report").mkdir(exist_ok=True)
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
