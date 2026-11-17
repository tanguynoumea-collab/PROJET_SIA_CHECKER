# V5_PLAN — Refonte de l'onglet Benchmark

> Statut : plan d'implémentation, validé partie par partie (1 → 5). Version cible : 5.0.0 (à confirmer).
> Rédigé le 17.11.2026 après analyse de `dashboard/` (page web dans WebView2), de la visionneuse WPF et du moteur
> `benchmark.py`. Base actuelle : 11 MDP, 7 fiables.

## Objectif

Le Benchmark devient l'endroit où l'on compose la **sélection de référence** : un ensemble de projets dont les KPI
représentent la typologie du projet à chiffrer. Cette sélection alimente Programmer et l'export Excel. Les
**maquettes comparées** sont situées par rapport à elle, sans jamais la modifier.

## Décisions prises (17.11.2026)

| Sujet | Décision |
|---|---|
| Valeur de référence | Celle des Tendances actuelles : la **médiane** (projet type), avec la répartition (histogramme, bandes, densité). Elle est recalculée sur les seuls projets cochés. Pas de « moyenne » au sens strict. |
| Pré-filtre | Typologie, Canton, Intervention, en haut de la page. Il agit sur les KPI, sur la liste des projets de référence et sur la liste des maquettes comparables. |
| Projets de référence | Tous les projets fiables du pré-filtre sont cochés par défaut. L'utilisateur décoche à volonté. |
| Maquettes comparées | Choisies parmi les maquettes du pré-filtre, plusieurs à la fois. Chacune reçoit une couleur propre sur toutes les figures et tous les KPI. |
| 3D | **Dans la page web**, avec un format 3D web propre, rangé **à côté du MDP** dans le dossier de la base. |
| Carte | Fond **hors ligne** : cantons, lacs et localités livrés avec la page. |
| Défilement | La vue 3D ou la carte **reste fixe à l'écran** pendant que la page et les volets défilent. La molette ne zoome dans la vue qu'après un clic dedans, ou avec Ctrl+molette. |

## Structure de la page

```
┌ Typologie ▾  Canton ▾  Intervention ▾        (pré-filtre)              n projets cochés / N ┐
├──────────────────────────┬────────────────────────────────────────────────────────────────┤
│ MAQUETTES À COMPARER     │  Légende : ● Maquette A  ● Maquette B                    [Carte]│
│ ☐ ● 1746 Avallons    ⬛  │                                                                │
│ ☑ ● 1714 Clos des H. ⬛  │  Zone centrale : Tendances (KPI clés, groupes, anatomie)        │
│ ★ Mon projet  ▸ saisie   │        ou visionneuse 3D d'un projet                           │
│──────────────────────────│        ou carte de la Suisse                                   │
│ PROJETS DE RÉFÉRENCE     │  (vue 3D ou carte : fixée à l'écran, ✕ pour revenir)            │
│ tri ▾  forme ▾  tout/aucun│                                                               │
│ ☑ 1746 Avallons      ⬛  │                                                                │
│ ☑ 1467 La Bâtie B        │                                                                │
│ ▸ Écartés de la base (4) │                                                                │
└──────────────────────────┴────────────────────────────────────────────────────────────────┘
```

Le volet gauche est collant et défile seul. ⬛ = icône cube, affichée seulement si le projet a une maquette 3D web.

## Partie 1 — Fusion de Tendances et Comparer

**État** (une seule source, conservée d'une session à l'autre) :

- `filtre` : typologie, canton, intervention, comme aujourd'hui.
- `exclus` : identifiants des projets décochés. On garde les exclusions plutôt que les cochés, pour qu'un projet ajouté
  à la base entre coché. « Tout recocher » vide la liste.
- `reference` = projets fiables du filtre, moins `exclus`. Tous les calculs de la page la lisent : Tendances,
  Anatomie, Base, Typologies, puis Programmer (partie 4).
