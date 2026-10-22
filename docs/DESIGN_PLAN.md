# DESIGN_PLAN — SIA Check Viewer

> Statut : ☑ Brouillon ☑ Auto-critiqué (Passe B) ☑ **VALIDÉ PAR L'UTILISATEUR** (21.10.2026)
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
