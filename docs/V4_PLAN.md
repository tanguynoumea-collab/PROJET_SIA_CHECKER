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

## 15. Phase 23 livrée (28.10.2026) : logements et chaîne USPI

### Modèle Treegram reproduit (relevé sur L'Orée, 314 logements)

| Code | Treegram | Moteur (`generation/uspi.py`) |
|---|---|---|
| SNH | somme des SUP du logement (au millième) | idem ; `Bedrooms` = pièces de type Chambre |
| SHA | SNH + cloisons (SHA / SNH ≈ 1,02) | contour intérieur dessiné du logement (Myonaz : `LOG`, « Surface utile principal »), sinon SUP fermées sur 0,2 m, gaines exclues |
| SBH | un contour par logement, murs extérieurs et mitoyens (SBH / SHA ≈ 1,16) | contour brut dessiné du logement (La Bâtie : « 3P », « 4P »), sinon croissance des logements et des communs dans les murs (mitoyens partagés), bornée par le contour brut du niveau s'il existe (Myonaz : `LOG` « SBH »), sinon par la SP |
| SVN, SVB | SHA + SEU, SBH + SEU (au centième) | idem |
| totaux | SNH = SUP + SUS du niveau ; les autres = somme des logements | idem |

Les contours dessinés prennent leur aire déclarée, comme les pièces (Myonaz N03, combles). Un lot sans SUP (caves du sous-sol) n'a pas de chaîne USPI.

**Logement d'une pièce, La Bâtie** : le numéro d'appartement ne suffit pas, il faut la cage d'escalier (`with` dans `config.yaml > generation.lot`) : 4, 5 puis 6 logements par niveau, comme le MDP (avant : 2 ou 3).

### Comparaison aux MDP

