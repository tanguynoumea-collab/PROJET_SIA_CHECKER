# V2_PLAN — Corrections et export MDP

> Statut : ☑ Brouillon · ☑ Validé par l'utilisateur (22.10.2026)
> Version : 0.2 — 22.10.2026 · phases 0 à 6 livrées

## 1. Objectif

Aujourd'hui : export Excel Treegram → contrôle dans Treegram → corrections à la main dans l'Excel → copier-coller dans le tableau MDP HRS. La V2 fait tout dans l'outil :

1. répertorier les sujets, proposer une correction par sujet, l'appliquer dans le projet (sans toucher au `.tgm`) ;
2. exporter les surfaces corrigées directement dans le gabarit MDP, **toutes feuilles remplies** ;
3. exporter, à côté du rapport d'analyse, un **Excel de correction** au gabarit Treegram, avec une colonne « correction » et une colonne « explication ».

Décisions prises (22.10.2026) :

| Question | Décision |
|---|---|
| Source des exports | Le `.tgm`, mis au gabarit des exports Excel Treegram |
| Correction partielle d'une surface (ex. la part de SEP sur l'emprise du sous-sol) | Un module de **tracé** des surfaces |
| Affectation (MDP) | Une proposition, à prendre ou non, avec une option « Inconnu » |
| Périmètre du MDP | Tout remplir |

## 2. Ce que les fichiers nous apprennent (L'Orée, 1778)

### Le lien `.tgm` ↔ Excel Treegram

- `ID TGM` = `H<conteneur>::H<élément>`, les deux entiers de l'en-tête d'enregistrement qui précède chaque sac (`tgm.Bag.tgm_id`). Sur L'Orée, toutes les surfaces SIA sont dans le conteneur 170. Vérifié sur les 3 221 + 160 lignes des deux exports : aucune absente. Le décodeur cherchait l'octet `aa` (170) en dur ; il lit désormais le conteneur, ce qui le rend valable pour d'autres projets.
- `Object.Name` (nettes) = l'identifiant de surface du moteur (`A01_N01_ShellByTgm-12_SpaceByTgm-1_SD`).
- Brutes : une ligne SP et une SEP par (bâtiment, niveau), avec `Perimeter` et `GrossHeight`, tous deux lus dans le `.tgm`.

### L'export Treegram est incomplet

| Catégorie | Dans le `.tgm` (feuilles) | Dans l'export Nettes |
|---|---:|---:|
| SUP, SUS, SD, SI, SEU | 3 221 | 3 221 |
| **SED** (coursives, `CirculationExt`) | 26 | **0** |
| **SUT** (commerces, `Commerce`) | 47 | **0** |
| SPT (toitures), USPI (SNH…SVB) | — | 0 (attendu) |

Le MDP actuel n'a donc ni les coursives ni les commerces. La V2 les inclut, en gardant le gabarit Treegram.

### Défauts du MDP 1778 dus au copier-coller

