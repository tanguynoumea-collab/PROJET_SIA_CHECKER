# sia-check

Contrôle par sommation des surfaces SIA 416 (2003) produites par Treegram, niveau par niveau, puis par bâtiment et au total.

## Installation

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Utilisation

```bash
sia-check model.ifc --config config.yaml --out report/
sia-check "L OREE.tgm" --config config.yaml --out report/ --project "L'Orée"
sia-check model.ifc --all --verbose          # console seule, contrôles OK compris, chaque surface lue
```

- Sources acceptées : projet Treegram `.tgm` (surfaces SIA lues dans le fichier projet) ou `.ifc` (mapping dans `config.yaml > sources.ifc`).
- Codes de sortie : `0` aucun écart au-delà de la tolérance, `1` écarts (verdict ALERTE ou ERREUR), `2` erreur de lecture, de configuration ou d'écriture des rapports.

## Rapports (`--out`)

`<projet>_<date>.xlsx`, `.html` et `.json` :

- **xlsx** : onglets *Résidus* (contrôles hors OK, écart décroissant), *Surfaces* (toutes les surfaces lues), *Codes inconnus*, *Synthèse* (par catégorie, puis aire par bâtiment), *Contrôles* (tous les contrôles, OK compris).
- **html** : même contenu, lisible sans Excel, avec un tableau par niveau aux couleurs de la légende SIA 416 (surfaces externes hachurées).
- **json** : pour n8n : `exit_code`, `counts` par verdict, `residuals` (hors OK), `unknown_codes`.

## Règles

| Règle | Contrôle | Référence |
| --- | --- | --- |
| R1 | SP = SN + SC, SN = SU + SD + SI ; résidu ≤ 20 % sans SC = « SC implicite » (INFO) | SIA 416 §2, §2.1, §2.2 |
| R2 | SU = SUP + SUS (si SU est fournie) | §2.1.1 |
| R3 | SEP = SEN + SEC, SEN = SEU + SED + SEI | §3, §3.1 |
| R4 | sous-catégories supérieures au parent, ou sans parent au même niveau | |
| R5 | niveau avec SP sans surface utile (sauf niveaux techniques) | §2.1.1 |
| A1 | SEP au niveau du terrain : candidate surface des abords SA | §3, renvoi §1.2 |
| A2 | SEP sur un niveau sans SP ou au-dessus du dernier niveau avec SP : candidate toiture non accessible | §3 |
| A3 | code absent de la config : listé, exclu des sommes | |
| U1–U4 | chaîne USPI par lot : SH ≥ SNH, SBH ≥ SH, SVB ≥ SVN, SVB − SVN = SBH − SH (MEM) | USPI 2014 p. 4 |

Tolérance : un écart est signalé si **à la fois** 0,5 m² et 0,5 % sont dépassés (`config.yaml > tolerance`).

## Structure

```
src/sia_check/
  config.py   chargement de config.yaml
  tgm.py      décodeur du format binaire Treegram (non documenté, voir docs/ifc-schema.md §2.2)
  reader.py   .tgm / .ifc -> DataFrame normalisé (seul module à lire les fichiers)
  rules.py    règles, fonctions pures sur le DataFrame
  cli.py      ligne de commande
tests/        jeu synthétique (tests/data/synth.csv) + intégration L'Orée (ignorée si le projet est absent)
docs/         ifc-schema.md (phase 0), normes de référence
```

```bash
.venv/Scripts/python -m pytest
```
