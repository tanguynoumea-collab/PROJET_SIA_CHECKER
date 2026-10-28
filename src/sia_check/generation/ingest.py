"""Maquette architecte IFC -> modèle du moteur de génération (V4_PLAN §3.1, phase 20).

Seul module du moteur à toucher à l'IFC. Il lit :
- les bâtiments et les niveaux (altitude en mètres, prise dans le placement du niveau, à défaut `Elevation`) ;
- les `IfcSpace` : nom, nom long, type prédéfini, propriétés et quantités (aplaties en « Pset.Propriété »),
  logement (config.yaml > generation.lot), niveau et bâtiment ;
- les éléments utiles au moteur (generation.ingest.classes : murs, dalles, toitures, ouvertures, escaliers…).

La géométrie est triangulée par IfcOpenShell en coordonnées monde, en mètres : un maillage par objet, au format
de `geom.Mesh`. Un objet décomposé sans géométrie propre (mur en couches `IfcBuildingElementPart`, toiture faite
de dalles, escalier de volées, mur-rideau de panneaux) prend celle de ses composants. Les plans (contours 2D,
plans.py) se calculent ensuite sans relire l'IFC.

Un espace est rattaché à son niveau par la structure spatiale (contenu ou agrégé, comme les pièces Revit) ;
à défaut, par son plancher : le niveau le plus haut du bâtiment dont l'altitude ne le dépasse pas.
"""

from __future__ import annotations

import logging
import math
import multiprocessing
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..geom import Mesh

log = logging.getLogger(__name__)

SPACE = "IfcSpace"


class IngestError(RuntimeError):
    pass


@dataclass
class Storey:
    gid: str
    name: str
    building: str
    elevation: float            # m, repère du projet
    height: float | None = None  # m, jusqu'au niveau suivant du même bâtiment
    rank: int = 0                # ordre dans le bâtiment, du plus bas au plus haut


@dataclass
class Item:
    """Espace ou élément de la maquette, avec sa géométrie."""
    gid: str
    ifc_class: str
    name: str | None
    building: str | None
    storey: str | None          # gid du niveau
    storey_by: str = "structure"  # structure | altitude | aucun
    type_name: str | None = None
    long_name: str | None = None
    predefined: str | None = None
    props: dict[str, object] = field(default_factory=dict)   # « Pset.Propriété » -> valeur
    lot: str | None = None
    mesh: Mesh | None = None
    z_min: float | None = None
    z_max: float | None = None

    @property
    def is_space(self) -> bool:
        return self.ifc_class == SPACE


@dataclass
class Model:
    path: str
    schema: str
    project: str | None
    storeys: list[Storey]
    spaces: list[Item]
    elements: list[Item]
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)   # géométries impossibles à trianguler

    def storey(self, gid: str | None) -> Storey | None:
        return next((s for s in self.storeys if s.gid == gid), None)

    @property
    def buildings(self) -> list[str]:
        return list(dict.fromkeys(s.building for s in self.storeys))


