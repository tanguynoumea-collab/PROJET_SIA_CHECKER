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
sia-check "L OREE.tgm" --treegram exports/   # exports au gabarit Excel Treegram, depuis le .tgm
sia-check "L OREE.tgm" --mdp MDP-1778-Loree.xlsx --project-id 1778   # tableau MDP HRS rempli
sia-check "L OREE.tgm" --sujets sujets.json   # sujets et corrections proposées (journal à accepter)
sia-check "L OREE.tgm" --revue L_OREE_2026-10-22.verdicts.json --sujets sujets.json   # sujets réorientés par la revue IA
sia-check "L OREE.tgm" --corrections journal.json --out report/ --mdp MDP.xlsx   # surfaces corrigées
```

- Sources acceptées : projet Treegram `.tgm` (surfaces SIA lues dans le fichier projet) ou `.ifc` (mapping dans `config.yaml > sources.ifc`).
- Codes de sortie : `0` aucun écart au-delà de la tolérance, `1` écarts (verdict ALERTE ou ERREUR), `2` erreur de lecture, de configuration ou d'écriture des rapports.

## Rapports (`--out`)

`<projet>_<date>.xlsx`, `.html` et `.json` :

- **xlsx** : onglets *Résidus* (contrôles hors OK, écart décroissant), *Surfaces* (toutes les surfaces lues), *Codes inconnus*, *Synthèse* (par catégorie, puis aire par bâtiment), *Contrôles* (tous les contrôles, OK compris), *Ratios*.
- **html** : même contenu, lisible sans Excel, avec un tableau par niveau aux couleurs de la légende SIA 416 (surfaces externes hachurées).
- **json** : pour n8n : `exit_code`, `counts` par verdict, `residuals` (hors OK), `unknown_codes`, `ratios`.

## Exports au gabarit Treegram (`--treegram`)

`<projet>-SurfacesNettes.xlsx` (une ligne par local) et `<projet>-SurfacesBrutes.xlsx` (SP et SEP par niveau), colonnes et ordre des exports Excel de Treegram, clé `ID TGM` (`H<conteneur>::H<élément>`, lu dans le `.tgm`).

Sur L'Orée, les lignes, les valeurs et l'ordre sont identiques à l'export Treegram du 22.10.2026, à une différence près : celui-ci omet les surfaces SED (26 coursives) et SUT (47 commerces), que `--treegram` garde. Les codes ignorés (SPT…) et USPI n'y figurent pas.

## Tableau MDP (`--mdp`)

Le tableau MDP HRS, rempli depuis le `.tgm` sans copier-coller. Le gabarit par défaut est `src/sia_check/templates/MDP-gabarit.xlsx`, un MDP vierge produit par `scripts/make_mdp_template.py` à partir d'un MDP existant. `--mdp-template` accepte aussi un MDP déjà rempli : ses tableaux de données sont remplacés.

| Feuille | Contenu |
| --- | --- |
| SurfacesBrutesVolumeSIA416 | SP et SEP par niveau : découpage (table `HsSs` du gabarit), largeur et longueur (`DeltaX`/`DeltaY`), périmètre, hauteur brute, m², m³ |
| SurfacesNettesSIA416 | une ligne par local, comme l'export Treegram, SED et SUT compris |
| SurfacesUSPI | SNH, SH, SBH, SE (= SVN − SH), SVN, SVB par lot |
| ListeLogements | un lot par ligne, avec son nombre de chambres |
| SurfacesEnveloppe | façade de chaque niveau (SFN : longueur, hauteur, surfaces brute, nette et vitrée) et toitures (SPT) |
| InfosBatiment | étages hors-sol et sous-sol, largeur et longueur du plus grand niveau courant |
| InfosProjet | nombre de bâtiments, d'étages, de logements (par nombre de chambres) et de chambres |

Restent vides, faute de source dans le `.tgm` : l'affectation, les typologies, le nombre de pièces, les cages d'escalier, la forme des bâtiments et les champs administratifs. Le reste du classeur est recopié tel quel : listes déroulantes, feuille « Listes formulaire », documents. Le tableau croisé de la feuille SurfacesEnveloppe n'est pas recalculé. Les filtres actifs sont levés, les formules gardent leur valeur en cache et sont recalculées à l'ouverture.

## Corrections (`--corrections`)

Un journal JSON de corrections est appliqué aux surfaces lues avant les contrôles. Le `.tgm` n'est jamais modifié. Rapports, exports (`--treegram`, `--mdp`) et visionneuse portent alors sur les surfaces corrigées. Le format est décrit dans `src/sia_check/corrections.py`, et `docs/corrections/L_OREE_exemple.json` en donne un exemple (S1, S2).

| Opération | Effet |
| --- | --- |
| `reclasser` | change la catégorie des cibles (`vers`) |
| `exclure` | retire les cibles des sommes et des exports ; avec `aire`, seulement cette part d'une surface (ex. toit d'attique) |
| `découper` | fait passer `aire` m² d'une surface dans une nouvelle surface de catégorie `vers` (ex. SEP → SA), au même niveau |
| `ajuster` | fixe l'aire des cibles |
| `affecter` | renseigne l'affectation (tableau MDP) |

- La cible se donne par identifiants de surface, par ID TGM ou par sélection (bâtiment, niveau, catégorie, sorte, type, lot).
- Seules les corrections au statut « acceptée » sont appliquées. Une correction inapplicable (cible introuvable, champ manquant) est signalée et laissée de côté, jamais appliquée à moitié.
- Quand une surface élémentaire change de catégorie ou d'aire, le total Treegram de son niveau est décalé d'autant.
- Le bilan s'affiche en console : chaque correction, puis les verdicts avant → après. Avec `--out`, il est aussi écrit dans `<projet>_<date>_corrections.json`, contrôle par contrôle (résolu, réduit, nouveau…).

## Sujets (`--sujets`)

Les points d'attention sont regroupés par cause. Chaque sujet porte une correction de base, au format du journal (statut « proposée », origine « règle »). Le fichier écrit sert aussi de journal : on passe les corrections retenues à « acceptée », puis on l'applique avec `--corrections`. Les sujets figurent aussi dans le fichier visionneuse (`subjects`).

| Sujet | Points | Correction proposée |
| --- | --- | --- |
| `toitures` | A2, et R3 des niveaux dont la SEP est recouverte par la toiture Treegram (SPT) | `exclure` la SEP d'un niveau Toiture, ou seulement sa part sous SPT (attiques), terrasses SEU/SED gardées |
| `abords` | A1, et R3 du niveau du terrain | `découper` vers SA la SEP hors plancher et hors SEU/SED, tracé pré-calculé |
| `sc-implicite` | R1 compatibles avec la surface de construction | aucune |
| `agregats` | contrôles sommés par bâtiment et projet | aucune (suivent leurs niveaux) |
| `<règle>-<catégorie>` | les autres | à vérifier |

**Revue IA (`--revue`).** La revue IA reçoit ces propositions dans ses preuves (`propositions`). Elle rend, à côté des verdicts, un bloc `sujets` (verdicts version 2, format dans `.claude/skills/revue-ia/SKILL.md`, étape 6) : pour chaque sujet S1, S2…, quelles propositions garder, modifier, rejeter ou ajouter, avec un défaut par sujet de base (`"base": ["toitures"], "par_defaut": "garder"` : toutes les toitures sortent).
- `--revue` applique ces décisions. Les points passent dans le sujet IA de leur verdict, et les corrections décidées y passent avec l'origine « ia ».
- Une proposition rejetée reste au journal au statut « rejetée ».
- Une décision invalide (identifiant inconnu, correction incomplète, cible absente) est écartée et signalée.
- Tout reste « proposée » : l'utilisateur accepte.

Sur L'Orée, la revue v2 (`docs/revue-ia/L_OREE_2026-10-22.verdicts.json`) donne 31 décisions appliquées et aucune écartée, réparties en S1 (9 découpes), S2 (22 exclusions), S4 et S5 à vérifier, S6 faux positifs. La revue lancée depuis la visionneuse écrit le même bloc.

Aires et tracés viennent de la géométrie (shapely). Sans elle, les aires viennent des bilans de niveau et les découpes n'ont pas de tracé.

Sur L'Orée, sans IA : `toitures` propose 7 280 m² (S2 de la revue IA : 7 279) et `abords` 1 812,65 m² pour B03 N00. Une fois toutes les propositions appliquées, l'écart R3 du projet passe de 15 091 m² à 250 m². Il reste les petits écarts d'étage, que la revue laissait à confirmer. A1 reste une alerte sur les terrasses du rez gardées en SEU/SED : la question est posée, la réponse se donne point par point.

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
- **Sujets et corrections** (onglet `Sujets`, ouvert par défaut quand il y en a ; Ctrl+1 / Ctrl+2 pour passer de Sujets à Points) :
  - les sujets du moteur, réorientés par la dernière revue IA. Pour chacun : action, origine (IA ou règle), surface en jeu, et un symbole d'état par correction (proposée, acceptée, appliquée, rejetée, inapplicable) ;
  - la carte d'un sujet propose « Accepter les n » et « Rejeter les n ». Sur une correction sélectionnée : `1` / `2` / `3` (proposée, acceptée, rejetée), « Modifier » (aire, explication : la correction devient « manuel ») ;
  - sélectionner un sujet ou une correction isole ses surfaces en 3D. Le tracé d'une découpe ou d'une exclusion partielle est dessiné à l'accent ;
  - les décisions sont gardées par projet, dans `%APPDATA%\SiaCheckViewer\corrections\` (journal lu par `sia-check --corrections`). « Analyser » les applique : son libellé compte les décisions en attente (`Analyser · 22`), et la barre de commande indique les corrections appliquées ;
  - avant/après dans le bilan par niveau : ce que les corrections ont retiré prolonge la barre en pointillé, et l'ancien résidu est barré à côté du nouveau ;
  - « Exporter » : rapports d'analyse, tableau MDP (gabarit livré ou choisi), exports Treegram, tous sur les surfaces corrigées.
- **Module de tracé** (« Tracer… » sur une découpe ou une exclusion partielle, ou T ; « Découper cette surface… » dans la fiche d'une surface) : volet sur la 3D avec le plan du niveau.
  - Le plan montre les surfaces aux couleurs SIA, la surface source en contour épais et l'emprise du niveau inférieur en pointillé.
  - Modes Tracer et Modifier : accrochage aux sommets et aux arêtes (Alt pour le désactiver), Maj pour l'horizontale ou la verticale, Ctrl+Z / Ctrl+Y, F pour cadrer, molette et clic milieu pour se déplacer.
  - L'aire comptée s'affiche en direct : tracé ∩ surface source, moins les SEU/SED/SEI pour une SEP. Elle est décomposée, et l'aperçu de l'écart R3 du niveau l'accompagne.
  - « Enregistrer le tracé » écrit dans la correction le polygone, l'aire et la triangulation, avec l'origine « manuel ». Une découpe créée depuis une surface rejoint le sujet qui la couvre, sinon « Corrections manuelles ».
  - À l'application, le moteur recalcule l'aire depuis le polygone (shapely) et signale un écart au-delà de la tolérance.
- **Revue IA** (sur-vérification, procédure `.claude/skills/revue-ia/SKILL.md`) :
  - les verdicts de la dernière revue du projet s'affichent dans la liste et la carte Détail (`vrai sujet`, `à confirmer`, `faux positif`, `agrégat`, sujet `S1`…, raison) ; filtre « Verdict IA » ; « Appliquer les faux positifs » passe en « Faux positif » les points encore « À traiter » ;
  - le bouton **Revue IA** enchaîne analyse, preuves géométriques (`sia-check --preuves`, ratios compris), estimation du coût, puis, après accord, l'appel à Claude Opus 5.5 par l'API Anthropic. Le rapport s'ouvre dans un volet sur la 3D. Le bouton **Rapport IA** (ou Ctrl+I) le rouvre à tout moment sans relancer la revue ;
  - la clé API est saisie dans l'app et chiffrée avec DPAPI pour le compte Windows (`%LOCALAPPDATA%\SiaCheckViewer\anthropic-key.bin`), jamais en clair ;
  - revues lancées depuis l'app : `%APPDATA%\SiaCheckViewer\revue-ia\<projet>\` ; revues faites dans Claude Code : `docs/revue-ia/` (lu quand l'app tourne depuis le dépôt).
- **Limite** : si le projet a été modifié après la dernière ouverture dans le viewer Treegram, le cache 3D est périmé. La visionneuse l'indique.

Développement : `dotnet test app/SiaCheckViewer.sln`.
`SiaCheck.Viewer.exe <dossier projet> --capture image.png [--focus clé] [--subject S2 [--correction id [--trace]]] [--points] [--report | --ai-panel] [--profile dossier]` produit une capture pour la revue visuelle. `--profile` isole statuts, journal, revues et analyses dans un dossier jetable.

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
  treegram.py exports au gabarit Excel Treegram (--treegram)
  mdp.py      tableau MDP HRS (--mdp)
  corrections.py  journal de corrections, application, avant / après (--corrections)
  sujets.py   points regroupés par cause, corrections de base et tracés pré-calculés (--sujets)
  xlsx_tables.py  remplissage des tableaux d'un classeur sans perte (validations, tableaux croisés)
  preuves.py  preuves géométriques de la revue IA (--preuves, shapely)
  cli.py      ligne de commande
tests/        jeu synthétique (tests/data/synth.csv) + intégration L'Orée (ignorée si le projet est absent)
docs/         ifc-schema.md (phase 0), normes de référence
```

```bash
.venv/Scripts/python -m pytest
```