- `comparees` : liste ordonnée, 6 au maximum, chaque entrée avec sa couleur. Aucun calcul de référence ne la lit.

**Volet « Maquettes à comparer »** : les projets du filtre, fiables et écartés, plus « Mon projet ». On peut en
sélectionner plusieurs. La couleur est attribuée à la sélection, puis libérée quand on retire la maquette. La saisie
« Mon projet » et la réception du projet ouvert dans SIA Check sont reprises de Comparer, dans un formulaire repliable.

**Volet « Projets de référence »** : cases à cocher, tri (ID, nom, SP hors-sol), « tout cocher » et « aucun », et la
liste « Écartés de la base » repliable. Les projets écartés ne peuvent pas être cochés ; une infobulle dit pourquoi.

**Repères colorés** :

- Chaque figure de répartition reçoit un trait vertical par maquette comparée, à sa couleur, avec sa valeur au survol.
  Une valeur hors échelle est rabattue au bord avec une flèche.
- Sous chaque KPI, une ligne par maquette comparée : pastille, valeur, écart à la médiane (points, m², CHF si un prix
  est saisi). Ces calculs sont repris de Comparer.
- Dans l'Anatomie, une barre par maquette comparée, bordée de sa couleur, sous la barre Référence.
- La légende reste visible en haut de la zone centrale.
- Palette : 6 teintes distinctes des couleurs SIA, de l'accent et des couleurs de verdict, lisibles dans les six
  thèmes.

**Comparer disparaît.** Ce qui en est repris :

- la saisie « Mon projet » ;
- les écarts en m² et en CHF ;
- le tableau des cages d'escalier, pour les maquettes comparées ;
- la proximité, sous forme d'un bouton « Cocher seulement les 5 plus proches de [maquette] » ;
- les liens « Comparer → » des tableaux, qui deviennent « Ajouter aux comparées ».

**Changement de calcul** : les écarts se mesuraient au ratio combiné des projets similaires. Ils se mesurent
désormais à la médiane de la référence.

**Tests** : ajouter ou retirer une maquette comparée ne change aucune valeur de référence. Décocher un projet met à
jour toutes les figures. Les tests existants du benchmark (`BenchmarkTests`) restent verts.

## Partie 2 — Visionneuse 3D dans la page

**Format 3D web** (moteur Python, `sia-check --maquette-web`) :

- Un fichier `MAQ-<id>.json.gz` par projet, à côté de `MDP-<id>-….xlsx`.
- Contenu : les surfaces de l'analyse corrigée, chacune avec son code SIA, son bâtiment, son niveau, son aire, son
  nom et ses triangles.
- Les coordonnées sont arrondies au centimètre et recentrées sur le projet : environ 0,5 à 1 Mo par projet, contre
  2 à 4 Mo pour le cache d'analyse.

**Production et lecture** :

- Le fichier est écrit à chaque publication du MDP dans la base.
- Une commande « Republier les maquettes » produit en une fois les fichiers des projets déjà publiés, à partir de leur
  analyse.
- `benchmark.json` indique pour chaque projet s'il a une maquette.
- L'application expose le dossier de la base à la page, en lecture seule.

**Rendu** : three.js, livré dans `dashboard/vendor/` (sans réseau).

- Navigation : orbite, zoom, cadrage, vues de dessus et 3D.
- Surfaces groupées par catégorie, bâtiment et niveau, comme dans la visionneuse.
- Panneau de droite : surfaces cochables (catégories SIA, bâtiments, niveaux) et KPI du projet face à la médiane de
  la référence.

**Comportement** : la zone centrale est remplacée et fixée à l'écran. Les volets restent actifs : cocher, passer
d'une maquette à l'autre. ✕ ou Échap ramènent aux graphiques, à la même position de défilement.

**Version web publiée** : les fichiers `MAQ-*` seront à publier avec `benchmark.json`.

## Partie 3 — Carte

**Rendu** : en SVG, sans bibliothèque. Les coordonnées suisses (LV95) sont métriques, donc une simple mise à l'échelle
suffit.

