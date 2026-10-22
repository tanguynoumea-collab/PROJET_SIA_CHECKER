"""Retrouve l'affectation réelle des surfaces d'un code donné (ex. SUT) dans les plans PDF de l'architecte.

Usage :
    python scripts/affectations_plans.py report/<projet>.viewer.json "<dossier pdf>" SUT docs/classification/<projet>_SUT.csv

Méthode :
1. Chaque plan est identifié par son nom de fichier : bâtiment (E0900 → E09, GTOUT → G12) et niveau (N00, S01, TOI…).
2. Dans le PDF (texte vectoriel), on lit chaque segment de texte avec sa position. Les aires
   s'écrivent « 82.50 m2 » ; le libellé du local est le segment non numérique le plus proche,
   au-dessus de l'aire (convention de cartouche de local sur les plans d'exécution).
3. Chaque surface du code demandé est appariée à l'aire du plan la plus proche, sur le même
   bâtiment et le même niveau (écart ≤ 1 m² ou 1 %). Sans appariement, la ligne reste vide
   et doit être vérifiée à la main.

Le CSV produit est une PROPOSITION : la colonne `code_sia` est remplie ensuite (à la main ou
par la revue IA), puis validée avant d'être utilisée par sia-check (config `reclassify`).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium

AREA_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*m2$")
PLAN_RE = re.compile(r"-(?P<bld>[A-Z]{1,5}\d{0,4}|GTOUT)-ITB-ARCH-53-PLA-(?P<lvl>[NS]\d\d|TOI)-", re.I)
BUILDING_ALIASES = {"GTOUT": "G12"}   # plan « G tout » = bâtiment G12 sur L'Orée
MAX_ABS, MAX_REL = 1.0, 0.01
MAX_LABEL_DISTANCE = 40.0             # points PDF entre l'aire et son libellé


def plan_key(name: str) -> tuple[str, str] | None:
    m = PLAN_RE.search(name)
    if not m:
        return None
    b = m["bld"].upper()
    b = BUILDING_ALIASES.get(b, b[0] + b[1:3] if len(b) > 3 else b)   # E0900 → E09
    lvl = "Toiture" if m["lvl"].upper() == "TOI" else m["lvl"].upper()
    return b, lvl


def segments(pdf: Path) -> list[tuple[str, float, float]]:
    """(texte, x centre, y centre) de chaque segment de texte de la première page."""
    page = pdfium.PdfDocument(str(pdf))[0]
    tp = page.get_textpage()
    out = []
    for i in range(tp.count_rects()):
        l, b, r, t = tp.get_rect(i)
        text = tp.get_text_bounded(l, b, r, t).strip()
        if text:
            out.append((text, (l + r) / 2, (b + t) / 2))
    return out


def labelled_areas(pdf: Path) -> list[tuple[float, str]]:
    segs = segments(pdf)
    labels = [(s, x, y) for s, x, y in segs if not AREA_RE.match(s) and re.search(r"[A-Za-zÀ-ÿ]{3,}", s)]
    out = []
    for s, x, y in segs:
        m = AREA_RE.match(s)
        if not m:
            continue
        area = float(m[1].replace(",", "."))
        # libellé : segment textuel le plus proche, de préférence au-dessus (y PDF croissant vers le haut)
        cands = [(abs(lx - x) + 2 * max(0.0, y - ly), lab) for lab, lx, ly in labels
                 if abs(lx - x) < MAX_LABEL_DISTANCE * 2 and 0 <= ly - y < MAX_LABEL_DISTANCE]
        out.append((area, min(cands)[1] if cands else ""))
    return out


def main(viewer_json: str, pdf_dir: str, code: str, dst: str) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    doc = json.loads(Path(viewer_json).read_text(encoding="utf-8"))
    targets = [s for s in doc["surfaces"] if s["category"] == code and s["kind"] == "leaf"]
    needed = {(s["building"], s["level"]) for s in targets}
    plans: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for pdf in sorted(Path(pdf_dir).glob("*.pdf")):
        if (k := plan_key(pdf.name)) in needed:
            plans.setdefault(k, []).extend(labelled_areas(pdf))
            print(f"plan {k[0]}·{k[1]} : {pdf.name}")

    rows = []
    for s in sorted(targets, key=lambda s: (s["building"], s["level"], -s["area"])):
        cands = plans.get((s["building"], s["level"]), [])
        best = min(cands, key=lambda c: abs(c[0] - s["area"]), default=None)
        ok = best is not None and abs(best[0] - s["area"]) <= max(MAX_ABS, MAX_REL * s["area"])
        rows.append({
            "id": s["id"], "batiment": s["building"], "niveau": s["level"], "aire_treegram": round(s["area"], 2),
            "type_treegram": s["room_type"] or "",
            "aire_plan": best[0] if ok else "", "libelle_plan": best[1] if ok else "",
            "code_sia": "", "justification": "",
        })
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    matched = sum(1 for r in rows if r["aire_plan"] != "")
    print(f"{len(rows)} surfaces {code}, {matched} appariées à un local du plan -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
