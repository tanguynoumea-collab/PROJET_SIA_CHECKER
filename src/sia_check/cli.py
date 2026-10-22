"""sia-check : contrôle par sommation des surfaces SIA 416 Treegram.

Codes de sortie : 0 aucun écart au-delà de la tolérance, 1 écarts, 2 erreur de lecture/config/écriture.
Résultats en console ; avec --out, rapports <projet>_<date>.xlsx / .html / .json ;
avec --viewer-json, fichier pour SIA Check Viewer (surfaces, maillages du cache VWR, points liés) ;
avec --preuves, preuves géométriques de la revue IA (sia_check.preuves, shapely requis) ;
avec --treegram, exports au gabarit Excel Treegram (<projet>-SurfacesNettes.xlsx / -SurfacesBrutes.xlsx).
Les lignes de journal « ÉTAPE n/N » servent d'indicateur de progression à la visionneuse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import pandas as pd

from . import config as config_mod
from . import geom, reader, report, rules, treegram, viewer

log = logging.getLogger("sia_check")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="sia-check", description=__doc__.splitlines()[0])
    ap.add_argument("models", nargs="+", type=Path,
                    help="fichiers .tgm ou .ifc Treegram, ou dossier de projet Treegram")
    ap.add_argument("--config", type=Path, help="défaut : config.yaml du dossier courant, sinon celle livrée")
    ap.add_argument("--out", type=Path, help="dossier des rapports xlsx, html et json")
    ap.add_argument("--viewer-json", type=Path, help="fichier JSON pour SIA Check Viewer (un seul projet)")
    ap.add_argument("--preuves", type=Path, help="preuves géométriques pour la revue IA (avec --viewer-json)")
    ap.add_argument("--treegram", type=Path, help="dossier des exports au gabarit Excel Treegram (depuis le .tgm)")
    ap.add_argument("--project", help="nom du projet dans les rapports (défaut : nom du premier fichier)")
    ap.add_argument("--all", action="store_true", help="afficher aussi les contrôles OK")
    ap.add_argument("-q", "--quiet", action="store_true", help="ne pas afficher les résidus en console")
    ap.add_argument("-v", "--verbose", action="store_true", help="afficher chaque surface lue")
    return ap.parse_args(argv)


def _default_config() -> Path:
    """config.yaml du dossier courant, sinon celle livrée avec l'exécutable ou le dépôt."""
    candidates = [Path("config.yaml"), Path(sys.executable).parent / "config.yaml",
                  Path(getattr(sys, "_MEIPASS", "")) / "config.yaml",
                  Path(__file__).resolve().parents[2] / "config.yaml"]
    return next((c for c in candidates if c.is_file()), candidates[0])


def _resolve(model: Path) -> Path:
    """Un dossier de projet Treegram désigne son unique fichier .tgm."""
    if not model.is_dir():
        return model
    tgms = sorted(model.glob("*.tgm"))
    if len(tgms) != 1:
        raise reader.ReadError(f"{model} : {len(tgms)} fichiers .tgm trouvés, 1 attendu (dossier du projet Treegram)")
    return tgms[0]


def _print(result: rules.Result, show_all: bool) -> None:
    res = result.residuals if show_all else result.residuals[result.residuals.verdict != "OK"]
    # Plus grave d'abord, puis écart décroissant.
    res = res.assign(_sev=res.verdict.map(rules.VERDICTS.index), _abs=res.diff_m2.abs())
    res = res.sort_values(["_sev", "_abs"], ascending=False)
    with pd.option_context("display.width", 200, "display.max_rows", None, "display.max_colwidth", 70,
                           "display.float_format", "{:.2f}".format):
        cols = ["verdict", "rule", "building", "level", "lot", "category", "expected", "obtained", "diff_m2", "diff_pct", "message"]
        print(res[cols].to_string(index=False) if len(res) else "Aucun résidu.")
    counts = result.residuals.verdict.value_counts().reindex(rules.VERDICTS, fill_value=0)
    print("\n" + " · ".join(f"{v} {n}" for v, n in counts.items()))


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s", stream=sys.stderr)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252 par défaut
    try:
        cfg = config_mod.load(args.config or _default_config())
        models = [_resolve(m) for m in args.models]
        if args.viewer_json and len(models) != 1:
            raise reader.ReadError("--viewer-json attend un seul projet")
        if args.preuves and not args.viewer_json:
            raise reader.ReadError("--preuves s'utilise avec --viewer-json")
        steps = 4 if args.preuves else 3
        log.info("ÉTAPE 1/%d lecture des surfaces", steps)
        frames = [reader.read(p, cfg) for p in models]
    except (OSError, config_mod.ConfigError, reader.ReadError) as ex:
        log.error("%s", ex)
        return 2
    df = pd.concat(frames, ignore_index=True)
    log.info("ÉTAPE 2/%d contrôles SIA 416", steps)
    result = rules.run(df, cfg)
    if not args.quiet:
        _print(result, args.all)
    project = args.project or models[0].stem
    try:
        if args.out:
            rep = report.build(result, cfg, project, models)
            for p in report.write_all(rep, args.out):
                log.info("rapport écrit : %s", p)
        if args.treegram:
            for p in treegram.write(result, cfg, args.treegram, project):
                log.info("export Treegram écrit : %s", p)
        if args.viewer_json:
            log.info("ÉTAPE 3/%d géométrie (cache VWR)", steps)
            cache = geom.read_cache(models[0].parent) if models[0].suffix.lower() == ".tgm" else geom.Cache()
            modified = dt.datetime.fromtimestamp(models[0].stat().st_mtime)
            doc = viewer.build(result, cfg, cache, project, [str(m) for m in models], modified)
            log.info("fichier visionneuse écrit : %s", viewer.write(doc, args.viewer_json))
        if args.preuves:
            log.info("ÉTAPE 4/%d preuves géométriques", steps)
            try:
                from . import preuves  # shapely : dépendance de la revue IA seulement
            except ImportError as ex:
                log.error("preuves impossibles : %s (pip install shapely)", ex)
                return 2
            ev = preuves.build(doc)
            log.info("preuves écrites : %s (%s)", preuves.write(ev, args.preuves), preuves.summary(ev))
    except OSError as ex:  # ex. classeur ouvert dans Excel
        log.error("écriture impossible : %s", ex)
        return 2
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
