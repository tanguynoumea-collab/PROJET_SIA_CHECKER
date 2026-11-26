# V7_PLAN — Carte d'identité des projets, exploitée au benchmark

> Statut : terminée le 26.11.2026, à publier en version 7.0.0.
> Source : docs/ROADMAP.md, « Vers l'outil de préconception du DEV », étape 1 ; le modèle de données est dans
> docs/CARTE_IDENTITE.md (liste des champs : src/sia_check/carte.py, `CHAMPS`).

## Objectif

Donner à chaque projet de la base une carte d'identité rangée en contraintes → réponse → performance, à partir de laquelle le
DEV compare les projets par leur forme et leur densité, pas seulement par leurs ratios de surfaces. C'est la première
brique de l'outil de préconception (V8 à V12).

## 1. La carte dans la visionneuse (20.11.2026)

- Clic droit sur un projet de l'accueil ou de la base : « Carte d'identité ». Le moteur la calcule à chaque lecture de la
  base (`carte.carte`, dans benchmark.json, version complète seulement).
- Mesures sur la maquette 3D de la base (`carte.mesures`) : emprise, hauteur, hauteur du rez, épaisseur, orientation,
  socle, niveaux de sous-sol ; dérivées : GSI, FSI, L, OSR, logements à l'hectare et tranche a+t.
- En tête : le volume du projet en axonométrie, la forme bâtie, la densité, la typologie.
- « Compléter la carte » : jauge de remplissage, ce qui manque rangé par qui doit agir, saisies écrites dans InfosProjet du
  MDP de la base (`SAISIES`), prompt pour remplir la carte avec une IA.

## 2. Tri des données (CARTE_IDENTITE.md, partie 4)

- **Ratios en double** sortis des KPI affichés, toujours calculés : SN / SP (complément de SC / SP), vitrée / pleine
  (doublon de la part vitrée), façade / SP hors-sol (recoupe le coefficient de forme ; le Programmer s'en sert encore pour
  estimer la façade). `Kpi.affiche` ; le dashboard les écarte de Tendances, Base et de l'export. La part vitrée remplace
  vitrée / pleine parmi les trois ratios clés.
- **SVN / SP hors-sol** sans objet pour un projet en location ou d'utilité publique (mode de commercialisation saisi dans la
  carte) : `Kpi.vente`, le ratio du projet est absent et il sort de la médiane. La carte affiche « sans objet ».
- **Données SIG de contrôle** (RegBL, demande de chaleur, radon, sol, accessibilité, densités brutes) : annexe de la carte.
- **« Îlot de bâtiments »** devient « Plusieurs bâtiments » (formes.py, BuildingShapes.cs, filtre du dashboard). Chez a+t, un
  îlot est une forme précise ; la forme d'ensemble d'un projet est sa forme bâtie a+t.

## 3. Origine de chaque valeur

Chaque champ renseigné porte son origine (`carte._origine`) : Saisie (carte ou fiche), IA (forme confirmée), Proposé (par
SIA Check, à confirmer), MDP, Maquette (mesuré sur la maquette 3D), Calcul, SIG. La ligne « Origine de chaque valeur » les
compte ; la visionneuse l'affiche sous la source de chaque donnée.

## 4. Phase : filtre « réalisés et autorisés »

Phase SIA 112 du gabarit : 21, 31-33 (avant le permis), puis 41 et plus (autorisé, réalisé). `benchmark.realise`.

- Dashboard : case « Réalisés et autorisés » dans le pré-filtre, visible quand la base compte des projets en études.
- Moteur : `similaires(..., realises=True)`.
- **Décochée par défaut.** La phase des MDP de la base est le plus souvent celle de l'étude (avant-projet), pas l'état
  actuel du projet : activée par défaut, elle viderait la référence. À revoir quand la phase sera tenue à jour (question
  au DEV, CARTE_IDENTITE.md partie 6).

## 5. Forme et contexte dans la similarité

`benchmark.FEATURES` compte aussi le GSI (emprise de la maquette / terrain), la famille de forme bâtie a+t (confirmée,
sinon proposée) et le type de site de la fiche SIG. Les deux derniers sont catégoriels (« cat » : écart 0 si identiques,
1 sinon). Le dashboard refait la même distance pour « Mon projet » (`verifierDistances` contrôle l'accord).
Nouveau KPI de la famille Terrain : emprise / terrain (GSI).

## 6. Le benchmark par la forme (dashboard)

`carte.resume` donne à chaque projet, dans toutes les versions de la base (Light comprise), son « identite » : forme bâtie
a+t et son origine, famille, distribution, phase, terrain, emprise, GSI, FSI, L, OSR, logements à l'hectare et tranche,
opération d'ensemble et sa densité, plan d'implantation.

- **Pré-filtre** : forme bâtie (famille a+t) et distribution, montrés quand la base en a.
- **Projets de référence** : tri par forme bâtie et par densité.
- **Onglet Formes** :
  - **Spacematrix** (GSI × FSI) avec les droites de L constant et les courbes d'OSR constant ; points colorés par tranche
    de densité a+t (l'accent, de plus en plus plein), en creux les projets décochés ou écartés, cerclés les maquettes
    comparées.
  - **Planche des implantations**, comme les planches « Implantaciones » de Density : chaque projet à la même échelle
    (1:5000 à l'écran tant que le plus grand tient dans sa case), parcelle au trait, emprise en aplat dans la couleur de sa
    tranche ; rangée par surface de terrain, densité, forme bâtie ou ID.
- **Export Excel** : forme bâtie, distribution et logements à l'hectare dans la feuille des projets de référence.

## 7. Parcelle et implantation

- La fiche SIG garde le polygone de la parcelle (`sig.geometrie_parcelle`, LV95 au décimètre). Les fiches d'avant la V7 sont
  complétées de leur seule parcelle à la lecture suivante de la base (une requête par projet, la fiche garde sa date).
- La carte en tire la géométrie, la forme (rectangle minimal, élancement, remplissage) et l'orientation de la parcelle.
- **Plan d'implantation** (`carte.implantation`) : parcelle et emprise hors-sol de la maquette, centrées sur la parcelle.
  La maquette n'est pas géoréférencée : son emprise est posée au point de l'adresse (sinon au centre de la parcelle), dans
  son orientation propre. Position et orientation sont donc indicatives, les surfaces exactes ; la planche et la carte le
  disent.
- **Vignette d'implantation** dans l'en-tête de la carte, au 1:5000, la même échelle que la planche (Controls/FootprintPlan.cs).

## 8. Opération d'ensemble

Deux saisies de plus dans « Compléter la carte » : les logements et la surface de l'opération d'ensemble (plan de
quartier). La carte et le résumé en tirent sa densité et sa tranche a+t : a+t classe un bâtiment par la densité de son plan.

## Restent pour le DEV (CARTE_IDENTITE.md, partie 6)

- Valider les listes : 33 formes a+t (toutes, ou par famille tant que la base est petite) et types de distribution.
- Densité de quel périmètre : la parcelle ou l'opération d'ensemble.
- Tenir la phase des projets à jour, pour activer « Réalisés et autorisés » par défaut.
