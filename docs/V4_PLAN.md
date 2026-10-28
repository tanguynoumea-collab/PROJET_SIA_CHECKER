# V4_PLAN — Génération des surfaces SIA depuis l'IFC architecte

> Statut : ☑ Brouillon · ☐ Validé par l'utilisateur
> Version : 0.6 — 28.10.2026 · phases 19 à 22 livrées (§10 à §14), comparaisons à des MDP réels (§13, §14)

## 1. Objectif

La V1 à la V3 **contrôlent, corrigent et exploitent** les surfaces SIA produites par Treegram. La V4 les **produit** : un moteur lit une maquette architecte IFC (avec ses `IfcSpace`) et génère les surfaces SIA 416 / USPI **au format et selon les classifications de Treegram**.

Contrainte majeure : la Fiabilisation et le Dashboard ne doivent **pas être retravaillés**. Les surfaces générées entrent dans le pipeline au même point que celles de Treegram.

Le moteur devient une **troisième section de l'accueil**, à côté de la Fiabilisation et du Benchmark : *Génération*. Elle a sa vue 3D (IFC + surfaces), permet d'ajuster à la main ce que sort le moteur, et combine un **moteur algorithmique** et une **analyse IA** (même clé API, chiffrée DPAPI) pour ce qui demande du jugement.

## 2. Ce que l'exploration a montré (28.10.2026)

### 2.1 Le point d'entrée du pipeline n'est pas le `.tgm`, c'est le DataFrame normalisé

Tout le pipeline (règles, corrections, sujets, MDP, exports Treegram, viewer, benchmark) ne voit que :

- le **DataFrame de `reader.py`** (`SURFACE_COLUMNS` : `id`, `building`, `level`, `category`, `area`, `kind` leaf/node, `room_type`, `lot`, `element_id`, `tgm_id`, `perimeter`, `gross_height`, `dx`, `dy`, `bedrooms`, `gross_area`, `net_area`, `reservations_area`) ;
- les **maillages par `element_id`** (`geom.Cache`).

Seuls `tgm.py` et `geom.py` connaissent les formats binaires Treegram. Ce sont deux formats **non documentés, rétro-ingéniés en lecture**. Écrire un vrai `.tgm` serait fragile et sans intérêt : Treegram n'a pas à le relire.

**Décision proposée : le moteur écrit son propre fichier projet, qui reproduit à l'identique le modèle Treegram** (mêmes noms d'éléments, mêmes propriétés, mêmes totaux de niveau, mêmes `Type`, mêmes ID), et `reader.py` gagne un troisième backend. Tout ce qui est en aval reste tel quel.

### 2.2 Le modèle Treegram à reproduire (relevé sur L'Orée, `docs/ifc-schema.md` §2.2)

| Étage de l'arbre | Contenu | Nom des éléments |
|---|---|---|
| Totaux de niveau (nœuds) | 17 codes par niveau, ordre fixe : `SFN, SRV, SUP, SUS, SD, SED, SI, SUT, SEU, SNH, SHA, SBH, SVN, SVB, SP, SEP, SPT`. **SP et SEP n'existent qu'ici.** `SFN` porte `GrossArea`, `NetArea`, `ReservationsArea`, `Perimeter`, `GrossHeight` | le code seul |
| Espaces intérieurs | SUP, SUS, SD, SI, SUT | `Bât_Niv_ShellByTgm-n_SpaceByTgm-m_CODE` |
| Espaces extérieurs | SEU, SED, SPT | `Bât_Niv_ExtShellByTgm-n_CODE` |
| Chaîne USPI par lot | SNH, SHA, SBH, SVN, SVB (+ `Bedrooms` sur SNH) | `Bât_Niv_Apart-n_CODE` |

`Type` (sous-type) : SUP `PieceDeVie`, `Chambre`, `PieceSecondaire_{2,3,4}PointsEau`, `Distribution` ; SD `Ascenseur`, `CirculationH`, `Escalier` ; SI `Gaine`, `Local` ; SEU `Balcon`, `Terrasse` ; SED `CirculationExt` ; SUT `Commerce` ; SPT `Toiture`. Lot : `ApartmentByTgm`.

