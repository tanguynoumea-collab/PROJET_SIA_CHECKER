# DESIGN_PLAN — SIA Check Viewer

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (21.10.2026)
> Évolutions : 1.1 Revue IA (validée 22.10.2026) · 2.0 Sujets et corrections (validée et implémentée 22.10.2026) · 2.1 Module de tracé (validée et implémentée 22.10.2026), en fin de document.
> Phase 2 (revue visuelle) : captures de référence dans `docs/ui-baseline/` (accueil, revue, isolement sombre, isolement clair).
> Version : 1.0 — 21.10.2026 · Mode CRÉATION

## 1. Ancrage

- **Métier** : contrôle de cohérence des surfaces SIA 416 produites par Treegram. Une surface parent (SP, SEP) doit être entièrement redistribuée dans ses sous-catégories ; on cherche où ce n'est pas le cas, et pourquoi.
- **Utilisateur type** : coordinateur BIM, à chaque livraison Treegram d'un projet (usage régulier, sessions de 30 min à 2 h), sur un écran large, souvent en 4K à 150 %. Il connaît la norme et l'arbre Treegram ; il veut aller vite du chiffre au lieu.
- **Job unique de l'écran principal** : *passer d'un écart chiffré à l'endroit du bâtiment qui le produit, puis statuer.*
- **Densité choisie** : ☑ Dense/production. C'est un outil de revue récurrente : on veut voir 3D, bilan et liste en même temps, sans navigation entre écrans.

## 2. Tokens

### Contrainte qui pilote toute la palette

La 3D est **déjà très colorée** : la légende SIA occupe le magenta, le rouge, l'orange, le jaune et le bleu. Le chrome de l'application doit donc s'effacer (graphite neutre). L'accent doit tomber dans le seul secteur de teinte libre : **le violet-pervenche**. Le vert est réservé, car la SIA 416 l'attribue aux abords (SA).

Deuxième conséquence, posée comme règle : **le remplissage dit la catégorie SIA, le trait dit le verdict.** Les catégories s'affichent toujours en aplats ou pastilles pleines ; les verdicts toujours en glyphes contourés avec un libellé. Sans cette règle, « ERREUR » rouge et « SUP » rouge se confondraient.

### Couleurs de l'interface

| Token | Hex (dark, défaut) | Hex (light) | Rôle |
|---|---|---|---|
| Background | `#15171C` | `#F3F4F6` | Fond de fenêtre, fond de la vue 3D |
| Surface | `#1E2128` | `#FFFFFF` | Panneaux latéraux, cartes |
| SurfaceRaised | `#272B33` | `#E9EBEF` | Ligne sélectionnée, survol, champs |
| TextPrimary | `#E7E9EE` | `#1B1E24` | Texte courant |
| TextSecondary | `#9BA1AD` | `#5D6470` | Contexte, unités, libellés |
| Accent | `#8B83FF` (texte dessus `#15171C`) | `#5A50D6` (texte dessus blanc) | **Action unique** (Analyser), focus clavier, sélection 3D |

Couleurs sémantiques (verdicts et statuts, **en trait et glyphe uniquement**) :

| Token | Dark | Light | Glyphe |
|---|---|---|---|
| VerdictError | `#F27272` | `#C62F2F` | cercle barré |
| VerdictWarning | `#E8B04A` | `#9A6700` | triangle |
| VerdictInfo | `#8FA3BF` | `#4F6380` | « i » cerclé |
| StatusSeen | `#59C28F` | `#1E7F52` | coche |

Contraste estimé ≥ 4,5:1 sur Surface dans les deux thèmes pour TextSecondary, l'accent et les verdicts ; ☐ à mesurer en Phase 2.

### Légende SIA 416 (couleurs de contenu, figures de la norme)

| Code | Couleur | Rendu 3D |
|---|---|---|
| SP | `#B1005D` | plaque translucide 20 %, toujours sous les sous-catégories |
| SUP | `#D5003B` | plein |
| SUS | `#F0A900` | plein |
| SD | `#F2E900` | plein |
| SI | `#0C9DDA` | plein |
| SEP / SEU / SED | `#B1005D` / `#D5003B` / `#F2E900` | **hachuré** (texture diagonale projetée en plan) |
| Ignorés (SUT, SPT) | gris `#6B7280` | hachuré gris, masqués par défaut |

### Typographie

| Rôle | Police | Taille | Usage |
|---|---|---|---|
| Titre | Segoe UI Variable Semibold | 20 | Nom du projet (barre de commande) |
| Sous-titre | Segoe UI Variable Semibold | 14 | En-têtes de panneau |
| Corps | Segoe UI Variable | 13 | Listes, messages |
| Caption | Segoe UI Variable | 12 | Unités, horodatages, compteurs |
| Codes | **Cascadia Mono** | 12 | Codes SIA (`SUP`, `SEP`), règles (`R3`), niveaux (`B03·N00`), identifiants |
| Chiffres | Segoe UI Variable, chiffres tabulaires | 13 | Aires, écarts (alignés à droite) |

Les codes en mono, partout et toujours, forment la « voix » de l'outil : un code SIA se reconnaît d'un coup d'œil dans un message comme dans un calque.

### Espacement et formes

- Grille 4 px : XS 4 / S 8 / M 12 / L 16 / XL 24. La densité production justifie M = 12.
- Rayons : contrôles 4 px, cartes 6 px. Pas d'ombres : les panneaux se distinguent par la Surface, pas par une élévation.
- Fondation : ☑ **WPF UI (Fluent 2)** · thème ☑ **Dark par défaut** (convention des visionneuses CAO ; les couleurs SIA ressortent mieux sur graphite), Light disponible et persistée.
- 3D : **HelixToolkit.Wpf**. Les maillages sont regroupés par (bâtiment, niveau, catégorie) pour tenir ~5 700 surfaces à 60 i/s ; une table triangle → surface sert à la sélection au clic.
- Icônes : Segoe Fluent Icons via `ui:SymbolIcon`.
- MVVM : CommunityToolkit.Mvvm.

## 3. Wireframes ASCII

