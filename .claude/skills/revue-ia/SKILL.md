---
name: revue-ia
description: Sur-vérification par IA d'une analyse sia-check d'un projet Treegram. Regroupe les points d'attention par cause, les confronte aux preuves géométriques et à la SIA 416, et livre un rapport des vrais sujets avec un verdict par point. À utiliser quand l'utilisateur demande « revue IA », « sur-vérification », « quels sont les vrais sujets », « analyse le rapport sia-check », ou après une nouvelle livraison Treegram.
---

# Revue IA d'une analyse sia-check

Objectif : transformer la liste des points d'attention (souvent > 100) en **quelques vrais sujets chiffrés**, chacun avec une cause, une preuve, une action et ce qui reste à confirmer. Ensuite, donner un verdict à chaque point : `vrai sujet`, `à confirmer`, `faux positif` ou `agrégat`.

Exemple de référence : `docs/revue-ia/L_OREE_2026-10-22.md` (L'Orée, 156 points → 3 vrais sujets).

## Étapes

1. **Analyse fraîche et preuves**, en une exécution (dossier du projet Treegram, qui contient `Nom.tgm` et `VWR\` ; shapely requis : `.venv/Scripts/python -m pip install -e ".[revue]"`) :
   ```bash
   .venv/Scripts/sia-check "<dossier projet>" -q --viewer-json report/<projet>.viewer.json --preuves docs/revue-ia/<PROJET>_<date>.preuves.json
   ```
2. **Preuves** (calculées par `sia_check.preuves` ; à partir d'un fichier visionneuse existant : `scripts/revue_ia_preuves.py`). Le fichier contient :
   - un bilan par niveau enrichi des codes maison (SUT hors logement, SPT toitures), avec le résidu R1 SUT compris. Sous la règle personnalisée P1 (SU = SUP + SUS + SUT), le moteur compte déjà SUT : `SUT_counted_by_engine` est vrai et le résidu n'est pas modifié ;
   - la décomposition géométrique de chaque SEP : sous la SP du même niveau, au-dessus du niveau inférieur, au-dessus d'un sous-sol seul, au-dessus de rien, part classée SEU/SED, part recouverte par SPT ;
   - les recouvrements entre pièces (doublons) et les pièces hors de l'emprise SP ;
   - les totaux de niveau Treegram qui diffèrent de la somme de leur détail ;
   - la liste des points d'attention ;
   - les **ratios informatifs** (`ratios`, définis dans `config.yaml > ratios`) : par portée (`*` = projet, puis chaque bâtiment), valeur, numérateur et dénominateur en m², repère indicatif `ref_min`–`ref_max` et statut `ok|bas|haut|info|n/a`. Les ratios USPI (SNH, SH, SBH, SVN, SVB) ne somment que les lots ; SC absente vaut SP − SN ; `LOTS` compte les lots ;
   - les règles personnalisées actives (`custom_rules`).
3. **Lire et regrouper.** Chercher les causes communes avant de lire les points un par un. Les questions qui ont payé sur L'Orée :
   - Un résidu R1 disparaît-il si l'on compte un code maison ? Si oui, c'est une question de nomenclature, pas de modélisation. Vérifier d'abord dans `config.yaml > custom_rules` si une règle personnalisée le compte déjà (P1 pour SUT).
   - Où repose la SEP ? Au RDC, au-dessus du sous-sol : dalle sur sous-sol, donc abords SA (SIA 416 §1.2). Recouverte par SPT : toiture comptée en SEP (§3).
   - Le résidu est-il régulier d'un étage à l'autre et dans la plage habituelle (SC 14–18 % aux étages, 4–15 % en sous-sol) ? Si oui, faux positif.
   - Un écart identique sur plusieurs étages courants indique un élément type mal classé, pas une erreur ponctuelle.
   - **Les ratios sont-ils cohérents ?** Les repères sont indicatifs, pas normatifs : un ratio hors repère n'est pas une erreur, c'est une question. Pour chacun, l'expliquer par un sujet déjà trouvé (SEP/SP haut ← SEP mal classée ; SUP/SU bas ← P1 compte SUT dans SU ; SH/SNH bas ← SCI USPI faible dans Treegram) ou par la typologie (logement, commerce, parking), sinon le signaler comme sujet à confirmer. Vérifier aussi la cohérence interne : num/den = valeur, SN/SP + SC/SP = 1, mêmes tendances d'un bâtiment à l'autre, bâtiment isolé qui s'écarte du projet.
4. **Vérifier chaque chiffre avant de l'écrire.** Recalculer depuis le fichier de preuves tout total, part ou fourchette cité dans le rapport. Ne jamais arrondir un ordre de grandeur sans l'avoir calculé.
5. **Écrire le rapport** `docs/revue-ia/<PROJET>_<date>.md`, sur le modèle de L'Orée :
   - « En bref » : un tableau des sujets (points, surface en jeu, certitude, action) et l'effet sur les totaux ;
   - un chapitre par sujet : **Constat** chiffré (avec un tableau si plusieurs niveaux), **Pourquoi c'est un vrai sujet** (chiffre SIA 416 cité), **Ce qui reste à confirmer**, **Points concernés** ;
   - les faux positifs et leur justification statistique ;
   - « Ratios de développement » : un tableau des ratios du projet (valeur, repère, statut, explication) puis les bâtiments qui s'écartent ; chaque ratio hors repère est relié à un sujet ou déclaré inexpliqué ;
   - « Hors sujets SIA, mais à connaître » (cache 3D, USPI, corrections d'affirmations antérieures) ;
   - « Ce que la revue n'a pas pu vérifier ».
6. **Écrire les verdicts** `docs/revue-ia/<PROJET>_<date>.verdicts.json` :
   ```json
   {"projet": "...", "analyse": "AAAA-MM-JJ", "revue_ia": "AAAA-MM-JJ", "modele": "...",
    "points": {"<clé du point>": {"verdict_ia": "vrai sujet|à confirmer|faux positif|agrégat",
                                  "sujet": "S1", "raison": "une phrase chiffrée"}}}
   ```
   La clé est celle du point (`règle|bâtiment|niveau|lot|catégorie`) ; c'est elle que la visionneuse utilise pour les statuts. Chaque point de l'analyse doit recevoir un verdict.

## Règles de conduite

- **Honnêteté avant tout.** Si une preuve contredit une affirmation antérieure (de la revue, de `docs/ifc-schema.md` ou du rapport), la corriger explicitement. Si un chiffre du script semble aberrant (des milliers de recouvrements, par exemple), en chercher la cause avant de l'interpréter : sur L'Orée, c'était un artefact du script.
- Citer la norme par son chiffre (SIA 416 §x.y, USPI 2014). Paraphraser, ne pas recopier.
- Distinguer **modélisation** (géométrie fausse), **classement** (bonne géométrie, mauvaise catégorie) et **nomenclature** (code hors SIA).
- L'IA ne voit ni les plans ni l'accessibilité réelle des toitures : le dire, et renvoyer à une vérification ciblée (« ouvrir B03 N01 dans Treegram »).

## Dans la visionneuse

SIA Check Viewer fait le même enchaînement avec une clé API (bouton « Revue IA ») : ce fichier y est embarqué comme prompt, et le modèle reçoit le fichier de preuves complet. Rapport et verdicts sont écrits au même format, dans `%APPDATA%\SiaCheckViewer\revue-ia\<projet>\`.