### 2.3 Comment Treegram y arrive (journal des actions, `DB/*.db3` de L'Orée)

Les surfaces SIA **ne sont pas une copie des `IfcSpace`**. Treegram reconstruit ses propres objets à partir des murs, dalles et ouvertures, puis classe :

1. **BAAMER** : niveaux, dalles, murs, espaces, ouvertures par niveau ; nettoyage des doublons, fusion des murs superposés (tolérance de joint 0,07 m).
2. **DATCHA** : enveloppes et coques (`Shell` = logement ou unité ; prolongation des axes 0,15 m, épaisseur des murs de loggia 0,29 m), espaces reconstruits (`SpaceByTgm`), gaines (0,0025–1,5 m²), circulations, escaliers, réservations, toitures, extérieurs (balcons, terrasses, porte-à-faux depuis dalles, toitures et espaces architecte), façades.
3. **APARTMENT** : logements, appartenance des objets aux coques, ouvertures vers les espaces, forme.
4. **BOOMER :: Create : SIA Surfaces** : l'arbre SIA final.

C'est la feuille de route du moteur : mêmes étapes, mêmes paramètres, réglables dans `config.yaml`.

### 2.4 Un jeu de référence existe déjà, presque

Le `.tgm` de L'Orée contient **la maquette importée** (638 `Space3d`, 6 834 murs, 2 051 portes, 1 644 fenêtres), **tous les intermédiaires** (coques, espaces reconstruits avec leur profil horizontal) et **le résultat SIA** (6 090 surfaces). Il manque l'IFC source lui-même : les `Audits/2D3D-*.ifc` ne contiennent que leurs réglages (maquettes issues de plans 2D via Wisebim).

