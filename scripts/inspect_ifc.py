"""Phase 0 — inventaire du schéma d'un IFC de surfaces Treegram.

Usage : python scripts/inspect_ifc.py model.ifc [--sample 5] [--geom 20] > inventaire.md

Répond aux questions du brief §4 / §11 sans rien présupposer :
classes porteuses, où est la catégorie, où est l'aire, niveau, bâtiment,
trace d'un GlobalId source, cohérence aire déclarée / aire géométrique.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict

import ifcopenshell
import ifcopenshell.util.element as uel

# Codes connus du brief §3 : sert uniquement à repérer *où* ils apparaissent.
KNOWN_CODES = {
    "SP", "SN", "SU", "SUP", "SUS", "SD", "SI", "SC", "SCP", "SCN",
    "SEP", "SEN", "SEU", "SED", "SEI", "SEC", "SECP", "SECN",
    "ST", "SB", "SA", "SAA", "SAN",
    "SNH", "SHA", "SH", "SBH", "SVN", "SVB", "SCI", "MEM", "SE",
    "SFN", "SRV", "SPT", "SUT",
}
CODE_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(sorted(KNOWN_CODES, key=len, reverse=True)) + r")(?![A-Za-z])")
GUID_RE = re.compile(r"^[0-9A-Za-z_$]{22}$")

# Classes candidates pour porter une surface.
CANDIDATES = ("IfcSpace", "IfcBuildingElementProxy", "IfcZone", "IfcGroup", "IfcSlab", "IfcCovering", "IfcAnnotation")


def h(title: str, level: int = 2) -> None:
    print(f"\n{'#' * level} {title}\n")


def codes_in(value) -> set[str]:
    return set(CODE_RE.findall(value)) if isinstance(value, str) else set()


def parent_of(el):
    """Containment (IfcRelContainedInSpatialStructure) sinon agrégation (IfcRelAggregates, cas des IfcSpace)."""
    return uel.get_container(el) or uel.get_aggregate(el)


def ancestor(el, cls: str):
    c = parent_of(el)
    while c is not None and not c.is_a(cls):
        c = uel.get_aggregate(c)
    return c


def storey_of(el):
    return ancestor(el, "IfcBuildingStorey")


def building_of(el):
    return ancestor(el, "IfcBuilding")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc")
    ap.add_argument("--sample", type=int, default=5, help="entités détaillées par classe")
    ap.add_argument("--geom", type=int, default=20, help="échantillon pour le contrôle géométrique (0 = off)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows : console cp1252 par défaut

    f = ifcopenshell.open(args.ifc)
    h(f"Inventaire de `{args.ifc}`", 1)
    print(f"- Schéma : **{f.schema}**")
    app = f.by_type("IfcApplication")
    print(f"- Application : {[(a.ApplicationFullName, a.Version) for a in app]}")
    print(f"- Header : {f.header.file_name.originating_system!r} / {f.header.file_name.preprocessor_version!r}")

    h("Classes présentes (top 40)")
    cnt = Counter(e.is_a() for e in f)
    for k, v in cnt.most_common(40):
        print(f"- {k}: {v}")

    h("Spatial : sites, bâtiments, niveaux")
    for b in f.by_type("IfcBuilding"):
        print(f"- IfcBuilding `{b.Name}` ({b.GlobalId}) LongName={b.LongName!r}")
    for s in sorted(f.by_type("IfcBuildingStorey"), key=lambda s: s.Elevation or 0):
        n = sum(len(r.RelatedElements) for r in s.ContainsElements)
        n += sum(len(r.RelatedObjects) for r in s.IsDecomposedBy)
        print(f"- IfcBuildingStorey `{s.Name}` elev={s.Elevation} enfants={n}")

    h("Où apparaissent les codes de catégorie ?")
    where = Counter()
    by_code = defaultdict(Counter)
    for cls in CANDIDATES:
        for e in f.by_type(cls, include_subtypes=False) if cls in cnt else []:
            for attr in ("Name", "LongName", "ObjectType", "Description"):
                for c in codes_in(getattr(e, attr, None)):
                    where[f"{cls}.{attr}"] += 1
                    by_code[f"{cls}.{attr}"][c] += 1
            for pset, props in uel.get_psets(e).items():
                for p, v in props.items():
                    for c in codes_in(v):
                        where[f"{cls} · {pset}.{p}"] += 1
                        by_code[f"{cls} · {pset}.{p}"][c] += 1
    for k, v in where.most_common(30):
        print(f"- `{k}` : {v} occurrences → {dict(by_code[k].most_common(12))}")
    if not where:
        print("_Aucun code trouvé dans les attributs/psets des classes candidates._")

    h("Classifications et groupes")
    for r in f.by_type("IfcRelAssociatesClassification")[:20]:
        ref = r.RelatingClassification
        print(f"- {ref.is_a()} {getattr(ref, 'Identification', None) or getattr(ref, 'ItemReference', None)!r} "
              f"Name={ref.Name!r} → {len(r.RelatedObjects)} objets")
    for g in (list(f.by_type("IfcZone")) + [x for x in f.by_type("IfcGroup") if x.is_a() == "IfcGroup"])[:40]:
        n = sum(len(r.RelatedObjects) for r in g.IsGroupedBy)
        print(f"- {g.is_a()} `{g.Name}` LongName={getattr(g, 'LongName', None)!r} ObjectType={g.ObjectType!r} → {n} membres")

    h("Échantillon détaillé par classe candidate")
    for cls in CANDIDATES:
        if cls not in cnt:
            continue
        ents = f.by_type(cls, include_subtypes=False)
        h(f"{cls} ({len(ents)})", 3)
        for e in ents[: args.sample]:
            st, bd = storey_of(e), building_of(e)
            print(f"**#{e.id()} {e.GlobalId}** Name={e.Name!r} LongName={getattr(e, 'LongName', None)!r} "
                  f"ObjectType={getattr(e, 'ObjectType', None)!r}")
            print(f"- niveau (containment) : {st.Name if st else None} · bâtiment : {bd.Name if bd else None}")
            print(f"- type : {uel.get_type(e).Name if uel.get_type(e) else None}")
            print(f"- groupes : {[r.RelatingGroup.Name for r in getattr(e, 'HasAssignments', []) if r.is_a('IfcRelAssignsToGroup')]}")
            for pset, props in uel.get_psets(e).items():
                props = {k: v for k, v in props.items() if k != "id"}
                print(f"- `{pset}` : {props}")
            print()

    h("Traces d'un GlobalId source (valeurs au format GUID IFC dans les psets)")
    hits = Counter()
    for cls in CANDIDATES:
        for e in f.by_type(cls, include_subtypes=False) if cls in cnt else []:
            for pset, props in uel.get_psets(e).items():
                for p, v in props.items():
                    if p != "id" and isinstance(v, str) and GUID_RE.match(v) and v != e.GlobalId:
                        hits[f"{cls} · {pset}.{p}"] += 1
    for k, v in hits.most_common():
        print(f"- `{k}` : {v}")
    if not hits:
        print("_Aucune propriété ne ressemble à un GlobalId tiers._")

    if args.geom:
        h("Aire déclarée vs aire géométrique (projection horizontale)")
        geom_check(f, cnt, args.geom)
    return 0


def geom_check(f, cnt, n: int) -> None:
    """Compare les IfcQuantityArea à l'aire de la projection XY du maillage (SIA 416 §0.4 : projection verticale)."""
    import ifcopenshell.geom
    import numpy as np

    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    unit = ifcopenshell.util.unit.calculate_unit_scale(f)
    print("| entité | quantités déclarées | aire XY géom. (faces vers le haut) |\n|---|---|---|")
    done = 0
    for cls in CANDIDATES:
        for e in f.by_type(cls, include_subtypes=False) if cls in cnt else []:
            if done >= n or not getattr(e, "Representation", None):
                continue
            qs = {f"{p}.{k}": v for p, props in uel.get_psets(e, qtos_only=True).items()
                  for k, v in props.items() if "Area" in k}
            try:
                shp = ifcopenshell.geom.create_shape(settings, e)
            except Exception as ex:  # noqa: BLE001 — diagnostic only
                print(f"| #{e.id()} {e.Name} | {qs} | erreur géom : {ex} |")
                continue
            v = np.array(shp.geometry.verts).reshape(-1, 3)
            t = np.array(shp.geometry.faces).reshape(-1, 3)
            a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
            nz = np.cross(b - a, c - a)[:, 2] / 2  # aire projetée signée
            print(f"| #{e.id()} {e.Name} | {qs} | {nz[nz > 0].sum():.2f} m² |")
            done += 1
    print(f"\n_Facteur d'unité de longueur : {unit}_")


if __name__ == "__main__":
    import ifcopenshell.util.unit  # noqa: F401
    sys.exit(main())
