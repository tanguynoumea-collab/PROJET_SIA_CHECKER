"""Source unique de la carte d'identité : régénère la partie 3 de docs/CARTE_IDENTITE.md et les données de docs/carte-identite.html.

La liste des champs est dans src/sia_check/carte.py (CHAMPS).

Usage : python docs/carte_identite.py docs/CARTE_IDENTITE.md docs/carte-identite.html
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sia_check.carte import SOURCES, schema  # noqa: E402  la liste vit dans le moteur (carte d'identité de la visionneuse)

rows = [{k: v for k, v in r.items() if k != "cle"} for r in schema()]


def md() -> str:
    out = ["## 3. La carte, par source de données", "",
           "Chaque tableau regroupe les données qui viennent d'une même source : on voit ainsi qui doit les fournir et comment "
           "on les extrait. Colonnes : **Rôle** (contraintes, réponse ou performance, voir partie 1), **Type** et **unité** de "
           "la donnée, **Extraction** (comment on l'obtient), **Mode** (automatique, proposé puis confirmé, saisie, import) et "
           "**Statut** (existe, ajouter, modifier, reléguer hors de la carte, retirer).", "",
           "### Vue d'ensemble", "", "| Source | Qui fournit, comment | Existe | À ajouter ou modifier |", "|---|---|---|---|"]
    for k, (nom, desc) in SOURCES.items():
        sel = [r for r in rows if r["source"] == k]
        ex = sum(r["statut"] == "existe" for r in sel)
        aj = sum(r["statut"] in ("ajouter", "modifier") for r in sel)
        out.append(f"| {nom} | {desc} | {ex} | {aj} |")
    for k, (nom, desc) in SOURCES.items():
        sel = [r for r in rows if r["source"] == k]
        out += ["", f"### {nom}", "", desc, "", "| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |",
                "|---|---|---|---|---|---|---|---|"]
        for r in sel:
            out.append(f"| {r['donnee']} | {r['bloc']} | {r['role']} | {r['type']} | {r['unite'] or '–'} | {r['extraction']} | {r['mode']} | {r['statut']} |")
    return "\n".join(out) + "\n"

if __name__ == "__main__":
    doc = Path(sys.argv[1]); html = Path(sys.argv[2])
    t = doc.read_text(encoding="utf-8")
    a, b = t.index("## 3. La carte"), t.index("## 4. ")
    doc.write_text(t[:a] + md() + "\n" + t[b:], encoding="utf-8")
    data = json.dumps({"sources": {k: {"nom": n, "desc": d} for k, (n, d) in SOURCES.items()}, "rows": rows}, ensure_ascii=False)
    h = html.read_text(encoding="utf-8")
    import re
    h = re.sub(r"^const DATA = .*;$", lambda m: f"const DATA = {data};", h, count=1, flags=re.M)
    html.write_text(h, encoding="utf-8")
    print(len(rows), "lignes")