def _scalar(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def _props(entity) -> dict[str, object]:
    import ifcopenshell.util.element as ue
    out = {}
    for pset, values in (ue.get_psets(entity) or {}).items():
        for k, v in values.items():
            if k != "id":
                out[f"{pset}.{k}"] = _scalar(v)
    return out


def _lot(props: dict, spec: dict | list | None, storey: str | None = None) -> str | None:
    """Logement d'un espace : première propriété renseignée de la liste (config.yaml > generation.lot). Avec
    `scope: storey`, le numéro ne vaut que dans son étage (La Bâtie : « 2 ») et prend le nom de l'étage en tête ;
    `with` met d'autres propriétés devant (La Bâtie : cage d'escalier, « 26-2 »)."""
    for s in spec if isinstance(spec, list) else [spec] if spec else []:
        v = props.get(f"{s.get('pset')}.{s.get('property')}")
        if v in (None, "", "-"):
            continue
        v = str(v).strip()
        if s.get("pattern"):
            m = re.match(s["pattern"], v)
            if not m:
                continue
            v = m["lot"]
        head = [str(props[k]).strip() for k in s.get("with") or [] if props.get(k) not in (None, "", "-")]
        v = "-".join(head + [v])
        return f"{storey}/{v}" if s.get("scope") == "storey" and storey else v
    return None


VOID_HOSTS = ("IfcWall", "IfcCovering", "IfcCurtainWall")   # éléments de façade dont un percement est une réservation


def _ancestor(el, cls: str):
    import ifcopenshell.util.element as ue
    c = ue.get_container(el) or ue.get_aggregate(el)
    while c is not None and not c.is_a(cls):
        c = ue.get_aggregate(c) or ue.get_container(c)
    return c


def _storeys(f, scale: float) -> tuple[list[Storey], dict[int, str]]:
    import ifcopenshell.util.placement as up
    out, building_of = [], {}
    for st in f.by_type("IfcBuildingStorey"):
        bd = _ancestor(st, "IfcBuilding")
        bname = (bd.Name or bd.GlobalId) if bd is not None else "?"
        z = None
        if st.ObjectPlacement is not None:
            try:
                z = float(up.get_local_placement(st.ObjectPlacement)[2][3]) * scale
            except Exception:  # noqa: BLE001 — placement exotique : on prend l'altitude déclarée
                z = None
        if z is None and st.Elevation is not None:
            z = float(st.Elevation) * scale
        out.append(Storey(st.GlobalId, st.Name or st.GlobalId, bname, z if z is not None else 0.0))
        building_of[st.id()] = bname
    for b in dict.fromkeys(s.building for s in out):
        levels = sorted((s for s in out if s.building == b), key=lambda s: s.elevation)
        for k, s in enumerate(levels):
            s.rank = k
            if k + 1 < len(levels):
                s.height = round(levels[k + 1].elevation - s.elevation, 4)
    return out, building_of


def _item(e, storeys_by_id: dict, lot_spec: dict | list | None) -> Item:
    import ifcopenshell.util.element as ue
    st = _ancestor(e, "IfcBuildingStorey")
    bd = _ancestor(e, "IfcBuilding")
    props = _props(e)
    t = ue.get_type(e)
    return Item(
        gid=e.GlobalId, ifc_class=e.is_a(), name=e.Name,
        building=(bd.Name or bd.GlobalId) if bd is not None else None,
        storey=st.GlobalId if st is not None and st.id() in storeys_by_id else None,
        storey_by="structure" if st is not None else "aucun",
        type_name=t.Name if t is not None else getattr(e, "ObjectType", None),
        long_name=getattr(e, "LongName", None) if e.is_a(SPACE) else None,
        predefined=_scalar(getattr(e, "PredefinedType", None)),
        props=props, lot=_lot(props, lot_spec, st.Name if st is not None else None) if e.is_a(SPACE) else None)


def _tessellate(f, entities: list, threads: int) -> tuple[dict[str, Mesh], list[str]]:
    import ifcopenshell.geom
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    settings.set("weld-vertices", True)
    meshes, errors = {}, []
    if not entities:
        return meshes, errors
    it = ifcopenshell.geom.iterator(settings, f, threads or multiprocessing.cpu_count(), include=entities)
    if not it.initialize():
        return meshes, ["triangulation impossible (aucune géométrie lisible)"]
    while True:
        shape = it.get()
        g = shape.geometry
        verts, faces = list(g.verts), list(g.faces)
        if verts and faces:
            meshes[shape.guid] = Mesh([float(x) for x in verts], [int(i) for i in faces])
        if not it.next():
            break
    return meshes, errors


def _merge(meshes: list[Mesh]) -> Mesh | None:
    if not meshes:
        return None
    v, i = [], []
    for m in meshes:
        base = len(v) // 3
        v += m.vertices
        i += [k + base for k in m.indices]
    return Mesh(v, i)


def _parts(e) -> list:
    """Composants porteurs de géométrie d'un objet décomposé (ouvertures et menuiseries exclues : objets à part)."""
    import ifcopenshell.util.element as ue
    return [c for c in ue.get_decomposition(e)
            if not c.is_a("IfcOpeningElement") and not c.is_a("IfcDoor") and not c.is_a("IfcWindow")
            and not c.is_a(SPACE)]


def _locate(item: Item, storeys: list[Storey]) -> None:
    """Niveau par l'altitude du plancher, pour un objet hors de la structure spatiale."""
    if item.storey is not None or item.z_min is None:
        return
    cands = [s for s in storeys if item.building in (None, s.building) and s.elevation <= item.z_min + 0.05]
    if cands:
        best = max(cands, key=lambda s: s.elevation)
        item.storey, item.storey_by = best.gid, "altitude"
        item.building = item.building or best.building


def load(path: str | Path, cfg_generation: dict | None = None) -> Model:
    import ifcopenshell
    import ifcopenshell.util.unit as uu
    path = Path(path)
    if not path.is_file():
        raise IngestError(f"fichier introuvable : {path}")
    gen = cfg_generation or {}
    ing = gen.get("ingest") or {}
    t0 = time.perf_counter()
    try:
        f = ifcopenshell.open(str(path))
    except Exception as ex:  # noqa: BLE001 — IFC illisible : erreur de lecture
        raise IngestError(f"IFC illisible : {path.name} ({ex})") from ex
    scale = uu.calculate_unit_scale(f)
    storeys, _ = _storeys(f, scale)
    by_id = {st.id(): st for st in f.by_type("IfcBuildingStorey")}

    entities = list(f.by_type(SPACE))
    for cls in ing.get("classes") or []:
        try:
            entities += [e for e in f.by_type(cls) if not e.is_a(SPACE)]
        except RuntimeError:   # classe absente du schéma (ex. IfcRamp en IFC2X3 : présente ; autre cas : ignorée)
            continue
    entities = list({e.id(): e for e in entities}.values())
    items = [_item(e, by_id, gen.get("lot")) for e in entities]
    # Percements sans menuiserie (baie libre, ouverture de parking, CGA L04) dans un mur, un bardage ou un mur-rideau :
    # une réservation de façade comme une fenêtre. Niveau, bâtiment et IsExternal sont ceux de l'élément percé.
    voids = []
    for o in f.by_type("IfcOpeningElement") if ing.get("voids", True) else []:
        host = o.VoidsElements[0].RelatingBuildingElement if o.VoidsElements else None
        if o.HasFillings or host is None or not host.is_a().startswith(VOID_HOSTS):
            continue
        it, h = _item(o, by_id, None), _item(host, by_id, None)
        it.storey, it.storey_by, it.building = h.storey, h.storey_by if h.storey else "aucun", h.building
        external = next((v for k, v in h.props.items() if k.endswith(".IsExternal")), None)
        if isinstance(external, bool):
            it.props["Hôte.IsExternal"] = external
        voids.append(o)
        items.append(it)
    parts = {e.GlobalId: _parts(e) for e in entities if not e.is_a(SPACE)}
    known = {e.id() for e in entities}
    extra = list({c.id(): c for cs in parts.values() for c in cs if c.id() not in known}.values())
    # Sans espace, la génération est bloquée (audit G1) : la triangulation des éléments serait du temps perdu.
    todo = entities + extra + voids if f.by_type(SPACE) else []
    meshes, errors = _tessellate(f, todo, int(ing.get("threads") or 0))
    for it in items:
        it.mesh = meshes.get(it.gid) or _merge([meshes[c.GlobalId] for c in parts.get(it.gid, []) if c.GlobalId in meshes])
        if it.mesh:
            zs = it.mesh.vertices[2::3]
            it.z_min, it.z_max = round(min(zs), 4), round(max(zs), 4)
        _locate(it, storeys)
    missing = {}
    for it in items if todo else []:
        if it.mesh is None:
            missing[it.ifc_class] = missing.get(it.ifc_class, 0) + 1
    errors += [f"{cls} : {n} sans géométrie lisible" for cls, n in sorted(missing.items())]
    project = next((p.LongName or p.Name for p in f.by_type("IfcProject")), None)
    model = Model(str(path), f.schema, project, storeys,
                  [i for i in items if i.is_space], [i for i in items if not i.is_space],
                  round(time.perf_counter() - t0, 1), errors)
    log.info("%s : %s, %d bâtiments, %d niveaux, %d espaces, %d éléments (%.1f s)", path.name, f.schema,
             len(model.buildings), len(storeys), len(model.spaces), len(model.elements), model.seconds)
    for e in errors:
        log.warning("%s : %s", path.name, e)
    return model
