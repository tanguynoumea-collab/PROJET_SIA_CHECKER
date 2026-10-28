"""sia-check : contrôle par sommation des surfaces SIA 416 Treegram.

Codes de sortie : 0 aucun écart au-delà de la tolérance, 1 écarts, 2 erreur de lecture/config/écriture.
Résultats en console ; avec --out, rapports <projet>_<date>.xlsx / .html / .json ;
avec --viewer-json, fichier pour SIA Check Viewer (surfaces, maillages du cache VWR, points liés) ;
avec --preuves, preuves géométriques de la revue IA (sia_check.preuves, shapely requis) ;
avec --treegram, exports au gabarit Excel Treegram (<projet>-SurfacesNettes.xlsx / -SurfacesBrutes.xlsx) ;
avec --mdp, tableau MDP HRS rempli (sia_check.mdp, gabarit vierge livré ou --mdp-template) ;
avec --corrections, journal de corrections appliqué avant les contrôles (sia_check.corrections) : rapports,
exports et visionneuse portent sur les surfaces corrigées ; bilan avant / après en console et, avec --out,
dans <projet>_<date>_corrections.json ;
avec --sujets, points regroupés par cause avec une correction de base proposée (sia_check.sujets) : le fichier
écrit sert aussi de journal (--corrections) une fois les corrections acceptées. Les sujets sont aussi dans
le fichier visionneuse ; avec --revue, les décisions d'une revue IA (fichier verdicts, bloc « sujets »)
réorientent ces sujets et leurs corrections.
avec --surfaces-cache, les surfaces lues (avant corrections) sont gardées pour l'aperçu ; avec --depuis-cache et
--apercu, le journal est réappliqué à ces surfaces sans relire le .tgm ni le cache VWR, et seuls le bilan par
niveau et les ratios sont écrits (aperçu en direct de la visionneuse, quelques secondes).
avec --benchmark, la base des tableaux MDP d'un dossier est lue (sia_check.benchmark) et écrite dans
--benchmark-json (défaut : benchmark.json du dossier --out, sinon du dossier courant), sans projet Treegram ;
avec --benchmark-projet, les totaux et ratios du projet lu (corrections comprises), au format d'un projet du
benchmark : la visionneuse les envoie au dashboard (« Mon projet ») ;
avec --identite, la fiche « Identité du projet » (JSON : description InfosProjet -> valeur) part dans le MDP exporté ;
avec --mdp-identite, elle est écrite dans un MDP existant, sans projet Treegram ;
avec --siagen, les surfaces lues (avant corrections) et leurs maillages sont écrits au contrat `.siagen.json` (V4) :
un projet généré se lit comme un `.tgm`, et ce fichier tiré d'un `.tgm` en est la preuve ;
avec --inventaire, une maquette architecte IFC est lue par le moteur de génération (V4) : niveaux, espaces,
éléments, plans, audit d'entrée (sia_check.generation.audit), écrits dans --inventaire-json ; code de sortie 1
si un point bloque la génération ;
avec --generer, la maquette devient un projet généré <--out>/<projet>/<projet>.siagen.json, au modèle Treegram,
avec son rapport de génération (sia_check.generation.engine) ; le dossier s'ouvre comme un projet Treegram.
Les lignes de journal « ÉTAPE n/N » servent d'indicateur de progression à la visionneuse.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd

from . import config as config_mod
from . import benchmark, corrections, geom, mdp, propositions, reader, report, rules, siagen, sujets, treegram, viewer

log = logging.getLogger("sia_check")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="sia-check", description=__doc__.splitlines()[0])
    ap.add_argument("models", nargs="*", type=Path,
                    help="fichiers .tgm, .siagen.json ou .ifc, ou dossier de projet (sauf avec --depuis-cache)")
    ap.add_argument("--config", type=Path, help="défaut : config.yaml du dossier courant, sinon celle livrée")
    ap.add_argument("--out", type=Path, help="dossier des rapports xlsx, html et json")
    ap.add_argument("--viewer-json", type=Path, help="fichier JSON pour SIA Check Viewer (un seul projet)")
    ap.add_argument("--preuves", type=Path, help="preuves géométriques pour la revue IA (avec --viewer-json)")
    ap.add_argument("--treegram", type=Path, help="dossier des exports au gabarit Excel Treegram (depuis le .tgm)")
    ap.add_argument("--sujets", type=Path, help="sujets et corrections proposées (JSON, utilisable comme journal)")
    ap.add_argument("--revue", type=Path, help="verdicts d'une revue IA dont les décisions réorientent les sujets")
    ap.add_argument("--corrections", type=Path, help="journal de corrections (JSON) à appliquer")
    ap.add_argument("--corrections-xlsx", type=Path,
                    help="Excel de correction (gabarit Treegram + colonnes de correction ; avec --corrections)")
    ap.add_argument("--mdp", type=Path, help="tableau MDP HRS à écrire (fichier .xlsx)")
    ap.add_argument("--mdp-template", type=Path, help="gabarit MDP (défaut : gabarit vierge livré) ; ses tableaux sont remplacés")
    ap.add_argument("--project-id", help="ID projet HRS écrit dans InfosProjet (défaut : celui du gabarit)")
    ap.add_argument("--project-name", help="Nom Projet HRS écrit dans InfosProjet (défaut : nom du dossier)")
    ap.add_argument("--surfaces-cache", type=Path, help="surfaces lues, avant corrections, gardées pour --depuis-cache")
    ap.add_argument("--depuis-cache", type=Path, help="surfaces gardées par --surfaces-cache, au lieu de relire le projet")
    ap.add_argument("--apercu", type=Path, help="bilan par niveau et ratios (JSON), avec --depuis-cache et --corrections")
    ap.add_argument("--benchmark", type=Path, help="dossier des tableaux MDP de la base du benchmark")
    ap.add_argument("--benchmark-json", type=Path, help="fichier du benchmark à écrire (avec --benchmark)")
    ap.add_argument("--identite", type=Path, help="fiche « Identité du projet » (JSON) écrite dans InfosProjet du MDP")
    ap.add_argument("--mdp-identite", type=Path, help="MDP existant dont l'identité est remplacée par --identite")
    ap.add_argument("--benchmark-projet", type=Path, help="totaux et ratios du projet lu, au format du benchmark (JSON)")
    ap.add_argument("--siagen", type=Path, help="projet au contrat .siagen.json à écrire (surfaces lues et maillages)")
    ap.add_argument("--inventaire", type=Path, help="maquette architecte IFC à inventorier (moteur de génération)")
    ap.add_argument("--inventaire-json", type=Path,
                    help="inventaire à écrire (défaut : <maquette>.inventaire.json dans --out, sinon à côté)")
    ap.add_argument("--comparer-mdp", type=Path, help="MDP de référence auquel comparer un projet généré (V4)")
    ap.add_argument("--batiment-mdp", help="bâtiment du MDP à comparer (« Partie d'Ouvrage »)")
    ap.add_argument("--generer", type=Path, help="maquette architecte IFC dont générer les surfaces SIA (V4)")
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
    """Un dossier de projet désigne son unique fichier source : .tgm (Treegram) ou .siagen.json (projet généré)."""
    if not model.is_dir():
        return model
    sources = sorted([*model.glob("*.tgm"), *model.glob(f"*{siagen.SUFFIX}")])
    if len(sources) != 1:
        raise reader.ReadError(f"{model} : {len(sources)} fichiers .tgm ou {siagen.SUFFIX} trouvés, 1 attendu "
                               "(dossier du projet)")
    return sources[0]


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


def _geometry_of(cache: geom.Cache):
    """Géométrie en plan d'une surface (maillage du cache VWR), pour recalculer l'aire des tracés ; None sans shapely."""
    try:
        from .preuves import polygon_of
    except ImportError:
        return None
    memo: dict[int, object] = {}

    def get(row):
        eid = row.get("element_id")
        if eid is None or pd.isna(eid):
            return None
        eid = int(eid)
        if eid not in memo:
            mesh = viewer._mesh(cache.meshes.get(eid))
            memo[eid] = polygon_of(mesh) if mesh else None
        return memo[eid]
    return get


def _print_corrections(applied: corrections.Applied, before: rules.Result, after: rules.Result) -> None:
    lg = applied.log
    counts = " · ".join(f"{k} {v}" for k, v in lg.application.value_counts().items())
    print(f"\nCorrections : {len(lg)} au journal · {counts}")
    for r in lg[lg.application != corrections.SKIPPED].itertuples():
        detail = f"{r.surfaces} surface(s), {r.m2:.2f} m²" if r.application == corrections.APPLIED else r.raison
        print(f"  {r.id:<12} {r.op:<10} {r.sujet or '':<5} {r.application:<18} {detail}")
    b, a = corrections.counts(before), corrections.counts(after)
    print("Verdicts avant → après : " + " · ".join(f"{v} {b[v]} → {a[v]}" for v in rules.VERDICTS))


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s", stream=sys.stderr)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252 par défaut
    if args.apercu or args.depuis_cache:
        return _preview(args)
    if args.benchmark:
        return _benchmark(args)
    if args.mdp_identite:
        return _mdp_identite(args)
    if args.inventaire:
        return _inventaire(args)
    if args.generer:
        return _generer(args)
    if args.comparer_mdp:
        return _comparer_mdp(args)
    if not args.models:
        log.error("fichier .tgm, .ifc ou dossier de projet attendu")
        return 2
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
        journal = corrections.load(args.corrections) if args.corrections else None
        identite = _lire_identite(args.identite)
        review = sujets.load_review(args.revue) if args.revue else None
    except (OSError, config_mod.ConfigError, reader.ReadError, corrections.JournalError) as ex:
        log.error("%s", ex)
        return 2
    df = pd.concat(frames, ignore_index=True)
    if args.surfaces_cache:
        try:
            args.surfaces_cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_pickle(args.surfaces_cache)
        except OSError as ex:   # l'aperçu en direct n'est qu'un confort : l'analyse continue
            log.warning("surfaces non gardées pour l'aperçu : %s", ex)
    log.info("ÉTAPE 2/%d contrôles SIA 416", steps)
    applied = before = cache = None
    if journal is not None:
        try:
            geometry = None
            if any(c.get("polygone") for c in journal["corrections"]) and (
                    models[0].suffix.lower() == ".tgm" or siagen.is_siagen(models[0])):
                cache = geom.for_model(models[0])
                geometry = _geometry_of(cache)
            applied, before, result = corrections.run(df, journal, cfg, geometry)
        except corrections.JournalError as ex:
            log.error("%s", ex)
            return 2
    else:
        result = rules.run(df, cfg)
    if not args.quiet:
        _print(result, args.all)
    if applied is not None:
        _print_corrections(applied, before, result)
    project = args.project or siagen.project_name(models[0])
    try:
        if args.out:
            rep = report.build(result, cfg, project, models)
            for p in report.write_all(rep, args.out):
                log.info("rapport écrit : %s", p)
            if applied is not None:
                p = corrections.write_summary(applied, before, result, args.out / f"{rep.stem}_corrections.json")
                log.info("bilan des corrections écrit : %s", p)
        if args.treegram:
            for p in treegram.write(result, cfg, args.treegram, project):
                log.info("export Treegram écrit : %s", p)
        if args.mdp:
            pid = int(args.project_id) if args.project_id and args.project_id.isdigit() else args.project_id
            infos = applied.infos if applied is not None else None
            log.info("tableau MDP écrit : %s", mdp.write(result, cfg, args.mdp, args.mdp_template, pid,
                                                          args.project_name or project, infos, identite))
        if args.benchmark_projet:
            # Même lecture qu'un MDP de la base : le projet passe par le tableau MDP, puis par benchmark.lire
            with tempfile.TemporaryDirectory() as tmp:
                x = Path(tmp) / "MDP-projet.xlsx"
                mdp.write(result, cfg, x, args.mdp_template, None, args.project_name or project,
                          applied.infos if applied is not None else None, identite)
                p = benchmark.lire(x)
            p.nom = args.project_name or project
            benchmark.ecrire({"version": benchmark.VERSION, "projet": benchmark.projet_json(p)}, args.benchmark_projet)
            log.info("projet pour le benchmark écrit : %s", args.benchmark_projet)
        if args.siagen:
            if len(models) != 1 or models[0].suffix.lower() != ".tgm":
                log.error("--siagen s'écrit depuis un seul projet .tgm")
                return 2
            log.info("projet .siagen écrit : %s", _write_siagen(models[0], cfg, args.siagen, project))
        if args.corrections_xlsx:
            if applied is None:
                log.error("--corrections-xlsx demande un journal (--corrections)")
                return 2
            log.info("Excel de correction écrit : %s", treegram.write_corrections(applied, journal, cfg, args.corrections_xlsx))
        if args.viewer_json or args.sujets:
            log.info("ÉTAPE 3/%d géométrie (cache VWR)", steps)
            if cache is None:
                cache = geom.for_model(models[0])
            modified = geom.source_modified(models[0])
            excluded = applied.surfaces[applied.surfaces.excluded] if applied is not None else None
            doc = viewer.build(result, cfg, cache, project, [str(m) for m in models], modified, before=before,
                               excluded=excluded)
            # Sujets et preuves portent sur le projet tel que livré : une correction appliquée ne fait pas
            # disparaître son sujet, et la revue IA juge Treegram, pas nos corrections.
            raw = viewer.build(before, cfg, cache, project, [str(m) for m in models], modified) if before is not None else doc
            if applied is not None:
                doc["corrections_log"] = json.loads(applied.log.to_json(orient="records", force_ascii=False))
            base = sujets.build(raw, cfg)
            base["subjects"] += propositions.build(before if before is not None else result, cfg)
            sj = sujets.apply_review(base, review, {s["id"] for s in raw["surfaces"]}) if review else base
            doc["subjects"] = sj["subjects"]
            doc["review"] = sj.get("revue")
            if review:
                rv = sj["revue"]
                log.info("revue IA : %d décisions appliquées, %d écartées", rv["decisions"], len(rv["problemes"]))
                for pb in rv["problemes"]:
                    log.warning("revue IA, %s %s : %s", pb["sujet"], pb["id"] or "", pb["raison"])
            if args.viewer_json:
                log.info("fichier visionneuse écrit : %s", viewer.write(doc, args.viewer_json))
            if args.sujets:
                p = sujets.write(sj | sujets.journal(sj, project), args.sujets)
                log.info("sujets écrits : %s (%s)", p, sujets.summary(sj))
        if args.preuves:
            log.info("ÉTAPE 4/%d preuves géométriques", steps)
            try:
                from . import preuves  # shapely : dépendance de la revue IA seulement
            except ImportError as ex:
                log.error("preuves impossibles : %s (pip install shapely)", ex)
                return 2
            ev = preuves.build(raw, base["subjects"])
            log.info("preuves écrites : %s (%s)", preuves.write(ev, args.preuves), preuves.summary(ev))
    except mdp.TemplateError as ex:
        log.error("gabarit MDP : %s", ex)
        return 2
    except OSError as ex:  # ex. classeur ouvert dans Excel
        log.error("écriture impossible : %s", ex)
        return 2
    return result.exit_code


def _write_siagen(model: Path, cfg, out: Path, project: str) -> Path:
    """Surfaces du `.tgm` et maillages de son cache VWR au contrat `.siagen.json` (siagen.py)."""
    if out.is_dir() or not siagen.is_siagen(out):
        out = (out if out.is_dir() or not out.suffix else out.parent) / f"{project}{siagen.SUFFIX}"
    elements = reader.tgm_elements(model, cfg)
    meshes = geom.read_cache(model.parent).meshes
    for e in elements:   # un identifiant porté par deux éléments : ses maillages ne sont écrits qu'une fois
        e.meshes = meshes.pop(e.element_id, []) if e.element_id is not None else []
    return siagen.write(elements, out, project, source=str(model))


def _lire_identite(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        raise reader.ReadError(f"fiche d'identité illisible ({path}) : {ex}") from ex
    if not isinstance(data, dict):
        raise reader.ReadError(f"fiche d'identité invalide ({path}) : objet JSON attendu")
    return data


def _mdp_identite(args: argparse.Namespace) -> int:
    try:
        identite = _lire_identite(args.identite)
        if identite is None:
            raise reader.ReadError("--mdp-identite demande la fiche --identite")
        mdp.ecrire_identite(args.mdp_identite, identite)
    except PermissionError:
        log.error("%s est ouvert dans Excel : fermez-le puis réessayez.", args.mdp_identite.name)
        return 2
    except (OSError, reader.ReadError, mdp.TemplateError, KeyError) as ex:
        log.error("%s", ex)
        return 2
    log.info("identité écrite dans %s", args.mdp_identite)
    return 0


def _inventaire(args: argparse.Namespace) -> int:
    from .generation import audit, ingest, plans
    try:
        cfg = config_mod.load(args.config or _default_config())
        model = ingest.load(args.inventaire, cfg.generation)
    except (OSError, config_mod.ConfigError, ingest.IngestError) as ex:
        log.error("%s", ex)
        return 2
    pl = plans.build(model)
    issues = audit.run(model, pl, cfg.generation)
    inv = audit.inventory(model, pl, issues)
    out = args.inventaire_json or (args.out or args.inventaire.parent) / f"{args.inventaire.stem}.inventaire.json"
    try:
        audit.write(inv, out)
    except OSError as ex:
        log.error("écriture impossible : %s", ex)
        return 2
    if not args.quiet:
        print(audit.summary(inv))
    log.info("inventaire écrit : %s", out)
    return 1 if inv["blocking"] else 0


def _generer(args: argparse.Namespace) -> int:
    from .generation import engine, ingest
    try:
        cfg = config_mod.load(args.config or _default_config())
        g = engine.generate(args.generer, cfg.generation, args.out or args.generer.parent, args.project)
    except engine.GenerationBlocked as ex:
        for i in ex.issues:
            log.error("%s %s", i.code, i.message)
        return 1
    except (OSError, config_mod.ConfigError, ingest.IngestError) as ex:
        log.error("%s", ex)
        return 2
    if not args.quiet:
        print(engine.summary(g.data))
    log.info("projet généré : %s", g.siagen)
    log.info("rapport de génération : %s", g.report)
    return 0


def _comparer_mdp(args: argparse.Namespace) -> int:
    from .generation import compare
    if len(args.models) != 1 or not args.models[0].is_dir():
        log.error("--comparer-mdp attend le dossier d'un projet généré")
        return 2
    try:
        cfg = config_mod.load(args.config or _default_config())
        c = compare.compare(args.models[0], args.comparer_mdp, cfg, args.batiment_mdp)
    except (OSError, ValueError, StopIteration, config_mod.ConfigError, reader.ReadError) as ex:
        log.error("comparaison impossible : %s", ex)
        return 2
    out = args.models[0] / "generation" / "comparaison-mdp.json"
    out.write_text(json.dumps(c, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(compare.summary(c))
    log.info("comparaison écrite : %s", out)
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    if not args.benchmark.is_dir():
        log.error("dossier de la base introuvable : %s", args.benchmark)
        return 2
    projets, erreurs = benchmark.lire_dossier(args.benchmark)
    for e in erreurs:
        log.warning("%s", e)
    out = args.benchmark_json or (args.out or Path(".")) / "benchmark.json"
    try:
        benchmark.ecrire(benchmark.construire(projets, erreurs), out)
    except OSError as ex:
        log.error("%s", ex)
        return 2
    for p in projets:
        manque = ", ".join(c.label for c in p.controles if not c.ok)
        print(f"{p.id:>6}  {p.nom[:28]:28}  {'fiable ' if p.fiable else 'écarté '}  {p.score:4.0%}  {manque}")
    print(f"{sum(p.fiable for p in projets)}/{len(projets)} projets dans les références -> {out}")
    return 0


def _preview(args: argparse.Namespace) -> int:
    """--depuis-cache + --corrections → --apercu : bilan par niveau et ratios après le journal, sans géométrie VWR.

    Les tracés (découpes) gardent l'aire du journal : seul l'Analyser complet la recalcule depuis le cache VWR."""
    if not args.apercu or not (args.depuis_cache or args.models):
        log.error("--apercu demande --depuis-cache, ou le projet à lire (première fois)")
        return 2
    try:
        cfg = config_mod.load(args.config or _default_config())
        if args.depuis_cache:
            df = pd.read_pickle(args.depuis_cache)
        else:   # pas encore de surfaces gardées : lecture du projet, gardée pour les aperçus suivants
            df = pd.concat([reader.read(_resolve(m), cfg) for m in args.models], ignore_index=True)
            if args.surfaces_cache:
                args.surfaces_cache.parent.mkdir(parents=True, exist_ok=True)
                df.to_pickle(args.surfaces_cache)
        journal = corrections.load(args.corrections) if args.corrections else {"corrections": []}
        applied, before, after = corrections.run(df, journal, cfg)
        out = viewer.balance(after, cfg, before=before)
        out["corrections_log"] = json.loads(applied.log.to_json(orient="records", force_ascii=False))
        args.apercu.parent.mkdir(parents=True, exist_ok=True)
        args.apercu.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except (OSError, ValueError, config_mod.ConfigError, reader.ReadError, corrections.JournalError) as ex:
        log.error("aperçu impossible : %s", ex)
        return 2
    log.info("aperçu écrit : %s", args.apercu)
    return after.exit_code


if __name__ == "__main__":
    sys.exit(main())
