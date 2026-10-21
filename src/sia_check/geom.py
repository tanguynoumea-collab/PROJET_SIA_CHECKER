"""Géométrie des surfaces SIA lue dans le cache du viewer Treegram (`VWR/**/_Data/*-SiaSurface*.3drtgm`).

Treegram n'exporte pas d'IFC des surfaces SIA, mais son viewer met en cache leurs maillages,
un jeu de fichiers par niveau (`<Bât>_<Niv>-SiaSurface.3drtgm`, `…SiaSurface1/2…`).
Format observé (rétro-ingénierie L'Orée, juin 2026 — docs/ifc-schema.md §2.4) :

    0   octets[4] + 1 octet       en-tête (magique, ou zéros)
    21  int32 nobjets
    25  int32 nmatériaux
    35  nmatériaux × 20 octets    int32 index + RGBA float32
        nobjets × enregistrement  int32 index, 0xA9, int32 element_id, … (longueur variable)
    puis, pour chaque maillage :
        préfixe (19 octets ; 45/49 pour le premier) dont l'int32 à -15 est l'index d'objet
        int32 nsommets, int32 ntriangles
        nsommets × 3 float32 (X, Y, Z en mètres, coordonnées du projet)
        int32 ngroupes
        ngroupes × ( int32 ntri, 2 octets, ntri × 3 indices )   indices sur 1, 2 ou 4 octets
                                                                 selon nsommets ; Σ ntri = ntriangles

`element_id` est l'identifiant interne de l'élément dans le `.tgm` (tgm.Bag.element_id) :
c'est le lien entre un maillage et sa surface SIA nommée. Un objet peut avoir plusieurs maillages.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

OBJECT_TAG = b"\xa9\x00\x00\x00"
OBJECT_INDEX_OFFSET = 15      # int32 index d'objet, 15 octets avant chaque maillage
MAX_OBJECT_GAP = 64           # écart max. entre deux enregistrements d'objet
MAX_COORD = 1e5               # au-delà, ce ne sont pas des coordonnées en mètres


@dataclass
class Mesh:
    vertices: list[float]     # x0, y0, z0, x1, …
    indices: list[int]        # triangles, 3 indices par triangle


@dataclass
class Cache:
    meshes: dict[int, list[Mesh]] = field(default_factory=dict)   # element_id -> maillages
    files: int = 0
    newest: dt.datetime | None = None
    oldest: dt.datetime | None = None
    errors: list[str] = field(default_factory=list)


def _objects(d: bytes) -> tuple[list[int], int] | None:
    n_obj, n_mat = struct.unpack_from("<ii", d, 21)
    if not (0 <= n_obj <= 1_000_000 and 0 <= n_mat <= 1000):
        return None
    pos, ids = 35 + 20 * n_mat, []
    for k in range(n_obj):
        at = d.find(struct.pack("<i", k) + OBJECT_TAG, pos)
        if at < 0 or at - pos > MAX_OBJECT_GAP:
            return None
        ids.append(struct.unpack_from("<i", d, at + 8)[0])
        pos = at + 12
    return ids, pos


def _mesh(d: bytes, p: int) -> tuple[Mesh, int] | None:
    if p + 8 > len(d):
        return None
    nv, nt = struct.unpack_from("<ii", d, p)
    if not (3 <= nv <= 2_000_000 and 1 <= nt <= 4_000_000):
        return None
    ev = p + 8 + 12 * nv
    if ev + 4 > len(d):
        return None
    v = struct.unpack_from(f"<{3 * nv}f", d, p + 8)
    if any(not math.isfinite(x) or abs(x) > MAX_COORD for x in v):
        return None
    (ng,) = struct.unpack_from("<i", d, ev)
    if not 1 <= ng <= nt:
        return None
    widths = (1, 2, 4) if nv <= 0xFF else (2, 4) if nv <= 0xFFFF else (4,)
    for w in widths:
        fmt = {1: "B", 2: "H", 4: "I"}[w]
        q, total, idx = ev + 4, 0, []
        for _ in range(ng):
            if q + 6 > len(d):
                break
            (k,) = struct.unpack_from("<i", d, q)
            q += 6  # ntri + 2 octets non interprétés
            if k < 1 or total + k > nt or q + 3 * k * w > len(d):
                break
            tri = struct.unpack_from(f"<{3 * k}{fmt}", d, q)
            if max(tri) >= nv:
                break
            idx.extend(tri)
            total += k
            q += 3 * k * w
        else:
            if total == nt:
                return Mesh(list(v), idx), q
    return None


def read_file(path: Path) -> dict[int, list[Mesh]]:
    """Maillages d'un fichier .3drtgm, par element_id. Lève ValueError si la table d'objets est illisible."""
    d = path.read_bytes()
    t = _objects(d)
    if t is None:
        raise ValueError(f"table d'objets illisible : {path.name}")
    ids, p = t
    out: dict[int, list[Mesh]] = {}
    while p < len(d):
        r = _mesh(d, p)
        if r is None:
            p += 1
            continue
        (k,) = struct.unpack_from("<i", d, p - OBJECT_INDEX_OFFSET)
        if 0 <= k < len(ids):
            out.setdefault(ids[k], []).append(r[0])
        p = r[1]
    return out


def find_vwr(project_dir: Path) -> Path | None:
    vwr = project_dir / "VWR"
    return vwr if vwr.is_dir() else None


def read_cache(project_dir: str | Path) -> Cache:
    """Toutes les géométries SIA du cache VWR. Un fichier en double (plusieurs dossiers H…) : le plus récent gagne."""
    cache = Cache()
    vwr = find_vwr(Path(project_dir))
    if vwr is None:
        cache.errors.append(f"pas de dossier VWR dans {project_dir}")
        return cache
    newest_by_name: dict[str, Path] = {}
    for f in vwr.glob("*/_Data/*-SiaSurface*.3drtgm"):
        cur = newest_by_name.get(f.name)
        if cur is None or f.stat().st_mtime > cur.stat().st_mtime:
            newest_by_name[f.name] = f
    for f in sorted(newest_by_name.values()):
        try:
            for eid, meshes in read_file(f).items():
                cache.meshes.setdefault(eid, []).extend(meshes)
        except (OSError, ValueError, struct.error) as ex:
            cache.errors.append(f"{f.name} : {ex}")
            continue
        mtime = dt.datetime.fromtimestamp(f.stat().st_mtime)
        cache.files += 1
        cache.newest = max(cache.newest or mtime, mtime)
        cache.oldest = min(cache.oldest or mtime, mtime)
    log.info("cache VWR : %d fichiers, %d éléments avec géométrie", cache.files, len(cache.meshes))
    for e in cache.errors:
        log.warning("cache VWR : %s", e)
    return cache
