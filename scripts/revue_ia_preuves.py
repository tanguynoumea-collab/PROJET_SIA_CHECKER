"""Revue IA, étape 1 : preuves géométriques à partir d'un fichier visionneuse existant.

    python scripts/revue_ia_preuves.py analyse.json docs/revue-ia/<projet>_<date>.preuves.json

Le calcul vit dans sia_check.preuves (embarqué dans le moteur de la visionneuse) ;
`sia-check … --viewer-json analyse.json --preuves preuves.json` fait les deux en une exécution.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sia_check.preuves import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