→ Avec l'IFC source de L'Orée (ou un autre projet Treegram dont on a l'IFC architecte), on mesure le moteur **surface par surface et niveau par niveau** contre Treegram. Sans paire IFC ↔ Treegram, « identique à Treegram » ne peut pas être vérifié (§9, question 1).

## 3. Architecture

```
IFC architecte ──► [1 Ingestion] ──► [2 Géométrie] ──► [3 Classification règles] ──► [4 Analyse IA] ──► [5 Ajustements manuels]
                    ifcopenshell      shapely, plans     dictionnaire, score         Claude Opus 5.5       journal (comme V2)
                                      par niveau         de confiance                propositions
                                                                                              │
                                     <Nom>.siagen  ◄── [6 Assemblage au modèle Treegram] ◄────┘
                                          │
                      reader.read_siagen ─┴─► DataFrame normalisé + maillages ─► Fiabilisation, MDP, Benchmark (inchangés)
```

### 3.1 Moteur (Python, `src/sia_check/generation/`)

| Module | Rôle |
|---|---|
| `ingest.py` | IFC → bâtiments, niveaux (altitudes, hauteurs), `IfcSpace` (contour, psets, `Name`/`LongName`, zones `IfcZone`), murs, dalles, toitures, ouvertures, escaliers, garde-corps. Seul module à toucher à l'IFC |
| `plans.py` | Coupe de chaque niveau : contours 2D (shapely), contour extérieur brut du niveau (SP), emprise du niveau inférieur, rattachement des éléments |
| `envelope.py` | Enveloppes et coques (logements, unités), extérieurs (balcons, terrasses, coursives, toitures), façades (SFN brute / nette, réservations) et vitrages (SRV) |
| `classify.py` | Règles : nom de pièce → (code, `Type`), avec un score de confiance ; dictionnaire FR/DE/IT dans `config.yaml > generation` |
| `uspi.py` | Chaîne USPI par lot (SNH, SHA, SBH, SVN, SVB), chambres |
| `assemble.py` | Arbre Treegram : noms, propriétés, ID, totaux de niveau dans l'ordre, maillages |
| `compare.py` | Moteur vs Treegram (même projet) : écarts par code, niveau, surface ; sert aux tests et au réglage |

CLI : `sia-check --generer maquette.ifc --out dossier/` écrit le projet généré ; `--comparer-treegram projet.tgm` donne le rapport d'écarts.

### 3.2 Format de sortie `.siagen` (contrat, version 1)

Un dossier projet, ouvrable par la Fiabilisation comme un dossier Treegram :

```
<Nom>/
  <Nom>.siagen.json     éléments au modèle Treegram : name, props (Catégorie SIA, Area, Type, ApartmentByTgm,
                        Bedrooms, Perimeter, GrossHeight, DeltaX, DeltaY, GrossArea, NetArea, ReservationsArea),
                        element_id, container_id, kind (leaf | node), building, level, mesh
  <Nom>.ifc             copie (ou lien) de la maquette source, pour la 3D
  generation/           journal des décisions (règles, IA, manuel), rapport du moteur
```

`reader.py` lit `.siagen.json` et rend exactement le même DataFrame que pour un `.tgm` ; `geom` y lit les maillages au lieu du cache VWR. Les ID gardent la forme `H<conteneur>::H<élément>` (exports Excel, Excel de correction).

### 3.3 Algorithme d'abord, IA ensuite

L'algorithme fait tout ce qui est mesurable : contours, aires, SP, extérieurs, façades, sommes, et la classification des noms clairs. L'IA ne reçoit **que ce qui demande du jugement**, sous forme de preuves compactes (pas l'IFC) :

| Question pour l'IA | Exemple |
|---|---|
| Pièce au nom ambigu ou absent | « Dégag. », « Raum 12 », « Local » sans usage → SUP Distribution, SD CirculationH, SI Local ? |
| SUP, SUS ou SUT selon la destination | une buanderie commune, un local vélos, un commerce en pied d'immeuble |
| Regroupement en logements quand l'IFC n'a pas de zones | pièces reliées par des portes, derrière une porte palière |
| Nombre de chambres, typologie | 3 chambres dont une de 8 m² |
| Extérieur : SEU, SED, SA ou toiture | terrasse de plain-pied avec le terrain (SA, SIA 416 §3), toiture accessible ou non |
| Cohérence d'ensemble | niveau sans SD, logement sans pièce d'eau, ratio SUP/SP hors repère |

Chaque réponse est une **proposition** au format du journal existant (origine « ia », statut « proposée », raison), jamais une écriture directe. Même mécanique que la revue IA : estimation du coût, accord, appel, rapport. Les appels partent de l'app (C#, `AiReviewService`), avec la clé DPAPI existante.

### 3.4 Section *Génération* de l'app

- **Accueil** : troisième carte, « Générer depuis un IFC… », projets générés récents.
- **Vue 3D** (HelixToolkit, déjà en place) : maquette IFC en gris translucide, surfaces générées aux couleurs SIA, mêmes calques, filtres et éclatement des niveaux que la Fiabilisation.
- **Liste des surfaces** : code, `Type`, lot, aire, origine (règle / IA / manuel), confiance. Les surfaces à faible confiance d'abord.
- **Ajustements** : changer code, `Type`, lot ; fusionner / découper (module de tracé V2 réutilisé) ; affecter une pièce à un logement. Tout passe par le journal, la génération se rejoue.
- **« Envoyer en fiabilisation »** : écrit le projet `.siagen` et l'ouvre dans la Fiabilisation. Le statut, le MDP et la base du benchmark suivent comme pour un projet Treegram, avec la source « IFC » dans la fiche projet.

## 4. Mesure de la qualité

1. **Paire de référence** IFC ↔ Treegram (§9, q. 1) : écart par code et par niveau, surfaces appariées par contour (recouvrement ≥ 90 %), taux de classification identique.
2. **Cibles V4.0** (à valider) : SP et SUP à ±1 % par niveau ; ≥ 95 % des surfaces intérieures au même code que Treegram ; aucun écart de classification sans explication dans le rapport.
3. **La Fiabilisation comme juge** : un projet généré passe par les règles R1–R5, A1–A3, U1–U4. Il ne doit pas en sortir plus de points d'attention qu'un projet Treegram.
4. Tests : jeu IFC synthétique (un niveau, deux logements, un balcon, une cage) dans `tests/data/`, plus l'intégration sur la paire de référence (ignorée si absente, comme L'Orée aujourd'hui).

## 5. Phases proposées

Numérotation à la suite de la V3 (phase 18).

| Phase | Livrable | Vérification |
|---|---|---|
| **19** Contrat et lecteur | Format `.siagen` v1, `reader.read_siagen`, maillages ; un `.siagen` produit **depuis le `.tgm` de L'Orée** doit donner exactement la même analyse que le `.tgm` | rapports identiques, tests |
| **20** Ingestion IFC | `ingest.py`, `plans.py` : niveaux, espaces, murs, dalles, ouvertures, contours 2D | inventaire de la paire de référence |
| **21** Intérieurs | SP par niveau, SpaceByTgm depuis les `IfcSpace`, classification par règles (SUP/SUS/SUT/SD/SI + `Type`) | `compare.py` vs Treegram |
| **22** Extérieurs et enveloppe | SEP, SEU, SED, SPT, SFN, SRV | idem |
| **23** Logements et USPI | coques, lots, chambres, SNH…SVB | idem, règles U1–U4 |
| **24** Analyse IA | preuves, prompt, propositions, coût, rapport | jeu de cas ambigus |
| **25** Section Génération (app) | accueil, 3D IFC + surfaces, liste, ajustements, envoi en fiabilisation | revue visuelle (Daedalus) |
| **26** Clôture V4.0 | doc, README, version 4.0.0 | pipeline complet sur un projet réel |

La phase 19 est sans risque et débloque tout : elle prouve que le pipeline accepte une source non Treegram sans retouche.

## 6. Ce qui ne change pas

Règles, corrections, sujets, propositions MDP, exports Treegram et MDP, revue IA, benchmark, dashboard. Le seul fichier modifié en aval est `reader.py` (un backend de plus) et la lecture des maillages.

## 7. Risques

| Risque | Parade |
|---|---|
| Pas de paire IFC ↔ Treegram : on ne peut pas prouver la conformité | l'obtenir avant la phase 21 (§9) |
| Qualité très variable des IFC architecte (espaces manquants, mal nommés, ouverts, hors niveau) | audit d'entrée bloquant avec liste des défauts ; l'IA et l'ajustement manuel comblent le reste |
| Règles de Treegram implicites (déductions forfaitaires, escaliers, 95 % SHAB, épaisseurs) | paramètres relevés dans le `.tgm` repris dans `config.yaml`, réglés sur la paire de référence |
| Maquettes lourdes (100 Mo – 1 Go dans `Analyse parametrique des projets`) | ingestion par classes utiles seulement, cache de géométrie, calcul hors du thread UI |
| Coût IA | seules les décisions ambiguës partent, estimation et accord avant chaque appel |

## 8. Mise en ligne

Comme la V3 : rien en ligne avant la fin de la validation.

## 9. Décisions (28.10.2026)

1. **Paire de référence : aucune pour l'instant.** On avance sur un jeu IFC synthétique et sur les maquettes architecte du dossier `Analyse parametrique des projets` (ingestion, robustesse). La conformité à Treegram reste **non prouvée** tant qu'aucune paire IFC ↔ `.tgm` n'est disponible ; `compare.py` est prêt à la mesurer dès qu'elle arrive. La phase 19 prouve déjà le format (`.siagen` tiré du `.tgm` de L'Orée).
2. **Format de sortie : `.siagen.json`** (§3.2), lu par un troisième backend de `reader.py`.
3. **Périmètre V4.0 : tout l'arbre Treegram**, USPI par logement et enveloppe (SFN, SRV) compris.
4. **Logements : marqués par une propriété des `IfcSpace`.** Le nom du pset et de la propriété se règle dans `config.yaml > generation` ; sans elle, l'algorithme puis l'IA regroupent les pièces (§3.3).

## 10. Phase 19 livrée (28.10.2026)

- **Contrat `.siagen.json` v1** dans `src/sia_check/siagen.py`. Un élément porte son nom Treegram, `kind` (leaf ou node), son bâtiment et son niveau explicites, ses identifiants, ses propriétés Treegram telles quelles et ses maillages (float32 et uint32 en base64). Le contrat diffère sur un point du §3.2 : la maquette IFC n'est pas encore copiée dans le dossier, elle viendra avec la phase 20.
- **Lecteur** : `reader.read` reconnaît `.siagen.json`. La lecture du `.tgm` est coupée en deux : les éléments situés (`tgm_elements`), puis les lignes du DataFrame (`_rows`). Les deux formats partagent la seconde étape, ce qui garantit des colonnes identiques. `geom.for_model` et `geom.source_modified` choisissent la géométrie selon la source.
- **CLI** : un dossier contenant un seul `.tgm` ou un seul `.siagen.json` est un projet ; `--siagen` écrit le contrat depuis un `.tgm`.
- **App** : la fiche projet et l'ouverture acceptent un dossier `.siagen.json`, où la géométrie est comprise, sans exiger de VWR.
- **Preuve sur L'Orée**, avec le journal d'exemple : rapports xlsx, html et json, bilan des corrections, sujets, fichier visionneuse (5 173 maillages), MDP et exports Treegram sont identiques à ceux du `.tgm`. Seul le chemin du fichier source change. Le fichier pèse 5,3 Mo et s'écrit en 10 s.
- Tests : `tests/test_siagen.py` (aller-retour, maillages au bit près, contrat violé, projet écrit à la main comme le fera le moteur, intégration L'Orée) et le contrôle du dossier dans l'app.

## 11. Phase 20 livrée (28.10.2026)

### Ce que disent les maquettes HRS

Sondage de quatre maquettes du dossier `Analyse parametrique des projets` et de Gare-Casino (`10.03.05.01.1-Audit IFC`).

- **Logement** : `Pset_HRS.NumeroPiece` vaut par exemple « 1A.01.02.01 » (bâtiment, étage, logement, pièce). Les parties communes sont numérotées « .99. ». C'est la propriété retenue (§9, décision 4).
- **Indices de classification déjà présents** :
  - `Pset_SpaceCommon.Category` en toutes lettres SIA (« Surface utile principal », « Surface de dégagement », « Surface d'installation »…) sur les Myonaz ;
  - un `SIA416` explicite sur Afiro ;
  - un préfixe de code dans le nom long sur CGA (`SUS_CON`, `SD_ASC_1`, `SI_VEN`).

  La phase 21 les lira avant le dictionnaire de noms.
- **Espaces de nature différente** : en plus des pièces, on trouve des espaces « Surface de plancher » (type prédéfini `GFA`, donc une SP), des contours de logement (`LOG`, nom long « SBH »), des places de parc (`PARKING`), et des surfaces de terrain et d'abords. Ils se superposent aux pièces : la phase 21 doit d'abord dire ce qu'est chaque espace, avant de compter.
- **Géométrie** : les murs en couches n'ont de géométrie que dans leurs `IfcBuildingElementPart`, et les toitures que dans leurs dalles. Ces objets reçoivent la géométrie de leurs composants.
- **Altitudes** : elles sont souvent absolues (≈ 609 m sur les Myonaz, géoréférencées). Les espaces Revit commencent parfois sous leur niveau (−0,5 m au rez des Myonaz), et l'audit le signale (G7).
- **Aires déclarées et aires en plan** : sous les toitures en pente (E03 des Myonaz), l'aire Revit est plus petite que l'aire en plan, de 8 à 15 %. La phase 21 tranchera laquelle fait foi au sens SIA 416 (§0.4 : projection horizontale).

### Livré

- `generation/ingest.py` : modèle `Model` / `Storey` / `Item`, triangulation multi-cœurs, géométrie des composants, niveau par la structure sinon par l'altitude, logement par propriété.
- `generation/plans.py` : emprise en plan (union vectorisée des triangles non verticaux) et `Plan` par niveau.
- `generation/audit.py` : audit G1 à G10, inventaire JSON, résumé console ; CLI `--inventaire` (code 1 si bloquant).
- `config.yaml > generation` : classes lues, motif du logement, tolérances de l'audit. `shapely` passe dans les dépendances principales.
- Tests : `tests/ifc_synth.py`, une maquette IFC synthétique avec géométrie (deux niveaux, un logement, un couloir commun, un local hors structure, mur, porte, dalle), réutilisable par les phases suivantes ; `tests/test_generation_ingest.py`.

| Maquette | Schéma | Niveaux | Espaces | Éléments | Durée | Audit |
|---|---|---|---|---|---|---|
| La Myonaz 1 (22 Mo) | IFC4 | 7 | 137 | 508 | 16 s | G6 ×9 (toiture en pente), G7 ×2 |
| Afiro pièces (12 Mo) | IFC2X3 | 5 | 138 | 0 | 5 s | G7 ×33 (niveaux « I », « S02 » mal placés), sans logements |
| CGA L04 (36 Mo) | IFC2X3 | 5 | 31 | 775 | 28 s | aucun logement (parking, technique) |
| Gare-Casino (217 Mo) | IFC2X3 | 9 | 0 | 7 744 | 18 s | **G1 bloquant** : aucun espace (273 s avant de sauter la triangulation inutile) |

### À reprendre plus tard

- Le moteur embarqué dans l'app exclut aujourd'hui ifcopenshell (`app/build.ps1`). La section Génération (phase 25) devra l'embarquer, ce qui alourdira l'exécutable.
- Pas encore de cache de triangulation : sur les maquettes de plus de 200 Mo, chaque lecture la refait.

## 12. Phase 21 livrée (28.10.2026) : surfaces intérieures

### Livré

- `classify.py` : nature de chaque espace (pièce, plancher, logement, extérieur, site), puis classement des pièces par source (propriété, catégorie, préfixe, dictionnaire), sous-type Treegram, convention « dégagement de logement = SUP Distribution », confiance et désaccords.
- `interiors.py` : SP par niveau, à partir des surfaces de plancher moins les extérieurs, sinon du contour des pièces, des murs et des poteaux.
- `assemble.py` : éléments `.siagen` au modèle Treegram (coques, `ApartmentByTgm`, totaux SUP, SUS, SD, SI, SUT et SP par niveau, maillages triangulés), codes de niveau Treegram.
- `engine.py` et CLI `--generer` : projet généré et `generation/rapport.json`, la liste de travail de l'IA et des ajustements.
- Tests : `tests/test_generation_interiors.py` (27 tests : dictionnaire, sources, natures, SP, noms, contrôle par la Fiabilisation).

### Essais (IFC → `.siagen.json` → Fiabilisation)

| Maquette | Pièces | Sources | À confirmer | Fiabilisation |
|---|---|---|---|---|
| La Myonaz 1 | 101 | catégorie 101 | 2 | INFO ×6 (SC implicite 15–18 %), ERREUR R1 au N00 : 79 m² de surface de plancher sans pièce dessinée |
| La Myonaz 2 | 193 | catégorie 193 | 7 | INFO ×7, aucune erreur |
| Afiro | 135 | propriété 132, dictionnaire 3 | 39 | INFO ×7, aucune erreur |
| CGA L04 | 31 | préfixe 31 | 4 | ERREUR R1 au N02 (toit-terrasse : 68 m² de SP pour 9 m² de pièces) |

Le projet généré s'ouvre dans l'app (3D aux couleurs SIA, bilan par niveau, propositions MDP).

### Points à contrôler par l'utilisateur

1. **Réduits** : l'architecte les classe en SUS (« Surface utile secondaire »), alors qu'un réduit de logement serait de la SUP chez Treegram. L'IFC est suivi, et la décision est marquée à confirmer.
2. **Bâtiments non résidentiels** (Afiro) : le `SIA416` de l'architecte est suivi même quand le nom dit autre chose (couloir en SUP, stockages en SUP, « cage des secours » en SUP). 36 désaccords sont listés pour l'IA.
3. **SUP sans sous-type reconnu** (bureaux, ateliers) : elle prend « PieceDeVie ». Treegram n'a pas de sous-type pour le tertiaire.
4. **Aire d'une pièce** : l'emprise en plan est retenue (SIA 416 §0.4), pas l'aire déclarée par Revit. Sous les toitures en pente, l'écart va jusqu'à 15 %. C'est réglable : `generation.sp.area_source: declared`.
5. **SP d'une maquette sans murs** (Afiro n'exporte que les pièces) : la SP est le contour des pièces, sans l'épaisseur des murs de façade. Elle est donc sous-estimée.
6. **Cages d'escalier** : les Myonaz n'ont aucun espace « escalier » (les paliers sont des SD de circulation). Le KPI cages reste vide, ce qui relève de la phase 22 (escaliers depuis les `IfcStair`).

## 13. Comparaison à des MDP réels (28.10.2026)

Une paire IFC ↔ `.tgm` manque toujours, mais la base du benchmark contient les MDP de projets dont on a les maquettes ARC : 1712 Myonaz (bâtiments 1, 2, 3, P), 1467 La Bâtie (bâtiments B et C), 1399 Quartier de l'Étang C (C1 à C4). Le MDP est le livrable HRS final, construit depuis les exports Treegram. `--comparer-mdp` mesure l'écart.

### Ce que la référence a tranché

| Point du §12 | Décision prise sur la référence |
|---|---|
| Aire d'une pièce | **aire déclarée par l'IFC** (Revit), à défaut l'emprise : sous la toiture en pente (Myonaz N03), le MDP compte 164,7 m² de SUP et non les 182,6 m² de l'emprise |
| Réduits classés SUS par l'architecte | **SUP** dans un logement (convention Treegram) |
| SP « surface de plancher » dessinée | on la respecte telle quelle ; on n'en retire qu'un extérieur dessiné **dedans** (≥ 80 %), et on y ajoute les pièces qui en sortent, avec leurs murs (La Bâtie, rez : poussettes, buanderie) |
| « Surface de plancher externe » | c'est un extérieur, pas de la SP |

Le moteur lit aussi les conventions de La Bâtie : les catégories préfixées (« 416-SN-Surface utile principale »), et le logement noté dans `Pset_SpaceOccupancyRequirements.Appartement`, valable dans son étage, « C » désignant les parties communes.

### Résultats

| Projet | Locaux MDP / générés | Même code | SP par étage | SUP, SUS, SD, SI par étage |
|---|---|---|---|---|
| Myonaz bât. 1 (22 Mo) | 101 / 101 | **100 %** | identique (5 étages) | identiques |
| Myonaz bât. 2 (39 Mo) | 193 / 193 | **100 %** | identique (5 étages) | identiques |
| La Bâtie B (83 Mo, 540 espaces) | 358 / 413 | 99 % des appariés | identique du N01 au N05 ; rez −19,8 m² (−3,9 %) ; sous-sol +11,7 m² (+0,7 %) | SUP, SUS et SI identiques ; SD +2,8 m² au N02 |

Écarts de La Bâtie restant ouverts :

- **55 locaux générés en trop** : ce sont de petites gaines de logement (0,1 à 0,6 m²). Le MDP les regroupe en une ligne « Gaines techniques Logements » par logement, pour la même aire totale. Treegram regroupe-t-il les gaines par coque ? Cela se vérifiera sur L'Orée.
- **Rez, −19,8 m²** : la SP du MDP dépasse le contour pièces + murs. On ne sait pas encore ce qu'elle compte de plus (les entrées couvertes « ENT », dessinées en extérieur ?).
- **Sous-sol, +0,7 %** : aucune surface de plancher n'y est dessinée, et le contour pièces + murs déborde légèrement.

Le test d'intégration `test_myonaz_matches_its_mdp` fixe le résultat Myonaz (100 % des locaux au même code, aucun écart d'étage au-delà de 0,5 m²).

## 14. Phase 22 livrée (28.10.2026) : extérieurs, toitures, enveloppe

### Modèle Treegram reproduit (relevé sur L'Orée)

- **SEU, SED, SEI** : une surface élémentaire `ExtShellByTgm-n` par extérieur, avec son logement et son type (Balcon, Terrasse, CirculationExt).
- **SEP** : un total seulement. Elle additionne les extérieurs, les contours « plancher externe » et les toitures SPT (que la Fiabilisation retire de la SEP, comme pour un `.tgm`).
- **SPT** : ce que la SP du niveau inférieur laisse à découvert, posée sur le niveau du dessus. Un niveau « Toiture » est créé s'il manque.
- **Dalle sur sous-sol** à découvert : des abords (SA), hors SEP (décision du 28.10.2026, voir plus bas). Treegram L'Orée la laissait dans la SEP du rez (erreur R3 et alerte A1 dans la Fiabilisation).
- **SFN** : périmètre de la SP × hauteur d'étage, sous-sols compris (Treegram les calcule aussi) ; réservations = fenêtres et portes de façade. **SRV** = ces mêmes ouvertures (L'Orée : SRV ≈ réservations).
- Les totaux SP, SEP et SPT portent la hauteur d'étage, le périmètre et DeltaX / DeltaY (rectangle minimal).

### Comparaison aux MDP

| Projet | SEU par étage | SEP | Façade (SFN brute) | Vitrages (SRV) |
|---|---|---|---|---|
| Myonaz 1 et 2 | identique | le MDP n'y met que les « Surface externe de plancher » dessinées : écart attendu | absente du MDP | absente du MDP |
| La Bâtie B | identique à tous les niveaux (337,1 m²), entrées comprises | étages +1,7 m² (murs des balcons, comme le MDP) ; rez 70,5 contre 49,8 m² (le MDP y compte moins de SEP que de SEU) | −10 % (321 contre 356 m² par étage courant) | +2 % |

Myonaz 1 et 2 restent à 100 % des locaux au même code, balcons compris (111 et 210 locaux).

### Points à contrôler

1. ~~Entrées couvertes du rez~~ : **tranché le 28.10.2026, SEU comme le MDP** (`config.yaml`, `exterior_rooms` : entrée, porche, perron). Les passages, coursives et préaux restent en SED.
1. ~~Dalle sur sous-sol dans la SEP du rez~~ : **corrigé le 28.10.2026**. La Bâtie y avait 1 131 m² de SEP, dont 1 066 m² sans sous-catégorie (R3, A1) ; le MDP n'en compte pas. Elle reste hors SEP (`Level.slab`, `slab_m2` dans `generation/rapport.json`).
2. **Façade** : le MDP La Bâtie (« enveloppe thermique ») est 10 % plus long que le périmètre de la SP. Sur les attiques, il compte aussi une façade au niveau TOI (122,6 m²), que le moteur ne produit pas.
3. **Jardins privatifs** : en SEU dans un logement (MDP Myonaz), sinon en extérieur par défaut.
4. **SP et locaux hors du contour dessiné** : on ajoute les locaux utiles et de dégagement (La Bâtie : poussettes, buanderie), pas les installations (Myonaz 2 : bassin de rétention en SI hors SP). C'est une règle déduite de deux références seulement.

### Correctif du 28.10.2026 : précision des maillages

Les maillages générés étaient écrits en coordonnées nationales (E ≈ 2 552 777 m) dans le `.siagen.json`, en float32 comme le cache VWR. Avec 24 bits de mantisse, chaque sommet était arrondi au quart de mètre, d'où des triangles en éventail et un scintillement en 3D (signalés sur Myonaz 2), et des aires de maillage fausses. Le moteur écrit désormais ses maillages par rapport à une origine locale (`siagen.local_origin`, arrondie à 100 m), enregistrée dans l'en-tête (`"origin"`, champ facultatif du contrat v1). Ce repère local est celui de la visionneuse, comme pour Treegram.

La visionneuse pose aussi la dalle SEP sous ses surfaces élémentaires, comme la SP : SEP et balcons étaient coplanaires et se disputaient la profondeur.

### Correctif du 28.10.2026 : altitude des niveaux, dalles fermées

- **Altitude** : chaque surface était posée à la base de son IfcSpace, et les totaux à l'altitude du niveau IFC. Au S01 de Myonaz 2, cela donnait trois altitudes (escalier à 610,20, pièces à 611,40, SP à 612,04). Toutes les surfaces d'un niveau sont désormais posées au sol de la plupart de ses pièces (`Level.z` : altitude de base la plus fréquente, pondérée par l'aire ; à défaut, celle du niveau IFC). La hauteur d'étage (SFN, GrossHeight) est l'écart au niveau suivant : 3,60 m au S01 de Myonaz 2 au lieu de 2,96.
- **Visionneuse** : les dalles ont maintenant un dessous. Vues d'en dessous, elles étaient ouvertes et laissaient voir la triangulation de leur dessus.