- 359 lignes `#REF!` en fin de `SurfacesNettesSIA416` (restes d'un collage plus long).
- `SurfacesBrutesVolumeSIA416` ligne 40 (G12 N00) : `ID Projet` saisi 1746 au lieu de la formule.
- 7 SEP renommées à la main `SEP-Toiture`.
- `SurfacesEnveloppe` : tableau croisé d'un autre projet (BAT A, B, C…).

### Correspondance MDP ← `.tgm`

| Feuille MDP | Colonnes | Source `.tgm` | Remarque |
|---|---|---|---|
| `SurfacesBrutesVolumeSIA416` | Catégorie, Partie d'ouvrage, Étage, Découpage, Périmètre, Hauteur brute, m², m³ (formule) | SP/SEP par niveau : `Area`, `Perimeter`, `GrossHeight` | Découpage : S → Sous-sol, N → Hors-sol, Toiture → Divers. Largeur et longueur globales : `DeltaX` / `DeltaY` de la SP (à confirmer) |
| `SurfacesNettesSIA416` | Catégorie, Partie d'ouvrage, Affectation, Étage, Appartement, N° local, Nom du local, m² | surfaces feuilles : `Area`, `Type`, `ApartmentByTgm`, `element_id` | Affectation : proposition (§5.3) |
| `SurfacesUSPI` | Catégorie USPI, Appartement, m² | SNH, SHA, SBH, SVN, SVB par lot ; SE = SVN − SH | Libellés de la liste `BD` |
| `ListeLogements` | Partie d'ouvrage, Étage, Appartement, nb chambres… | `ApartmentByTgm`, `Bedrooms` (sur SNH) | Pièces GE/VD : proposition calculée (convention de comptage à valider). Typologie, Exploitation, Gamme : proposition ou « Inconnu » |
| `SurfacesEnveloppe` | Partie de l'enveloppe, Partie d'ouvrage, Étage, Longueur, Hauteur, Surfaces brute / nette / vitrée | SFN par niveau : `Perimeter`, `GrossHeight`, `GrossArea`, `NetArea`, `ReservationsArea` (= vitrée : 413,66 − 307,87 = 105,79) ; SPT pour la toiture | Murs d'enceinte : pas de source identifiée |
| `InfosBatiment` | Étages hors-sol / sous-sol, cages d'escalier, forme, dimensions | comptages par bâtiment | Forme et type de cage : proposition ou « Inconnu » |
| `InfosProjet` | Comptages (bâtiments, étages, logements par nb de chambres, chambres, pièces) | calculés | Champs administratifs et constructifs (canton, phase, CVSE…) : saisis dans l'app, sinon laissés vides |
| `Documents`, `Listes formulaire` | — | — | inchangés |

### Contrainte d'écriture

Les listes déroulantes du MDP sont des validations au format Excel 2010 (`x14:dataValidation`), qu'openpyxl supprime. Le MDP est donc rempli **par réécriture des seules feuilles de données dans le zip** (`sheetData`, `ref` des tableaux), le reste du classeur étant recopié octet pour octet. Un test vérifie que les validations, le tableau croisé et les formules survivent à l'export.

## 3. Modèle de correction

Une **correction** est une opération sur des surfaces, jamais une modification du `.tgm`.

| Opération | Effet | Exemple |
|---|---|---|
| `reclasser` | change la catégorie SIA de surfaces | 26 SED absentes → restent SED ; un local SUP → SUS |
| `exclure` | sort des surfaces des sommes et des exports SIA (motif obligatoire) | SEP des niveaux Toiture (S2) |
| `découper` | crée, à partir d'un **tracé** (polygone), une nouvelle surface prise sur une surface existante, dans une autre catégorie ; l'aire d'origine diminue d'autant | SEP N00 sur l'emprise du sous-sol → SA (S1) |
| `ajuster` | fixe une aire à la main (dernier recours, sans tracé) | |
| `affecter` | renseigne l'Affectation MDP | `Commerce`, `Inconnu` |

Chaque correction porte : `id`, `sujet` (S1…), `origine` (`règle` / `ia` / `manuel`), `cible` (liste d'identifiants **ou** sélecteur : catégorie, bâtiment, niveau, type), `explication`, `statut` (`proposée` / `acceptée` / `rejetée`), auteur et date.

- **Journal par projet** : `%APPDATA%\SiaCheckViewer\corrections\<projet>.json`, à côté des statuts actuels. Une correction dont la cible a disparu dans une nouvelle livraison passe en « à revoir ».
- **Application** : le moteur reçoit le journal (`sia-check --corrections journal.json`), applique les corrections acceptées sur le DataFrame, puis relance les règles. Le bilan montre l'**avant/après**, et un niveau corrigé doit boucler.

## 4. Des points aux sujets

1. **Recommandation de base par règle** (`config.yaml > recommendations`) : A2 → `exclure` la SEP du niveau Toiture ; A1 → `découper` vers SA avec un tracé pré-calculé (SEP ∩ emprise du niveau inférieur, `preuves.py` le calcule déjà) ; R1 « SC implicite » → aucune action ; A3 → `reclasser` vers un code connu. Les points de même cause sont regroupés en sujets provisoires.
2. **La revue IA réoriente les sujets.** Le fichier de verdicts gagne, par sujet, une liste de corrections structurées (même schéma qu'au §3), validée par un schéma JSON. Elles **remplacent** la recommandation de base sur tous les points du sujet. Exemple : l'agent juge que toute la SEP de toiture sort, alors tous les A2 et R3 liés reçoivent `exclure` ; il juge qu'une terrasse d'attique reste en SEU, alors le point lié passe à « aucune action ». Un faux positif n'a pas de correction.
3. **L'utilisateur statue par sujet**, en un clic, ou point par point, et peut modifier la correction avant de l'accepter.

## 5. Interface (à concevoir avec Daedalus, mode Évolution, avant tout XAML)

### 5.1 Panneau Sujets
Remplace ou complète la liste des points : sujets avec leur correction proposée, l'origine (règle ou IA), l'impact en m², et les actions Accepter / Rejeter / Modifier. L'avant/après s'affiche dans le bilan par niveau.

### 5.2 Module de tracé
Vue en plan 2D d'un niveau, avec les surfaces aux couleurs SIA et, en fond, l'emprise du niveau inférieur.
- Tracé de polygone, accrochage aux sommets et aux arêtes des surfaces existantes, aire affichée en direct.
- Le polygone est découpé sur la surface source (intersection, shapely côté moteur) et l'opération `découper` est créée avec la catégorie cible.
- Les tracés pré-calculés (S1) s'ouvrent dans cette vue pour être ajustés.
- La géométrie tracée est conservée dans le journal.

### 5.3 Propositions avec « Inconnu »
Pour l'Affectation, les typologies et la forme du bâtiment : une valeur proposée par groupe (ex. `Type = Gaine` → `Gaines` ; `Commerce` → `Commerce` ; SUP d'un appartement → `Logement general`), que l'utilisateur prend ou non. La valeur « Inconnu » est écrite telle quelle dans le MDP. Elle ne figure pas dans la liste déroulante : Excel l'accepte, mais la signale si l'on rouvre la cellule.

## 6. Exports

| Export | Contenu |
|---|---|
| Rapport d'analyse (existant) | inchangé, plus un chapitre « Corrections appliquées » |
| **Excel de correction** | gabarit des exports Treegram (Nettes, Brutes), une ligne par surface, plus les colonnes `Catégorie corrigée`, `Aire corrigée`, `Correction` (opération et sujet) et `Explication` ; les surfaces créées par tracé apparaissent en lignes ajoutées |
| **MDP** | copie du gabarit choisi, toutes feuilles remplies avec les valeurs corrigées, tableaux redimensionnés, lignes parasites supprimées, formules et listes conservées |

## 7. Phases

| # | Phase | Livrable | Vérification |
|---|---|---|---|
| 0 | ☑ **Fondations moteur** | ID TGM, `Perimeter`, `GrossHeight`, `DeltaX/Y`, `Bedrooms` dans le modèle ; `sia-check --treegram` | ☑ exports 1778 régénérés : lignes, valeurs et ordre identiques, plus 26 SED et 47 SUT ; seul écart, les 7 `SEP-Toiture` saisis à la main |
| 1 | ☑ **Export MDP brut** | SFN (enveloppe) dans le modèle ; `sia-check --mdp`, gabarit vierge livré | ☑ L'Orée : ouvert dans Excel sans réparation ; validations, tableau croisé et formules intacts ; Σ m³ = 237 428,90, comme le MDP 1778 |
| 2 | ☑ **Corrections** | `corrections.py` : journal, 5 opérations, `--corrections`, nouveau contrôle, bilan avant/après | ☑ tests de chaque opération ; L'Orée : S2 exclut 2 549 m² de SEP de toiture, R3 et A2 des niveaux Toiture disparaissent ; S1 (découpe 1 800 m²) réduit R3 B03 N00 d'autant |
| 3 | ☑ **Sujets et recommandations de base** | `sujets.py`, `--sujets`, `subjects` dans le fichier visionneuse ; `exclure` partiel (avec `aire`) | ☑ L'Orée sans IA : toitures 7 280 m² (S2 : 7 279), abords B03 N00 1 812,65 m² (S1), SC implicite (S6) ; propositions appliquées : R3 projet 15 091 → 250 m² |
| 4 | ☑ **IA → corrections** | verdicts v2 (bloc `sujets` : garder, modifier, rejeter, ajouter, `par_defaut`), propositions dans les preuves, `--revue`, prompt et skill `revue-ia`, analyseur et sauvegarde dans l'app | ☑ revue L'Orée v2 : 31 décisions appliquées, 0 écartée ; journal accepté entièrement applicable (erreurs 56 → 33) |
| 5 | ☑ **UI Sujets** (Daedalus) | onglet Sujets, carte Sujet, décisions (journal), Analyser avec compteur, avant/après dans le bilan, tracé en 3D, menu Exporter | ☑ revue visuelle par captures (`docs/DESIGN_PLAN.md`, Évolution 2.0) ; 67 tests .NET, 133 Python |
| 6 | ☑ **Module de tracé** (Daedalus) | volet Tracé (plan du niveau, modes Tracer / Modifier, accrochage, aire comptée en direct, aperçu R3), « Découper cette surface… », sujet « Corrections manuelles », recalcul de l'aire par le moteur | ☑ S1 B03 N00 : tracé pré-calculé rouvert, 1 812,20 m² comptés (moteur : 1 812,65, sous la tolérance) ; 75 tests .NET, 134 Python |
| 7 | ☑ **Exports corrigés** | `propositions.py` (affectation, typologies, formes), opération `renseigner`, refus → « Inconnu », SA dans les exports bruts, `--corrections-xlsx`, « Inconnu » et « Excel de correction… » dans l'app | ☑ L'Orée, 62 corrections : MDP brutes SP 80, SEP 71, SA 9 (7 561 m²), 3 294 locaux tous affectés, 9 formes ; Excel de correction 3 294 + 169 lignes et journal ; les deux s'ouvrent dans Excel sans réparation ; 75 tests .NET, 140 Python |

Les phases 0 et 1 apportent un gain immédiat : la fin du copier-coller, et un MDP qui contient enfin les SED et SUT.

## 8. Points ouverts (sans blocage pour les phases 0 à 2)

- Convention de comptage des pièces GE et VD : proposée (VD = chambres + 1,5, GE = chambres + 2), à valider.
- Libellés « Nom du local » : garder le `Type` Treegram, comme aujourd'hui, ou proposer la liste MDP (`Chambre principale`, `Gaine technique`…).
- Source des murs d'enceinte (feuille Enveloppe).