### Écran principal — Espace de revue

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ L'ORÉE   …\Treegram\Projects\L OREE   ● analysé 21.10 14:02   ⚠ cache 3D antérieur au .tgm    [▶ Analyser] [Exporter ▾] │
├──────────────────┬───────────────────────────────────────────────────────┬──────────────────────────┤
│ CALQUES          │                                                       │ POINTS D'ATTENTION   157  │
│ Intérieur        │                                                       │ [⊘ 71] [△ 19] [ⓘ 66]      │
│ ■ SP     80 56210│                                                       │ Règle [Toutes ▾] Statut [À traiter ▾] │
│ ■ SUP  1475 22772│                 VUE 3D                                │ ┌──────────────────────┐ │
│ ■ SUS   181 16319│        (bâtiments, niveaux empilés,                   │ │⊘ R3  B03·N00  1 812,57│ │
│ ■ SD    408  4716│         couleurs SIA, extérieurs hachurés)            │ │ SEP non sous-classifiée│ │
│ ■ SI    839  1678│                                         ┌───┐         │ ├──────────────────────┤ │
│ Extérieur        │                                         │cube│        │ │△ A1  B03·N00  1 961,75│ │
│ ▨ SEP    80 18308│                                         └───┘         │ │ SEP au niveau terrain  │ │
│ ▨ SEU   318  2049│ [⌂ Vue d'ensemble] [◎ Isoler] [≡ Éclater ━━○━━]       │ ├──────────────────────┤ │
│ ▨ SED    26  1168│                                                       │ │ …                      │ │
│ ▸ USPI · Maison  │═══════════════════════════════════════════════════════│ └──────────────────────┘ │
│                  │ BILAN PAR NIVEAU — B03            (élément signature) │ ┌ DÉTAIL ──────────────┐ │
│ BÂTIMENTS        │ Toit  ▨▨▨▨▨▨▨▨ SEP 216 hors bilan                       │ │ R3 · B03·N00 · SEP    │ │
│ (A01)(B03)(B04)… │ N05 ███████████████▓▓░░░░  ⊘ 36,4                      │ │ attendu   1 961,75    │ │
│ NIVEAUX          │ N01 █████████████████▓▓▒░  ⓘ 129,1                     │ │ obtenu      149,18    │ │
│ [Tous ▾]         │ N00 ██████████▓▓▓▒░░░░░░░  ⊘ 134,1                     │ │ écart     1 812,57    │ │
│                  │ S01 ███████████████████▓▒  ⓘ 115,2                     │ │ 3 surfaces concernées │ │
│                  │                                                       │ │ (À traiter|Vu|Faux +) │ │
│                  │                                                       │ │ Commentaire…          │ │
├──────────────────┴───────────────────────────────────────────────────────┴──────────────────────────┤
│ 6 090 surfaces · 9 bâtiments · 80 niveaux · tolérance 0,5 m² et 0,5 % · sia-check 0.1.0              │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
  gauche 280 px fixe · centre * · droite 380 px redimensionnable · bilan 220 px repliable
```

Hiérarchie de lecture : **1er** la vue 3D (le lieu) · **2e** la liste des points d'attention (quoi regarder) · **3e** le bilan par niveau (pourquoi ça ne boucle pas). Les calques sont un outil, pas une information : ils restent calmes.
Action primaire : **Analyser** (accent, seul bouton accentué). Le geste principal reste le double-clic dans la liste.

### Écran d'accueil — aucun projet ouvert (état vide)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│        Ouvrez un projet Treegram pour contrôler ses          │
│        surfaces SIA 416.                                     │
│                                                              │
│        [▶ Ouvrir un dossier projet…]   (accent)              │
│        Le dossier contient le fichier .tgm et le cache VWR.  │
│                                                              │
│        RÉCENTS                                               │
│        L OREE        …\Projects\L OREE    157 points · 21.10 │
│        …                                                     │
└──────────────────────────────────────────────────────────────┘
```

Hiérarchie : 1er l'invitation et le bouton · 2e les projets récents (le cas majoritaire : rouvrir le même projet après une nouvelle livraison).

### Superposition — analyse en cours

```
          ┌──────────────────────────────────────────┐
          │ Analyse de L OREE                        │
          │ Lecture du .tgm            ✔ 6 090 surfaces │
          │ Géométrie (VWR)           ━━━━━━━━○──  612/803 fichiers │
          │ Contrôles SIA 416          …            │
          │                               [Annuler] │
          └──────────────────────────────────────────┘
```

La vue précédente reste visible derrière, en grisé : on ne perd pas son contexte pendant une ré-analyse.

### Fiche d'une surface — clic simple dans la 3D (volet flottant)

```
┌ SUP · B03·N00 ───────────────────────┐
│ B03_N00_ShellByTgm-04_SpaceByTgm-2_SUP│  (mono, sélectionnable)
│ Aire          24,71 m²               │
│ Sous-type     PieceDeVie             │
│ Lot           B03_N00_Apart-02       │
│ Points d'attention : ⊘ R1 B03·N00    │  (lien → sélectionne dans la liste)
└──────────────────────────────────────┘
```

## 4. Carte de navigation

```
Accueil ──Ouvrir / Récent──▶ Analyse (superposition) ──▶ Espace de revue
Espace de revue ──Analyser──▶ Analyse (superposition) ──▶ Espace de revue (statuts reportés)
Espace de revue ──double-clic point / Entrée──▶ caméra centrée + éléments isolés
Espace de revue ──clic surface 3D──▶ Fiche surface (volet) ──lien point──▶ point sélectionné
Espace de revue ──clic barre de niveau (bilan)──▶ niveau isolé en 3D
Espace de revue ──Exporter──▶ dialogue d'enregistrement (xlsx/html/json)
Espace de revue ──Fichier > Ouvrir──▶ Accueil
```

### Mapping fonctionnalités → emplacements (aucune orpheline)

| Fonctionnalité du brief | Écran | Emplacement / contrôle |
|---|---|---|
| Lire un projet Treegram (.tgm + VWR) | Accueil | « Ouvrir un dossier projet… » + liste des récents |
| Visionneuse 3D de toutes les surfaces, couleurs SIA | Espace de revue | zone centrale, `HelixViewport3D` |
| Surfaces externes hachurées | Espace de revue | texture hachurée sur les matériaux SEP/SEU/SED |
| Calques par classification SIA | Espace de revue | panneau gauche « Calques » : case de visibilité, pastille, nombre, aire |
| Filtres bâtiment / niveau | Espace de revue | panneau gauche, puces bâtiments + liste niveaux |
| Liste des points d'attention | Espace de revue | panneau droit, liste virtualisée |
| Filtres par règle / verdict / statut | Espace de revue | barre de filtres du panneau droit (bascules de verdict avec compteurs) |
| Double-clic = centrer + isoler | Espace de revue | liste ; aussi Entrée au clavier. Les autres surfaces passent en fantôme 10 % |
| Statut (à traiter / vu / faux positif) | Espace de revue | carte Détail : contrôle segmenté ; raccourcis 1 / 2 / 3 |
| Commentaire | Espace de revue | carte Détail : zone de texte, enregistrement automatique |
| Persistance des statuts entre analyses | (invisible) | fichier `%APPDATA%\SiaCheckViewer\<projet>.review.json`, clé = règle + bâtiment + niveau + lot + catégorie |
| Ré-analyse | Espace de revue | bouton « Analyser » (Ctrl+R) |
| Points disparus après ré-analyse | Espace de revue | statut automatique « Résolu », visible via le filtre Statut |
| Export xlsx / html / json | Espace de revue | menu « Exporter » (appelle les rapports de sia-check) |
| Fraîcheur du cache 3D | Espace de revue | pastille ⚠ dans la barre de commande si le cache VWR est plus ancien que le .tgm |
| Bilan chiffré par niveau | Espace de revue | **bilan par niveau** (signature), sous la 3D |

## 5. États non-nominaux

| Écran | État vide | Chargement | Erreur | Aucun résultat |
|---|---|---|---|---|
| Accueil | Invitation + « Ouvrir un dossier projet… » ; pas de liste « Récents » vide affichée | — | « Ce dossier ne contient pas de fichier .tgm. Choisissez le dossier du projet Treegram (celui qui contient *Nom*.tgm et VWR\). » + bouton « Choisir un autre dossier » | — |
| Analyse | — | Progression déterminée en 3 étapes (lecture, géométrie, contrôles), annulable | Message de sia-check, code de sortie 2 : « Lecture impossible de L OREE.tgm : aucune surface SIA. Lancez « Create SIA Surfaces » dans Treegram, puis réanalysez. » + « Voir le journal » | — |
| Vue 3D | Surfaces sans géométrie dans le cache : bandeau « 132 surfaces sans géométrie dans le cache VWR (ouvrez le projet dans le viewer Treegram pour le régénérer) » ; les surfaces restent dans la liste | Barre fine sous la barre de commande pendant la construction des maillages | Cache VWR absent : 3D remplacée par « Pas de cache 3D. Le contrôle chiffré reste disponible. » | Tous les calques masqués : « Aucun calque visible » + « Tout afficher » |
| Points d'attention | Aucun écart : « Aucun écart au-delà de la tolérance. » (glyphe coche, StatusSeen), sans faux enthousiasme | — | — | Filtres trop stricts : « Aucun point pour ces filtres. » + « Réinitialiser les filtres » |
| Bilan par niveau | Bâtiment non sélectionné : « Choisissez un bâtiment pour voir son bilan. » | — | — | — |

## 6. Élément signature — le bilan par niveau

**Une coupe schématique du bâtiment où chaque niveau est une barre de sommation.**

Chaque niveau est une ligne, empilée dans l'ordre réel : sous-sols en bas, toiture en haut, comme une coupe.
- La **longueur totale** de la barre est la SP du niveau.
- La barre est **remplie par ses sous-catégories** aux couleurs SIA (SUP, SUS, SD, SI), dans l'ordre de la norme.
- Ce qui n'est pas couvert reste **vide, avec un simple contour** : c'est le résidu, rendu visible. Sa valeur s'affiche en bout de ligne avec le glyphe du verdict.
- La SEP est une seconde barre, hachurée, juste en dessous et en plus fin.

On lit le problème avant de lire un chiffre :
- un RDC à moitié vide ;
- une toiture qui n'est qu'une bande hachurée sans plancher ;
- des étages courants tous identiques.

Clic sur une ligne : le niveau est isolé en 3D. Survol : le détail des aires.

C'est la traduction directe du métier, puisque la SIA 416 est une **sommation par niveau** (§0.4). Aucune autre app ne l'aurait. La prise de risque assumée : retirer 220 px à la 3D pour un graphique. Le bilan est repliable si on veut la 3D plein cadre.

## 7. Motion

- Caméra : interpolation de 300 ms (ease-out) au double-clic sur un point. C'est la seule animation qui porte du sens : elle montre d'où l'on vient.
- Fantôme des autres surfaces : fondu de 150 ms. Panneaux et snackbars : 150 ms.
- Aucun moment orchestré. Pas d'animation sur les chiffres. Si Windows demande une réduction des animations, la caméra saute directement à sa position.

## 8. Auto-critique (Passe B)

- **« Produirais-je ce plan pour une autre app ? »**
  - Premier jet : trois panneaux, accent bleu Fluent, verdicts rouge/ambre/bleu. C'était générique, et faux ici : le bleu est SI, le rouge est SUP. Je l'ai révisé : accent pervenche (seul secteur libre de la légende SIA, vert réservé aux abords) et règle « remplissage = catégorie, trait = verdict ».
  - Premier jet : « tableau des résidus » sous la 3D. Je l'ai remplacé par le bilan par niveau, qui montre la sommation au lieu de la lister.
- **Points faibles assumés (checklist)** :
  - Trois panneaux + bilan font beaucoup sur un écran 1920×1080 à 100 %. Fenêtre minimale fixée à 1400×860 ; en dessous, le bilan se replie automatiquement.
  - VerdictWarning (ambre) reste proche de SUS (orange). La distinction repose sur la forme (triangle contouré contre pastille pleine) et sur le libellé, jamais sur la couleur seule.
  - 80 niveaux empilés cachent les niveaux intermédiaires. « Éclater » et l'isolement par niveau sont donc indispensables, pas optionnels.
  - Contraste des verdicts en light à mesurer en Phase 2.
- **Accessoire retiré (Chanel)** : la mini-carte de site et le plan 2D par niveau en onglet. Utiles un jour, mais la 3D isolée par niveau vue de dessus (touche T) couvre le besoin sans un deuxième mode de vue à maintenir.

## 9. Journal des choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Accent bleu Fluent par défaut | Se confond avec SI `#0C9DDA` | 21.10.2026 |
| Verdicts en pastilles pleines rouge/ambre | Se confondent avec SUP / SUS dans la liste et la 3D | 21.10.2026 |
| Accent vert | Couleur des abords SA dans la légende SIA 416 ; futur conflit | 21.10.2026 |
| Tableau des résidus sous la 3D | Duplique la liste ; le bilan par niveau montre la même chose en forme | 21.10.2026 |
| Onglet plan 2D par niveau | Couvert par vue de dessus + isolement ; un mode de vue de moins | 21.10.2026 |
| HelixToolkit SharpDX (DirectX 11) | Plus performant mais plus lourd à intégrer ; Helix.Wpf suffit si les maillages sont regroupés. À revoir si < 30 i/s en Phase 2 | 21.10.2026 |
| Liste triée par écart seul (Phase 2) | Les agrégats « Projet » et « tous niveaux » occupaient le haut de la liste ; ils sont maintenant placés après les points de niveau, qui sont actionnables | 21.10.2026 |
| Isolement par simple fantôme (Phase 2) | Les étages en fantôme voilaient le niveau isolé, y compris ceux des bâtiments voisins sur un socle commun ; ajout d'une coupe à l'altitude du point isolé | 21.10.2026 |
| Accent via la surcharge « thème » de WPF UI (Phase 2) | Éclaircissait la pervenche jusqu'au blanc en sombre ; les 4 teintes sont désormais imposées | 21.10.2026 |

---

## Évolution 1.1 — Revue IA (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ **VALIDÉ PAR L'UTILISATEUR** (22.10.2026)
> Aucun nouveau token : tout reprend §2 (Surface, SurfaceRaised, TextSecondary, verdicts en trait). L'accent reste réservé à « Analyser » dans l'espace de revue ; dans la boîte « Revue IA », seule action visible, « Envoyer à Claude » le prend.

### Règle de lecture

Le verdict IA est une **étiquette contourée avec son libellé**, jamais une pastille pleine (règle §2 : le trait dit le verdict).
`vrai sujet` → trait VerdictError · `à confirmer` → trait VerdictWarning · `faux positif` et `agrégat` → trait TextSecondary.
Le sujet (`S1`…) est en mono. Le libellé est toujours écrit : la couleur ne porte jamais seule l'information.

### Zones nouvelles ou modifiées

```
Barre de commande
│ L'ORÉE  …\L OREE  analysé 22.10 14:02  [IA 22.10 · 3 sujets ↗]      [▶ Analyser] [✦ Revue IA] [Exporter…] ◐ ⌂ │
                                          └ lien : ouvre le rapport        └ secondaire : ouvre la boîte Revue IA

Panneau droit — filtres (2e ligne, visible si une revue est chargée)
│ Règle [Toutes ▾]          Statut [À traiter ▾]  │
│ Verdict IA [Tous ▾]   [Appliquer les faux positifs (98)] │   bouton secondaire ; ne touche que les points « À traiter »

Ligne de la liste (2e ligne : l'étiquette IA à droite du titre)
│ ⊘ R3  B03·N00                         1 812,57 │
│    SEP non sous-classifiée   ╭ S1 · vrai sujet ╮│
│    SEP 1961,75 m², sous-catégories 149,18 m²     │

Carte Détail (bloc sous « À vérifier », même gabarit)
│ REVUE IA   ╭ S1 · vrai sujet ╮            Voir le rapport ↗ │
│ 1943 m² de cette SEP reposent sur l'emprise du sous-sol :   │
│ dalle sur sous-sol, donc abords SA (SIA 416 §1.2).          │

Rapport — volet posé sur la zone 3D (la liste reste cliquable à droite)
┌ REVUE IA — L OREE · 22.10.2026 · Claude Opus 5.5 ─────── [Ouvrir le fichier] [✕] ┐
│  # Revue IA … (markdown rendu : titres, tableaux, listes, gras, code en mono)      │
│  …défilement…                                                                      │
└────────────────────────────────────────────────────────────────────────────────────┘

Boîte « Revue IA » — superposition centrée, 520 px, même gabarit que « Analyse en cours »
┌ Revue IA de L OREE ──────────────────────────────────────────────┐
│ CLÉ API ANTHROPIC                                                │
│ Clé enregistrée  sk-ant-…x7Qa            [Remplacer] [Oublier]   │
│   (sinon : [••••••••••••••] [Enregistrer])                       │
│   Chiffrée pour votre compte Windows (DPAPI), jamais en clair.   │
│                                                                  │
│ ✔ Analyse sia-check            6 090 surfaces                    │
│ ✔ Preuves géométriques         80 niveaux, 62 SEP                │
│ ✔ Estimation                   61 200 jetons envoyés             │
│ ○ Rédaction par Claude Opus 5.5                                  │
│                                                                  │
│ Coût estimé : 0,51 – 1,04 USD                                    │
│ Envoyés à l'API Anthropic : les preuves chiffrées (aires,        │
│ identifiants), pas la géométrie ni le fichier .tgm.              │
│                                    [Annuler] [Envoyer à Claude]  │
└──────────────────────────────────────────────────────────────────┘
  pendant la rédaction : barre ━━━━○── « ~4 200 / ~13 400 jetons · 1 min 12 s » + [Annuler]
  à la fin : la boîte se ferme, le rapport s'ouvre, snackbar « Revue terminée · coût réel 0,74 USD »
```

### États non-nominaux

| Zone | Vide | Chargement | Erreur |
|---|---|---|---|
| Barre / filtres / carte | Pas de revue pour ce projet : ni lien, ni filtre, ni bloc (aucun bruit) | — | Fichier de verdicts illisible : ignoré, on cherche le précédent |
| Boîte Revue IA | Pas de clé : saisie seule, « Lancer » désactivé | Étapes cochées une à une, annulable à chaque étape (le moteur est tué, l'appel API coupé) | Bandeau trait VerdictError avec le message de l'API (clé refusée, quota, réponse tronquée) ; la clé et les résultats précédents sont conservés |
| Rapport | — | — | Rapport absent à côté des verdicts : lien masqué |

### Choix rejetés

| Proposition | Raison du rejet |
|---|---|
| Badge IA en pastille pleine colorée | Viole « remplissage = catégorie » ; se confond avec SUP/SUS |
| Onglet « Rapport » à la place de la 3D | Perd le lien rapport → point ; le volet laisse la liste active |
| Clé API dans les paramètres JSON | En clair sur disque ; DPAPI par utilisateur à la place |
| Appliquer les faux positifs sans condition | Écraserait un « Vu » posé à la main ; on ne touche que « À traiter » |

---

## Évolution 2.0 — Sujets et corrections (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (22.10.2026) ☑ Implémenté, revue visuelle faite
> Captures de référence : `docs/ui-baseline/subjects-dark.png`, `subjects-light.png`, `points-light.png` (L'Orée, revue v2, 31 corrections appliquées).
> Version : 2.0 — 22.10.2026 · référence : `docs/V2_PLAN.md` §5.1 (phase 5). Capture de l'état actuel analysée avant conception : panneau droit déjà dense (liste, 2 lignes de filtres, carte Détail avec bloc IA).
> Hors périmètre : le module de tracé (phase 6) et l'Excel de correction (phase 7). Rien de ces phases n'apparaît à l'écran, pas même désactivé.

### Ancrage

- **Ce qui change dans le métier** : on ne fait plus seulement *constater* des écarts, on les *traite*. L'unité de travail n'est plus le point (155 sur L'Orée), c'est le **sujet** (5 à 8) et ses **corrections** (31).
- **Job du nouvel écran** : *statuer sujet par sujet sur les corrections proposées, puis voir dans le bilan que le bâtiment boucle.*
- Le geste dominant devient « accepter un sujet entier ». Le réglage correction par correction reste possible, mais il est minoritaire.

### Emplacement — décision

| Option | Verdict |
|---|---|
| **Onglets en tête du panneau droit : `Sujets` · `Points`** | ✅ **Retenue.** Même largeur, même logique liste + carte. Une seule liste visible à la fois : la densité baisse au lieu de monter. `Sujets` est l'onglet par défaut dès qu'il y a des sujets. |
| Sujets dans le panneau gauche | ❌ Le panneau gauche porte des outils de vue (calques, filtres) ; les sujets sont du contenu à traiter. |
| Fenêtre ou dialogue « Corrections » | ❌ Coupe le lien correction → 3D → bilan, qui est tout l'intérêt. |
| Remplacer le bilan par un tableau avant/après | ❌ Le bilan est l'élément signature ; on l'enrichit (voir plus bas), on ne le remplace pas. |

### Action primaire — une seule, toujours « Analyser »

On garde la règle V1 : un seul bouton accentué. **Analyser = relire le `.tgm` + appliquer les corrections acceptées + relancer les contrôles.** Il n'y a pas de bouton « Appliquer » séparé, donc pas de deuxième accent, et pas d'état « accepté mais pas appliqué » oublié.

- Quand des décisions n'ont pas encore été appliquées, le bouton porte un compteur : `[▶ Analyser · 22]`. Son infobulle dit : « Réanalyser le projet et appliquer 22 corrections acceptées ».
- Barre de commande : `analysé le 22.10 14:02 · 31 corrections appliquées` (le compteur est un lien vers l'onglet Sujets, filtre « Appliquées »).

### Tokens

**Aucun nouveau token d'interface.** Tout reprend §2 et l'évolution 1.1, avec une seule addition de contenu, déjà prévue par la règle V1 « vert réservé aux abords » :

| Token | Dark | Light | Usage |
|---|---|---|---|
| `SiaSA` (couleur de contenu, légende SIA 416 §1.2) | `#5BA845` | `#3F8A2C` | pastille « SA » dans les corrections « découper vers SA », plus tard (phase 6) les surfaces SA en 3D |

États de correction, **en glyphe et trait seulement** (règle V1 : le trait dit le verdict) :

| État | Glyphe | Trait | Raccourci |
|---|---|---|---|
| Proposée | cercle vide ○ | TextSecondary | `1` |
| Acceptée | coche ✓ | StatusSeen | `2` |
| Rejetée | croix ✕, texte barré | TextSecondary | `3` |
| Appliquée (après analyse) | coche pleine dans un cercle | StatusSeen | — |
| Inapplicable (cible absente, refusée par le moteur) | triangle | VerdictWarning | — |

`1 / 2 / 3` reprennent les raccourcis des statuts de points (« à traiter / vu / faux positif ») : même place sous les doigts, même sens (à décider / oui / non).

### Wireframes des zones touchées

**Panneau droit, onglet Sujets** (380 px, redimensionnable comme aujourd'hui)

```
┌──────────────────────────────────────────────────────────┐
│ [ Sujets 6 ]  Points 155                                 │  onglets (Ctrl+1 / Ctrl+2)
│ △ Revue IA : 2 décisions écartées · Voir                 │  bandeau, seulement s'il y en a
│ [Tous ▾]                       31 corrections · 18 acc.  │  filtre : à décider / acceptées / appliquées / tous
├──────────────────────────────────────────────────────────┤
│ S2  Toitures comptées en SEP                 7 280 m²    │  id mono · titre · surface en jeu
│     ╭corriger╮ ╭IA╮  31 points · 22 corrections           │  étiquettes contourées
│     ✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓○○   20 / 22                     │  frise : un glyphe par correction
├──────────────────────────────────────────────────────────┤
│ S1  SEP du rez = dalle sur sous-sol → SA     7 561 m²    │
│     ╭corriger╮ ╭IA╮  18 points · 9 corrections            │
│     ○○○○○○○○○   0 / 9                                    │
├──────────────────────────────────────────────────────────┤
│ S4  Petits écarts de SEP aux étages      ╭à vérifier╮    │  sans correction : pas de frise
│ S5  SEP en sous-sol, I17 S01             ╭à vérifier╮    │
│ S6  Surface de construction implicite    ╭aucune╮        │  en bas, texte secondaire
│     Agrégats                             ╭aucune╮        │
└──────────────────────────────────────────────────────────┘
  Tri : « corriger » (surface en jeu décroissante), puis « à vérifier », puis « aucune ».
```

**Carte Sujet** (sous la liste, même gabarit que la carte Détail)

```
┌ S2 · Toitures comptées en SEP ─────────────── ╭IA · vrai sujet╮ ┐
│ Une toiture non accessible n'est ni SP ni SEP (SIA 416 §3) ; Treegram │
│ la classe déjà en SPT. Terrasses d'attique classées SEU gardées.      │  explication (IA si revue, sinon règle)
│                                                                       │
│ [✓ Accepter les 22]  [✕ Rejeter les 22]            Voir le rapport ↗  │  secondaires ; « Rejeter » à droite, loin
│                                                                       │
│ CORRECTIONS                                                           │
│ ✓ exclure  A01·Toiture  SEP entière                        249,13 m²  │
│ ✓ exclure  A01·N07      part sous SPT                      453,03 m²  │
│▶○ exclure  E09·N04      part sous SPT                      200,55 m²  │  ligne sélectionnée (SurfaceRaised)
│ ✕ exclure  H16·Toiture  toiture-jardin accessible (IA)     ̶3̶2̶6̶,̶8̶8̶     │
│ …défilement (virtualisé)…                                             │
│ ─────────────────────────────────────────────────────────────────────│
│ E09·N04 · SEP → exclue en partie                     origine : IA      │
│ Seuls les 200,55 m² sous SPT sortent ; les 166,33 m² de SEU restent.   │
│ ( Proposée | Acceptée | Rejetée )                       [Modifier]    │  segmenté, comme les statuts de points
│   Modifier : Aire [ 200,55 ] m²   Explication [.................]     │  inline, Entrée valide, Échap annule
│              origine passe à « manuel », l'ancienne valeur est gardée   │
└───────────────────────────────────────────────────────────────────────┘
```

Pour une découpe vers SA, la ligne porte la pastille `SA` (token SiaSA) : `○ découper A01·N00  SEP → ● SA  281,75 m²`.

**Lien avec la 3D** (gestes existants, même sens)
- Sélectionner un sujet : les surfaces de tous ses points sont mises en évidence, comme le simple clic sur un point. Double-clic ou Entrée : isolement et cadrage, comme pour un point.
- Sélectionner une correction : isolement de sa surface cible. Si la correction a un tracé, il est dessiné par-dessus, en contour Accent et remplissage Accent à 20 % : c'est la part qui va bouger. L'Accent sert déjà à la sélection 3D.

**Onglet Points (inchangé, deux ajouts)**
- L'étiquette `S1 · vrai sujet` devient un lien vers le sujet, dans l'onglet Sujets.
- Sans revue IA, l'étiquette montre le sujet du moteur (`toitures`, en mono, trait TextSecondary).

**Bilan par niveau — l'avant / après dans l'élément signature**

```
Toiture  ▨▨▨▨▨▨▨▨┄┄┄┄┄┄┄┄┄┄┄                                ̶2̶1̶6̶,̶4̶7̶  ✓ 0,00
N04      ████████████▓▓░░ ▨▨▨▨┄┄┄┄┄┄                       ̶1̶0̶3̶,̶7̶6̶  ✓ 3,28
N00      ██████████▓▓▓▒░░░  ▨▨┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  ̶1̶ ̶8̶1̶2̶,̶5̶7̶  ✓ 0,08
          barre pleine = état corrigé ; ┄ contour pointillé TextSecondary = ce que les corrections ont retiré
          colonne résidu : ancien résidu barré, puis le nouveau avec son glyphe de verdict
```

Le bilan montre toujours l'état corrigé. L'« avant » est une trace : la longueur retirée en pointillé et l'ancien résidu barré. Il n'y a pas de bascule Avant / Après : on lit les deux en même temps, ce qui est le but.

**Exporter** (le bouton existant devient un menu, chaque entrée appelle le moteur)

```
[↥ Exporter ▾]
   Rapports d'analyse…        xlsx / html / json (existant)
   Tableau MDP…               choix du gabarit (défaut : vierge livré), ID projet ; surfaces corrigées
   Exports Treegram…          SurfacesNettes / SurfacesBrutes ; surfaces corrigées
```

### Carte de navigation (delta)

```
Espace de revue ──onglet Sujets (défaut si sujets)──▶ liste des sujets ──sélection──▶ carte Sujet (+ 3D en évidence)
carte Sujet ──Accepter les n / 1·2·3 sur une correction──▶ journal enregistré (immédiat, sans bouton)
carte Sujet ──Modifier──▶ édition inline ──Entrée──▶ correction « manuel »
Analyser · n ──▶ Analyse (superposition, étape « corrections » en plus) ──▶ bilan avant/après, corrections « appliquées »
étiquette sujet (onglet Points) ──▶ sujet dans l'onglet Sujets
Exporter ▾ ──▶ dialogue d'enregistrement (MDP, Treegram, rapports)
```

### Mapping fonctionnalités → emplacements

| Fonctionnalité (V2_PLAN) | Emplacement |
|---|---|
| Voir les sujets (moteur et revue IA) | onglet Sujets, liste |
| Correction proposée par sujet, origine règle / IA / manuel | carte Sujet, liste des corrections, étiquette d'origine |
| Statuer par sujet | carte Sujet : « Accepter les n », « Rejeter les n » |
| Statuer par correction | carte Sujet : contrôle segmenté, raccourcis 1 / 2 / 3 |
| Modifier une correction (aire, explication) | carte Sujet : « Modifier », édition inline |
| Décisions IA écartées | bandeau en tête de l'onglet Sujets → liste des raisons |
| Appliquer les corrections | Analyser (avec compteur) |
| Avant / après | bilan par niveau (traces), compteur de la barre de commande |
| Corrections inapplicables après analyse | glyphe triangle sur la ligne + raison du moteur |
| Journal persistant | invisible : `%APPDATA%\SiaCheckViewer\corrections\<projet>.json` ; décisions conservées par `id` d'une analyse à l'autre |
| Export MDP et Treegram corrigés | menu Exporter |

### États non-nominaux

| Zone | Vide | Chargement | Erreur | Aucun résultat |
|---|---|---|---|---|
| Onglet Sujets | Aucun point : l'onglet n'est pas affiché, on reste sur Points (« Aucun écart au-delà de la tolérance. ») | Pendant l'analyse : la liste reste visible, grisée (règle V1) | Revue IA illisible : sujets du moteur seuls, et bandeau « Revue IA ignorée : fichier illisible (nom) » | Filtre sans résultat : « Aucune correction acceptée pour l'instant. » + « Tout afficher » |
| Carte Sujet | Sujet sans correction : l'explication, puis « Pas de correction automatique : à vérifier dans Treegram. » ; pas de boutons d'acceptation | — | Modifier : aire hors bornes (négative, ou plus grande que la surface) refusée sous le champ (« L'aire découpée dépasse la SEP du niveau (1 961,75 m²). ») ; la saisie est gardée | — |
| Après Analyser | — | Superposition existante, nouvelle étape « Corrections : 22 acceptées » | Correction inapplicable : glyphe triangle + raison du moteur ; les autres sont appliquées (jamais à moitié) | — |
| Nouvelle livraison | Correction dont la cible a disparu : état « à revoir », triangle, en tête du sujet | — | — | — |
| Pas de géométrie | Découpe sans tracé : ligne « aire estimée, sans tracé » ; rien n'est dessiné en 3D | — | — | — |

### Contrat de données requis (moteur → app)

Pour cette interface, la phase 5 étend le moteur :
- `sia-check --viewer-json … --revue <verdicts les plus récents> --corrections <journal>` à chaque analyse lancée par l'app ;
- dans le fichier visionneuse :
  - `levels[].values_before` (bilan sans corrections) ;
  - `corrections_log` (application de chaque correction, avec sa raison) ;
  - `review` (décisions appliquées et écartées) ;
- le journal de l'app est la source des décisions. Il fusionne par `id` les propositions de chaque nouvelle analyse :
  - une décision de l'utilisateur prime toujours sur la proposition ;
  - une correction modifiée devient « manuel ».

### Passe B — auto-critique

- **« Produirais-je ce plan pour une autre app ? »**
  - Premier jet : un écran « Corrections » en tableau (cible, opération, aire, statut) avec un bouton « Appliquer » accentué. C'était générique : un CRUD de lignes. Il cassait la règle d'un seul accent et séparait les corrections de la 3D et du bilan. Révisé : le sujet comme unité, l'acceptation en bloc comme geste dominant, Analyser comme unique action, l'avant/après dans le bilan.
  - Premier jet de l'avant/après : une bascule « Brut / Corrigé » sur le bilan. Rejetée : il faudrait alterner pour comparer. Les traces (pointillé, ancien résidu barré) montrent les deux en même temps.
- **Checklist heuristiques**
  - ✅ Hiérarchie : 1er la liste des sujets (quoi traiter), 2e la carte Sujet (décider), 3e la 3D et le bilan (vérifier).
  - ✅ Une seule action accentuée par écran.
  - ✅ Fitts : « Accepter les n » est proche de la liste, en cible de 32 px ; « Rejeter » est à droite, éloigné. Les deux sont réversibles (repasser à « Proposée »), donc sans confirmation.
  - ✅ Raccourcis : 1/2/3 réutilisés avec le même sens. Échap ferme l'édition ; Entrée valide.
  - ⚠️ Charge : 22 corrections dans une carte de 380 px. La liste est virtualisée et la frise résume l'état d'un coup d'œil, mais l'édition inline réduit la place. **Point faible assumé** : en dessous de 1 080 px de hauteur, la carte Sujet prend la hauteur et la liste des sujets se replie sur une ligne (sujet courant ▾).
  - ⚠️ Deux vocabulaires d'identifiants : `S1` (IA) et `toitures` (moteur). Après une revue, seuls les `S…` apparaissent (les sujets du moteur repris par l'IA disparaissent). Sans revue, les identifiants du moteur s'affichent en mono, avec leur titre en clair.
  - ⚠️ La frise de glyphes devient illisible au-delà d'environ 40 corrections par sujet. Au-delà, elle est remplacée par une barre de progression segmentée (acceptées / rejetées / à décider), avec les compteurs écrits.
  - ✅ La couleur n'est jamais seule : glyphe + libellé, texte barré pour les rejets, pastille SA doublée du code `SA`.
- **Accessoire retiré (Chanel)** :
  - un « score de confiance » IA en jauge sur chaque sujet : la certitude est déjà dite par l'étiquette (`vrai sujet` / `à confirmer`) ;
  - un historique des décisions (qui, quand) affiché dans la carte : il reste dans le journal, sans écran.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Écran tableau « Corrections » + bouton « Appliquer » accentué | Deux accents ; correction coupée de la 3D et du bilan ; unité de travail fausse (ligne au lieu de sujet) | 22.10.2026 |
| Bascule « Brut / Corrigé » sur le bilan | Empêche la comparaison simultanée ; les traces la remplacent | 22.10.2026 |
| Sujets dans le panneau gauche | Le panneau gauche porte les outils de vue, pas le contenu à traiter | 22.10.2026 |
| Bouton « Tracer » désactivé en attendant la phase 6 | Pas de fonctionnalité fantôme à l'écran | 22.10.2026 |
| Jauge de confiance IA par sujet | Redit l'étiquette de certitude | 22.10.2026 |
| Confirmation avant « Rejeter les n » | Action réversible (repasser à « Proposée ») : la confirmation ralentirait sans protéger | 22.10.2026 |

### Revue visuelle (Phase 2, 22.10.2026)

Captures L'Orée, en sombre et en clair : sujet S2 avec une correction d'attique sélectionnée et son tracé, S1 avec la découpe de B03 N00, onglet Points avec le point A1 de B03 N00.

| Constat | Classe | Suite |
|---|---|---|
| Identifiants du moteur (« toitures ») tronqués dans la colonne du repère court | Bloquant | Corrigé : le repère n'est affiché que s'il est court (`S1`), sinon le titre prend la colonne |
| « Rejeter les n » coupé par « Voir le rapport » sur la même ligne | Bloquant | Corrigé : le lien passe sous l'explication |
| Résumé de correction tronqué (« part de SEP e… ») et pastille SA rognée | Bloquant | Corrigé : libellé court (« part de SEP », « SEP → » + pastille), colonnes resserrées |
| Étiquette « S1 · vrai sujet » coupée par deux liens dans la carte Détail | Bloquant | Corrigé : « Voir le sujet et ses corrections » sous la raison de l'IA |
| Compteur « Analyser · 31 » resté après l'analyse | Bloquant (fonctionnel) | Corrigé : la signature des décisions compare la cible normalisée |
| Calque SFN à 0,00 m² ; bandeau « 9 surfaces sans géométrie » pour les découpes SA | Bloquant | Corrigé dans le moteur : aire brute des façades ; les surfaces créées par une correction ne comptent pas comme sans maillage |
| Calque SA gris | Mineur | Corrigé : couleur des abords (`SiaSA`) |
| « Tout afficher » recouvert par la barre de défilement du panneau gauche (défaut V1, révélé par le calque SA) | Mineur | Corrigé : marge droite, grille des calques resserrée |
| Écarts au plan, assumés : la frise au-delà de 40 corrections n'a pas de barre segmentée (compteur seul) ; la liste des sujets ne se replie pas sous 1 080 px ; l'export MDP ne demande pas l'ID projet (celui du gabarit fait foi) | Mineur | Roadmap |

---

## Évolution 2.1 — Module de tracé (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (22.10.2026) ☑ Implémenté, revue visuelle faite
> Captures de référence : `docs/ui-baseline/trace-dark.png` (découpe B03 N00), `trace-attic-dark.png` (exclusion partielle A01 N07).
> Version : 2.1 — 22.10.2026 · référence : `docs/V2_PLAN.md` §5.2 (phase 6). Repart de l'écran Sujets livré (captures `docs/ui-baseline/subjects-*.png`).

### Ancrage

- **Le besoin** : une correction partielle (S1 : la dalle sur sous-sol d'une SEP, S2 : la part sous toiture d'un attique) ne se décrit bien qu'en plan. Aujourd'hui, le tracé vient du moteur et on ne peut changer que l'aire, à la main, ce qui détruit le tracé (`a_retracer`).
- **Job du module** : *dessiner ou ajuster, sur le plan d'un niveau, la part d'une surface qui change de catégorie, et voir tout de suite ce que cela fait à l'écart du niveau.*
- **Usage** : ponctuel, quelques tracés par livraison (9 sur L'Orée). Il faut de la précision (accrochage), pas de la vitesse. On reste en densité production, mais avec moins d'éléments que l'espace de revue.

### Retour sur un choix rejeté en V1

Le V1 avait retiré un « onglet plan 2D par niveau », couvert par la vue de dessus (touche T). Ce motif valait pour **regarder**. Pour **dessiner**, la 3D vue de dessus ne convient pas : la perspective déforme, le test d'impact passe par les maillages extrudés, et on ne peut ni accrocher un sommet ni lire des cotes. Le plan 2D revient donc, **mais seulement comme outil de tracé** : un volet ouvert pour une correction, pas un deuxième mode de navigation.

### Emplacement — décision

| Option | Verdict |
|---|---|
| **Volet « Tracé » posé sur la zone 3D + bilan, comme le rapport IA** | ✅ **Retenue.** Même gabarit que le volet Rapport (évolution 1.1). Le panneau Sujets reste visible et actif à droite : on voit la correction qu'on trace et son sujet. Fermer le volet rend la 3D. |
| Fenêtre séparée | ❌ Perd le lien avec la carte Sujet ; une fenêtre de plus à gérer sur un écran déjà chargé. |
| Dessin dans la 3D (vue de dessus) | ❌ Perspective, extrusions, pas d'accrochage fiable (voir ci-dessus). |
| Onglet du bilan | ❌ 220 px de haut : trop petit pour dessiner. |

### Points d'entrée

1. **Carte Sujet, correction sélectionnée** (`découper`, ou `exclure` avec aire) : bouton **« Tracer… »** à côté de « Modifier ». Le tracé existant (pré-calculé ou déjà ajusté) s'ouvre en mode Modifier.
2. **Fiche d'une surface cliquée en 3D** (SEP, SEU…) : **« Découper cette surface… »**. Le volet s'ouvre en mode Tracer, avec une catégorie cible à choisir (SA par défaut pour une SEP, liste des catégories SIA sinon). Enregistrer crée une correction « manuel », rangée dans le sujet de ses points s'il y en a un, sinon dans un sujet **« Corrections manuelles »**.
3. Raccourci **T**, sur une correction sélectionnée de l'onglet Sujets, ouvre aussi le volet. Hors de ce contexte, T reste la vue de dessus.

### Wireframe — volet Tracé (sur la zone 3D + bilan)

```
┌ TRACÉ · B03·N00 · SEP → SA ─────────────────────────────────────────────────────────── [Annuler] [Enregistrer le tracé] [✕] ┐
│ ( Tracer | Modifier )   Accrochage [■ Sommets] [■ Arêtes]   [⟲ Annuler Ctrl+Z] [⌫ Effacer]   [⌖ Cadrer F]                  │  barre d'outils
├────────────────────────────────────────────────────────────────────────────────────────────────┬──────────────────────────┤
│                                                                                                │ AIRE DU TRACÉ             │
│     ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐   emprise du niveau inférieur (S01),         │   1 812,65 m²             │  signature du volet
│     ╎  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ╎   contour pointillé TextSecondary             │   chiffres 20 px tabulaires│
│     ╎  ░░ SEP (source : contour épais) ░░░░░ ╎                                                │                           │
│     ╎  ░░┌────────┐░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓░░░ ╎   ▓ = tracé : liseré Accent + aplat Accent 20 % │ sur la SEP      1 961,75  │
│     ╎  ░░│ SP N00 │░░ ■───────────────■ ░░░ ╎   ■ = sommets (8 px), le sommet survolé grossit │ retiré : SEU/SED  149,10  │  ce que le tracé ne compte pas
│     ╎  ░░│ (gris) │░░ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓ │ ░░░ ╎   ◇ = point d'accrochage sous le curseur         │ hors de la SEP      0,00  │
│     ╎  ░░└────────┘░░ ■───────────────■ ░░░ ╎   SEU / SED : aplats pâles de leur couleur,     │                           │
│     └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘   jamais recouverts par le tracé compté         │ ÉCART R3 DU NIVEAU        │
│                                                                                                │  1 812,57 → ⊘ 0,08        │  aperçu : comme le bilan
│  ⊢──── 10 m ────⊣                                          x 2 541 312,40  y 1 117 805,12      │  (si la correction est    │
│  échelle                                                    coordonnées du curseur (mono)      │   appliquée)              │
├────────────────────────────────────────────────────────────────────────────────────────────────┴──────────────────────────┤
│ Clic : ajouter un point · Entrée ou double-clic : fermer · ⌫ : retirer le dernier point · Échap : annuler le point en cours │  aide contextuelle (Caption)
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  Panneau droit (onglet Sujets) toujours actif ; la correction tracée reste sélectionnée dans la carte Sujet.
```

**Hiérarchie** : 1. le plan avec le tracé (le lieu) ; 2. l'aire du tracé (le chiffre qu'on règle) ; 3. l'écart du niveau, avant et après.
**Action primaire du volet** : « Enregistrer le tracé », accentuée. C'est le précédent de la boîte Revue IA : l'accent passe à la seule action de la superposition, et « Analyser » est inaccessible tant que le volet est ouvert.

### Ce que l'aire compte

- **Aire du tracé = (polygone ∩ surface source) − sous-catégories classées de la même famille** : SEU, SED et SEI pour une SEP ; aucune pour une surface élémentaire.
- C'est la règle des tracés pré-calculés (S1), désormais visible : les trois lignes sous l'aire disent ce qui est compté et ce qui ne l'est pas.
- Un tracé qui déborde de la source n'est pas une erreur : seule la part sur la source compte (ligne « hors de la SEP »).
- L'aperçu de l'écart R3 du niveau reprend la forme du bilan : ancien écart, flèche, nouveau verdict et nouvel écart.

### Interactions

| Geste | Mode Tracer | Mode Modifier |
|---|---|---|
| Clic | ajoute un sommet (accroché si un sommet ou une arête est à moins de 8 px) | sélectionne un sommet |
| Glisser | — | déplace le sommet sélectionné (accrochage actif) ; glisser l'intérieur du tracé le déplace en entier |
| Double-clic sur une arête du tracé | — | insère un sommet |
| Entrée / double-clic | ferme le polygone, passe en Modifier | — |
| ⌫ / Suppr | retire le dernier sommet | supprime le sommet sélectionné (minimum 3) |
| Maj maintenue | segment horizontal ou vertical | idem pendant le glisser |
| Molette / glisser au clic milieu ou Espace | zoom autour du curseur / déplacement | idem |
| Ctrl+Z / Ctrl+Y | annuler / rétablir (pile de 50 gestes) | idem |
| F | cadrer le niveau | idem |
| Échap | annule le point en cours, puis ferme le volet (avec confirmation si le tracé a changé) | ferme le volet (même confirmation) |

- **Accrochage** : sommets d'abord, puis arêtes, des surfaces du niveau et de l'emprise du niveau inférieur (c'est souvent le bord de la dalle).
- Le losange ◇ montre le point d'accrochage. Maintenir **Alt** le désactive pour ce clic.
- Plusieurs polygones par tracé (ex. dalle en deux parties) : en mode Tracer, un nouveau polygone peut commencer hors du premier. Les trous ne se dessinent pas ; on les obtient par l'inverse (tracer moins large).

### Rendu du plan (contenu, pas chrome)

- Surfaces du niveau aux couleurs SIA en aplat pâle, comme dans la 3D (`ExternalTint`). SP en gris clair sous les pièces.
- Surface source : contour épais (2 px) TextPrimary.
- Emprise du niveau inférieur : contour pointillé TextSecondary, sans remplissage.
- Tracé : aplat Accent à 20 % et liseré Accent 2 px. C'est la même règle qu'en 3D.
- Fond : token Background, sans grille. Échelle graphique en bas à gauche.
- Infobulle au survol d'une surface : code, aire, identifiant. Même contenu que la fiche surface.

### Tokens

Aucun nouveau token. L'aire du tracé utilise FontSizeTitle (20) en chiffres tabulaires : c'est le chiffre réglé, il doit dominer le volet comme le titre de projet domine la barre de commande.

### Mapping fonctionnalités → emplacements

| Fonctionnalité (V2_PLAN §5.2) | Emplacement |
|---|---|
| Vue en plan 2D d'un niveau, couleurs SIA | volet Tracé, plan |
| Emprise du niveau inférieur en fond | volet Tracé, contour pointillé |
| Tracé de polygone | mode Tracer |
| Accrochage aux sommets et aux arêtes | bascules Accrochage, ◇, Alt pour désactiver |
| Aire en direct | colonne droite : aire du tracé et sa décomposition |
| Découpe sur la surface source, catégorie cible | titre du volet (`SEP → SA`) ; choix de la cible à l'ouverture depuis la fiche surface |
| Ajuster les tracés pré-calculés | « Tracer… » sur une correction, mode Modifier |
| Géométrie conservée dans le journal | « Enregistrer le tracé » : polygone, aire et triangulation enregistrés dans la correction (origine « manuel ») |
| Créer une découpe sans proposition | fiche surface : « Découper cette surface… », sujet « Corrections manuelles » |

### États non-nominaux

| Situation | Rendu |
|---|---|
| Niveau sans géométrie dans le cache VWR | Le volet ne s'ouvre pas : « Pas de géométrie pour ce niveau dans le cache VWR : ajustez l'aire avec Modifier. » (snackbar) |
| Tracé vide (mode Tracer, aucun point) | Plan seul, avec l'aide contextuelle « Clic : ajouter un point… » ; « Enregistrer » désactivé |
| Polygone qui se recoupe | Liseré VerdictError sur les arêtes concernées et message sous l'aire : « Le contour se recoupe : déplacez un sommet. » ; « Enregistrer » désactivé |
| Tracé hors de la source (aire 0) | Aire 0,00 et « Le tracé ne recouvre pas la SEP du niveau. » ; « Enregistrer » désactivé |
| Aire du tracé = toute la source | Message neutre : « Le tracé couvre toute la surface : une exclusion ou un reclassement entier serait plus simple. » ; on peut quand même enregistrer |
| Fermeture avec un tracé modifié non enregistré | « Abandonner le tracé ? » [Continuer le tracé] [Abandonner] |
| Correction tracée puis aire modifiée à la main | `a_retracer` (déjà en V2) : « Tracer… » rouvre le dernier tracé, avec le bandeau « L'aire a été modifiée à la main depuis ce tracé. » |

### Contrat de données et technique

- **Géométrie** : les maillages du fichier visionneuse sont déjà dans le repère du plan, en mètres. Les contours se recalculent dans l'app : on prend les arêtes de bord des triangles, comme `SceneController.BoundaryEdges`.
- **Calcul en direct dans l'app** : Clipper2 (NuGet, licence Boost) pour les intersections, différences et aires ; LibTessDotNet (MIT) pour trianguler le tracé pour la 3D. Ce sont deux bibliothèques sans dépendance native.
- **Correction enregistrée** :
  - `polygone` (GeoJSON, même format que le moteur), `aire` (aire comptée), `trace` (triangulation), `origine` « manuel » ;
  - `base` garde la proposition d'origine ;
  - `a_retracer` est remis à faux.
- **Le moteur reste l'autorité** : à l'application, `corrections.py` recalcule l'aire depuis `polygone` avec shapely, selon la même règle (∩ source − SEU/SED/SEI). Si l'écart dépasse la tolérance, il le signale dans `corrections_log` (« aire recalculée : 1 812,40 m² au lieu de 1 812,65 »). L'app l'affiche comme une correction appliquée avec avertissement.
- **Corrections manuelles ajoutées** : le journal sait déjà les garder ; l'app les range dans « Corrections manuelles » au lieu de « à revoir ». Le critère : origine « manuel » et identifiant `manuel-…`.

### Passe B — auto-critique

- **« Produirais-je ce plan pour une autre app ? »**
  - Premier jet : un éditeur de polygones générique, avec une grille, une palette d'outils à gauche et une liste des sommets avec leurs coordonnées. C'était un mini-CAO, hors sujet. On ne dessine pas un plan : on délimite une part de surface existante. Révisé : accrochage sur la géométrie existante, une seule catégorie cible, aire décomposée à droite et aperçu de l'écart R3 du niveau. Ce sont les deux chiffres du métier.
  - L'aperçu de l'écart reprend la notation du bilan (barré → nouveau) : le volet parle la même langue que l'élément signature, il n'en invente pas une deuxième.
- **Checklist heuristiques**
  - ✅ Hiérarchie : plan, puis aire, puis écart. Une seule action accentuée dans le volet.
  - ✅ Fitts : outils de 32 px, sommets saisissables à 8 px avec une zone d'accroche de 12 px.
  - ✅ Feedback : l'aire se recalcule à chaque mouvement de sommet. Clipper2 sur quelques centaines de sommets reste sous 16 ms.
  - ✅ Clavier : tout le tracé est possible au clavier, sauf le placement initial des points. Les flèches déplacent le sommet sélectionné de 0,10 m (Maj : 1 m).
  - ⚠️ Conventions : double-clic à la fois pour fermer le polygone (mode Tracer) et pour insérer un sommet (mode Modifier). C'est acceptable parce que les modes sont exclusifs et affichés, mais c'est le point le plus fragile. À surveiller en revue visuelle.
  - ⚠️ Charge : deux modes, deux accrochages, annuler/rétablir. C'est à la limite des 7±2 pour un outil ponctuel. Le mode est choisi automatiquement (Modifier si un tracé existe, sinon Tracer), si bien qu'on bascule rarement à la main.
  - ⚠️ Écart d'aire entre l'app (Clipper2) et le moteur (shapely) : les deux calculs diffèrent de quelques centièmes de m². Le moteur fait foi, et l'écart n'est signalé qu'au-delà de la tolérance (0,5 m² et 0,5 %).
- **Accessoire retiré (Chanel)** :
  - la saisie numérique des coordonnées d'un sommet : l'accrochage et les flèches suffisent pour délimiter une part de surface existante ;
  - la mesure de distances entre deux points : utile un jour, mais ce n'est pas le job du module.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Fenêtre « Tracé » séparée | Coupe le lien avec la carte Sujet ; une fenêtre de plus | 22.10.2026 |
| Dessin directement dans la 3D vue de dessus | Perspective et maillages extrudés : pas d'accrochage fiable | 22.10.2026 |
| Grille et palette d'outils façon CAO | On délimite une part de surface existante, on ne dessine pas un plan | 22.10.2026 |
| Aire « brute » du polygone | Ne correspond pas à ce que le moteur appliquerait ; l'aire comptée (∩ source − sous-catégories classées) est la seule utile | 22.10.2026 |
| Intersection calculée seulement par le moteur | Pas d'aire en direct ; le moteur garde la vérification à l'application | 22.10.2026 |
| Saisie des coordonnées des sommets | Accessoire : accrochage et flèches suffisent | 22.10.2026 |

### Revue visuelle (Phase 2, 22.10.2026)

Captures L'Orée : volet ouvert sur la découpe B03 N00 (tracé pré-calculé, 1 812,20 m² comptés, R3 −0,08 → 0,37) et sur l'exclusion partielle de l'attique A01 N07, en sombre et en clair, fenêtre maximisée et fenêtre de 1 600 px.

| Constat | Classe | Suite |
|---|---|---|
| « Tracer… » et « Modifier » écrasaient le contrôle Proposée / Acceptée / Rejetée dans la carte Sujet | Bloquant | Corrigé : les deux boutons passent sous le contrôle |
| Aplats éclaircis vers le blanc : en sombre, le plancher SP gris clair dominait le plan | Bloquant | Corrigé : aplats en transparence sur le fond, pâles dans les deux thèmes |
| Bascules « Sommets » / « Arêtes » en police mono (style des puces de bâtiment) | Mineur | Corrigé : police d'interface, ce sont des mots et non des codes |
| À 1 600 px, le badge « Cache 3D antérieur » passait sous « Analyser » (chemin du projet trop large, lien des corrections appliquées en plus) | Bloquant | Corrigé : chemin limité à 240 px, avec points de suspension |
| Annuler / rétablir pendant le dessin perdait le polygone en cours (trouvé par les tests) | Bloquant (fonctionnel) | Corrigé : l'historique garde l'état du dessin |
| Écart Clipper2 (app) / shapely (moteur) de l'ordre de 0,1 à 0,5 m² sur les tracés pré-calculés | Accepté | Sous la tolérance : le moteur ne recalcule qu'au-delà de 0,5 m² et 0,5 % |
| Double-clic : fermer (Tracer) et insérer un sommet (Modifier) | À surveiller | Pas de confusion constatée : les modes sont exclusifs et affichés ; à revoir avec l'usage |

---

## Évolution 3.0 — Accueil en deux sections : Fiabilisation et Benchmark (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.0 — 27.10.2026 · Phase 10 de `docs/V3_PLAN.md`

### Ancrage

- **Deux métiers sur le même écran.** Le coordinateur BIM *fiabilise* un projet Treegram (inchangé). Le développement immobilier *exploite* la base des MDP pour comparer un projet à ceux qui lui ressemblent.
- **Job de l'accueil** : *choisir son travail du jour et voir, avant d'entrer, l'état de chaque côté* (projets en cours d'un côté, solidité de la base de l'autre).
- **Le lien entre les deux** : un projet « Traité » produit un MDP propre, qui nourrit la base. L'accueil rend ce flux visible, de gauche à droite.

### Emplacement — décision

Un seul écran, deux colonnes de même largeur, séparées par un filet vertical (Divider). Pas d'onglets : les deux sections doivent se voir en même temps, puisque l'une alimente l'autre. Le dashboard s'ouvre dans un écran à part (phase 11, HTML dans WebView2) ; l'accueil n'en montre que l'entrée et l'état de la base.

### Wireframe

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ SIA Check Viewer                                                                                  │
│                                                                                                   │
│   FIABILISATION                                  │   BENCHMARK                                    │
│   Contrôler et corriger les surfaces             │   Comparer un projet à ceux qui lui            │
│   d'un projet Treegram.                          │   ressemblent.                                 │
│                                                  │                                                │
│   [▸ Ouvrir un dossier projet…]  (accent)        │   [▸ Ouvrir le benchmark]  (accent)            │
│   Le dossier contient le .tgm et le cache VWR.   │   5 projets de référence sur 10 · lue le 27.10 │
│                                                  │                                                │
│   PROJETS ACTIFS                         2       │   BASE DE DONNÉES                  [↻] [📁]    │
│   L OREE        En traitement  156 pts · 21.10 🗑│   …\03-DataBase-DonneesProjets                 │
│   SAUVABELINES  Traité   ⇥base 12 pts · 20.10 🗑│   1714 Le Clos des Hêtres  VD  ▮▮▮▮▮▮▮▮▮▮ ✓  │
│   …                                              │   1467 La Bâtie            GE  ▮▮▮▮▮▮▮▮▮▯ ✓  │
│                                                  │   1784 Sauvabelines        —   ▮▮▮▮▮▮▮▮▮▯ ✓  │
│                                                  │   1778 L'Orée              —   ▮▮▮▯▯▯▯▯▮▯ △  │
│                                                  │   1023 Côté Gare           VS  ▮▯▯▯▯▯▯▮▯▮ △  │
│                                                  │   …                                            │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
  deux colonnes * / *, largeur max 1 360, centrées en haut · listes défilantes, en-têtes fixes
```

Hiérarchie : **1er** les deux titres et leurs boutons (le choix du travail) · **2e** les listes (l'état de chaque côté) · **3e** les légendes (chemin, date de lecture).

- **Projets actifs** (les récents, renommés puisqu'ils portent un statut) : « En traitement » d'abord, puis « Traité ». Même ligne qu'aujourd'hui. Sur une ligne « Traité », une action **⇥ Ajouter à la base** exporte le MDP du projet directement dans le dossier de la base (ID et nom HRS demandés comme à l'export MDP), puis relit la base. **Depuis le 27.10.2026, passer un projet en traité fait cet export automatiquement** (identité prise dans la fiche projet ; fiche ouverte s'il manque un champ requis ; confirmation avant de remplacer un MDP de même ID). Le statut « traité » est enregistré d'abord : si l'export n'a pas lieu (identité incomplète, pas de dossier de base, erreur), un message le dit et ⇥ permet de réessayer. **Traité · modifié** (27.10.2026) : une décision de correction (accepter, rejeter, modifier, tracer) ou un changement de fiche projet (identité, dossier) sur un projet traité le fait passer « Traité · modifié » (pastille en contour vert, icône de republication ; orange dans les projets actifs ; `traite_modifie` dans projets.json). On peut continuer à modifier et enregistrer : la base ne change pas. Un clic sur la pastille propose « Republier » (MDP réexporté dans la base sans question de remplacement, dashboard mis à jour, retour à « Traité ») ou « Plus tard ». Les statuts et commentaires des points ne comptent pas : ils ne changent pas le MDP.
- **Base de données** : une ligne par MDP, fiables d'abord, puis par score. ID en mono, nom, canton (mono, « — » s'il manque), empreinte de fiabilité, verdict. Survol : la liste des données manquantes. Clic : rien en phase 10 (la fiche projet vient avec le dashboard). [↻] relit la base, [📁] change de dossier.

### Élément signature — l'empreinte de fiabilité

Dix petits segments par projet, **un par contrôle du moteur** (brutes, découpage, nettes, SP ≥ SN, SC plausible, logements, chambres, USPI, enveloppe, infos), toujours dans le même ordre. Segment plein = donnée présente, segment vide (contour Divider) = manquante. La colonne se lit comme un code-barres : on voit d'un coup *quelle* donnée manque dans la base, pas seulement *combien*. C'est le pendant du bilan par niveau (une barre qui montre ce qui manque), appliqué à la base.

Règle conservée : le remplissage reste neutre (TextSecondary) ; le verdict est porté par le glyphe en bout de ligne, coche StatusSeen « dans les références », triangle VerdictWarning « écarté ». Pas de vert en aplat (abords SA).

**Lisibilité (retours utilisateur, 27.10.2026)** : l'empreinte ne disait pas ce qu'elle mesure, et des infobulles ne suffisaient pas. Version retenue : la colonne verdict (✓ / ⚠) et le chemin du dossier de la base sont retirés de l'accueil (le chemin reste dans l'infobulle du bouton « Changer le dossier ») ; les en-têtes (ID, Projet, Typologie, Canton, Données du MDP) **trient la liste** au clic (même en-tête : sens inversé, ▲ / ▼) ; **un clic sur une ligne ouvre la page du MDP** : entrée dans les références ou raison exacte de l'écart, puis **l'identité du projet, à remplir en priorité** (champs requis manquants en erreur, bouton « Renseigner l'identité »), puis chaque contrôle des données avec sa valeur et ce que son absence retire au benchmark ; « Ouvrir le MDP » (Excel) et « Recharger » (relit la base, la page reste sur le même fichier). Les contrôles requis pour les références sont « SP ≥ SN » et « SC / SP plausible » (benchmark.REQUIS).

### Tokens

Aucune nouvelle couleur. Ajouts de dimensions dans `Tokens.xaml` : `HomeMaxWidth` 1360, segment d'empreinte 6 × 12 px (pas de 2 px). Titres de colonne en `TextSection`, phrases d'intention en `TextTitle`.

### Arbitrage — deux boutons accentués

Le plan V1 réserve l'accent à une action unique par écran. Ici l'écran porte deux tâches indépendantes, pour deux publics ; chacune a son action primaire. Je propose **deux boutons accentués, un par colonne**, symétriques. L'alternative est rejetée plus bas.

### Carte de navigation (delta)

| Depuis | Action | Vers |
|---|---|---|
| Accueil, Fiabilisation | Ouvrir un dossier / clic sur un projet | Espace de revue (inchangé) |
| Accueil, Fiabilisation | ⇥ Ajouter à la base | Dialogue ID / nom HRS → export MDP dans la base → relecture |
| Accueil, Benchmark | Ouvrir le benchmark | Écran Dashboard (phase 11) ; en phase 10, bouton désactivé avec l'infobulle « Disponible avec le dashboard (phase 11) » |
| Accueil, Benchmark | ↻ / 📁 | Relecture de la base / sélecteur de dossier |
| Espace de revue | Accueil | Accueil, base relue si un MDP a changé |

### États non-nominaux

| Zone | État | Rendu |
|---|---|---|
| Benchmark | Aucun dossier choisi | « Choisissez le dossier qui contient les MDP du benchmark. » + [Choisir le dossier…] à la place de la liste |
| Benchmark | Dossier sans MDP | « Aucun fichier MDP-*.xlsx dans ce dossier. Exportez un MDP depuis un projet traité, ou choisissez un autre dossier. » |
| Benchmark | Lecture en cours | Barre fine indéterminée sous l'en-tête ; la liste précédente reste affichée |
| Benchmark | MDP illisibles | Bandeau VerdictError : « 2 fichiers ignorés : … (pas un MDP) » |
| Benchmark | Moins de 3 projets fiables | Sous le bouton, en VerdictWarning : « 2 projets de référence : trop peu pour comparer. » |
| Fiabilisation | Aucun projet | Invitation et bouton seuls, pas de liste vide (inchangé) |

### Contrat technique

- La base est lue par le moteur : `sia-check --benchmark <dossier> --benchmark-json %LOCALAPPDATA%\SiaCheckViewer\benchmark\benchmark.json`. L'app lit ce JSON ; elle relance le moteur au démarrage seulement si un MDP est plus récent que le JSON, ou sur [↻].
- Dossier de la base : `AppSettings.BenchmarkFolder` (vide = pas encore choisi).

### Passe B — auto-critique

- **Générique ?** Premier jet : deux tuiles « portail » avec une grande icône chacune. Rejeté : décoratif, ne dit rien de l'état. L'empreinte de fiabilité remplace l'icône par une information.
- **Charge cognitive** : 10 segments par ligne, c'est dense. Acceptable, parce que l'ordre ne change jamais et que le survol nomme ce qui manque ; le verdict en bout de ligne suffit pour une lecture rapide.
- **Fitts / clavier** : boutons ≥ 32 px, lignes navigables au clavier (Tab entre colonnes), focus visible en accent.
- **Point faible assumé** : à 1 400 px de large, chaque colonne fait environ 650 px ; la colonne Fiabilisation tronque le chemin du projet (déjà le cas aujourd'hui, avec points de suspension et infobulle).
- **Accessoire retiré** : le nombre de logements et la SP par ligne de la base. Ce sont des chiffres de dashboard, pas l'état de la base.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Onglets Fiabilisation / Benchmark | Cache le lien entre les deux ; l'accueil doit montrer les deux états d'un regard | 27.10.2026 |
| Tuiles portail avec grande icône | Décoratif, n'informe pas | 27.10.2026 |
| Un seul bouton accentué (Ouvrir un dossier), « Ouvrir le benchmark » secondaire | Hiérarchise un public sur l'autre ; les deux tâches sont indépendantes | 27.10.2026 |
| Score de fiabilité en pourcentage seul | Dit combien il manque, pas quoi ; l'empreinte dit quoi | 27.10.2026 |

### Revue visuelle (Phase 2, 27.10.2026)

Capture en thème clair, fenêtre maximisée (1 456 px), base des 10 MDP de `00_RESSOURCES` : les deux colonnes, 5 projets de référence sur 10, empreintes et verdicts lisibles.

| Constat | Classe | Suite |
|---|---|---|
| En clair, les segments vides de l'empreinte (contour Divider) étaient presque invisibles : une donnée manquante se lisait comme un simple espace | Bloquant | Corrigé : contour TextSecondary à 45 % d'opacité ; rendu corrigé non recapturé |
| Grand vide sous « Projets actifs » quand il n'y a qu'un projet | Accepté | La colonne se remplit avec l'usage ; pas de contenu de remplissage |
| Chemin complet de la base affiché en entier | À surveiller | Tient à 1 456 px ; points de suspension au-delà |

---

## Évolution 3.1 — Dashboard du benchmark (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.1 — 27.10.2026 · Phase 11 de `docs/V3_PLAN.md`

### Ancrage

- **Utilisateur** : développement immobilier (chef de projet, analyste), pas forcément familier de Treegram ; connaît la SIA 416 de nom, raisonne en m² vendables et en rentabilité.
- **Job de l'écran** : *voir où un projet se place face aux projets qui lui ressemblent, ratio par ratio, et ce que l'écart représente en m².*
- **Contrainte qui pilote tout** : le dashboard partira sur le web. Il est donc écrit en **HTML/CSS/JS sans dépendance** (pas de CDN, pas de build), graphiques en SVG dessinés à la main, données lues dans `benchmark.json` (même fichier en local et sur un serveur). L'application WPF n'est qu'un cadre : barre de titre + WebView2.

### Emplacement — décision

Un **écran Dashboard** dans l'application, au même niveau que l'espace de revue : on y entre par « Ouvrir le benchmark » (accueil), on en sort par ⌂ Accueil. Pas de fenêtre séparée : une seule fenêtre, comme aujourd'hui.

### Écran hôte (WPF)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ [⌂]  Benchmark   5 projets de référence sur 10 · lue le 27.10.2026 10:32         [↻]     │  ← barre Surface, comme l'espace de revue
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│                         WebView2 : dashboard/index.html                                  │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Le thème (clair / sombre) de l'application est transmis à la page ; [↻] relit la base puis recharge la page.

### Page HTML — trois vues, un onglet chacune

```
  Comparer · Base · Typologies                                                    (onglets texte, soulignés en accent)

COMPARER ──────────────────────────────────────────────────────────────────────────────────
  Projet  [1784 · Sauvabelines        ▾]     Référence : 4 projets similaires · ratios combinés

┌ PROJETS SIMILAIRES ──────────┐  ┌ RENDEMENT ────────────────────────────────────────────────────────┐
│ ☑ 1467 La Bâtie       ●●●●○  │  │ SUP hors-sol / SP hors-sol                                        │
│ ☑ 1712 La Myonaz      ●●●●○  │  │   ce projet 74,0 %   référence 73,1 %   +0,9 pt   ▲ +39 m² de SUP │
│ ☑ 1746 Avallons       ●●●○○  │  │   60 %  ─────────·──[▒▒▒▒│▒▒▒]──◉──────────────────  85 %          │
│ ☑ 1714 Clos des Hêtres●●○○○  │  │                    ·  ·    │    ·                                   │
│                              │  │ SVN / SP hors-sol   …                                              │
│ Filtres                      │  ├ PERTES ───────────────────────────────────────────────────────────┤
│ ☑ même catégorie d'ouvrage   │  │ Construction : SC / SP   10,5 %  réf. 16,4 %  −5,9 pts  ▲ −360 m² │
│ ☑ même type d'intervention   │  │ …                                                                 │
│                              │  ├ SOUS-SOL · COMPACITÉ · PROGRAMME ─────────────────────────────────┤
│ Écartés de la base (5) ▸     │  │ …                                                                 │
└──────────────────────────────┘  └───────────────────────────────────────────────────────────────────┘
   280 px                             reste ; une ligne par KPI, groupées par famille (V3_PLAN §4.2)
```

Hiérarchie : **1er** la position du projet sur chaque règle (le point accent) · **2e** l'écart chiffré et sa traduction en m² · **3e** la liste des projets similaires (sur quoi repose la référence).

- **Projets similaires** : les 5 plus proches calculés par le moteur, cochés. Décocher un projet recalcule à l'instant les ratios combinés (Σ num / Σ den, dans la page). La proximité s'affiche en 5 pastilles (plus il y en a, plus le projet est proche), avec la distance au survol. Les filtres retirent les projets d'une autre catégorie ou d'un autre type d'intervention (une valeur inconnue ne retire pas, comme dans le moteur).
- **Projets écartés** (SP et SN incohérentes) : repliés, pour mémoire ; on peut les choisir comme projet à comparer (avec un bandeau « données incohérentes ») mais jamais comme référence.
- Moins de 3 projets dans la référence : la référence est affichée en pointillé avec « 2 projets : référence fragile ».

```
BASE ──────────────────────────────────────────────────────────────────────────────────────
  Projet              Canton  SUP/SP hs  SVN/SP hs  SC/SP   SD/SP hs  …   SUP/log
  ─────────────────────────────────────────────────────────────────────────────────────
  Ensemble (n)                73,2 % (5) 93,3 % (4) 15,8 %  7,1 %         75 m²     ← ratios combinés de la base
  1714 Clos des Hêtres  VD    81,1 %     119,6 %    18,6 %  1,0 %   …     82 m²
  …
  1778 L'Orée (écarté)  —     49,9 %     —          56,1 %  …                       ← grisé, hors « Ensemble »
```

Tableau triable (clic sur un en-tête), une ligne par MDP ; un clic sur une ligne ouvre Comparer sur ce projet. Les valeurs ne sont pas colorées : un petit ▲/▼ à côté de la valeur dit seulement si elle est au-dessus ou au-dessous de l'ensemble, dans le sens favorable ou défavorable du ratio (glyphe + infobulle, jamais la couleur seule).

```
TYPOLOGIES ────────────────────────────────────────────────────────────────────────────────
  SUP par logement selon le nombre de chambres (4 projets, 248 logements)
  Studio    ├────[████|██]──────┤          40 m²   (21 logements, 3 projets)
  1 ch.          ├──[█|█]───┤              55 m²   (97, 4)
  2 ch.                ├──[██|███]────┤    75 m²   (75, 4)
  3 ch.                       ├─[█|██]───┤ 96 m²   (53, 4)
  4 ch.                           |        94 m²   (2, 1)  ← moins de 3 projets : grisé
        20      40      60      80      100     120 m²
```

Boîtes horizontales (min, quartiles, médiane, max) sur une seule échelle en m² ; la médiane est écrite en bout de ligne.

### Élément signature — la règle

Chaque KPI est une **règle graduée** : les projets similaires y sont de petits points neutres, la boîte des quartiles un aplat léger, le **ratio combiné un trait vertical**, et le projet étudié **le seul point en accent**. On lit d'un coup d'œil s'il est dans le peloton, en tête ou décroché, sans lire un chiffre. À droite, l'écart traduit en m² : c'est ce qui parle au développement immobilier (« 360 m² de construction en moins que la référence »). Toutes les règles d'une famille partagent la même largeur, pas la même échelle (chaque ratio a son domaine) : l'échelle est écrite aux deux bouts.

### Tokens

Mêmes rôles que l'application, déclarés une fois en variables CSS (`--surface`, `--text`, `--text-2`, `--accent`, `--divider`, `--ok`, `--warning`) avec leurs valeurs claires et sombres (§2). Aucune couleur de série : seul l'accent distingue le projet étudié ; les autres projets sont en `--text-2`. ▲ favorable en `--ok`, ▼ défavorable en `--warning`, toujours avec le glyphe et le mot dans l'infobulle. Polices : Segoe UI Variable, chiffres tabulaires ; ID et codes SIA en Cascadia Mono.

### Sens des ratios (contrat moteur → page)

Chaque KPI reçoit un **sens** dans `benchmark.json` : `+1` plus haut = favorable (SUP/SP, SVN/SP, SN/SP), `−1` plus bas = favorable (SC, SD, SI, SUS hors-sol, sous-sol, façade/SP), `0` neutre (vitrage, hauteur, programme). La traduction en m² n'existe que pour les ratios de surface : écart × dénominateur du projet.

### États non-nominaux

| Zone | État | Rendu |
|---|---|---|
| Page | benchmark.json absent ou illisible | « La base n'a pas encore été lue. Revenez à l'accueil et relisez la base. » |
| Comparer | Projet sans le ratio (ex. pas d'USPI) | Ligne présente, « donnée absente du MDP » en secondaire, pas de règle |
| Comparer | Moins de 3 projets dans la référence | Trait de référence en pointillé + « référence fragile » |
| Comparer | Aucun projet similaire (filtres) | « Aucun projet ne passe ces filtres. » + « Retirer les filtres » |
| Typologies | Aucun logement avec chambres | « Aucun MDP fiable ne donne les chambres de ses logements. » |
| Hôte | WebView2 absent | Message dans l'écran : « Le composant Microsoft Edge WebView2 est requis » + lien d'installation |

### Passe B — auto-critique

- **Générique ?** Premier jet : une grille de tuiles KPI avec un grand chiffre chacune (style Power BI). Rejeté : un chiffre seul ne dit pas où l'on se situe ; la règle montre la position dans le groupe, et le m² dit ce que ça coûte.
- **Charge cognitive** : 13 règles sur un écran. Groupées en 5 familles avec titre, la famille Rendement en premier ; les règles sont fines (une ligne de 44 px), l'écran tient sans défiler à 1 080 px de haut.
- **Peu de données (5 projets fiables)** : jamais de moyenne seule ni d'histogramme ; tous les points sont visibles et le *n* est toujours écrit.
- **Clavier** : onglets, liste déroulante, cases et tableau atteignables au clavier ; focus visible en accent.
- **Accessoire retiré** : un radar des familles de KPI (spectaculaire, illisible avec 13 axes de domaines différents) et une carte des cantons (4 cantons, aucune information spatiale utile).

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Bibliothèque de graphiques (ECharts, Chart.js) | Dépendance à embarquer et à suivre ; les formes nécessaires (règles, boîtes) se dessinent en SVG en quelques lignes | 27.10.2026 |
| Tuiles KPI à grand chiffre | Pas de position relative, pas de *n* | 27.10.2026 |
| Tableau Base coloré en carte de chaleur | Avec 5 projets fiables, la couleur exagère des écarts non significatifs ; glyphe ▲/▼ plus honnête | 27.10.2026 |
| Fenêtre séparée pour le dashboard | Deuxième fenêtre à gérer ; l'app fonctionne déjà en écrans successifs | 27.10.2026 |
| Radar des KPI | 13 axes de domaines différents, illisible | 27.10.2026 |

### Revue visuelle (Phase 2, 27.10.2026)

Page servie en local (`dashboard/`, base des 10 MDP) : 1 440 px en sombre, 375 px (téléphone) en clair, trois vues. Écran hôte WPF compilé et lancé ; affichage de la page dans WebView2 confirmé par l'utilisateur dans l'application.

| Constat | Classe | Suite |
|---|---|---|
| Règles en SVG étiré (`preserveAspectRatio="none"`) : points ovales, graduations écrasées | Bloquant | Corrigé : règle en HTML positionné en %, points ronds à toutes les largeurs |
| À 800 px, la grille Comparer débordait en largeur | Bloquant | Corrigé : sous 1 000 px, la liste des similaires passe au-dessus et chaque KPI tient sur deux lignes ; aucun défilement horizontal à 375 px |
| Typologies : effectifs coupés (« 14 logements, 2 pro… ») | Bloquant | Corrigé : colonne de droite élargie |
| Trait de référence caché sous le point du projet quand les deux coïncident (SN / SP de La Bâtie) : il semble pointillé | Mineur | Accepté : l'écart chiffré (± 0,1 pt) lève l'ambiguïté |

---

## Évolution 3.2 — Mon projet (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.2 — 27.10.2026 · Phase 12 de `docs/V3_PLAN.md`

### Ancrage

Jusqu'ici on ne compare que des projets déjà dans la base. Le vrai besoin du développement immobilier est en amont : **un projet en conception, qui n'a pas encore de MDP**. Deux portes d'entrée :

1. **Saisie rapide** dans le dashboard (faisabilité, concours) : quelques chiffres tirés d'un tableau de surfaces d'architecte. Fonctionne aussi sur le web.
2. **Projet ouvert dans SIA Check** (avant-projet modélisé dans Treegram) : ses surfaces, corrections comprises, envoyées au dashboard d'un clic.

Dans les deux cas, le projet est comparé exactement comme un projet de la base (mêmes ratios, mêmes projets similaires, même règle), mais il n'entre jamais dans les références.

### Emplacement — décision

Pas de nouvel onglet : « Mon projet » est un **choix de plus dans la liste Projet** de la vue Comparer, en tête de liste (groupe « Mon projet »). Le choisir ouvre, au-dessus des règles, un **panneau de saisie repliable** ; les règles se mettent à jour à chaque champ saisi.

```
COMPARER ─────────────────────────────────────────────────────────────────────────────────────
  Projet  [★ Mon projet : Chemin des Vignes ▾]   Référence : 5 projets similaires · ratios combinés

┌ PROJETS SIMILAIRES ──────────┐  ┌ MON PROJET ─────────────────────────────────────── [Replier ▴] ┐
│ ☑ 1712 La Myonaz      ●●●●○  │  │ Nom [Chemin des Vignes      ]  Catégorie [Logement ▾]  Intervention [Neuve ▾]  Canton [VD]│
│ ☑ 1746 Avallons       ●●●●○  │  │ SURFACES (m²)                                                                 │
│ …                            │  │ SP hors-sol [4 200]  SP sous-sol [1 600]  SUP hors-sol [3 050]  SD hors-sol [  ]│
│                              │  │ SI [  ]  SUS hors-sol [  ]  SVN [  ]  Façade [  ]  VB (m³) [  ]               │
│                              │  │ PROGRAMME   Logements : studio [2] 1 ch. [10] 2 ch. [12] 3 ch. [8] 4 ch. [0] · étages hors-sol [5] │
│                              │  │ PRIX DE VENTE (facultatif)  [9 500] CHF / m² de SVN                           │
│                              │  │ 7 ratios calculables sur 13 · les champs vides laissent la ligne « donnée absente » │
│                              │  └───────────────────────────────────────────────────────────────────────────────┘
│                              │  ┌ RENDEMENT ──────────────────────────────────────────────────────────────────┐
│                              │  │ SUP hors-sol / SP hors-sol  ce projet 72,6 %  réf. 71,8 %   ▲ +0,8 pt         │
│                              │  │ ─────·──[▒▒│▒◉▒]──·──────                       +34 m² de SUP · ≈ +323 000 CHF │
└──────────────────────────────┘  └─────────────────────────────────────────────────────────────────────────────┘
```

- Champs **facultatifs** sauf SP hors-sol : chaque ratio ne s'affiche que si ses deux termes sont saisis (« donnée absente » sinon, comme pour un MDP incomplet). Un compteur dit combien de ratios sont calculables.
- **Projets similaires** : calculés dans la page avec la même formule que le moteur (écart moyen normalisé sur SP hors-sol, logements, étages, part de sous-sol, part de grands logements), d'où la nécessité de saisir au moins deux de ces cinq valeurs ; sinon « Saisissez au moins la SP hors-sol et le nombre de logements pour trouver des projets similaires. »
- **CHF** : seulement sur la famille Rendement (m² de SUP ou de SVN × prix de vente saisi), précédé de « ≈ » et arrondi au millier. Les pertes restent en m² : les convertir demanderait un coût de construction, qui n'est pas l'objet ici.
- La saisie est gardée dans le navigateur (le poste de chacun), pas dans la base. Bouton « Effacer la saisie ».

**Depuis SIA Check** : dans l'espace de revue, menu **Exporter → Comparer au benchmark**. L'app calcule les totaux du projet ouvert (corrections appliquées, même lecture que le MDP) et ouvre le dashboard sur « ★ Mon projet : *nom* (SIA Check) », panneau de saisie prérempli et en lecture seule (les surfaces viennent du modèle).

### Tokens

Aucun nouveau. Le ★ et le panneau de saisie utilisent `--surface` et `--accent` (focus) ; les champs suivent le style des contrôles de la page (32 px, filet, rayon 4).

### États non-nominaux

| Zone | État | Rendu |
|---|---|---|
| Saisie | Aucun champ rempli | Panneau ouvert, règles « donnée absente », invitation : « Saisissez la SP hors-sol et le nombre de logements pour commencer. » |
| Saisie | Valeur impossible (SUP > SP, négatif) | Champ bordé VerdictError + phrase sous le champ (« La SUP dépasse la SP hors-sol. ») ; le ratio n'est pas calculé |
| Similaires | Moins de 2 caractéristiques | Message ci-dessus, pas de référence |
| SIA Check | Projet non analysé ou analyse périmée | Le menu lance d'abord l'analyse (comme l'export MDP) |

### Passe B — auto-critique

- **Générique ?** Premier jet : un formulaire long de 30 champs calqué sur le MDP. Rejeté : en faisabilité on a 4 ou 5 chiffres. Neuf surfaces, le mix et un prix suffisent ; tout est facultatif.
- **Deux formules de distance (Python et JS)** : risque de divergence. Parade : la page recalcule au chargement les distances entre projets de la base et les compare à celles du moteur ; un écart est signalé dans la console de développement et par un test.
- **Charge** : le panneau de saisie pousse les règles vers le bas ; il est repliable et se replie seul quand le projet vient de SIA Check.
- **Accessoire retiré** : plusieurs « Mes projets » enregistrés sous des noms. Utile plus tard (V3_PLAN, phase web) ; ici une seule saisie suffit à tester l'usage.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Onglet « Mon projet » séparé | Dupliquerait la vue Comparer ; un projet saisi se compare comme les autres | 27.10.2026 |
| CHF sur tous les ratios | Les pertes demandent un coût de construction, pas un prix de vente ; mélange trompeur | 27.10.2026 |
| Saisie enregistrée dans la base (dossier MDP) | La base ne contient que des MDP contrôlés ; un projet saisi n'est pas fiabilisé | 27.10.2026 |
| Liste de projets saisis nommés | Prématuré ; une saisie suffit pour la V3 | 27.10.2026 |

### Écarts au plan, décidés à l'implémentation

- **Retour du dashboard** : la flèche ← ramène au projet ouvert quand on vient de « Comparer au benchmark », à l'accueil sinon (au lieu de ⌂ Accueil, qui fermait le projet).
- **Pas d'analyse préalable** : « Comparer au benchmark » relit le .tgm avec le journal de corrections, comme l'export MDP ; le projet comparé est donc toujours à jour, analysé ou non.

### Revue visuelle (Phase 2, 27.10.2026)

Saisie testée dans la page (1 440 px, sombre) ; parcours complet testé dans l'application (thème clair) : L'Orée ouvert → Exporter → Comparer au benchmark → dashboard sur « ★ Mon projet : L OREE (SIA Check) ».

| Constat | Classe | Suite |
|---|---|---|
| Concordance des distances page / moteur sur les 10 MDP | Vérifié | Écart maximal 0,0005 (arrondi du moteur au millième) ; la page le recalcule à chaque chargement |
| Ligne sans donnée d'un projet saisi : « Donnée absente du MDP » | Mineur | Corrigé : « Non saisi » |
| L'Orée (16 % de commerces, « Logement mixte ») : aucun projet similaire avec le filtre de catégorie, la base fiable ne comptant que du logement | Accepté | Comportement voulu ; « Retirer les filtres » donne la comparaison. À revoir quand la base aura des projets mixtes fiables |
| En-tête « cochez au moins un projet similaire » alors que la liste est vide | Mineur | Corrigé : « aucun projet similaire » |
| Saisie : SUP supérieure à la SP hors-sol | Vérifié | Champ signalé, ratio non calculé |

---

## Évolution 3.3 — Programmation inverse (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.3 — 27.10.2026 · Phase 13 de `docs/V3_PLAN.md`

### Ancrage

- **Moment** : acquisition, faisabilité. On connaît la constructibilité (SP hors-sol permise par le règlement), le gabarit (étages) et le programme visé (mix). On ne connaît pas encore le plan.
- **Question** : *« Avec 4 200 m² de SP hors-sol, combien de m² vendables, de logements, de sous-sol dois-je attendre ? »*
- **Différence avec Comparer** : Comparer part d'un projet dessiné et le juge. Programmer part d'une constructibilité et **prédit** le programme, en appliquant les ratios des projets similaires.

### Emplacement — décision

Un **quatrième onglet, « Programmer »**, entre Comparer et Base. C'est un autre travail (du terrain vers le programme), avec ses propres entrées ; le mettre dans Comparer mélangerait jugement et prédiction.

```
  Comparer · Programmer · Base · Typologies

PROGRAMMER ───────────────────────────────────────────────────────────────────────────────────
┌ HYPOTHÈSES ──────────────────────────────────────────────────────────────────────────────────┐
│ SP hors-sol [4 200] m²   Étages hors-sol [5]   Catégorie [Logement ▾]  Intervention [Neuve ▾] │
│ Mix visé (%)  studio [5] 1 ch. [30] 2 ch. [40] 3 ch. [20] 4 ch.+ [5]   = 100 %               │
│ Prix de vente (facultatif) [9 500] CHF / m² de SVN                                            │
│ D'après 5 projets similaires : 1712 La Myonaz · 1784 Sauvabelines · 1467 La Bâtie · … [modifier]│
└──────────────────────────────────────────────────────────────────────────────────────────────┘

OÙ VONT LES 4 200 m² DE SP HORS-SOL  (estimation centrale)
 ███████████████████████████████████████████████▓▓▓▓▓▓░░░░░░░░░
 SUP 3 075 m² (73 %)                              SD 300 (7 %)  construction, installations… 780 (19 %)

PROGRAMME ATTENDU                       bas (P25)     central       haut (P75)    d'après
 SUP hors-sol                            2 940 m²      3 075 m²      3 110 m²      SUP / SP hors-sol (n = 5)
 Surface de vente nette (SVN)            3 150 m²      3 920 m²      4 160 m²      SVN / SP hors-sol (n = 4)
 Logements (mix visé)                       41            43            44         SUP ÷ surface moyenne du mix (Typologies)
   dont studio · 1 ch. · 2 ch. · 3 ch. · 4 ch.+    2 · 13 · 17 · 9 · 2
 SP sous-sol                             2 340 m²      2 380 m²      2 600 m²      SP sous-sol / SUP (n = 5)
 Façade                                  3 070 m²      3 700 m²      4 540 m²      Façade / SP hors-sol (n = 4)
 Chiffre d'affaires (SVN × prix)         ≈ 29,9 M      ≈ 37,2 M      ≈ 39,5 M CHF
```

Hiérarchie : **1er** la barre « où vont les m² » (ce que la constructibilité devient) · **2e** le tableau bas / central / haut · **3e** la ligne « d'après » (sur quoi repose chaque chiffre).

### Les règles du calcul

- **Projets similaires** : la même formule que partout (§4.4), sur ce qui est connu à ce stade : SP hors-sol, étages hors-sol, part de grands logements (tirée du mix). Il en faut au moins deux ; sinon, toute la base fiable passant les filtres, avec la mention « faute de caractéristiques, tous les projets fiables ». La liste est modifiable (cases), comme dans Comparer.
- **Central** = ratio combiné du groupe ; **bas / haut** = 1er et 3e quartiles des projets du groupe. « bas » et « haut » sont les valeurs, pas le favorable ou le défavorable.
- **Logements** : SUP ÷ surface moyenne d'un logement du mix, chaque typologie prise à sa médiane (onglet Typologies, toute la base fiable). Sans mix : SP hors-sol ÷ (SP hors-sol par logement) du groupe. Arrondi à l'unité.
- **Chiffre d'affaires** : SVN × prix, en millions, arrondi au 100 000 CHF, précédé de « ≈ ».
- Une grandeur dont aucun projet du groupe n'a le ratio est absente du tableau (« pas de donnée dans les projets similaires »).

### Élément signature — la barre « où vont les m² »

L'arbre du m² de V3_PLAN §4.2, en une barre : la SP hors-sol découpée en SUP, SD, SUS hors-sol et le reste (construction, installations), à l'estimation centrale. Ici, et seulement ici dans le dashboard, les **couleurs de la légende SIA 416** (SUP `#D5003B`, SD `#F2E900`, SUS `#F0A900`) : c'est la même règle que dans l'application (« le remplissage dit la catégorie SIA »). Le reste est un aplat neutre hachuré. Chaque segment porte son libellé et son aire en texte (jamais la couleur seule) ; 2 px de surface entre segments.

### États non-nominaux

| État | Rendu |
|---|---|
| SP hors-sol vide | Invitation : « Saisissez la SP hors-sol constructible pour estimer le programme. » ; barre et tableau masqués |
| Mix ≠ 100 % | Total écrit en VerdictWarning (« = 95 % ») ; le calcul normalise les parts |
| Typologie du mix sans médiane dans la base (ex. 4 ch. : 1 projet) | Médiane utilisée quand même, marquée « (1 projet) » dans l'infobulle |
| Groupe de moins de 3 projets | « Estimation fragile : 2 projets » au-dessus du tableau |

### Passe B — auto-critique

- **Générique ?** Premier jet : un formulaire qui renvoie un seul chiffre par grandeur. Rejeté : avec 5 projets, un chiffre seul promet une précision qui n'existe pas. Bas / central / haut et la ligne « d'après » disent sur quoi on s'appuie.
- **Couleurs SIA dans le dashboard** : rompt la règle « une seule couleur de donnée » de l'Évolution 3.1. Assumé ici parce que la barre montre des catégories SIA, que l'utilisateur de SIA Check connaît ces couleurs, et que le texte porte l'information.
- **Accessoire retiré** : un curseur « optimiste / pessimiste ». Bas / haut le disent sans interaction de plus.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Programmation dans l'onglet Comparer | Mélange jugement d'un projet dessiné et prédiction depuis une constructibilité | 27.10.2026 |
| Un seul chiffre par grandeur | Fausse précision avec 5 projets | 27.10.2026 |
| Fourchette min–max | Tirée par un seul projet atypique ; les quartiles sont plus stables | 27.10.2026 |
| Curseur optimiste / pessimiste | Redondant avec bas / haut | 27.10.2026 |

### Revue visuelle (Phase 2, 27.10.2026)

Page servie en local, 1 440 px en sombre et 375 px en clair. Cas testé : 4 200 m² de SP hors-sol, 5 étages, mix 5 / 30 / 40 / 20 / 5 %, 9 500 CHF/m² → 5 projets similaires ; SUP 3 029 – 3 075 – 3 106 m², SVN 3 736 – 3 917 – 4 364 m², 43 logements, SP sous-sol 1 741 m², CA ≈ 37,2 M CHF.

| Constat | Classe | Suite |
|---|---|---|
| En-tête « D'après » aligné à droite au-dessus d'une colonne de texte | Mineur | Corrigé |
| Répartition « 13 1 chambre · 17 2 chambres » difficile à lire | Mineur | Corrigé : « 13 × 1 ch. · 17 × 2 ch. » |
| SP seule (sans étages ni mix) : toute la base fiable, mentionnée ; logements par SP hors-sol par logement | Vérifié | — |
| SP vide : invitation, barre et tableau masqués ; à 375 px, aucun défilement horizontal | Vérifié | — |

---

## Évolution 3.4 — Identité des projets (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.4 — 27.10.2026 · Phase 15 de `docs/V3_PLAN.md` (§9)

### Ancrage

Le benchmark devient multi-typologies : on sélectionne « Santé » puis « Vaud ». Un projet mal identifié est donc un projet **invisible ou mal rangé**. L'identité doit être saisie une fois, au bon moment, et écrite dans le MDP (seule source de vérité, lue aussi par le Power BI).

### La fiche « Identité du projet »

Un dialogue unique, le même partout :

```
┌ Identité du projet ─────────────────────────────────────────────────┐
│ ID projet HRS *   [1778      ]      Nom du projet *  [L'Orée      ] │
│ Typologie *       [Logement (100-90% SU)                        ▾]  │
│ Canton *          [VD ▾]            Commune          [Lausanne    ] │
│ Type d'intervention * [Nouvelle construction                    ▾]  │
│ Phase SIA         [53 ▾]                                             │
│                                                                      │
│ * nécessaire pour entrer dans le benchmark                           │
│                                          [Annuler] [Enregistrer]     │
└──────────────────────────────────────────────────────────────────────┘
```

- Listes déroulantes = les listes du gabarit MDP (feuille « Listes formulaire ») : typologies (Logement, Logement mixte, Activités, Industriel, École, Hôtel, Sport, EMS, Santé, Centre commercial, Autre), cantons en abréviation, types d'intervention, phases SIA. Pas de saisie libre là où une liste existe : c'est ce qui rend la sélection fiable.
- « Typologie » est le libellé visible de la « Catégorie d'ouvrage » du MDP (le mot de l'équipe).
- Préremplie : avec la dernière saisie pour ce dossier (comme l'ID aujourd'hui), sinon avec ce que contient le MDP.
- **Enregistrer** reste actif même incomplet ; un rappel discret dit ce qui manque pour le benchmark.

### Où elle apparaît

| Point d'entrée | Rôle |
|---|---|
| Espace de revue → Exporter → Tableau MDP… | Remplace le petit dialogue « Projet HRS » (ID et nom) : l'identité complète part dans `InfosProjet` |
| Accueil, Fiabilisation → ⇥ Ajouter à la base | Ouverte d'office ; les champs * sont **obligatoires** avant l'export dans la base |
| Accueil, Benchmark → clic sur un MDP de la base | Complète ou corrige l'identité d'un MDP existant : écrit dans sa feuille `InfosProjet`, puis relit la base |

### Accueil, liste de la base (delta)

```
  1714  Le Clos des Hêtres   Logement   VD   ▮▮▮▮▮▮▮▮▮▮  ✓
  1747  Gare Casino          Log. mixte FR   ▮▮▮▮▯▮▯▯▯▮  △
  1746  Avallons             Non identifié —  ▮▮▮▮▮▮▮▮▮▯  ✓     ← en VerdictWarning, invite à cliquer
```

- Nouvelle colonne **Typologie** (libellé court), avant le canton : c'est désormais la première dimension du benchmark.
- Les lignes deviennent **cliquables** (style des lignes de projets actifs) : clic = fiche Identité.

### Côté moteur

- Fin de la déduction de la typologie à partir des affectations : une typologie absente reste vide, affichée « Non identifiée ».
- Écriture de l'identité dans un MDP existant sans toucher au reste du classeur (même mécanisme que l'export MDP, qui conserve listes et mises en forme).

### États non-nominaux

| État | Rendu |
|---|---|
| MDP ouvert dans Excel au moment d'écrire | « Le fichier est ouvert dans Excel : fermez-le puis réessayez. » ; rien n'est écrit |
| Ajouter à la base, identité incomplète | Enregistrer reste possible, mais « Exporter dans la base » est désactivé avec la liste de ce qui manque |
| ID déjà utilisé par un autre MDP de la base | Avertissement : « La base contient déjà le projet 1778 (MDP-1778-Loree.xlsx). Le remplacer ? » |

### Passe B — auto-critique

- **Générique ?** Premier jet : ajouter les champs un à un au dialogue texte existant. Rejeté : des champs libres redonneraient « Vaud », « VD », « vaud » et la sélection redeviendrait floue. Les listes du gabarit sont la vraie valeur ajoutée.
- **Friction** : rendre l'identité obligatoire à chaque export MDP gênerait un export de travail ; elle n'est obligatoire que pour entrer dans la base.
- **Accessoire retiré** : les champs techniques (labellisation, système de chauffage, façade…) du Power BI. Utiles un jour comme filtres, mais pas nécessaires pour sélectionner par typologie et canton.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Champs texte libres | Variantes d'orthographe, sélection non fiable | 27.10.2026 |
| Identité dans un fichier séparé | Deux sources à aligner ; décision : le MDP fait foi | 27.10.2026 |
| Identité obligatoire à tout export MDP | Bloquerait les exports de travail | 27.10.2026 |
| Déduire la typologie des affectations | Logique logement ; un immeuble de bureaux serait classé « Logement mixte » | 27.10.2026 |

### Revue visuelle (Phase 2, 27.10.2026)

Accueil capturé après relecture de la base (thème clair) : colonne Typologie présente, « Non identifié » en VerdictWarning pour 1746, 1784, 1280 et 1778, typologies lues pour les 6 autres (Logement, Log. mixte). La fiche Identité n'a pas pu être capturée (le bureau Windows gardait le premier plan) ; testée par l'utilisateur dans l'application.

| Constat | Classe | Suite |
|---|---|---|
| L'ID d'un MDP de la base est modifiable | Évité | Lecture seule dans la fiche ouverte depuis la base : il relie toutes les tables du MDP |
| Anciennes valeurs hors liste (MDP rempli à la main) | Prévu | Affichées en tête de liste pour être corrigées, jamais effacées en silence |

---

## Évolution 3.5 — Sélection et onglet Ratios (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.5 — 27.10.2026 · Phase 16 de `docs/V3_PLAN.md` (§9)

### Ancrage

Le parcours de l'équipe : *« nouveau projet de santé à Vaud → je choisis Santé, je lis les ratios ; puis j'affine sur Vaud »*. La sélection vient **avant** tout le reste ; le dashboard actuel la cache dans des filtres de similarité.

### Emplacement — décision

1. Une **barre de sélection** sous les onglets, toujours visible, commune à toutes les vues.
2. Un nouvel onglet **« Ratios »**, en premier et ouvert par défaut : ce que donne la sélection.
3. Les autres onglets travaillent **dans** la sélection.

```
  Ratios · Comparer · Programmer · Base · Typologies
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Typologie [Santé (4) ▾]   Canton [VD (2) ▾]   Intervention [Toutes ▾]      2 projets fiables · Réinitialiser │
└──────────────────────────────────────────────────────────────────────────────────────────────┘

RATIOS ─ Santé · VD ──────────────────────────────────────────────────────── 2 projets fiables sur 3
 ⚠ 2 projets : référence fragile. Élargir : retirer le canton (4 projets)

 KPI CLÉS
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ SUP hors-sol / SP hors-sol          71,8 %   médiane 72,1 % · quartiles 69,5 – 74,0 % · n = 4 │
 │ 60 % ───────·──[▒▒▒▒│▒▒▒]──·─────── 85 %                                                  │
 │ Vitrage / façade                    34,0 %   …                                            │
 │ Façade / SP hors-sol (compacité)    88,2 %   …                                            │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
 RENDEMENT · PERTES · SOUS-SOL · COMPACITÉ · PROGRAMME   (mêmes règles, plus compactes)

 PROJETS DE LA SÉLECTION
  1714 Le Clos des Hêtres   Logement  VD   SUP/SP 81,1 %   meilleur quart   [Comparer →]
  1467 La Bâtie             Logement  GE   72,1 %          2e quart
  …   (écartés en grisé, pour mémoire)
```

Hiérarchie : **1er** les KPI clés de la sélection (valeur combinée en grand, puis dispersion) · **2e** la position des projets (la règle et la liste) · **3e** les autres familles.

### La barre de sélection

- Listes alimentées par les valeurs présentes dans la base, chacune avec son nombre de projets fiables (« Santé (4) »), recalculé selon les autres choix. « Toutes / Tous » par défaut ; « Non identifiée » existe dans Typologie pour retrouver les MDP à compléter.
- Résumé à droite : « n projets fiables » ; « Réinitialiser » quand une sélection est active.
- La sélection est gardée (navigateur) et inscrite dans l'adresse de la page (`?typologie=Santé&canton=VD`) : un lien partagé ouvre la même sélection, utile pour la version web.

### L'onglet Ratios

- **KPI clés en tête** : SUP / SP hors-sol, vitrage, compacité. Tant que la phase 17 n'a pas fixé « vitrée / pleine » et le coefficient de forme, ce sont « Vitrage / façade » et « Façade / SP hors-sol », signalés comme provisoires. Valeur combinée en grand, médiane, quartiles et *n* à côté ; dessous, la règle avec **chaque projet** (point neutre ; survol : nom et valeur ; clic : Comparer ce projet).
- **Autres familles** : les mêmes règles, plus compactes.
- **Projets de la sélection** : tableau avec la position de chacun sur SUP / SP dans la sélection (meilleur quart… dernier quart, selon le sens du ratio : V3_PLAN §9, « indice de performance »). Écartés en grisé.

### Les autres onglets dans la sélection

| Onglet | Effet |
|---|---|
| Comparer | Projets similaires cherchés parmi les fiables de la sélection ; les cases « même catégorie / même intervention » disparaissent (remplacées par la barre) |
| Programmer | Idem ; ses listes Catégorie et Intervention disparaissent |
| Base | Ne liste que la sélection ; « Ensemble » = ratios combinés de la sélection |
| Typologies | Calculées sur les logements des projets de la sélection ; hors logement : « Les typologies de logement ne concernent pas cette sélection. » |

### États non-nominaux

| État | Rendu |
|---|---|
| Aucun projet fiable dans la sélection | « Aucun projet fiable pour Santé · VD. » + suggestion d'élargissement chiffrée (« sans le canton : 4 projets ») + Réinitialiser |
| 1 ou 2 projets | Valeurs affichées, bandeau « référence fragile » et la même suggestion |
| Projet ouvert dans Comparer hors de la sélection | Il reste comparé ; mention « hors sélection » sous son nom |

### Passe B — auto-critique

- **Générique ?** Premier jet : des filtres façon Power BI (segments cliquables à gauche). Rejeté : prend une colonne entière pour trois listes, et le Power BI montrait un seul projet. Une barre fine et des comptes par valeur disent tout de suite si la sélection tient.
- **Comptes dans les listes** : le chiffre entre parenthèses évite le cul-de-sac (choisir « Santé · TI » pour trouver zéro projet).
- **Accessoire retiré** : un graphique de répartition des projets par canton. Les comptes dans la liste suffisent.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Panneau de filtres latéral (segments) | Occupe une colonne pour trois listes | 27.10.2026 |
| Filtres propres à chaque onglet | Le contexte se perd en changeant d'onglet ; une sélection commune suit l'utilisateur | 27.10.2026 |
| Tuiles KPI à grand chiffre seules | Déjà rejetées (3.1) ; ici le grand chiffre reste, mais toujours avec sa règle et son *n* | 27.10.2026 |

### Revue visuelle (Phase 2, 27.10.2026)

Page servie en local (base des 10 MDP) : 1 440 px en sombre et en clair, 375 px en clair. Sélection testée : Logement (100-90 % SU) · VD → 2 projets fiables, bandeau « référence fragile » et « Élargir : sans le canton (3 projets) » ; adresse de la page mise à jour (`?typologie=…&canton=VD`) ; Comparer, Programmer, Base et Typologies restreints à la sélection ; Comparer signale « ce projet est hors sélection ».

| Constat | Classe | Suite |
|---|---|---|
| À 375 px, la rangée d'onglets débordait (« Typologies » coupé) | Bloquant | Corrigé : onglets défilants en largeur réduite ; aucun défilement horizontal de la page |
| « 1 projets » dans le titre des Typologies | Mineur | Corrigé |
| Position par quart vide sous 4 projets fiables | Voulu | Un quart n'a pas de sens sur 2 ou 3 valeurs |
| La sélection est gardée d'une visite à l'autre : un « Comparer au benchmark » depuis SIA Check peut s'ouvrir sur une sélection restreinte | À surveiller | La mention « hors sélection » et « Réinitialiser » le rendent visible |

---

## Évolution 3.6 — Enveloppe : façades et vitrages (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.6 — 27.10.2026 · Phase 17a de `docs/V3_PLAN.md` (§10)

### Ancrage

Jusqu'ici l'espace de revue ne parle que de surfaces **horizontales**, qui se somment niveau par niveau. La SFN (façade) et la SRV (vitrages) sont **verticales** : elles ne se somment pas avec la SP, mais elles portent deux KPI clés de l'équipe (vitrée / pleine, compacité). Il faut les contrôler comme le reste, sans les mélanger au bilan horizontal.

### Calques — un groupe « Enveloppe »

```
CALQUES
Intérieur        …
Extérieur        …
Enveloppe                         ← nouveau groupe, entre Extérieur et USPI · Maison
☐ ▦ SFN  Façades     71   30 138   (brute ; infobulle : nette 23 076, réservations 7 062)
☐ ▦ SRV  Vitrages    56    7 108
▸ USPI · Maison
```

- Les deux calques sont **masqués par défaut** : affichées, ces surfaces enveloppent le bâtiment et cachent les niveaux. Les cocher montre l'enveloppe, la touche « Isoler » garde son sens.
- Aire affichée : façade **brute** pour SFN (c'est la base des ratios), vitres pour SRV.

### Rendu 3D (contenu, pas chrome)

- Façade : aplat gris chaud `#A8A29E` opaque, arêtes fines. Vitrages : bleu-vert pâle `#9ED8E6` opaque, dessinés devant la façade. (D'abord translucides, passés en opaque le 27.10.2026 : la transparence WPF dépend de l'ordre de dessin et réagissait mal en vue 3D.)
- Aucune des deux ne reprend une couleur de la légende SIA 416 (qui n'en prévoit pas pour l'enveloppe) ; le bleu des vitrages est nettement plus pâle et transparent que le bleu SI, et ces surfaces sont verticales, là où toutes les SI sont horizontales.

### Contrôles — famille E (enveloppe)

| Règle | Contrôle | Verdict |
|---|---|---|
| E1 | Façade brute = nette + réservations | Erreur au-delà de la tolérance |
| E2 | SRV ≈ réservations de la façade | Information au-delà de la tolérance (vitres ≠ ouvertures : portes pleines, cadres) |
| E3 | Façade brute ≈ périmètre × hauteur brute du niveau | Alerte au-delà de 2 % |
| E4 | Vitres ≤ façade brute | Erreur |
| E5 | Niveau hors-sol avec SP mais sans façade | Alerte |

Ils entrent dans la liste des points d'attention et les sujets comme les autres règles (même glyphes, même fiche détail), avec « Enveloppe » comme catégorie. Le bilan par niveau reste horizontal : il n'est pas modifié.

### Ratios (zone Ratios de l'espace de revue)

Une famille « Enveloppe » : part vitrée (SRV / façade brute), vitrée / pleine (SRV / (façade brute − SRV)), façade / SP hors-sol. Depuis le 27.10.2026, aussi le **coefficient de forme** (SP/ENV) : SP hors-sol / (façades SFN + toitures SPT), repère 1,00–1,30 tiré de la base, comme le KPI clé du benchmark (L'Orée : 1,25). Par bâtiment et pour le projet, comme les autres ratios.

### Export MDP

Feuille SurfacesEnveloppe : « Surface vitrée » = SRV du niveau (au lieu des réservations). Brute et nette inchangées.

### États non-nominaux

| État | Rendu |
|---|---|
| Projet sans SFN ni SRV (Treegram ancien, export IFC) | Groupe Enveloppe absent ; aucun contrôle E ; ratios d'enveloppe « n/a » |
| SFN ou SRV sans géométrie dans le cache | Calque et chiffres présents ; la 3D n'affiche que les niveaux qui ont un maillage (comme pour les autres surfaces) |

### Passe B — auto-critique

- **Générique ?** Premier jet : ranger SFN et SRV avec SEP (« Extérieur »). Rejeté : ce sont des surfaces verticales qui ne participent à aucune somme ; les mêler aux catégories horizontales brouillerait le bilan.
- **Encombrement 3D** : affichées par défaut, les façades masqueraient tout le travail de contrôle horizontal ; d'où masquées par défaut.
- **Accessoire retiré** : une coupe verticale de façade dans le bilan par niveau. Belle, mais les ratios et les contrôles E suffisent au besoin.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| SFN / SRV dans le groupe « Extérieur » | Surfaces verticales, hors sommes | 27.10.2026 |
| Réservations de la SFN comme surface vitrée | Décision : SRV (vitres réelles, avec géométrie) | 27.10.2026 |
| Calques Enveloppe visibles par défaut | Masquent les niveaux en 3D | 27.10.2026 |

### Mise en œuvre et vérifications (27.10.2026)

- L'Orée : 80 SFN (30 138 m²) et 80 SRV (7 108 m²) lues ; géométrie pour 71 façades et 56 vitrages. Contrôles : E1, E3 et E4 sans écart, aucun niveau hors-sol sans façade (E5).
- **E2 : tolérance propre de 5 %**, et non la tolérance générale (0,5 m² et 0,5 %) : vitrages et réservations diffèrent normalement de 1 à 2 % (cadres, portes pleines), ce qui donnait 30 informations sans intérêt sur L'Orée. Aucune au-delà de 5 %.
- Ratios L'Orée : part vitrée 32,7 %, vitrée / pleine 48,6 %, façade / SP hors-sol 0,60.
- **Écart au plan** : l'infobulle du calque SFN ne donne pas encore la part nette et les réservations (données du moteur, non transmises à la visionneuse).
- Rendu 3D : la translucidité réagissait mal à l'écran (ordre de dessin WPF) ; façades et vitrages sont passés en opaque. La toiture SPT est affichée par défaut.
- **Bilan par niveau** (retour utilisateur) : une colonne « Façade » après l'écart R1 : mini-barre vitrages (bleu SRV) puis partie pleine (gris SFN), sur l'échelle de la plus grande façade du bâtiment (pas celle de la SP), et part vitrée en %. Infobulle : brute, nette + réservations, vitrages, pleine (ce qui manquait à l'infobulle du calque SFN).
- **Ratios d'enveloppe** (retour utilisateur) : colonne « Ratio » élargie (96 px, « SRV/PLEINE » débordait) ; repères de vraisemblance tirés de la base (part vitrée 0,20–0,45 ; vitrée / pleine 0,25–0,80 ; façade / SP 0,50–1,10), pour que la jauge s'affiche comme pour les autres ratios.

## Évolution 3.7 — Enveloppe dans le benchmark (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.7 — 27.10.2026 · Phase 17b de `docs/V3_PLAN.md` (§9, §10)

### Ancrage

L'équipe a trois KPI clés : SUP / SP, **vitrée / pleine**, coefficient de forme. Le dashboard affiche aujourd'hui « Vitrage / façade » et « Façade / SP hors-sol », marqués provisoires. La fiabilisation (3.6) produit maintenant une surface vitrée réelle (SRV) dans le MDP : le benchmark peut afficher le vrai KPI. Et la base n'est pas que du logement : les ratios par logement ne doivent plus s'imposer à une sélection Santé ou Bureaux.

### Ce que dit la base aujourd'hui

| Projet | Façade | Vitrée | Part vitrée | Vitrée / pleine | Façade / SP HS |
|---|---:|---:|---:|---:|---:|
| La Bâtie | 4 519 | 1 921 | 42,5 % | 73,9 % | 0,73 |
| Avallons | 4 416 | 1 500 | 34,0 % | 51,5 % | 1,07 |
| Le Clos des Hêtres | 2 612 | 559 | 21,4 % | 27,2 % | 1,08 |
| Les Patios (non fiable) | 8 820 | 1 836 | 20,8 % | 26,3 % | 0,67 |
| Sauvabelines | 3 515 | — | — | — | 0,81 |

4 projets sur 10 ont une surface vitrée. Les MDP déjà dans la base portent comme « vitrée » les réservations de façade : sur L'Orée, elles ne diffèrent des vitres SRV que de 0,7 %. **Pas besoin de régénérer la base pour ce KPI** ; seul un MDP sans enveloppe (L'Orée, Côté Gare…) gagne à être réexporté depuis SIA Check.

### Moteur (benchmark.py)

- Nouveau terme **PLEINE = FACADE − VITRE** (seulement si VITRE existe).
- La famille « Compacité » devient **« Enveloppe »** :

| Id | Libellé | Num / den | Sens | Statut |
|---|---|---|---|---|
| VITRE/PLEINE | Vitrée / pleine | VITRE / PLEINE | neutre | **KPI clé** |
| VITRE/FACADE | Part vitrée : vitrée / façade | VITRE / FACADE | neutre | remplace « Vitrage / façade » |
| FACADE/SP_HS | Façade / SP hors-sol | FACADE / SP_HS | plus bas = favorable | KPI clé **provisoire** (coefficient de forme) |
| VB/SP | Hauteur brute moyenne | VB / SP | neutre | inchangé |

- Sens **neutre** pour le vitrage : plus de vitrage coûte plus cher mais sert la lumière et la vente ; le benchmark situe le projet sans dire « mieux » ou « moins bien ».
- Les KPI SUP / logement et SP hors-sol / logement reçoivent un attribut `typologie: "logement"`.

### Dashboard

**Onglet Ratios — KPI clés** (chiffres des maquettes : exemples)
```
KPI CLÉS
SUP hors-sol / SP hors-sol      78,4 %   médiane … · quartiles … · n = 5   ──●──●─┃─●──
Vitrée / pleine                 51,5 %   médiane … · n = 3                  ──●───┃──●──
Façade / SP hors-sol   provisoire, en attendant le coefficient de forme     ──●─┃──●──
```
« Vitrée / pleine » n'est plus provisoire. « Part vitrée » passe dans la famille Enveloppe.

**Logement réservé au logement**
- Les KPI marqués logement ne s'affichent (Ratios, Comparer) que si la sélection est **Logement** ou **toutes typologies**. Sinon ils disparaissent sans mention : ils n'ont pas de sens pour un hôpital.
- Programmer : les lignes « Logements » et la saisie du mix ne s'affichent que pour une sélection logement (déjà le cas pour l'onglet Typologies).

**Programmer — deux lignes de plus**
```
Façade                 3 520 m²   (2 940 – 4 080)   Façade / SP hors-sol (n = 4)
  dont vitrée          1 200 m²   (  750 – 1 750)   Part vitrée (n = 3)
  dont pleine          2 320 m²                      façade − vitrée
```
Utile pour le plan financier : la façade pleine et les vitrages n'ont pas le même coût au m².

**Mon projet** : un champ « Vitrages » à côté de « Façade » dans la saisie ; les KPI d'enveloppe se calculent dès que les deux sont saisis. Depuis SIA Check, la valeur vient du MDP (SRV).

### Coefficient de forme

Défini par l'équipe DEV (27.10.2026) : **SP hors-sol / surface d'enveloppe**, l'enveloppe étant les façades hors-sol et les toitures (plancher bas non compté). Plus il est haut, plus le bâtiment est compact (un rectangle l'emporte sur une étoile : moins de périmètre pour la même surface, donc moins de coût et de pertes thermiques). Il remplace « Façade / SP hors-sol » dans les KPI clés, qui reste dans la famille Enveloppe (et sert au Programmer pour estimer la façade). Calculé seulement pour les MDP qui ont façades **et** toitures : sans toitures, il serait surestimé. Base au 27.10.2026 : n = 3 (Le Clos des Hêtres 1,03, La Bâtie 1,09, L'Orée 1,25 ; combiné 1,21). Mon projet : champ « Toitures ».

### États non-nominaux

| État | Rendu |
|---|---|
| Aucun projet de la sélection n'a de vitrée | Carte KPI clé : « Aucun projet de la sélection n'a ce ratio » (comportement existant) |
| Projet comparé sans vitrée | Ligne du KPI : « — » ; ses projets similaires restent calculés sans l'enveloppe |
| Programmer sans part vitrée dans le groupe | Ligne « Façade » seule, sans « dont vitrée / pleine » |
| Sélection non logement | Pas de KPI par logement, pas de mix, pas d'onglet Typologies (déjà) |

### Passe B — auto-critique

- **Premier jet** : régénérer toute la base avant d'afficher le KPI. Retiré : les réservations sont un très bon substitut (0,7 % d'écart sur L'Orée) ; exiger la régénération bloquerait l'équipe pour un gain négligeable.
- **Sens du vitrage** : une version « moins de vitrage = favorable » coloriait les écarts. Rejetée : ce n'est pas un ratio de rendement, et l'équipe n'a pas donné de cible.
- **Accessoire retiré** : un indicateur de la source de la vitrée (SRV ou réservations) par projet. L'écart est trop faible pour mériter un badge.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Régénérer toute la base avant 17b | Réservations ≈ SRV (0,7 %) | 27.10.2026 |
| Vitrage : sens « moins = mieux » | Pas de cible, pas un rendement | 27.10.2026 |
| Badge de source de la vitrée | Écart négligeable | 27.10.2026 |
| Message « ratios logement masqués » | Bruit pour une sélection non logement | 27.10.2026 |

### Mise en œuvre et vérifications (27.10.2026)

- Base actuelle, toutes typologies : vitrée / pleine **52,6 %** (combiné, n = 3 projets fiables : Avallons, La Bâtie, Le Clos des Hêtres ; quartiles 39,3 – 62,7 %).
- Programmer, 5 000 m² de SP hors-sol : façade 4 408 m², dont vitrée 1 519 m² et pleine 2 889 m². La fourchette de la façade pleine suit la part vitrée en sens inverse (bas = façade − vitrée haute).
- Sélection non logement : KPI par logement retirés de Ratios, Comparer et Base ; mix du Programmer masqué.
- **Écart au plan** : vitrée / pleine et part vitrée n'ont pas d'« objet » (pas d'écart traduit en m² dans Comparer), comme tout KPI neutre.
- Mon projet : une vitrée saisie sans façade est ignorée (aucun ratio d'enveloppe sans les deux).

---

## Évolution 3.8 — Fiche projet : identité et dossier dès la création (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (27.10.2026) ☑ Implémenté
> Version : 3.8 — 27.10.2026 · Phase 18 de `docs/V3_PLAN.md` (§11)

### Ancrage

Aujourd'hui, un projet de fiabilisation n'est qu'un **dossier Treegram** ouvert depuis l'accueil ; son identité (ID HRS, typologie, canton…) n'est demandée qu'au moment d'exporter le MDP, dans un dialogue qui revient à chaque export. Résultat : 4 MDP sur 10 de la base sont « Non identifié ». La demande : **renseigner l'identité à la création du projet**, avec son dossier, et pouvoir la modifier à tout moment ; le MDP produit la reprend telle quelle.

Le projet devient donc une **fiche** (identité + dossier), et non plus un simple dossier.

### La fiche projet

Un seul dialogue, à la création comme à l'édition :

```
┌ Nouveau projet ──────────────────────────────────────────────────────────┐
│ DOSSIER TREEGRAM                                                          │
│ [C:\…\Projets\L OREE\Treegram                         ] [Parcourir…]      │
│ ✓ L OREE.tgm · cache VWR présent                                          │
│                                                                           │
│ IDENTITÉ                                                                  │
│ ID projet HRS *   [1778      ]      Nom du projet *  [L'Orée          ]   │
│ Typologie *       [Logement (100-90% SU)                            ▾]    │
│ Canton *          [VD ▾]            Commune          [Lausanne        ]   │
│ Type d'intervention * [Nouvelle construction                        ▾]    │
│ Phase SIA         [53 ▾]                                                  │
│                                                                           │
│ * nécessaire pour entrer dans le benchmark. Il manque : canton.           │
│                                             [Annuler] [Créer et analyser] │
└───────────────────────────────────────────────────────────────────────────┘
```

- **Dossier** en tête : c'est lui qui rend le projet analysable. Vérifié à la sélection : un seul `.tgm`, cache VWR présent ou non (même contrôle qu'à l'ouverture aujourd'hui), message sous le champ.
- **Identité** : les champs et les listes de la fiche Identité (Évolution 3.4), inchangés. Le nom est prérempli avec le nom du dossier.
- **Obligatoire pour créer** : le dossier valide seulement. Les champs * restent un rappel (comme aujourd'hui) : on peut fiabiliser un projet dont on ne connaît pas encore le canton. Ils deviennent obligatoires pour « Ajouter à la base ».
- Bouton primaire : **Créer et analyser** à la création, **Enregistrer** à l'édition.

### Où elle apparaît

| Point d'entrée | Rôle |
|---|---|
| Accueil, Fiabilisation : **[▸ Nouveau projet…]** (remplace « Ouvrir un dossier projet… ») | Fiche vide ; Créer → analyse et ouvre l'espace de revue |
| Accueil, Projets actifs : action **✎ Fiche** sur chaque ligne (à côté de 🗑) | Édite identité et dossier sans ouvrir le projet |
| Espace de revue : clic sur le **nom du projet** dans la barre du haut | Édite la fiche du projet ouvert |
| Exporter → Tableau MDP / ⇥ Ajouter à la base | **Ne demandent plus rien** : l'identité de la fiche part dans `InfosProjet`. Seule exception : un champ manquant pour l'usage (ID pour un MDP, champs * pour la base) ouvre la fiche, avec ce qui manque |

### Projets actifs (delta)

```
PROJETS ACTIFS                                                     3
1778  L'Orée          Logement   VD   En traitement  156 pts · 21.10  ✎ 🗑
1784  Sauvabelines    Logement   VD   Traité  ⇥base   12 pts · 20.10  ✎ 🗑
 —    OUCHY B         Infos à compléter  En traitement  40 pts · 18.10  ✎ 🗑   ← VerdictWarning, clic ✎
```

- La ligne affiche le **nom du projet** de la fiche (plus le nom du dossier), précédé de l'ID en mono, puis la typologie courte et le canton, comme la liste de la base : les deux colonnes de l'accueil parlent la même langue.
- Un projet sans fiche complète (projets existants, créés avant cette évolution) : « Infos à compléter » en VerdictWarning à la place de typologie / canton.

### Changer de dossier

Cas réel : Treegram livre une nouvelle version dans un autre dossier. Changer le dossier dans la fiche **déplace tout ce que l'app garde du projet** vers le nouveau dossier : statuts et commentaires des points, décisions de corrections, revues IA, statut (en traitement / traité), identité. La dernière analyse est jetée : le projet est **réanalysé** à l'ouverture suivante (le .tgm a changé).

Avant d'enregistrer, une confirmation :

```
Changer le dossier de « L'Orée » ?
Les statuts, commentaires et décisions de corrections suivent le projet. Le projet
sera réanalysé : une correction qui vise une surface absente du nouveau .tgm le signalera.
                                                         [Annuler] [Changer de dossier]
```

### États non-nominaux

| État | Rendu |
|---|---|
| Dossier sans .tgm, ou plusieurs | Sous le champ, en VerdictError : « Aucun fichier .tgm » / « 3 fichiers .tgm : un seul attendu » ; bouton primaire désactivé |
| Cache VWR absent | Avertissement (VerdictWarning) : « Pas de cache VWR : l'analyse se fera sans 3D. » ; création possible |
| Dossier déjà utilisé par un autre projet actif | « Ce dossier est déjà celui de « Sauvabelines ». » ; bouton désactivé |
| ID déjà utilisé par un autre projet actif | Avertissement non bloquant : « L'ID 1778 est aussi celui de « L'Orée (ancienne livraison) ». » |
| Dossier d'un projet devenu introuvable (déplacé, réseau absent) | Ligne de projets actifs en VerdictWarning « Dossier introuvable » ; ✎ permet de le repointer |
| Projet ouvert dont on change le dossier | Enregistrer ferme l'espace de revue et rouvre le projet sur le nouveau dossier (analyse) |

### Passe B — auto-critique

- **Premier jet** : rendre toute l'identité obligatoire à la création. Rejeté : le coordinateur BIM n'a pas toujours le canton ou le type d'intervention au premier jour ; bloquer la fiabilisation pour ça serait contre-productif. La contrainte reste là où elle compte : l'entrée dans la base.
- **Friction** : le dialogue d'identité à chaque export disparaît ; la fiche est remplie une fois.
- **Risque** : changer de dossier pourrait faire perdre le travail de vérification. D'où le déplacement des données, la confirmation explicite et la réanalyse (les corrections orphelines sont déjà signalées par le moteur).
- **Accessoire retiré** : un historique des dossiers successifs d'un projet. Utile pour la traçabilité, mais rien ne le demande aujourd'hui.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Identité entièrement obligatoire à la création | Bloque la fiabilisation pour des infos administratives | 27.10.2026 |
| Écrire la fiche dans le dossier Treegram (fichier à côté du .tgm) | Le dossier change d'une livraison à l'autre ; la fiche doit lui survivre | 27.10.2026 |
| Garder le dialogue d'identité à chaque export MDP | Redemande ce qui est déjà connu | 27.10.2026 |
| Historique des dossiers successifs | Pas demandé | 27.10.2026 |

### Mise en œuvre et vérifications (27.10.2026)

- Fiche projet et fiche Identité partagent les mêmes champs (un seul formulaire dans le code) ; le nom du projet suit le nom du dossier choisi tant qu'il n'a pas été saisi à la main.
- Raccourci : **Ctrl+N** (Nouveau projet) remplace Ctrl+O.
- **Retour utilisateur** : « Nouveau projet… » ouvre d'abord l'explorateur de dossiers, comme avant, puis la fiche préremplie (dossier, nom) ; dans la fiche, le champ du dossier rouvre l'explorateur au clic. Fiches élargies à 680 px (la boîte WPF-UI coupait les champs) ; le bouton principal reste toujours visible (WPF-UI masque un bouton désactivé) et un dossier refusé est signalé à la validation.
- Changer de dossier déplace statuts et commentaires, décisions de corrections, revues IA, statut du registre (`projets.json`, lu par n8n) et identité ; l'analyse, son journal et les caches de l'aperçu sont supprimés (réanalyse).
- Un projet créé apparaît dans les projets actifs dès sa création, même si l'analyse échoue.
- Tests : contrôle du dossier, dossier déjà pris, ID en double, déplacement des données, refus du changement, création, identité reprise sans dialogue, fiche ouverte quand l'ID manque, dossier introuvable listé.
- **Non vérifié à l'écran** : rendu du dialogue et de la liste des projets actifs ; à regarder dans l'application.

---

## Retour utilisateur — sujets et points (27.10.2026)

- **Construction implicite** : les résidus R1 (SC) et R3 (SEC) compatibles avec la surface de construction (verdict INFO) ne sont plus des points d'attention (Treegram ne crée pas ces surfaces : le résidu est attendu). Ils restent contrôlés et visibles au bilan par niveau ; au-delà de la fourchette plausible, le résidu reste une erreur. L'Orée brut : 19 points au lieu de 113.
- **Sujets sans numéro** : un sujet du moteur dont la revue IA a repris toutes les corrections lui cède ses points (S1 reprend les 9 points des abords : plus de doublon « corriger » sans correction) ; un sujet IA vide et un sujet sans correction dont aucun point n'est ouvert ne sont plus listés.
- **Tableau MDP** : les propositions (affectation, forme, typologies) sont regroupées en fin de liste sous l'intertitre « Tableau MDP », étiquette « MDP » au lieu de « règle ».
- **Carte du sujet** : elle liste ses points ouverts (verdict, lieu, titre, écart) ; un clic ouvre le point dans l'onglet Points et l'isole en 3D.


---

## Évolution 4.0 — Génération depuis l'IFC (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (28.10.2026) ☑ Implémenté
> Version : 4.0 — 28.10.2026 · Phase 25 de `docs/V4_PLAN.md` (§3.4)
> Aucune nouvelle couleur. Tout reprend §2 : graphite, accent pervenche, légende SIA, et la règle « le remplissage dit la catégorie, le trait dit le verdict ».

### Ancrage

- **Troisième métier, en amont des deux autres.** Le coordinateur BIM n'a pas toujours de projet Treegram, mais il a la maquette architecte. Le moteur en tire les surfaces SIA. L'humain et l'IA tranchent ce que les règles n'ont pas su décider. Le projet entre ensuite dans la Fiabilisation, puis dans la base.
- **Job de la section** : *transformer une maquette en projet de surfaces fiable, en ne regardant que les espaces où le moteur hésite.*
- **Le lien** : Génération → Fiabilisation → Benchmark. L'accueil le montre de gauche à droite.

### Emplacement — décisions

1. **Accueil : une troisième colonne, à gauche.** Le flux se lit dans l'ordre du travail : Génération, Fiabilisation, Benchmark. Les trois colonnes sont égales, et `HomeMaxWidth` passe de 1 360 à 1 800.
2. **Pas de deuxième visionneuse.** Un projet généré s'ouvre **dans l'espace de revue existant**. Il y retrouve la même 3D, les mêmes calques, le même bilan par niveau, les mêmes sujets et points : c'est tout l'intérêt du format au modèle Treegram. La génération y ajoute trois choses :
   - **un troisième onglet du panneau droit, « Espaces »**, à côté de « Sujets » et « Points d'attention ». Il n'apparaît que pour un projet généré.
   - **un calque « Maquette IFC »**, dans un groupe « Contexte » des calques, masqué par défaut. Il montre murs, dalles, poteaux et toits en gris translucide. Le moteur l'écrit dans `generation/maquette.json`.
   - **un bouton « Régénérer »** dans la barre de commande. Il est secondaire, placé à gauche d'« Analyser », qui reste la seule action accentuée.

### Wireframe — accueil (delta)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  GÉNÉRATION                          │  FIABILISATION                      │  BENCHMARK                       │
│  Générer les surfaces SIA d'une      │  Contrôler et corriger les surfaces │  Comparer un projet à ceux qui   │
│  maquette architecte IFC.            │  d'un projet Treegram.              │  lui ressemblent.                │
│  [▸ Générer depuis un IFC…] (accent) │  [▸ Nouveau projet…] (accent)       │  [▸ Ouvrir le benchmark] (accent)│
│  La maquette doit contenir ses       │  …                                  │  …                               │
│  IfcSpace.                           │                                     │                                  │
│  PROJETS GÉNÉRÉS                 5   │  PROJETS ACTIFS                 4   │  BASE DE DONNÉES                 │
│  Afiro      ◐ 20 à trancher  28.10 ↻ │  …                                  │  …                               │
│  La-Batie-B ◐ 38 à trancher  28.10 ↻ │                                     │                                  │
│  Myonaz-1   ✓ tout tranché   28.10 ↻ │                                     │                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Ligne d'un projet généré** : le nom, puis l'**état de la décision**. C'est soit « 20 à trancher » en TextSecondary, soit « tout tranché » avec la coche StatusSeen. Viennent ensuite la date de génération et ↻ Régénérer. Un clic ouvre le projet dans l'espace de revue, sur l'onglet Espaces.
- **D'où vient la liste** : elle est lue dans le dossier des projets générés (`AppSettings.GenerationFolder`, par défaut `Documents\SIA Check - projets generes`). Tout sous-dossier qui contient `generation/rapport.json` y figure. Aucun registre de plus.
- **« Générer depuis un IFC… »** :
  1. choix du fichier .ifc ;
  2. une petite boîte avec le nom du projet (prérempli depuis le fichier) et le dossier de sortie (prérempli), puis « Générer » ;
  3. la superposition d'analyse existante montre les étapes du moteur (lecture, plans, classement, surfaces) ;
  4. à la fin, le projet s'ouvre.

### Wireframe — onglet « Espaces » (panneau droit)

```
┌ SUJETS 3 │ POINTS 1 │ ESPACES 135 ───────────────────────────┐
│ [À trancher 20 ▾]                        [✦ Analyse IA…]      │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ 0,50  S01  STOCKAGE BASE           (SUS)→(SUT)   ✦ IA      │ │
│ │ 0,70  S02  SUS_ELE_CFA             (SUS)→(SI)    ✦ IA      │ │
│ │ 0,75  N00  BUREAU DE DIRECTION      SUT          règle     │ │
│ │ …                                                          │ │
│ └───────────────────────────────────────────────────────────┘ │
│ ┌ DÉTAIL ───────────────────────────────────────────────────┐ │
│ │ STOCKAGE BASE · S1.020.09 · S01 · 97,0 m²                  │ │
│ │ Règles   SUS · dictionnaire · confiance 0,50               │ │
│ │ IA       SUT Commerce · incertain                          │ │
│ │          « Stock de 97 m² entouré d'ateliers… »            │ │
│ │ Voisins  ATELIER MSP (SUT) · STOCK MATIÈRE (SUT) · …       │ │
│ │ Code [SUT ▾]   Type [Commerce ▾]                           │ │
│ │ [Accepter la proposition] [Rejeter]   [Enregistrer ce choix]│ │
│ └───────────────────────────────────────────────────────────┘ │
│ ⓘ 3 décisions s'appliqueront à la prochaine génération [Régénérer] │
└────────────────────────────────────────────────────────────────┘
```

- **Filtre** (liste déroulante) :
  - *À trancher*, par défaut : propositions IA ouvertes, et espaces sous 0,8 de confiance sans décision ;
  - *Proposés par l'IA* ;
  - *Décidés* : décisions acceptées et manuelles ;
  - *Tous*.
- **Ligne** : de gauche à droite,
  - la confiance ;
  - le niveau, en mono ;
  - le nom de l'espace ;
  - le code : quand une proposition ou une décision le change, **le changement en pastilles SIA** `(SUS)→(SUT)`, sinon le seul code ;
  - l'origine, en mono : `règle`, `✦ IA` ou `manuel`.
  
  La liste est triée par confiance croissante.
- **Clic sur une ligne** : la surface est isolée et cadrée en 3D, comme un point d'attention (même geste, même caméra). Inversement, un double-clic sur une surface en 3D sélectionne sa ligne.
- **Détail** : les trois lectures de l'espace (règles, IA, voisins), puis la décision.
  - « Accepter la proposition » et « Rejeter » n'apparaissent que s'il y a une proposition IA ouverte.
  - « Enregistrer ce choix » écrit une décision « manuel », avec le code et le type choisis dans les listes. Les sous-types proposés sont limités à ceux du code.
  - Raccourcis : A pour accepter, R pour rejeter.
- **Bandeau du bas** : dès qu'une décision n'est pas encore appliquée, il affiche « 3 décisions s'appliqueront à la prochaine génération » et un bouton **Régénérer**.
- **« ✦ Analyse IA… »** : ouvre la boîte de la revue IA existante, avec le nombre de questions. La mécanique est la même : estimation, accord, flux, coût réel. Le bouton est désactivé s'il n'y a rien à demander, avec l'infobulle « Les règles n'hésitent sur aucun espace ».

### Élément signature — le changement en pastilles

`(SUS)→(SUT)` : deux pastilles pleines aux couleurs SIA, reliées par une flèche. On voit d'un coup d'œil *ce que la décision change dans le bilan* (l'orange passe au gris SUT, le jaune au bleu), avant de lire la moindre raison.

Dans la 3D, un espace dont la décision attend la régénération prend un **contour en pointillés** de la couleur cible : la maquette montre elle aussi ce qui va changer.

C'est la traduction directe du métier : une décision de classement, c'est une surface qui change de couleur dans la sommation.

### Carte de navigation (delta)

| Depuis | Action | Vers |
|---|---|---|
| Accueil, Génération | Générer depuis un IFC… | Choix du fichier → boîte nom / dossier → superposition (étapes du moteur) → espace de revue, onglet Espaces |
| Accueil, Génération | Clic sur un projet généré | Espace de revue, onglet Espaces |
| Accueil, Génération | ↻ | Régénération (superposition) puis espace de revue |
| Espace de revue (projet généré) | Régénérer | `--generer` (décisions acceptées appliquées), puis analyse ; la sélection et l'onglet sont conservés |
| Onglet Espaces | ✦ Analyse IA… | Boîte de la revue IA → `--reponse-ia` → liste rafraîchie sur *Proposés par l'IA* |
| Onglet Espaces | Accepter / Rejeter / Enregistrer | Journal `generation/decisions.json` (moteur), puis bandeau « à la prochaine génération » |

### Mapping fonctionnalités → emplacements

| Fonctionnalité (V4_PLAN §3.4) | Emplacement |
|---|---|
| Troisième section de l'accueil | colonne Génération, à gauche |
| Générer depuis un IFC | bouton accentué de la colonne + boîte nom / dossier |
| Projets générés récents | liste de la colonne, lue dans le dossier des projets générés |
| Vue 3D IFC + surfaces | espace de revue existant + calque « Maquette IFC » (contexte, translucide, masqué par défaut) |
| Liste des surfaces, origine, confiance, plus douteux d'abord | onglet Espaces |
| Ajustement manuel | détail de l'onglet Espaces, « Enregistrer ce choix » |
| Analyse IA (estimation, accord, appel) | « ✦ Analyse IA… » de l'onglet Espaces |
| Accepter / rejeter les propositions IA | détail de l'onglet Espaces |
| Appliquer les décisions | « Régénérer » (barre de commande et bandeau) |
| Envoyer à la Fiabilisation | implicite : le projet généré *est* déjà ouvert dans la Fiabilisation (sujets, points, export MDP) |

### États non-nominaux

| Zone | État | Rendu |
|---|---|---|
| Colonne Génération | Aucun projet généré | Invitation et bouton seuls, pas de liste vide |
| Génération | Audit bloquant (pas d'IfcSpace, aucun niveau…) | Superposition en erreur : la liste des points bloquants du moteur, mot pour mot, et « Choisir une autre maquette » |
| Génération | Bâtiment sans espace dans la maquette | Avertissement en bandeau ; la génération continue |
| Régénérer | Maquette introuvable (déplacée) | « Maquette introuvable : …\La Bâtie B.ifc. » + « Choisir la maquette… » ; le nouveau chemin est retenu |
| Onglet Espaces | Rien à trancher | « Les règles et vos décisions couvrent tous les espaces. » avec la coche StatusSeen ; un clic bascule le filtre sur *Tous* |
| Analyse IA | Pas de clé API | Bouton actif ; la boîte de la revue IA demande la clé, comme aujourd'hui |
| Analyse IA | Réponse inexploitable | Message du moteur dans la boîte ; la réponse brute reste dans `generation/reponse-ia.txt` |
| Calque Maquette IFC | `maquette.json` absent (projet généré avant la phase 25) | Calque grisé, infobulle « Régénérer pour afficher la maquette » |

### Contrat moteur → app

- `sia-check --generer` écrit aussi `generation/maquette.json` : murs, dalles, poteaux et toits, en maillages en repère local, avec la même origine que le `.siagen.json`. Il émet aussi les lignes « ÉTAPE n/N » de progression.
- `rapport.json` donne pour chaque espace le nom de sa surface générée (`surface`). L'onglet Espaces relie ainsi un espace à la 3D sans deviner.
- Décisions :
  - `--decider DOSSIER --ids … --code … --type …` pour une décision manuelle ;
  - `--accepter-ia` / `--rejeter-ia --ids …` pour les propositions.
  
  L'app ne lit que les JSON. Elle n'écrit jamais elle-même le journal.

### Passe B — auto-critique

- **Générique ?** Premier jet : un écran « Génération » à part, avec sa propre 3D, sa liste et sa barre d'outils. Rejeté : c'était un deuxième viewer à maintenir, alors que le projet généré devait de toute façon finir dans la Fiabilisation. L'onglet Espaces dans l'espace de revue garde *un seul lieu* pour un projet, de la maquette au MDP.
- **Trois boutons accentués sur l'accueil.** C'est l'extension directe de l'arbitrage 3.0 : une action primaire par colonne, un public par colonne. Au-delà de trois colonnes, il faudrait revoir l'accueil ; on n'y est pas.
- **Charge du panneau droit** : trois onglets, c'est le maximum. Le troisième n'apparaît que pour un projet généré ; un projet Treegram ne change pas.
- **Fitts / clavier** :
  - lignes d'au moins 32 px ;
  - Ctrl+3 pour l'onglet Espaces (Ctrl+1 et Ctrl+2 existent déjà) ;
  - A et R dans le détail ;
  - Entrée pour isoler en 3D, comme pour les points.
- **Point faible assumé** : à 1 456 px, chaque colonne de l'accueil fait environ 450 px, et la colonne Fiabilisation tronque davantage (les infobulles sont déjà en place). Sous 1 400 px, la colonne Génération passe sous les deux autres.
- **Accessoire retiré (Chanel)** : l'IFC complet en 3D (portes, fenêtres, mobilier). Seuls murs, dalles, poteaux et toits servent à juger un espace ; le reste encombre et pèse.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Écran Génération séparé, avec sa propre 3D | Deuxième visionneuse à maintenir ; le projet généré doit finir dans la Fiabilisation | 28.10.2026 |
| Régénérer automatiquement à chaque décision | Une génération prend de 30 s à 4 min ; on décide par lot, puis on régénère | 28.10.2026 |
| « Analyse IA » dans la barre de commande | Se confond avec la « Revue IA » de la Fiabilisation, qui ne porte pas sur les mêmes questions | 28.10.2026 |
| Accepter toutes les propositions IA d'un clic | Trop facile de valider sans lire ; on propose plutôt un filtre « sûres » et une acceptation par ligne. À rediscuter après usage | 28.10.2026 |

### Écarts au plan, décidés à l'implémentation

| Plan | Réalisé | Raison |
|---|---|---|
| Contour en pointillés de la couleur cible, sur la surface d'une décision en attente | La surface prend **déjà sa couleur cible**, par l'aperçu existant des corrections (`ScenePreview`, « reclasser ») | Cohérence avant nouveauté : c'est le geste de l'app pour « ce qui changera à la prochaine analyse ». Pas de deuxième langage en 3D. |
| « Analyse IA… » ouvre la boîte de la revue IA | Une confirmation (questions, jetons, coût estimé), puis la superposition de progression commune, et une notification avec le coût réel | La boîte de la revue IA porte un rapport et des verdicts par point, sans objet ici. La mécanique (estimation, accord, flux, coût) est la même. |
| Proportions des colonnes de l'accueil égales | Génération 0,8 · Fiabilisation 1,25 · Benchmark 1 | La colonne Fiabilisation coupait « 8 points » à 1 456 px ; la liste Génération est courte (nom, état, date). |
| Titre « … d'une maquette architecte IFC. » | « … d'une maquette IFC. » | Le titre passait sur deux lignes : le bouton de la colonne n'était plus aligné sur les deux autres. |
| Liste : nom de l'espace | Nom long d'abord (« TECHNIQUE CUISINE », « Réduit »), nom complet dans le détail et l'infobulle | Le nom court d'Afiro est un numéro (« S2.090.2 ») : la colonne n'en montrait que le numéro. |

### Revue visuelle (Phase 2, 28.10.2026)

Captures de référence ajoutées : `docs/ui-baseline/home-v4.png` (accueil en trois colonnes, thème clair), `spaces-afiro.png` (onglet Espaces, proposition IA sélectionnée, thème sombre), `spaces-context-batie.png` (calque Maquette IFC allumé, espace isolé).

| Constat | Classe | Suite |
|---|---|---|
| Liste « Projets générés » vide : le dossier Documents de Windows est redirigé vers OneDrive, les projets sont dans le profil | Bloquant | Corrigé : le dossier du profil est retenu s'il existe |
| Ligne sélectionnée de la liste des espaces : texte gris sur aplat accent, illisible | Bloquant | Corrigé : style `IssueItem` des autres listes (liseré accent) |
| « 8 points » tronqué dans la colonne Fiabilisation | Bloquant | Corrigé : proportions des colonnes |
| Titre Génération sur deux lignes, boutons désalignés | Mineur | Corrigé : titre raccourci |
| Origine (« ✦ IA ») mangée par la barre de défilement | Mineur | Corrigé : colonne élargie, marge à droite |
| Calque Maquette IFC grisé sur Afiro | Accepté | La maquette Solibri n'a que les pièces ; l'infobulle le dit |
| Le filigrane passe derrière la liste Génération | Accepté | Comme pour la Fiabilisation en V3 : contraste du texte inchangé |

Non-régression : les écrans de la Fiabilisation (barre de commande, calques, bilan, sujets) sont inchangés pour un projet Treegram. Le bouton Régénérer, le groupe Contexte et l'onglet Espaces n'apparaissent que pour un projet généré.

---

## Évolution 4.1 — Typologie du projet et repères des ratios (mode ÉVOLUTION)

> Statut : ☑ Implémenté (28.10.2026), sur demande de l'utilisateur. Delta minimal, sans nouveau composant ni nouveau token.

- **Onglet Ratios** : un bandeau (style `Banner`, liseré VerdictWarning) sous l'en-tête, dans deux cas.
  - Typologie non renseignée : « Typologie du projet non renseignée : les repères des ratios dépendent du type de bâtiment, ils ne s'appliquent pas. Proposée d'après les surfaces : Autre (parking : 98 % de la SU). » Bouton secondaire « Renseigner la typologie », qui ouvre la fiche projet avec la proposition présélectionnée.
  - Typologie hors logement : le bandeau dit que les repères (établis sur des projets de logement) ne s'appliquent pas, sans bouton.
- **Colonne Repère** : « typologie ? » ou « sans repère » à la place de la plage ; l'infobulle l'explique. La jauge n'a pas de bande de repère.
- **Analyser** : tant que la typologie manque, la fiche projet s'ouvre une fois par projet et par session, avec la typologie proposée. Annuler analyse sans repères.
- Capture de revue : `--ratios` ouvre l'onglet Ratios.

---

## Évolution 4.2 — Couleurs des surfaces USPI (mode ÉVOLUTION)

> Statut : ☑ Validé par l'utilisateur et implémenté (29.10.2026). Demande : « elles sont toutes grises, on ne peut même pas les contrôler ».

- **Teinte unique, le pétrole.** C'est la seule teinte libre : la légende SIA 416 occupe le magenta, le rouge, l'orange, le jaune et le bleu, le vert est réservé aux abords (SA), et le violet-pervenche à l'accent.
- **Rampe du net au brut**, comme la chaîne USPI 2014 : SNH `#5CCFB8` → SH (et SHA) `#22A08C` → SBH `#0F6E62`. Plus la teinte est foncée, plus la surface comprend de construction.
- **Surfaces de vente hachurées.** SVN reprend la teinte de SH, et SVB celle de SBH. Elles sont hachurées, car le hachuré veut déjà dire « surface externe » et SVN = SH + SE. Aucune nouvelle couleur.
- **3D : la chaîne empilée.** Les cinq surfaces sont coplanaires et se disputaient la profondeur (moiré). Elles sont maintenant posées de 1 à 6 cm sous le plan, de SNH (dessus) à SVB (dessous). Vue de dessus, chaque surface dépasse de la précédente de ce qu'elle ajoute : cloisons, murs, puis extérieurs.
- Les couleurs vivent une seule fois dans `report.SIA_COLORS` : calques, vue 3D, infobulles, rapport HTML et benchmark.
- Capture de revue : `--layers SNH,SH,SBH` ne montre que ces calques. Références : `docs/ui-baseline/uspi-myonaz2-dark.png`, `uspi-myonaz2-light.png`.
- **Revue visuelle (Myonaz 2, sombre et clair)** :
  - ✅ plus de moiré ;
  - ✅ SNH clair dessus, SH et SBH en liseré plus foncé sur les cloisons et les murs ;
  - ✅ SVN et SVB pâles et hachurées, qui débordent sur les balcons ;
  - ✅ légende lisible dans les deux thèmes.
  - Point faible restant : le liseré SH est mince (cloisons de 10 à 20 cm) et se lit mieux de près.
  - Le SNH clair reste proche des vitrages SRV (`#9ED8E6`), mais les uns sont verticaux et l'autre en plan : ils ne se superposent pas.

---

## Évolution 4.3 — Ratios rangés par groupe : SIA 416, USPI 2014, Enveloppe, Programme (mode ÉVOLUTION)

> Statut : ☑ Validé par l'utilisateur et implémenté (29.10.2026). Demande : « sépare bien les ratios en rapport avec les surfaces SIA des ratios USPI, visuellement plus facile à interpréter ».

- **Quatre groupes, toujours dans cet ordre** : SIA 416, USPI 2014, Enveloppe, Programme. On les retrouve dans l'onglet Ratios de l'application et dans le Dashboard (Ratios et Comparer).
- **En-tête de groupe** : une pastille de 10 px, le titre et une définition d'une ligne en texte secondaire, souligné d'un filet.
  - La pastille reprend la couleur des surfaces mesurées, comme dans les calques : SP (magenta) pour la SIA 416, SH (pétrole, Évolution 4.2) pour l'USPI, SFN (gris façade) pour l'enveloppe, gris neutre pour le programme.
  - Le titre dit toujours le groupe : la couleur n'est jamais seule.
- **Enveloppe à part** : façades, vitrages et toitures ne sont pas des surfaces de plancher. Les mêler à la SIA 416 brouillerait la lecture.
- **Dashboard** :
  - SVN / SP hors-sol quitte « Rendement » pour le groupe USPI 2014 ;
  - Rendement, Pertes et Sous-sol deviennent des sous-titres du groupe SIA 416 ;
  - les KPI clés en tête de page restent inchangés.
- **Revue visuelle** : onglet Ratios de Myonaz 2 (sombre) et Dashboard de la base (10 MDP), avec ✅ groupes, pastilles et définitions lisibles, et aucune erreur de console.
  - Accessoire retiré : pas de compteur de ratios par groupe, qui ne sert pas la lecture.

---

## Évolution 4.4 — Surfaces de construction SC et SEC (mode ÉVOLUTION)

> Statut : ☑ Validé par l'utilisateur et implémenté (29.10.2026). Objectif : modéliser la construction pour que le résidu R1 / R3 ne montre plus que les vraies zones de SP et de SEP non classées.

- **Couleurs** (`report.SIA_COLORS`), un fond neutre qui laisse ressortir les pièces et la plaque SP :
  - SCP (porteuse) anthracite `#3F4652` ;
  - SCN (non porteuse) gris `#7E8796` ;
  - SC (non modélisée : niveau sans mur dans la maquette) gris pâle `#A3AAB6`, en aplat. Le hachuré reste réservé aux surfaces externes.
  - SECP et SECN dans les mêmes gris, hachurés comme toute surface externe.
- **Calques** : SC, SCP et SCN dans le groupe Intérieur ; SECP et SECN dans le groupe Extérieur. Ils sont visibles d'emblée.
- **Zones non classées** : aucune nouvelle surface. La plaque SP magenta, posée sous les pièces, transparaît là où ni pièce ni construction ne la couvre. Le sujet « Plancher non entièrement classé (SP) » (R1) ne contient plus que ces zones.
- **Revue visuelle** (Myonaz 1, sombre, `docs/ui-baseline/construction-myonaz1-dark.png`) :
  - ✅ murs en gris sous les pièces ;
  - ✅ trou de 32 m² au rez visible en magenta ;
  - ✅ sujet SP à 32 m² ;
  - ✅ SECP et SECN hachurés.
  - Point faible restant : en thème sombre, la SCP anthracite contraste peu avec le fond, mais les pièces et le trou restent bien lisibles.
## Évolution 4.5 — Minage de données : une seule section, une seule fiche (mode ÉVOLUTION)

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (29.10.2026) ☑ Implémenté
> Demande du 29.10.2026 : fusionner Génération et Fiabilisation. Un projet est un projet, qu'il vienne de Treegram ou d'un IFC ; seule sa source diffère.
> Aucune nouvelle couleur, aucun nouveau token de couleur.

### Ancrage

- **Job de la section** : *tenir tous les projets de surfaces en cours au même endroit, quelle que soit la source.*
- L'ordre Génération → Fiabilisation de l'Évolution 4.0 disparaît : un projet généré finit de toute façon dans le même espace de revue. La source n'est qu'un attribut du projet, comme sa typologie.

### Wireframe — accueil

```
┌────────────────────────────────────────────────────────────────────────────────┬───────────────────────────┐
│  MINAGE DE DONNÉES                                                             │  BENCHMARK                │
│  Tirer les surfaces SIA d'un projet Treegram ou d'une maquette IFC.            │  (inchangé)               │
│  [▸ Nouveau projet…] (accent, Ctrl+N)                                          │                           │
│  La fiche projet : l'identité HRS, puis la source des données.                 │                           │
│                                                                                │                           │
│  PROJETS                                                                   6   │                           │
│  ⧉ 1778  L OREE       Log. mixte VD   Traité          8 points · 29.10   ⇥ ✎ 🗑 │                           │
│  ◫ —     Myonaz-1     Infos à compléter  En traitement  1 à trancher · 29.10 ↻ ✎ 🗑 │                           │
│  ◫ —     CGA-L04      Infos à compléter  En traitement  ✓ tout tranché · 29.10 ↻ ✎ 🗑 │                   │
│  …                                                                             │                           │
└────────────────────────────────────────────────────────────────────────────────┴───────────────────────────┘
  ⧉ = glyphe Treegram   ◫ = glyphe IFC (16 px, TextSecondary, infobulle « Projet Treegram » / « Généré depuis un IFC »)
```

- **Deux colonnes** : Minage de données (1,6*) | Benchmark (1*). Le séparateur central et la colonne Génération disparaissent.
- **Une liste unique, « Projets »**, avec les mêmes colonnes que les projets actifs actuels. Un **glyphe de source** s'ajoute en tête de ligne : c'est le seul signe distinctif. Ordre : en traitement d'abord, puis traités ; à statut égal, le plus récent d'abord.
- **Colonne d'état, selon la source** :
  - Treegram : « 8 points · date d'analyse » ;
  - IFC : « 1 à trancher · date » en TextSecondary, ou « ✓ tout tranché · date » avec la coche StatusSeen.
- **Actions** (alignées à droite, même emplacement pour toutes les lignes) :
  - ↻ Régénérer : IFC seulement (emplacement réservé et vide sur une ligne Treegram, pour que ✎ et 🗑 restent alignés) ;
  - ⇥ Ajouter à la base : projet traité, quelle que soit sa source ;
  - ✎ Fiche projet ; 🗑 Supprimer.
- **Clic sur une ligne** : un projet Treegram s'ouvre sur l'onglet Sujets, un projet IFC sur l'onglet Espaces (comme aujourd'hui).

### Wireframe — fiche « Nouveau projet »

```
┌ Nouveau projet ──────────────────────────────────────────────┐
│ IDENTITÉ                                                     │
│   ID projet HRS *        [            ]                      │
│   Nom du projet *        [            ]                      │
│   Typologie * · Canton * · Commune · Intervention * · Phase  │
│   (rappel des champs * pour le benchmark, inchangé)          │
│                                                              │
│ SOURCE DES DONNÉES                                           │
│   [ Treegram | Maquette IFC ]      ← choix segmenté          │
│                                                              │
│   Treegram :                                                 │
│   [ dossier du projet ………………………… ] [Parcourir…]            │
│   ✓ L OREE.tgm · cache VWR présent                           │
│                                                              │
│   Maquette IFC :                                             │
│   [ fichier .ifc ……………………………… ] [Parcourir…]                │
│   ✓ maquette.ifc · le projet sera créé dans                  │
│     Documents\SIA Check - projets generes\<Nom>   [Changer…] │
│   La maquette doit contenir ses IfcSpace. 30 s à 4 min.      │
│                                                              │
│            [Créer et analyser | Créer et générer] [Annuler]  │
└──────────────────────────────────────────────────────────────┘
```

- **L'identité d'abord, la source ensuite**, comme demandé. Ctrl+N ouvre directement la fiche : l'explorateur ne s'ouvre plus avant elle (écart assumé à l'Évolution 3.8).
- **Le choix de source** est un contrôle segmenté à deux options. La ligne en dessous change selon la source. Le bouton principal dit ce qu'il fera : « Créer et analyser » ou « Créer et générer ».
- **Nom suggéré** : tant que le nom n'a pas été saisi, le dossier Treegram ou le fichier IFC choisi le propose (mécanisme `SuggestName` existant).
- **Contrôles sous le champ source** :
  - Treegram : les messages de `ProjectFolder.Check`, inchangés ;
  - IFC : fichier introuvable, ou dossier `<Nom>` déjà pris par un autre projet généré, en erreur. Le nom du dossier est le nom du projet nettoyé (`CleanName`).
- **Fiche ✎ d'un projet IFC** : la même fiche, avec la source verrouillée sur « Maquette IFC ». Elle montre le chemin de la maquette, en lecture seule. ↻ redemande la maquette si elle a bougé.

### Mapping ancien → nouveau (iso-fonctionnalité)

| Avant | Après |
|---|---|
| Colonne Génération, « Générer depuis un IFC… » | Nouveau projet… → source « Maquette IFC » |
| Liste « Projets générés » (nom, état, date, ↻) | Liste « Projets », glyphe IFC, mêmes état, date et ↻ |
| Dossier des projets générés (boîte de génération) | Ligne « sera créé dans … [Changer…] » de la fiche |
| Colonne Fiabilisation, « Projets actifs » | Liste « Projets », glyphe Treegram |
| Projet généré sans fiche projet | Fiche ✎ ; ID, typologie et canton affichés dans la liste |

### Passe B — auto-critique

- **Glyphes** : un arbre pour Treegram n'est pas un logo officiel. Il est lisible grâce à l'infobulle, et l'œil apprend vite deux formes différentes. L'alternative, un badge mono « TGM » / « IFC », est plus explicite mais ajoute du texte sur une ligne déjà chargée.
- **Densité** : la ligne IFC porte une action de plus (↻). L'emplacement réservé évite le décalage des boutons.
- **Chanel** : pas de filtre par source au-dessus de la liste. Avec moins de 10 projets, le glyphe suffit. À rediscuter au-delà de 20.
- **Point ouvert** : 🗑 sur un projet IFC. Effacer seulement les traces dans l'app ne suffit pas : le dossier généré réapparaîtrait au prochain retour à l'accueil. Proposition : la suppression d'un projet IFC efface aussi son dossier généré, après confirmation. Ce dossier ne contient que des fichiers produits par l'app ; la maquette IFC n'est jamais touchée.

### Choix rejetés

| Proposition | Raison du rejet | Date |
|---|---|---|
| Deux sous-listes (Treegram, IFC) dans la même colonne | C'est garder deux sections sous un seul titre | 29.10.2026 |

### Écarts au plan, décidés à l'implémentation

| Plan | Réalisé | Raison |
|---|---|---|
| Glyphe « arbre » pour Treegram | `TextBulletListTree16` (une arborescence) ; `Cube16` pour IFC | La bibliothèque Fluent de WPF-UI 4.3 n'a pas d'arbre. L'arborescence dit la même chose : un projet Treegram est un arbre de surfaces. |
| Contrôle segmenté Treegram \| Maquette IFC | Deux boutons radio côte à côte | WPF-UI n'a pas de contrôle segmenté. Les radios gardent la navigation clavier et le focus visible sans style sur mesure. |
| Hauteur fixe de la fiche | La fiche suit son contenu (`SizeToContent`) | Le bloc IFC, plus haut, était coupé à la première revue. |
| Message rouge sous une source vide | En TextSecondary tant que rien n'est choisi | Une fiche vierge ne doit pas s'ouvrir sur une erreur. |
| Place réservée pour ↻ seulement | Places réservées pour ↻ et ⇥ | Sinon, la ligne d'un projet traité se décalait d'un bouton. |
| Colonne d'activité de largeur libre | Largeur fixe de 168 px | « 1 à trancher » est plus court que « ✓ tout tranché » : la ligne se décalait. |

### Revue visuelle (Phase 2, 29.10.2026, thème clair)

- `docs/ui-baseline/accueil-minage-light.png` : 6 projets, 5 IFC et 1 Treegram, mêlés. Les glyphes, les statuts, l'activité et les boutons sont alignés d'une ligne à l'autre.
- `docs/ui-baseline/nouveau-projet-ifc-light.jpg` :
  - l'identité vient en tête ;
  - la source « Maquette IFC » montre le dossier des projets générés, « Changer… » et le rappel des IfcSpace ;
  - le bouton devient « Créer et générer ».
- À surveiller : sur un projet IFC pas encore traité, une place vide sépare ↻ de ✎ (place réservée pour ⇥).
