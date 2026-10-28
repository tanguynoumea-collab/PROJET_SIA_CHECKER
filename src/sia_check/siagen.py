"""Projet de surfaces SIA au modèle Treegram, hors Treegram : fichier `<Nom>.siagen.json` (V4_PLAN §3.2).

Le moteur de génération (V4) écrit ses surfaces dans ce fichier, et `reader.py` le lit comme un `.tgm` : mêmes
éléments, mêmes propriétés, mêmes totaux de niveau. Tout ce qui suit la lecture (règles, corrections, MDP,
exports, visionneuse, benchmark) ne voit pas la différence. `--siagen` écrit le même fichier depuis un `.tgm`
et son cache VWR : c'est la preuve que le contrat suffit (même analyse, surface par surface).

Contrat (version 1) :
{
  "format": "sia-check-siagen", "version": 1,
  "project": nom du projet, "created": date ISO, "generator": {"tool", "version", "source"},
  "origin":  [x, y, z] facultatif : origine locale des maillages dans le repère de la maquette (m)
  "elements": [{
      "name":         nom de l'élément Treegram (ex. « A01_N00_ShellByTgm-1_SpaceByTgm-3_SUP », ou le code seul
                      pour un total de niveau)
      "kind":         "leaf" (surface élémentaire) | "node" (total de niveau)
      "building", "level":  bâtiment et niveau, explicites (un `.tgm` les donne par le nom ou par la position)
      "element_id", "container_id":  identifiants internes, ID TGM = H<container_id>::H<element_id> ; null admis
      "props":        propriétés Treegram telles quelles : « Catégorie SIA », Area, Type, ApartmentByTgm, Bedrooms,
                      Perimeter, GrossHeight, DeltaX, DeltaY, GrossArea, NetArea, ReservationsArea…
                      (noms lus selon config.yaml > sources.tgm, comme pour un `.tgm`)
      "meshes":       [{"v": base64 float32 LE (x, y, z en m, repère du projet moins « origin »),
                        "i": base64 uint32 LE (triangles)}]
  }]
}
L'ordre des éléments est celui du modèle Treegram : par niveau, les totaux puis les surfaces élémentaires.
Les maillages sont en float32, comme dans le cache VWR : la géométrie relue est identique, au bit près.
Un float32 n'a que 24 bits de mantisse : en coordonnées nationales (E ≈ 2 600 000 m), un sommet est arrondi au
quart de mètre (triangles faux, aires fausses, scintillement en 3D). Le moteur V4 écrit donc ses maillages par
rapport à une origine locale (`local_origin`, au mètre près sous la géométrie) ; les relire les laisse dans ce
repère local, celui de la visionneuse, comme le cache VWR de Treegram.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import math
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .geom import Cache, Mesh

FORMAT, VERSION = "sia-check-siagen", 1
SUFFIX = ".siagen.json"
KINDS = ("leaf", "node")


class FormatError(ValueError):
    pass


@dataclass
class Element:
    name: str
    kind: str
    building: str
    level: str
    props: dict[str, object]
    element_id: int | None = None
    container_id: int | None = None
    meshes: list[Mesh] = field(default_factory=list)

    @property
    def tgm_id(self) -> str | None:
        """Identifiant des exports Excel Treegram (colonne « ID TGM »), comme tgm.Bag.tgm_id."""
        if self.element_id is None or self.container_id is None:
            return None
        return f"H{self.container_id}::H{self.element_id}"


def is_siagen(path: Path) -> bool:
    return path.name.lower().endswith(SUFFIX)


def project_name(path: Path) -> str:
    """Nom du projet d'un fichier source : « L OREE » pour « L OREE.siagen.json » comme pour « L OREE.tgm »."""
    return path.name[: -len(SUFFIX)] if is_siagen(path) else path.stem


def _b64(values, code: str) -> str:
    return base64.b64encode(array(code, values).tobytes()).decode("ascii")


def _unb64(text: str, code: str) -> list:
    a = array(code)
    a.frombytes(base64.b64decode(text))
    return a.tolist()


def _value(v):
    return None if isinstance(v, float) and not math.isfinite(v) else v


ORIGIN_STEP_M = 100.0   # origine locale arrondie à 100 m : lisible, et sans effet sur la précision


