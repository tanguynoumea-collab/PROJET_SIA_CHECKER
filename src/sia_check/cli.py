"""sia-check : contrôle par sommation des surfaces SIA 416 Treegram.

Codes de sortie : 0 aucun écart au-delà de la tolérance, 1 écarts, 2 erreur de lecture/config/écriture.
Résultats en console ; avec --out, rapports <projet>_<date>.xlsx / .html / .json.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from . import config as config_mod
from . import reader, report, rules

log = logging.getLogger("sia_check")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="sia-check", description=__doc__.splitlines()[0])
    ap.add_argument("models", nargs="+", type=Path, help="fichiers .tgm ou .ifc Treegram")
    ap.add_argument("--config", type=Path, default=Path("config.yaml"))
    ap.add_argument("--out", type=Path, help="dossier des rapports xlsx, html et json")
    ap.add_argument("--project", help="nom du projet dans les rapports (défaut : nom du premier fichier)")
    ap.add_argument("--all", action="store_true", help="afficher aussi les contrôles OK")
    ap.add_argument("-v", "--verbose", action="store_true", help="afficher chaque surface lue")
    return ap.parse_args(argv)


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
        cfg = config_mod.load(args.config)
        frames = [reader.read(p, cfg) for p in args.models]
    except (OSError, config_mod.ConfigError, reader.ReadError) as ex:
        log.error("%s", ex)
        return 2
    df = pd.concat(frames, ignore_index=True)
    result = rules.run(df, cfg)
    _print(result, args.all)
    if args.out:
        rep = report.build(result, cfg, args.project or args.models[0].stem, args.models)
        try:
            for p in report.write_all(rep, args.out):
                log.info("rapport écrit : %s", p)
        except OSError as ex:  # ex. classeur ouvert dans Excel
            log.error("écriture des rapports impossible : %s", ex)
            return 2
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