**Données livrées avec la page** :

- Contours des cantons et des grands lacs : swisstopo, simplifiés, environ 150 Ko.
- Localités officielles avec coordonnées, environ 200 Ko.
- Une table d'alias pour les anciens noms (Estavayer-le-Lac → Estavayer, Petit-Lancy → Lancy).

Ces données seront téléchargées depuis swisstopo au moment de la partie 3, avec ton accord.

**Informations sur la carte** :

- Cantons colorés selon le nombre de projets cochés.
- Points : couleur = typologie ; taille = SP hors-sol ; plein = coché, cercle vide = décoché, pointillé = écarté.
- Halo de couleur = maquette comparée.
- Projets d'une même commune légèrement écartés pour rester cliquables.
- Infobulle : ID, nom, commune, SP, KPI clés.

**Interactions** :

- Filtres : typologie, intervention, phase, plage de SP, forme (partie 5), fiables seuls, avec maquette 3D.
- Un clic sur un point coche ou décoche le projet, synchronisé avec le volet.
- Cocher ou décocher une zone tracée en rectangle, ou tous les projets dans un rayon de X km d'une maquette comparée.
- Liste des projets non localisés (aujourd'hui 4 sur 11).

**Non réalisable avec les données actuelles** :

- L'année : la date de fin de projet est vide dans les 11 MDP.
- L'adresse exacte : aucun champ ne la porte.

## Partie 4 — Sélection partagée et export Excel

**Programmer** n'a plus de groupe propre : il lit `reference`. Le titre « D'après N projets de référence » renvoie
au volet.

**Export Excel** : la page envoie à l'application l'état affiché. Le moteur écrit le classeur avec openpyxl, puis
l'application ouvre un dialogue d'enregistrement.

1. **KPI** : un KPI par ligne. Colonnes : médiane de la référence, P25, P75, n, puis une colonne par maquette
   comparée. En tête : pré-filtre, nombre de projets, date.
2. **Projets de référence** : ID, nom, commune, canton, typologie, intervention, forme, SP hors-sol.
3. **Détail par projet** : tous les KPI, un projet de la référence par ligne.

L'export n'est disponible que dans l'application, pas dans la version web publiée.

## Partie 5 — Forme du bâtiment

**Liste proposée** :

- Carré
- Rectangle compact (≤ 2:1)
- Barre (> 2:1)
- L
- T
- U
- Cour fermée / îlot
- Redans / Z
- Peigne / H
- Rond / ovale
- Courbe / arc
- Plusieurs plots
- Irrégulier

**Stockage et saisie** :

- Une ligne « Forme du bâtiment » dans la feuille InfosProjet du MDP : gabarit, `make_mdp_template.py`, lecture par
  `benchmark._infos`.
- Modifiable depuis la page du MDP sur l'accueil et depuis la fiche projet.

**Remplissage automatique** :

- Une suggestion géométrique calculée sur l'emprise au sol (compacité, angles rentrants, rapport des côtés), que l'IA
  confirme ou corrige.
- Une valeur saisie à la main n'est remplacée qu'après confirmation.

**Usage** : tri et filtre dans le volet de référence et sur la carte.

## Journal

- **Partie 1, implémentée le 17.11.2026** (`dashboard/index.html`, `app.js`, `style.css`).
  - Onglets : Tendances, Programmer, Base, Typologies.
  - Base et Typologies suivent la référence cochée. Programmer garde son groupe de projets similaires jusqu'à la partie 4.
  - Une recherche (ID, nom, commune) filtre les deux volets.
  - Les maquettes comparées sortant du pré-filtre restent comparées, marquées « hors filtre ».
  - La sélection (exclusions et maquettes comparées) est gardée dans le stockage local de la page.
  - Vérifié dans le navigateur : ajouter des maquettes ne change aucune valeur de référence ; décocher un projet
    recalcule les figures ; le volet reste collé pendant le défilement.

- **Partie 1, reprise du 17.11.2026** :
  - « Maquettes à comparer » devient un menu dépliant. Fermé, il montre les pastilles des maquettes comparées.
  - La recherche passe au-dessus des deux volets et ouvre le menu.
  - L'en-tête des Tendances (titre, résumé, choix de la représentation) et la légende sont retirés : histogramme seul.
  - Chaque repère de maquette porte sa valeur au-dessus, à sa couleur, comme la médiane. Une étiquette qui en
    chevaucherait une autre monte d'une rangée.

- **Partie 1, icônes (17.11.2026)** : les libellés d'action deviennent des icônes au trait (SVG dans `app.js`,
  `ICONES`), avec le libellé en infobulle et en nom accessible.
  - Volet de référence : tout cocher, tout décocher, tri.
  - Maquettes comparées : écarté, hors filtre, 5 proches.
  - Saisie : replier ou déplier, effacer ou revenir à une saisie.
  - Pré-filtre : réinitialiser. Recherche : loupe dans le champ.
  - Tableau : état dans la référence, ajouter ou retirer des comparées.
  - Les phrases d'action des bandeaux (« Recocher les N projets », « Élargir ») restent écrites.