| Projet | Logements, chambres | SHA (le MDP l'appelle SVN) | SBH par niveau |
|---|---|---|---|
| Myonaz 1 | 8 / 8 | identique sur les 8 logements | 181,0 / 181,0 · 223,5 / 224,0 · 223,5 / 224,0 · 186,4 / 186,7 |
| Myonaz 2 | 16 (+1 pièce égarée) | identique du N00 au N02, sauf 2B.00.01 ; écarts au N03 (duplex ?) | −0,3 % à −0,4 % du N00 au N02 ; N03 +4,5 % |
| La Bâtie B | 32 / 32, chambres identiques (19 × 1, 6 × 2, 7 × 3) | pas d'USPI au MDP | pas d'USPI au MDP |

Les règles USPI de la Fiabilisation (U1 à U4) passent sur les trois projets. Le sujet « Typologies des logements » s'ouvre de lui-même, avec les chambres générées.

### Points à contrôler

1. **SNH du niveau = SUP + SUS** (sous-sol : SNH = SUS), comme Treegram. Le ratio SNH / SP en tient compte.
2. **Myonaz 2, N03** : 2A.03.01 et 2B.03.01 valent tous deux 104,6 m² au MDP. Ce sont peut-être des duplex, que la maquette répartit autrement. Il y a aussi une pièce de 2,2 m² portant un numéro de logement à part (2B.03.02).
3. **SE non pondérées** : SVN et SVB ajoutent les SEU à 100 %, comme Treegram. L'USPI pondère les surfaces externes.

## 16. Phase 24 livrée (28.10.2026) : analyse IA du classement

### Chaîne

1. **Questions** (`sia-check --questions-ia <projet généré>`, `generation/ia.py`) : seuls les espaces où les règles hésitent partent (confiance < 0,8, sources en désaccord, aucune source), du plus douteux au moins douteux, 300 au plus. Chaque question porte des preuves compactes : noms, propriétés de classement, aire, logement et ses autres pièces, voisins (espaces à moins de 0,35 m, du plus long contact au plus court, désormais dans `rapport.json`), décision des règles et désaccords. Sortie : `generation/questions-ia.json` et `generation/prompt-ia.json` (system + user + sortie attendue).
2. **Appel** (app, `AiGenerationService`) : estimation du coût (comptage des jetons par l'API), accord de l'utilisateur, appel en flux avec la clé chiffrée DPAPI, comme la revue IA. La réponse brute et sa consommation vont dans `generation/reponse-ia.txt` et `reponse-ia.json`. Point d'entrée provisoire : `SiaCheck.Viewer.exe --analyse-ia-generation <projet généré>` ; la section Génération (phase 25) le remplacera.
3. **Réponse** (`sia-check --reponse-ia`) : chaque décision devient une proposition du journal `generation/decisions.json` (`generation/journal.py`), ou une « confirmée » si l'IA garde le classement des règles. Une clé inventée ou un code hors liste est écarté ; un sous-type hors liste prend le premier du code. Synthèse dans `generation/synthese-ia.md`.
4. **Décision** (`--accepter-ia` / `--rejeter-ia`, toutes ou `--ids` ; la phase 25 le fera à l'écran) : à chaque génération, les décisions acceptées remplacent le classement des règles (source « ia » ou « manuel », confiance 1), et l'espace n'est plus jamais redemandé. Une décision acceptée, rejetée ou manuelle n'est jamais écrasée par une nouvelle proposition.

Le prompt rappelle les codes et sous-types Treegram et les conventions relevées : dégagements et réduits de logement en SUP Distribution, pièces d'eau par nombre de points d'eau, propriété SIA de l'architecte comme preuve forte, SUT hors logement, entrées couvertes en SEU.

### Questions par projet

| Projet | Questions | Exemples |
|---|---|---|
| La Bâtie B | 38 | balcons « BAL », entrées « ENT », une circulation « CIR » classée SUS par la catégorie de l'architecte |
| Myonaz 1 / 2 | 2 / 7 | réduits de logement (SUP par convention, SUS par la catégorie) |
| Afiro | 39 | bureaux et salles notés SUP par l'architecte, SUT par le nom |
| CGA L04 | 4 | locaux « SUS_ELE » (SUS par le préfixe, SI par le nom), un WC compté pièce de vie |

Coût estimé avec Claude Opus 5.5 : de 0,05 à 0,30 $ par projet.

### Premier appel réel (Afiro, 28.10.2026)

39 questions, 39 propositions (19 sûres, 18 probables, 2 incertaines) pour 0,28 $ (23 606 jetons en entrée, 9 153 en sortie). L'IA a relevé qu'Afiro n'a aucun logement : la SUP écrite par l'architecte, au sens de la SIA 416, est de la SUT chez Treegram, dont les sous-types SUP sont ceux du logement. Les 19 propositions sûres ont été acceptées.

**Décision du 28.10.2026, devenue une règle du moteur** (`classify.without_flats`, `config.yaml > generation.classify.sut_without_flats`) : dans un bâtiment sans aucune pièce de logement, la SUP devient SUT (type Commerce), et les sanitaires deviennent SUS. Afiro : 71 pièces reclassées, plus de SUP. Il ne reste que 20 questions à poser à l'IA. Les bâtiments avec logements ne changent pas.

## 17. Phase 25 livrée (28.10.2026) : section Génération de l'app

Plan de design : `docs/DESIGN_PLAN.md`, Évolution 4.0 (validée le 28.10.2026).

- **Accueil en trois colonnes** : Génération, Fiabilisation, Benchmark, dans l'ordre du travail. « Générer depuis un IFC… » demande la maquette, puis le nom du projet et son dossier, et montre les étapes du moteur. La liste des projets générés est lue dans `Documents\SIA Check - projets generes` (réglable), avec l'état de la décision (« 20 à trancher », « tout tranché ») et ↻ Régénérer.
- **Un projet généré s'ouvre dans l'espace de revue existant**, qui gagne :
  - **l'onglet Espaces** (Ctrl+3). On y voit les espaces les plus douteux d'abord, avec un filtre (*À trancher*, *Proposés par l'IA*, *Décidés*, *Tous*) et le changement en pastilles SIA `(SUS)→(SUT)`. Le détail montre ce que disent les règles, l'IA et les voisins. On peut accepter ou rejeter une proposition (A / R), ou enregistrer son propre choix de code et de type. L'analyse IA se lance de là, avec l'estimation du coût et l'accord avant l'appel. Un clic sur une ligne isole l'espace en 3D.
  - **un bouton Régénérer** : les décisions acceptées sont appliquées, puis le projet est analysé. Un bandeau compte les décisions en attente, et leurs surfaces prennent déjà leur couleur cible en 3D.
  - **un calque « Maquette IFC »** (groupe Contexte) : murs, dalles, toits et poteaux en gris translucide.
- **Moteur** :
  - `--generer` écrit les lignes « ÉTAPE n/N » et `generation/maquette.json` ;
  - `rapport.json` relie chaque espace à sa surface (`surface`) ;
  - `--decider --ids --code [--type]` enregistre une décision manuelle, qui remplace toute proposition sur l'espace.
- **Empaquetage** (`app\build.ps1`) : `ifcopenshell` est désormais embarqué dans le moteur, avec les modules de génération. Le moteur figé lit une maquette IFC (vérifié sur CGA L04) et pèse 220 Mo.

Reste pour la phase 26 (clôture V4.0) :
- un essai complet dans l'app installée ;
- le changelog et la version ;
- la mise à jour du README ;
- la publication, si l'utilisateur la demande.

## 18. Retours de l'utilisateur sur le moteur (28.10.2026)

| Remarque | Correction |
|---|---|
| La SRV ne compte que les vitrages extérieurs | Une ouverture est de façade si elle est posée sur le contour de la SP, sauf si la maquette la dit intérieure (`IsExternal` faux). Myonaz 1 : 6 fenêtres intérieures écartées. La SRV ne compte que les fenêtres et les portes vitrées (nom ou type : `generation.envelope.glazed_doors`). Les portes pleines (entrée, garage, caves) restent des réservations : La Bâtie, SRV d'un étage courant 156,65 m² (MDP 156,6). La règle E2 (vitrages ≠ réservations, info) le signale, comme prévu pour les portes pleines. |
| La SFN doit avoir les trous des ouvertures | Le maillage de la façade est percé des réservations, côté par côté de la SP. Une ouverture ne compte que pour sa part comprise dans la hauteur d'étage, puisque la plupart des fenêtres commencent 13 cm sous le sol fini. Écart de rendu restant : de 0 à 5 % d'aire de maillage en trop, quand une fenêtre déborde à l'angle d'un côté. Les chiffres (SFN brute, nette, réservations) sont exacts. |
| Sous-type « SUS » partout, aucun parking | Les SUS prennent le sous-type de leur affectation MDP : Parking, Cave, Buanderie, LocalVelos, LocalPoussettes, LocalConcierge, Depot, Sanitaires, et LocauxCommuns à défaut (`mdp.affectation` les traduit pour l'export). Les abréviations des maquettes sont reconnues : « VOI », « MOT », « POU », « SUS_VOI ». Une circulation que l'architecte compte en SUS (« CIR ») est la voie du parking. Le sous-type est cherché parmi les entrées du code retenu. Introuvable dans le nom, il part à l'analyse IA. La Bâtie : 53 Parking (1 197 m², comme le MDP : 48 places, 4 motos, la voie), 32 Cave, 2 Buanderie, 2 LocalPoussettes. CGA : 13 558 m² de Parking. Afiro : le garage de 27 places en Parking, les vestiaires en Sanitaires. Une décision IA acceptée avec l'ancien type « SUS » reprend le sous-type déduit du nom. |
| Paliers contenant l'escalier tous en CirculationH | La part d'un espace SD occupée par un IfcStair devient une surface SD « Escalier », le reste reste palier (`interiors.split_stairs`, `generation.stairs.min_m2`). Myonaz 1 et 2 : 1 ou 2 cages par niveau au lieu d'aucune. La Bâtie : 2 cages au rez (hall « ENT »). La comparaison au MDP compte les deux parts comme un seul local. |
| Lots et sous-types manquants | Vérifié sur les cinq projets : toutes les SUP sont dans un lot, et toutes les pièces ont un sous-type. La Bâtie : 509 surfaces sur 611 portent un lot dans la visionneuse ; celles sans lot sont les communs (SD, SI, SUS), comme chez Treegram. Les 160 surfaces « sans sous-type » sont les surfaces USPI des 32 logements, qui n'en ont pas chez Treegram non plus. Afiro et CGA n'ont pas de logement. **À préciser avec l'utilisateur** : le projet et les surfaces concernés. |

## 19. Clôture de la V4.0 (28.10.2026)

Version 4.0.0 (`src/sia_check/__init__.py`, `pyproject.toml`, `SiaCheck.Viewer.csproj`), tag local `v4.0.0`. Installeur : `app\dist\SiaCheckViewer-4.0.0-setup.exe`. Le moteur embarqué (220 Mo avec `ifcopenshell`) analyse L'Orée et génère CGA L04 depuis son IFC. Tests : 284 Python, 135 .NET.

**Livré** : tout l'arbre Treegram généré depuis une maquette architecte IFC, au format `.siagen.json`, que la Fiabilisation et le benchmark lisent sans changement.
- Surfaces intérieures, avec les cages d'escalier séparées des paliers.
- Extérieurs, toitures, façade percée et vitrages extérieurs.
- Logements et chaîne USPI.
- Analyse IA des seuls espaces douteux, avec un journal des décisions (IA et manuelles).
- Section Génération de l'app : accueil, onglet Espaces, Régénérer, calque Maquette IFC.

**Validation sur les maquettes ARC des projets de la base** (pas de paire IFC ↔ `.tgm` disponible) :
- Myonaz 1 et 2 : 100 % des locaux au même code que le MDP, SHA et SBH par niveau identiques au MDP ;
- La Bâtie B : 99 % des locaux au même code ; logements, chambres, SEU, vitrages et parkings conformes au MDP ;
- Afiro : premier appel IA réel (0,28 $), qui a donné la règle « bâtiment sans logement : SUP → SUT ».

**Reste ouvert** :
- Façade : le MDP de La Bâtie est 10 % plus long que le périmètre de la SP, et compte une façade au niveau toiture.
- Myonaz 2, N03 : logements en duplex à confirmer.
- Lots et sous-types « manquants » signalés par l'utilisateur : rien trouvé dans les données (§18), à préciser sur un cas.
- SE non pondérées dans SVN / SVB, comme Treegram.
- Une paire de référence IFC ↔ `.tgm` reste souhaitable pour comparer à Treegram lui-même.
- Le moteur pèse 220 Mo (`ifcopenshell`).

## 20. Retour de l'utilisateur sur CGA L04 (28.10.2026) : ouvertures sans menuiserie

**Remarque** : la SFN doit déduire toutes les ouvertures, pas seulement les vitrages. Une baie ou une porte percée dans la façade ne compte pas en SFN.

**Constat** : CGA L04 n'a aucune IfcWindow. Ses baies sont 69 percements sans menuiserie (IfcOpeningElement) : 37 dans des murs extérieurs, 32 dans le bardage (« M_Ext-007 »), souvent au même endroit que ceux du mur. Le moteur les ignorait, d'où 0 m² de réservations au N00 et au N01.

**Correction** :
- `ingest.py` lit les percements sans menuiserie d'un mur, d'un bardage ou d'un mur-rideau (`generation.ingest.voids`). Chacun prend le niveau, le bâtiment et l'`IsExternal` de l'élément percé.
- `exteriors.py` les compte en réservations de façade : ils sont déduits de la SFN et percés dans son maillage, sans entrer dans la SRV. La largeur d'une ouverture est maintenant mesurée dans le sens de la façade.
- Une même baie percée deux fois (bardage et mur, garde-corps modélisés deux fois) ne compte qu'une fois. Il faut pour cela que les deux ouvertures soient parallèles, à moins de 0,6 m, et se recouvrent vues de face. Deux fenêtres d'angle restent deux baies.

| CGA L04 | Réservations avant | Réservations après | SFN nette après |
|---|---|---|---|
| S02 | 44,4 | 87,3 | 1 013,0 |
| S01 | 76,9 | 62,4 (doublons retirés) | 1 012,3 |
| N00 | 0,0 | 21,2 | 1 050,8 |
| N01 | 0,0 | 31,1 | 1 134,9 |
| N02 | 2,8 | 8,7 | 1 348,1 |

Non-régression :
- La Bâtie : SRV de 156,65 m² à chaque étage courant, comme le MDP.
- Myonaz 1 : inchangé.
- Le maillage de la SFN égale la SFN nette à 1 % près, sauf aux angles (jusqu'à 2 %).

## 21. Retours de l'utilisateur sur CGA L04 (28.10.2026) : typologie, poteaux, rampes

| Remarque | Correction |
|---|---|
| Les repères des ratios n'ont de sens que pour un type de bâtiment ; CGA est un parking. Vaut aussi pour les projets Treegram | Les repères de `config.yaml` (établis sur les projets de logement de la base) ne valent que pour les typologies Logement et Logement mixte (`typologies` d'un ratio, `refs` pour d'autres). La typologie de la fiche projet part au moteur (`--typologie`, analyse et aperçu). Sans typologie, le ratio garde sa valeur, et son statut est « typologie » (« typologie ? » dans la colonne Repère) ; pour une autre typologie, il est « sans repère ». Le moteur propose une typologie d'après les surfaces (`ratios.suggest`) : CGA, « Autre (parking : 98 % de la SU) » ; La Bâtie, « Logement ». L'onglet Ratios le dit, avec « Renseigner la typologie » (fiche projet, proposition présélectionnée). « Analyser » la demande une fois par projet et par session tant qu'elle manque. |
| Les poteaux ne sont pas déduits | Au sens de la SIA 416, un poteau est de la construction (SC) : l'emprise des IfcColumn est retirée de la pièce qui les contient, en géométrie et en aire (`interiors.without_columns`). CGA : −17 m² de parking (44 poteaux par niveau, que Revit n'avait pas exclus). |
| Percements étranges après les ouvertures des rampes | Les garde-corps des rampes de CGA sont des IfcDoor (« Type de garde-corps »). Ils ne sont plus des ouvertures (`envelope.not_openings`). CGA S01 : réservations de 62,4 à 26,0 m². |
| Décroché du sol au S01, aux portes desservies par une rampe PMR (posée sur la dalle, sans décroché réel) | Le mur est évidé à l'ouverture : le contour SP (pièces + murs) rentrait dans la baie, et la façade suivait ce retrait, d'où un ressaut apparent sous la porte. Les baies des portes et fenêtres (l'ouverture prise dans l'enveloppe convexe des murs voisins, garde-corps exclus) font partie de la SP (`interiors.bays`). CGA : +1,4 m² de SP par niveau, façade d'un seul tenant ; La Bâtie : +0,1 m² ; Myonaz et Afiro inchangés. |

## 22. Toitures en pente (Myonaz 2, 29.10.2026)

| Remarque | Correction (`roofs.py`) |
|---|---|
| La SPT est calculée à plat sous une toiture à deux pans | La SPT est la surface développée : chaque morceau de toiture (IfcRoof, IfcSlab ROOF, plus de 5 m² en plan) compte son emprise au rapport de ses faces de dessus à leur projection, quel que soit le nombre de couches. Elle est drapée sur la couverture dans la vue 3D, et la SEP la compte de même. Myonaz 2 : 469,9 → 546,1 m² (pente de 32°) ; Myonaz 1 : 247,7 → 275,7 m². |
| La SFN ignore la toiture : murets de rive plus bas, pignons | Au dernier niveau occupé, la façade monte jusqu'à la sous-face de la toiture, là où aucun niveau ne la recouvre : plus bas aux rives, en pointe dans les pignons, et jusqu'au haut des fenêtres de lucarne. La sous-face est cherchée jusqu'à 1,2 m à l'intérieur quand la toiture repose sur les murets sans déborder. Les pignons ne suivent que des sous-faces en pente (plus de 10°) : les toits plats ne changent pas. Myonaz 2 N03 : façade brute 288,8 → 261,5 m² ; Myonaz 1 N03 : 218,1 → 168,2 m². |
| Les fenêtres de toit sont projetées à la verticale ou ignorées | Une fenêtre inclinée de plus de 15° sur la verticale (velux), ou hors façade et au-dessus d'elle sous la toiture (fenêtres hautes des lucarnes), à moins de 2,5 m sous la couverture, n'est ni une réservation ni de la façade. C'est un vitrage SRV du dernier niveau, à son aire vraie, dessiné dans son plan. Les fenêtres de lucarne que la maquette range dans le niveau de toiture comptent dans la façade du niveau dont elles percent la hauteur. Myonaz 2 N03 : SRV 108,1 → 120,6 m², dont 7,8 m² de fenêtres de toit. Une fenêtre déclarée intérieure (`IsExternal` faux, MOB-0010) reste écartée. |


**Simplification (retour du 29.10.2026, avant clôture de la V4.1)** : SPT et façades « biscornues » sur Myonaz 2, « piliers » sous la toiture de La Bâtie.

- **Causes** :
  - la SPT était drapée sur la plus haute face de dessus de toute la maquette :
    - les lucarnes, souches et faîtières y faisaient des bosses ;
    - un point hors couverture retombait au niveau, d'où les dents à la rive ;
    - La Bâtie : la marquise du rez, 15 m plus bas, faisait descendre la toiture plate jusqu'à elle ;
  - la façade suivait une sous-face faite de plusieurs couches, de chéneaux et de lucarnes, d'où les dents et les marches.
- **Pans principaux** (`roofs.py`) :
  - seules les orientations de faces qui portent au moins 10 % de l'aire de la toiture sont des pans ;
  - chaque pan est ramené à un plan, sa couche la plus haute : la couverture ;
  - sous une lucarne ou à la rive, le plan du pan le plus proche est prolongé, jusqu'à 3 m.
- **SPT** :
  - drapée sur ces pans, sans les toitures plus basses de plus de 3 m que le niveau de toiture (marquise, auvent) ;
  - une toiture plate, dont la surface développée dépasse l'emprise de moins de 1 %, est dessinée à plat ;
  - la surface développée ne change pas (Myonaz 2 : 546,1 m²).
- **SFN** :
  - la façade monte jusqu'à la couverture en pente, la même surface que la SPT : façade et toiture se rejoignent sans jour ;
  - une toiture plate ne la touche pas : La Bâtie garde 321,5 m² au dernier étage ;
  - une lucarne ne fait plus monter la façade ;
  - Myonaz 2 N03 : 261,5 → 222,3 m² ; Myonaz 1 N03 : 168,2 → 145,4 m².
- **SRV** :
  - une fenêtre au-dessus de la rive pour plus de moitié (lucarne) est une fenêtre de toit : vitrage SRV dans son plan ;
  - une fenêtre à cheval sur la rive compte en façade pour sa part sous la rive ;
  - Myonaz 2 N03 : SRV 120,6 → 121,1 m².
- **Tests** : la marquise sous une toiture plate, et la lucarne sur un pan.

**Fenêtres de toit dans leur ébrasement (retour du 29.10.2026)** : sur Myonaz 2, des vasistas encastrés (« Luc », types FT01, FT02, ST01) étaient dessinés debout comme des baies.

- **Cause** : la maquette les modélise avec leur ébrasement, des joues verticales jusqu'au plafond. Ces joues ont plus d'aire que la vitre, et l'orientation retenue était celle des plus grandes faces.
- **Correction** (`roofs.window_panel`) :
  - sous la toiture, une fenêtre dont des faces sont parallèles au pan est une fenêtre de toit. Il faut au moins 0,3 m² de ces faces, et au moins 30 % de sa silhouette verticale ;
  - sa vitre est faite de ces faces : aire vraie, dessinée dans le pan ;
  - une porte-fenêtre de pignon dont le linteau suit la pente n'en est pas une : ce chant ne fait que 15 % de sa silhouette.
- **Myonaz 2 N03** :
  - fenêtres de toit : 7,8 → 34,3 m² ;
  - réservations de façade : 85,0 m² ;
  - SRV : 121,1 → 119,3 m², les vitres comptées à leur aire vraie.
- **Myonaz 1 N03** : 16,8 m² de fenêtres de toit.
- **La Bâtie** : inchangée.
- **Test** : fenêtre de toit entourée de joues plus grandes que sa vitre.

**Taille et trou des fenêtres de toit (retour du 29.10.2026)** : des vasistas étaient plus grands que dans l'IFC et débordaient sur le côté ; la toiture n'était pas percée au droit des vasistas.

- **Cause** : la vitre réunissait toutes les faces parallèles au pan, dont le fond de l'ébrasement. Ce fond est 0,57 m plus bas et plus long que la fenêtre : FT02 était dessinée sur 2,83 m pour une fenêtre de 1,44 m.
- **Correction** :
  - la vitre est la couche de faces parallèles la plus chargée en aire, avec son cadre (5 cm) ;
  - son rectangle donne l'aire et le dessin : FT02 1,20 m², FT01 1,01 m², ST01 0,27 m² (minimum ramené à 0,15 m²) ;
  - la SPT drapée est percée au droit de chaque fenêtre de toit, comme la façade de ses ouvertures. Son aire reste brute (546,1 m²).
- **Myonaz 2 N03** : fenêtres de toit 34,8 m², SRV 119,9 m².
- **Test** : fond d'ébrasement plus long que la vitre, trou dans la SPT.

**Vitres qui dépassent du toit (retour du 30.10.2026)** : des vitrages sortaient encore de la toiture sur Myonaz 2. Deux cas :

- **Portes-fenêtres de pignon** (FS01, FS02) dont le linteau suit la pente. Elles étaient dessinées en rectangle, à la hauteur de façade lue en leur centre : le côté bas dépassait d'au plus 1,15 m, le côté haut était tronqué.
  - Correction : sous une toiture, chaque ouverture est rognée au contour de la façade, côté par côté (`_facade`). Le vitrage dessiné et l'aire (réservations, SRV) ne gardent que la part dans la façade.
  - Sous un pignon, l'ouverture va jusqu'en haut si la façade dépasse l'étage sur sa largeur (et non en son seul centre).
- **Fenêtres de lucarne** (FB09, FB12), verticales, comptées en fenêtres de toit. La lucarne n'est pas dans la toiture simplifiée : debout, la vitre en dépassait.
  - Correction : elle est couchée dans le pan sous elle, à la même aire (même largeur, le long de la pente).
- **Toutes les fenêtres de toit** sont posées à fleur de la couverture, dans le trou de la SPT. Avant, la vitre d'un vasistas flottait 12 à 14 cm au-dessus.
- **Myonaz 2 N03** : réservations 82,6 m², SRV 117,5 m², dont 34,8 m² de fenêtres de toit.
- **Myonaz 1 N03** : SRV 62,4 m².
- **Contrôle** : aucun triangle de vitrage au-dessus du toit sur Myonaz 1 et 2.
- **Test** : porte-fenêtre de pignon rognée à la pente.

## 23. Publication de la 4.0.0 (29.10.2026)

Le tag `v4.0.0` est posé sur l'état final, avec les retours des §20 à §22 :
- ouvertures sans menuiserie déduites de la SFN ;
- repères des ratios selon la typologie, poteaux déduits, garde-corps écartés ;
- baies des portes et fenêtres comprises dans la SP ;
- sanitaires reconnus au nom dans un bâtiment sans logement ;
- toitures en pente.

C'est la première publication de la V4 : release GitHub « SIA Check Viewer 4.0.0 », avec l'installeur. Tests : 291 Python.

## 24. Feuille de route V4.1 (demandes de l'utilisateur du 29.10.2026)

1. ☑ **Couleurs des surfaces USPI** (livré le 29.10.2026, DESIGN_PLAN Évolution 4.2 : rampe pétrole, vente hachurée, chaîne empilée en 3D). SNH, SH, SBH, SVN et SVB sont aujourd'hui toutes grises dans la vue 3D et les calques. On ne peut donc pas les contrôler. Il faut une teinte par code, distincte des codes SIA 416, lisible en clair et en sombre, et la même dans la légende, les infobulles et les exports. Le travail passe par une évolution du DESIGN_PLAN, sur les tokens de la famille USPI.
2. ☑ **Ratios du Dashboard : séparer SIA 416 et USPI** (livré le 29.10.2026, DESIGN_PLAN Évolution 4.3 : quatre groupes, SIA 416, USPI 2014, Enveloppe et Programme, dans l'onglet Ratios et le Dashboard).
   - Dans l'onglet Ratios du bilan, puis dans le benchmark, les ratios SIA 416 et les ratios USPI sont aujourd'hui mêlés.
   - Il faut deux groupes visuellement distincts, chacun avec un titre et une courte définition, dans le même ordre partout.
   - Les ratios d'enveloppe (SFN, SRV, SPT) forment un troisième groupe, ou restent avec les ratios SIA. C'est à trancher dans le plan de design.
3. ☑ **Compléter les classifications manquantes des projets générés** (relevé et décisions de l'utilisateur du 29.10.2026). Avant : 93 espaces à confirmer ou au sous-type par défaut sur les cinq projets. Après : 2, à Afiro, reconnus seulement à leur nom et corrects (STOCKAGE BASE en SUS Depot, BUREAU TECHNIQUE en SI Local).
   - **Sans logement**, le nom l'emporte sur la SUP de l'architecte quand il dit SUS, SD ou SI (`name_wins_without_flats`). Afiro : 13 stockages, dépôts et archives passent en SUS Depot, 4 circulations, SAS et cage en SD, la technique cuisine en SI. Les propositions IA contraires sont rejetées, et les 4 conformes acceptées.
   - **Un local technique préfixé ou catégorisé SUS est une SI** (`technical_over_sus`) : CGA SUS_ELE_MICROGRID et SUS_ELE_CFA, La Bâtie CVC.
   - **Abréviations des parties communes** : CON = conteneurs (SUS Depot, CGA et La Bâtie), « G » = garage à vélos (SUS LocalVelos, La Bâtie), ESC extérieur = escalier extérieur (SED CirculationExt, La Bâtie S01).
   - **Myonaz 2, S01** : « Couloir/stockage abri PC » reste en SD, sa catégorie Revit faisant foi. C'est une décision manuelle du journal.
   - **Règles validées qui ne remontent plus en « à trancher »** :
     - noms d'extérieurs (BAL, ENT, ESC) ;
     - conventions Treegram vérifiées sur les MDP (réduits et dégagements d'un logement en SUP) ;
     - nom compatible avec le code retenu (« CIR » au parking) ;
     - sanitaire confirmé par son nom.
   - Le conflit périmé « sous-type SUS par défaut » des réduits en SUP est retiré.
   - Il faut relever, projet par projet, les espaces encore douteux ou sans sous-type : la liste « À trancher » de l'onglet Espaces, les SUS sans affectation et les lots incomplets.
   - On les tranche avec l'utilisateur, en séance si besoin. Chaque décision passe par le journal (`decisions.json`), et les règles générales vont dans `config.yaml`.
4. ☑ **Le gros morceau : calculer les surfaces déduites, SC et SEC, depuis l'IFC** (livré le 29.10.2026, `generation/construction.py`, DESIGN_PLAN Évolution 4.4).
   - **SCP** : murs porteurs (`LoadBearing`) et poteaux. **SCN** : autres murs et murs-rideaux, plus les bandes de moins de 0,6 m entre les pièces et les murs. Les baies vont avec le mur qu'elles percent.
   - **SC** : sur un niveau sans aucun mur modélisé, toutes les bandes (Afiro).
   - **SECP / SECN** : garde-corps, murets et bandes minces autour des extérieurs.
   - L'écart entre emprise et aire déclarée des pièces est reporté sur la SCN, comme dans les MDP où il tombe dans la SC implicite. Par exemple, Myonaz N03 compte 18 et 28 m² sous les rampants.
   - La construction n'est pas exportée vers les MDP ni vers le format Treegram (`treegram.CONSTRUCTION`).
   - **Résultat sur les cinq projets** : R1 et R3 sont équilibrés à quelques centièmes près, sauf deux vraies zones non classées, aujourd'hui seules en erreur.
     - Myonaz 1, N00 : 32,3 m² de SP dans la « Surface de plancher » dessinée, sans pièce.
     - Myonaz 2, N00 : 13,3 m² de SEP sans extérieur.
   - Avant, elles se perdaient dans 30 à 140 m² de résidu « construction implicite » par niveau.
   - **Les deux zones vues avec l'utilisateur (29.10.2026)** :
     - **Myonaz 1, N00** : un local fermé à l'angle, desservi par une porte de garage et sans IfcSpace, absent aussi du MDP. C'est la règle générale des **espaces déduits** (`construction.deduce`) : une zone de SP non classée de plus de 2 m² devient un espace « Zone sans espace », en SUS (Parking si une porte de garage la dessert, sinon LocauxCommuns). Une zone de SEP devient une SEU Terrasse. La confiance est de 0,5, donc l'espace est toujours à trancher dans l'onglet Espaces. Son identifiant (`deduit-…`) ne dépend que de sa position : une décision du journal le suit d'une génération à l'autre.
     - **Myonaz 2, N00** : la « Surface externe de plancher » de l'architecte recouvre les deux entrées d'immeuble (SD). Désormais, un extérieur couvert à plus de moitié par des pièces ne sort pas de la SP, et un contour SEP ne compte que hors de la SP (`interiors.ROOM_WINS`). L'entrée reste en SD, comme le « Hall immeuble » du MDP.
   - Après ces deux règles, R1 et R3 sont équilibrés sur les cinq projets.
   - **SC (surface de construction, SIA 416 §2.2) :** la SP moins la SN. Elle comprend les murs porteurs et non porteurs, les poteaux, les gaines non accessibles et les parties de murs dans les embrasures. Le moteur la calcule aujourd'hui par différence.
   - **SEC (surface de construction externe) :** l'équivalent pour les surfaces externes, c'est-à-dire la SEP moins la SEN. On y trouve les garde-corps maçonnés, les murs de loggia et les acrotères.
   - **Calcul :** les identifier et les modéliser comme des surfaces à part entière, avec leur propre géométrie. Les sources sont les emprises des IfcWall, IfcColumn, IfcCurtainWall et IfcRailing pleins, et les dalles de balcon hors espaces.
   - **Objectif :** que SN + SC recolle à la SP, et SEN + SEC à la SEP. Ce qui reste non couvert révèle les vraies zones de SP ou de SEP non catégorisées : un espace oublié par l'architecte, une loggia non dessinée, une trémie. Ces zones deviennent des surfaces « à classer », visibles en 3D et proposées à la classification (règles, IA ou manuel).
   - **Vérification :** comparer aux SC et SEC des MDP de la base (Myonaz, La Bâtie) et vérifier qu'aucune surface n'est comptée deux fois.

## 25. Publication de la 4.1.0 (30.10.2026)

Le tag `v4.1.0` est posé sur l'état final de la feuille de route du §24 (les quatre points sont livrés), avec en plus :
- l'accueil « Minage de données » (DESIGN_PLAN Évolutions 4.5 à 4.8) ;
- les retours sur les toitures et les fenêtres de toit (§22).

Release GitHub « SIA Check Viewer 4.1.0 », avec l'installeur. Tests : 301 Python, 140 .NET.

## 26. Données manquantes des projets (30.10.2026)

- **Fiches des projets générés** (réglages de l'app), d'après les IFC et les MDP de la base :
  - La Myonaz 1 et 2 : 1712, Logement, VD, Oron ;
  - La Bâtie B : 1467, Logement, GE, Petit-Lancy ;
  - Côté Gare L04 : 1023, Autre (parking silo), VD, Bussigny ;
  - Afiro – Ateliers protégés : 1724, Activités, VD, Ecublens ;
  - tous en nouvelle construction, phase 31, sur décision de l'utilisateur.
- **Base** : phase 31 écrite dans les MDP du Clos des Hêtres, des Patios, d'Avallons et de Sauvabelines.
- **En attente** :
  - canton, commune, catégorie et intervention des Patios (1280), d'Avallons (1746) et de Sauvabelines (1784) ;
  - le canton de Côté Gare (VS dans le MDP, alors que Bussigny est vaudoise).
- **Benchmark** (`benchmark._sans_logement`) : pour une catégorie d'ouvrage renseignée sans logement, la liste des logements, les chambres et la SVN sont sans objet. Les contrôles sont réussis, avec la mention. CGA L04 et Afiro passent de 0,6 à 0,9.
- **Reste hors de la plage 8–30 % de SC / SP** :
  - CGA L04 (5 %) : un parking silo ouvert, plausible ;
  - Afiro (3 %) : l'IFC n'exporte que les pièces (« ALO_PIECES », aucun mur). Il faut une maquette avec ses murs.
- **Non comblées** : les surfaces manquantes de la base (SP brutes, logements, chambres, SVN, enveloppe). Les projets générés n'en sont que des parties : Myonaz 1 + 2 font 3 274 m² de SP pour 7 004 m² au MDP 1712, La Bâtie B 4 516 m² pour 8 178 m² au MDP 1467.
