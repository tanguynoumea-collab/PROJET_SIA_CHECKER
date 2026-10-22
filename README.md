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

- **xlsx** : onglets *Résidus* (contrôles hors OK, écart décroissant), *Surfaces* (toutes les surfaces lues), *Codes inconnus*, *Synthèse* (par catégorie, puis aire par bâtiment), *Contrôles* (tous les contrôles, OK compris), *Ratios*.
- **html** : même contenu, lisible sans Excel, avec un tableau par niveau aux couleurs de la légende SIA 416 (surfaces externes hachurées).
- **json** : pour n8n : `exit_code`, `counts` par verdict, `residuals` (hors OK), `unknown_codes`, `ratios`.

## Ratios informatifs

Ratios classiques du développement immobilier, calculés pour le projet et pour chaque bâtiment (`src/sia_check/ratios.py`, définitions et repères dans `config.yaml > ratios`) :

- **SIA 416** : SN/SP, SC/SP, SU/SP, SUP/SP, SUP/SU, SD/SP, SI/SP, SEP/SP ;
- **USPI 2014** : SNH/SP, SH/SNH, SBH/SH, SVN/SP, SVB/SP (hors sous-sol), SNH par lot.

Chaque code prend sa valeur niveau par niveau (le détail fait foi, règles personnalisées comprises), puis les niveaux sont sommés. Les codes USPI ne somment que les lots. SC absente vaut SP − SN.

Les repères sont **indicatifs, pas normatifs** : un ratio hors repère n'est pas une erreur du contrôle et ne change pas le code de sortie. C'est une question, que la revue IA doit relier à un sujet ou déclarer inexpliquée.

## SIA Check Viewer (application WPF)

Visionneuse 3D des surfaces SIA d'un projet Treegram, avec la liste des points d'attention à côté de la 3D. Le design est décrit dans `docs/DESIGN_PLAN.md`.

```bash
powershell -ExecutionPolicy Bypass -File app/build.ps1
```

La commande produit :

- `app/dist/SiaCheckViewer-<version>-setup.exe`, l'installeur (Inno Setup 6, s'il est installé). Il installe pour l'utilisateur, sans droits administrateur, dans `%LOCALAPPDATA%\Programs\SIA Check Viewer`, avec un raccourci dans le menu Démarrer et, en option, sur le bureau. On le désinstalle par Paramètres > Applications. Les statuts, commentaires et la clé API sont conservés.
- `app/dist/SiaCheckViewer/`, le dossier prêt à copier. On lance `SiaCheck.Viewer.exe` ; il ne demande ni Python ni runtime .NET.

La version vient de `<Version>` dans `SiaCheck.Viewer.csproj` et de `pyproject.toml`, qui doivent rester alignées. Une analyse en cache produite par une autre version du moteur est refaite à l'ouverture. Le logo est généré par `scripts/make_logo.py`.

- **Ouvrir** : le dossier du projet Treegram, celui qui contient `Nom.tgm` et `VWR\`. Le moteur `engine\sia-check.exe` analyse le `.tgm` et lit la géométrie dans le cache du viewer.
- **Calques par catégorie SIA**, filtres par bâtiment et par niveau, éclatement des niveaux.
- **Points d'attention** :
  - double-clic ou Entrée pour isoler les surfaces concernées et centrer la vue ;
  - Échap pour quitter l'isolement ;
  - `1` / `2` / `3` pour passer le statut à « à traiter », « vu » ou « faux positif » ;
  - un commentaire par point.

  Statuts et commentaires sont conservés d'une analyse à l'autre, dans `%APPDATA%\SiaCheckViewer\reviews\`. Un point suivi qui disparaît passe en « résolu ».
- **Bilan par niveau** : barres de sommation SP → SUP/SUS/SD/SI pour un bâtiment. Un clic sur une barre isole le niveau.
- **Ratios** (second onglet du bilan) : pour chaque ratio, la valeur du projet (cercle) et celle du bâtiment choisi (point, orange hors repère) sur une jauge du repère indicatif. L'infobulle donne les m², le repère et la note.
- **Revue IA** (sur-vérification, procédure `.claude/skills/revue-ia/SKILL.md`) :
  - les verdicts de la dernière revue du projet s'affichent dans la liste et la carte Détail (`vrai sujet`, `à confirmer`, `faux positif`, `agrégat`, sujet `S1`…, raison) ; filtre « Verdict IA » ; « Appliquer les faux positifs » passe en « Faux positif » les points encore « À traiter » ;
  - le bouton **Revue IA** enchaîne analyse, preuves géométriques (`sia-check --preuves`, ratios compris), estimation du coût, puis, après accord, l'appel à Claude Opus 5.5 par l'API Anthropic. Le rapport s'ouvre dans un volet sur la 3D. Le bouton **Rapport IA** (ou Ctrl+I) le rouvre à tout moment sans relancer la revue ;
  - la clé API est saisie dans l'app et chiffrée avec DPAPI pour le compte Windows (`%LOCALAPPDATA%\SiaCheckViewer\anthropic-key.bin`), jamais en clair ;
  - revues lancées depuis l'app : `%APPDATA%\SiaCheckViewer\revue-ia\<projet>\` ; revues faites dans Claude Code : `docs/revue-ia/` (lu quand l'app tourne depuis le dépôt).
- **Limite** : si le projet a été modifié après la dernière ouverture dans le viewer Treegram, le cache 3D est périmé. La visionneuse l'indique.

Développement : `dotnet test app/SiaCheckViewer.sln`.
`SiaCheck.Viewer.exe <dossier projet> --capture image.png [--focus clé] [--report | --ai-panel]` produit une capture pour la revue visuelle.

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
  ratios.py   ratios informatifs SIA 416 / USPI
  viewer.py   fichier pour SIA Check Viewer (--viewer-json)
  preuves.py  preuves géométriques de la revue IA (--preuves, shapely)
  cli.py      ligne de commande
tests/        jeu synthétique (tests/data/synth.csv) + intégration L'Orée (ignorée si le projet est absent)
docs/         ifc-schema.md (phase 0), normes de référence
```

```bash
.venv/Scripts/python -m pytest
```