- **Partie 2, implémentée le 17.11.2026** :
  - **Format.** `MAQ-<id>.json.gz` est écrit par l'application (`Services/WebModel.cs`), pas par le moteur Python. La
    règle des surfaces affichées et des calques existe déjà côté visionneuse ; elle est extraite dans
    `Models/LayerRules.cs` pour servir aux deux. L'Orée pèse 478 Ko et Afiro 418 Ko.
  - **Écriture.**
    - À chaque ajout ou republication d'un MDP dans la base.
    - Et, à chaque lecture de la base, pour tout projet de ce poste dont l'ID (fiche projet) a un MDP dans la base,
      quand la maquette manque ou est plus ancienne que l'analyse.
    - Ce rattrapage automatique remplace la commande « Republier les maquettes » du plan.
  - **Moteur.** `benchmark.json` porte `maquette` (nom du fichier, ou null) pour chaque projet.
  - **Page.** `vue3d.js`, avec three.js 0.170.0 dans `dashboard/vendor/` (MIT), chargé à la première ouverture.
    - Calques comme l'onglet Calques (groupes, visibilité d'emblée), bâtiments, niveau, éclatement.
    - Vue de dessus et vue 3D.
    - Fiche de la surface au clic.
    - KPI du projet face à la médiane de la référence.
    - Case « Dans la référence » synchronisée avec le volet.
    - Échap ou ✕ pour fermer, en revenant à la même position de défilement.
  - **Dans l'application.** Les maquettes sont servies sur un hôte à part, `https://maquettes.siacheck/`, avec un en-tête
    CORS pour la page. Seuls les noms `MAQ-*.json.gz` du dossier de la base sont servis.
    - Première version sous `base/` de l'hôte du dashboard : son dossier répondait avant le gestionnaire, d'où
      « Failed to fetch » (constaté par l'utilisateur, 17.11.2026).
  - **Mode maquette sans défilement de page** (retour du 17.11.2026). La vue et les volets tiennent exactement dans la
    fenêtre (`ajuster3D`, recalculé au redimensionnement) ; seuls les panneaux défilent en interne. Le défilement de la
    page revient à la fermeture.
  - **En-tête sur une ligne** (retour du 17.11.2026). Les onglets et le pré-filtre partagent une seule barre collante
    (`.entete-page`), avec les libellés à côté des listes. L'en-tête passe d'environ 110 à 44 px, pour toutes les vues.
  - **Nouveau poste.** Les fiches projet (ID) ont été perdues : aucune maquette ne se rattache seule tant que l'ID n'est
    pas ressaisi dans la fiche projet.

- **Partie 3, implémentée le 17.11.2026** :
  - **Données.** `scripts/make_carte.py` les prépare depuis deux sources téléchargées :
    - swiss-maps 4.5.0, millésime 2024 (Interactive Things, BSD-3, d'après swisstopo et l'OFS), converti en LV95 →
      `dashboard/carte-suisse.json` (51 Ko : pays, 26 cantons, 22 lacs) ;
    - le répertoire officiel des localités de swisstopo (OGD) → `src/sia_check/data/localites.json` (163 Ko, 4 332 noms).
  - **Moteur.** `sia_check.localites.position(commune, canton)` place le projet au centre de sa commune, ou de la
    localité du même nom. `benchmark.json` porte `position` [E, N].
    - Un nom de commune unique l'emporte sur un canton contradictoire : 1023 Côté Gare L04 a « Bussigny » et « VS »
      dans son MDP, et il est placé à Bussigny (VD).
    - 7 projets sur 11 sont placés ; les 4 autres n'ont pas de commune dans leur MDP.
  - **Page.**
    - Bouton « Carte » à droite de la recherche. La carte (`carte.js`, SVG sans bibliothèque) remplace les graphiques
      comme la maquette 3D, sans défilement de page ; ✕ ou Échap pour fermer. Ouvrir la 3D ferme la carte, et l'inverse.
    - Cantons teintés selon le nombre de projets de référence. Points : couleur de la typologie, taille selon la SP
      hors-sol, plein si coché, creux si décoché, pointillé si écarté, anneau de couleur pour une maquette comparée.
      Les projets d'une même commune s'écartent en couronne.
    - Clic sur un point : coché ou décoché, synchronisé avec les volets.
    - Outils « Cocher une zone » et « Décocher une zone » (rectangle).
    - Rayon de X km autour d'une maquette comparée placée : la référence devient les projets fiables du pré-filtre
      situés dans le cercle.
    - Filtres de la carte (affichage seulement) : phase, plage de SP hors-sol, fiables seulement, avec maquette 3D.
    - Liste des projets sans commune, cochables.
    - Zoom à la molette après un clic dans la carte (ou avec Ctrl), boutons + / − / toute la Suisse ; glisser pour
      déplacer.

- **Partie 3, refonte du 17.11.2026** (retour : carte « beaucoup trop sommaire ») :
  - **Décisions de l'utilisateur.**
    - La carte fonctionne en ligne, avec un fond minimum hors ligne.
    - Un projet est placé à son adresse exacte, saisie dans les données du projet ; sans elle, au centre de sa commune.
    - Toute la Suisse en détail hors ligne a été écartée : environ 100 Go, et environ un million de tuiles à
      télécharger, au-delà de l'usage raisonnable des serveurs fédéraux.
  - **Carte.** Leaflet 1.9.4 (`vendor/leaflet/`, BSD-2).
    - Fonds geo.admin.ch : carte nationale couleur, carte nationale grise, orthophoto SWISSIMAGE (jusqu'au bâtiment).
    - Fond hors ligne : `carte-suisse.json` régénéré en WGS84, avec cantons, districts, 2 134 communes (dont 2 107
      nommées) et lacs.
    - Calques avec réglage d'opacité et légende officielle : limites et noms des communes (vectoriel, aussi hors
      ligne, dès l'échelle régionale), districts, zones à bâtir (ARE), desserte TP (ARE), arrêts TP (OFT), bruit
      routier et ferroviaire de jour (OFEV).
    - Clic hors d'un projet : commune, coordonnées LV95, puis par le service d'interrogation de geo.admin.ch le type
      de zone à bâtir, la classe de desserte et l'arrêt. Le bruit est une couche image : légende seulement.
    - Sans réseau : bandeau, bascule sur le fond minimum, calques en ligne grisés. Au retour du réseau, le fond choisi
      revient.
  - **Adresse.**
    - Nouveau champ « Adresse » dans l'identité (fiche projet, page d'un MDP de la base), écrit dans InfosProjet. La
      ligne est ajoutée à la fin du tableau des MDP existants (`Workbook.append_row`, `mdp.AJOUTS_INFOS`).
    - Géocodage hors ligne (`sia_check.adresses`) : registre officiel des adresses de bâtiments de swisstopo (environ
      140 Mo), téléchargé une fois par poste dans `%LOCALAPPDATA%\SiaCheckViewer\geodonnees\` dès qu'un projet a une
      adresse, puis indexé en SQLite (environ 50 s une fois, 290 Mo).
    - `benchmark.json` porte `precision` : « adresse », « rue » (numéro introuvable : milieu de la rue) ou « commune ».
    - L'adresse d'un projet ne quitte jamais le poste.
  - **Correctif « calques invisibles »** (retour du 17.11.2026).
    - **Cause :** fonds et calques en tuiles partageaient le même panneau Leaflet. Changer de fond, ou la bascule
      automatique en ligne et hors ligne, remettait le fond par-dessus les calques actifs.
    - **Correction :** panneaux à empilement fixe, du bas vers le haut : fond en tuiles (200), fond hors ligne (250),
      calques en tuiles (350), communes et districts (450), projets (650).
    - **Cache :** les fichiers de la page sont versionnés (`?v=`, `VERSION_PAGE`, à changer à chaque version), et
      l'application vide le cache disque de WebView2 à l'ouverture du dashboard. Une page corrigée n'est plus
      masquée par l'ancienne.
  - **Correctif « bulles invisibles »** (retour du 17.11.2026).
    - **Cause :** les cercles SVG du panneau des projets restaient parfois à l'échelle d'un zoom précédent (minuscules
      ou énormes, mal placés).
    - **Correction :** les projets deviennent des marqueurs HTML (`L.divIcon`), toujours recalés : écart mesuré de 0 px
      après une série de zooms.
    - **Lisibilité :** taille de 20 à 40 px selon la SP hors-sol, et double contour blanc puis noir, lisible sur
      l'orthophoto comme sur les zones à bâtir. Le contour de focus du navigateur sur une commune cliquée est retiré.
  - **Style des projets** (retour « c'est moche », 17.11.2026). Pastilles de 16 à 30 px avec un liseré blanc et une
    ombre douce, sans contour noir.
    - États : plein = dans la référence ; anneau blanc à point de couleur = hors référence ; gris = écarté ; liseré
      pointillé = au centre de la commune ; anneau de couleur = maquette comparée.
    - Palette plus franche, attribuée par fréquence dans la base : la typologie la plus courante (logement) prend le
      bleu, qui tranche sur l'orange des zones d'habitation et le vert de l'orthophoto.
    - Étiquette de l'ID à droite de chaque pastille, dès l'échelle régionale.
  - **Échelle des cartes nationales** (retour « beaucoup trop gros », 17.11.2026). Les fonds « carte nationale » couleur
    et grise affichent à chaque zoom le niveau suivant, à demi-taille : tuiles de 128 px, `zoomOffset` 1.
    - Écritures et symboles deux fois plus petits, et l'édition plus détaillée de la carte arrive un cran plus tôt.
    - Le niveau le plus fin (18) est atteint au zoom 17 ; l'orthophoto ne change pas.
  - **Correctif « la carte disparaît au zoom »** (retour du 17.11.2026).
    - **Cause probable :** avec les tuiles fines, il y a quatre fois plus de requêtes, et quelques-unes refusées (proxy)
      atteignaient le seuil de 6 erreurs. La carte basculait alors sur le fond hors ligne, presque vide à l'échelle de
      la rue, et y restait.
    - **Correction :** une erreur de tuile déclenche un test réel du réseau (une tuile, au plus toutes les 15 s, délai
      de 8 s) ; seul son échec fait passer hors ligne.
    - Les tuiles du fond ne sont demandées qu'une fois le zoom posé (`updateWhenIdle`, `keepBuffer` 1).
  - **Quartiers et calques du développement immobilier** (demande du 17.11.2026).
    - **Quartiers :** quartiers statistiques de l'OFS (unités statistiques de base, niveau 1), découpage infracommunal
      national et nommé. Au clic : « Quartier : Lausanne Maupas / Valency », « Lancy Tivoli ».
    - **Calques ajoutés au choix de l'utilisateur**, tous vérifiés sans erreur, 26 au total en six thèmes repliables :
      - Urbanisme et foncier : parcelles cadastrales (WMS), bâtiments RegBL (statut projeté, autorisé, en
        construction ou existant, année, niveaux, logements, parcelle), ISOS.
      - Population et emplois à l'hectare : STATPOP, StatBL, STATENT (WMS, dernière année renseignée).
      - Contraintes : bruit de nuit routier et ferroviaire, aléa ruissellement, radon (WMS), sol de fondation SIA 261.
      - Énergie : solaire toitures et façades, demande de chaleur.
      - Accès et réseaux : accessibilité TP, temps au centre, fibre, antennes mobiles.
    - **Clic :** une requête d'interrogation par tolérance plutôt que par calque. Une quinzaine de requêtes
      simultanées en perdaient.
    - **Cadastre sur fond gris** (retour du 17.11.2026) : la carte cadastrale officielle est un plan en couleur
      (bâtiments rose, forêts vertes). Elle recolorait le fond gris dès l'échelle du quartier. Elle passe en niveaux de
      gris quand le fond gris est choisi (filtre CSS, `desature` dans CALQUES). Le calque au trait de la MO
      (`ch.swisstopo-vd.amtliche-vermessung`) a été essayé : le WMS le renvoie vide.
  - **Ce qui part sur le réseau** (carte en ligne) : les demandes de tuiles de la zone regardée, et les coordonnées d'un
    clic pour l'interrogation des calques.

- **Partie 4 — Programmer sur la sélection partagée, export Excel** (17.11.2026).
  - **Décisions de l'utilisateur :** Programmer calcule sur la référence seule (plus de groupe des 5 projets
    similaires) ; valeur centrale = médiane, comme les Tendances ; 4e feuille « Programme attendu » quand une SP est
    saisie.
  - **Programmer :** la liste de ses projets est celle des projets fiables du pré-filtre, cochés selon la référence.
    Décocher ici décoche dans Tendances, et inversement (`etat.exclus`, un seul état). Le champ « Étages hors-sol »,
    qui ne servait qu'à chercher les projets similaires, est retiré.
  - **Export :** bouton « Exporter en Excel » en tête des hypothèses. Le classeur est écrit par la page (`xlsx.js`,
    SpreadsheetML minimal, ZIP sans compression, sans bibliothèque ni réseau), donc identique dans SIA Check et en
    ligne. Dans SIA Check, WebView2 `DownloadStarting` ouvre « Enregistrer sous ».
    - KPI : groupe, famille, KPI, unité, n, P25, médiane, P75, ratio combiné, puis une colonne par maquette comparée.
    - Projets de référence : identité, adresse, phase, SP, SP hors-sol, SUP, logements, étages, maquette 3D.
    - Détail par projet : chaque KPI, projets de référence puis maquettes comparées (rôle indiqué).
    - Programme attendu : hypothèses et tableau Bas / Central / Haut, tel qu'à l'écran.
    - En tête de chaque feuille : pré-filtre, nombre de projets de référence, date.
  - **Refonte du classeur** (retour du 17.11.2026) :
    - KPI : médiane seule, plus de ratio combiné. Seules les maquettes comparées hors référence y figurent, avec
      valeur, écart à la médiane et place dans la fourchette P25–P75. Celles déjà en référence sont citées en légende.
    - Mise en forme : bandeau de titre, phrase de lecture et contexte en tête de chaque feuille. Groupes de KPI en
      bandeaux à leur couleur ; vert, rouge ou bleu selon le sens du ratio. Légende « Comment lire cette feuille »
      en pied ; mise en page d'impression.
    - Détail par projet : en pied, médiane, P25, P75 et n, puis le bloc des maquettes hors référence.
    - Programme attendu : carte des hypothèses et répartition de la SP hors-sol.
    - `xlsx.js` : styles décrits par cellule et dédupliqués, fusions, filtres, volets, mise en page. Rendus PDF
      vérifiés sur trois scénarios (complet, simple, référence fragile).
  - **Charte HRS** (retours du 17.11.2026, d'après les modèles de rapport et de présentation HRS) : une version
    noir et blanc a été jugée trop terne ; retenu : palette HRS seule mais assumée. Police Sofia Pro ; bandeau de
    titre orange #FF6600 ; en-têtes bleu foncé #001A82 ; groupes de KPI en bandeau #DBE9FD à barre orange ; médiane
    en #C3DAFC ; maquettes comparées sous un en-tête orange commun ; écarts sur fond bleu pâle (bon côté) ou
    rouge-orange pâle (mauvais) ; barre de la SP en orange, bleu foncé, bleu clair et gris ; « HRS Real Estate AG »
    en pied d'impression. Sofia Pro gras n'ayant ni « ★ » ni tiret demi-cadratin, les en-têtes concernés sont
    reformulés.
  - **Vérifié :** classeur généré par le même code ouvert par Excel sans réparation (formats %, entiers, décimales,
    en-têtes, onglets à nom nettoyé, colonnes au-delà de Z) ; un décochage dans Programmer change la référence de
    Tendances.

- **Partie 5 — Forme des bâtiments** (17.11.2026).
  - **Décisions de l'utilisateur :** liste des 13 formes validée (Carré, Rectangle compact, Barre, En L, En T, En U,
    Cour fermée / îlot, À redans / en Z, En peigne / en H, Rond / ovale, Courbe / arc, Plusieurs plots, Irrégulière).
    Une forme par bâtiment ; un projet à plusieurs bâtiments est un « Îlot de bâtiments » suivi des formes de ses
    bâtiments. Les deux analyses IA (revue IA Treegram, analyse IA de la génération IFC) proposent la forme.
  - **MDP :** champs « Forme » (« Rectangle compact », ou « A : Carré ; B : En L ») et « Forme (origine) »
    (« saisie » ou « IA ») ajoutés à InfosProjet comme l'adresse (`AJOUTS_INFOS`). Vocabulaire commun :
    `src/sia_check/formes.py` et `Services/BuildingShapes.cs`.
  - **Benchmark :** `infos.formes` ({bâtiment: forme}), `infos.forme` (libellé), `infos.forme_origine`,
    `infos.batiments` (feuille InfosBatiment) ; `listes.Forme` pour la fiche.
  - **Fiche projet :** une liste de formes par bâtiment (bâtiments du projet ouvert, sinon du MDP de la base). Une
    forme proposée par l'IA est signalée ; la modifier en fait une saisie.
  - **IA :** la revue IA rend un bloc `<formes>` (gardé dans les verdicts, clé `formes`) ; l'analyse IA de la
    génération écrit `generation/formes-ia.json`. L'application remplit la fiche si la forme est vide ou venait
    de l'IA ; une forme saisie n'est remplacée qu'après confirmation. Projet déjà dans la base : forme écrite
    aussi dans son MDP. Le moteur décrit l'emprise de chaque bâtiment aux deux IA (module `emprise`).
  - **Dashboard :** filtre de forme partagé par le volet et la carte (une forme, « Îlot de bâtiments », « Forme
    non renseignée »), avec le nombre de projets ; avec un filtre, le bouton coche ou décoche les projets de cette
    forme seulement (référence réduite à une forme) ; tri « Forme » ; forme dans l'infobulle de la carte et colonne
    « Forme » de la feuille Excel des projets de référence.

## Points ouverts, à trancher à la partie concernée

- **Partie 3** : faut-il un champ d'adresse ou de coordonnées dans le MDP pour une position plus précise que la
  commune ?