def local_origin(elements: list[Element]) -> tuple[float, float, float] | None:
    """Origine (x, y, 0) sous la géométrie, arrondie à ORIGIN_STEP_M ; None sans maillage."""
    xs, ys = [], []
    for e in elements:
        for m in e.meshes:
            xs += m.vertices[0::3]
            ys += m.vertices[1::3]
    if not xs:
        return None
    return (math.floor(min(xs) / ORIGIN_STEP_M) * ORIGIN_STEP_M, math.floor(min(ys) / ORIGIN_STEP_M) * ORIGIN_STEP_M, 0.0)


def _shift(vertices, origin) -> list[float]:
    if origin is None:
        return vertices
    ox, oy, oz = origin
    return [v - (ox, oy, oz)[k % 3] for k, v in enumerate(vertices)]


def to_json(elements: list[Element], project: str, source: str | None = None,
            origin: tuple[float, float, float] | None = None) -> dict:
    head = {
        "format": FORMAT, "version": VERSION, "project": project,
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {"tool": "sia-check", "version": __version__, "source": source},
    }
    if origin is not None:
        head["origin"] = list(origin)
    return {**head,
        "elements": [{
            "name": e.name, "kind": e.kind, "building": e.building, "level": e.level,
            "element_id": e.element_id, "container_id": e.container_id,
            "props": {k: _value(v) for k, v in e.props.items()},
            "meshes": [{"v": _b64(_shift(m.vertices, origin), "f"), "i": _b64(m.indices, "I")} for m in e.meshes],
        } for e in elements],
    }


def write(elements: list[Element], path: Path, project: str, source: str | None = None,
          origin: tuple[float, float, float] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(to_json(elements, project, source, origin), ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return path


def _int(v, what: str) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise FormatError(f"{what} : entier attendu, {v!r} lu")
    return v


def load(path: Path) -> tuple[dict, list[Element]]:
    """(en-tête, éléments) ; FormatError si le fichier ne suit pas le contrat."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as ex:
        raise FormatError(f"JSON illisible : {ex}") from ex
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise FormatError(f"format « {FORMAT} » attendu")
    if doc.get("version") != VERSION:
        raise FormatError(f"version {doc.get('version')!r} non prise en charge (attendu {VERSION})")
    elements = []
    for n, e in enumerate(doc.get("elements") or []):
        where = f"élément {n} ({e.get('name') if isinstance(e, dict) else '?'})"
        if not isinstance(e, dict):
            raise FormatError(f"{where} : objet attendu")
        for k in ("name", "building", "level"):
            if not isinstance(e.get(k), str) or not e[k]:
                raise FormatError(f"{where} : « {k} » manquant")
        if e.get("kind") not in KINDS:
            raise FormatError(f"{where} : « kind » vaut {e.get('kind')!r} (attendu leaf ou node)")
        if not isinstance(e.get("props"), dict):
            raise FormatError(f"{where} : « props » manquant")
        meshes = []
        for m in e.get("meshes") or []:
            try:
                v, i = _unb64(m["v"], "f"), _unb64(m["i"], "I")
            except (KeyError, TypeError, ValueError) as ex:
                raise FormatError(f"{where} : maillage illisible ({ex})") from ex
            if len(v) % 3 or len(i) % 3 or (i and max(i) >= len(v) // 3):
                raise FormatError(f"{where} : maillage incohérent")
            meshes.append(Mesh(v, i))
        elements.append(Element(e["name"], e["kind"], e["building"], e["level"], e["props"],
                                _int(e.get("element_id"), f"{where}, element_id"),
                                _int(e.get("container_id"), f"{where}, container_id"), meshes))
    return doc, elements


def cache(path: Path, elements: list[Element] | None = None) -> Cache:
    """Maillages du fichier par element_id, au format du cache VWR (geom.Cache). La géométrie est écrite avec les
    surfaces : elle n'est jamais périmée par rapport à elles."""
    c = Cache()
    try:
        elements = elements if elements is not None else load(path)[1]
    except (OSError, FormatError) as ex:
        c.errors.append(f"{path.name} : {ex}")
        return c
    for e in elements:
        if e.meshes and e.element_id is not None:
            c.meshes.setdefault(e.element_id, []).extend(e.meshes)
    mtime = dt.datetime.fromtimestamp(path.stat().st_mtime)
    c.files, c.newest, c.oldest = 1, mtime, mtime
    return c
