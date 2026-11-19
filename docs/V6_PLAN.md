# V6_PLAN — Version HTML du benchmark, ouverte depuis SharePoint

> Statut : publié en version 6.0.0 le 19.11.2026 (parties 1 à 8).
> Source : docs/ROADMAP.md, « V6 — Version locale HTML, ouverte depuis SharePoint ». Les deux autres idées de la V6
> (données SIG, onglet Contexte) restent dans la roadmap.

## Objectif

Consulter le benchmark sans installer SIA Check. Un fichier HTML déposé dans une bibliothèque SharePoint ouvre le
dashboard dans le navigateur, avec Tendances, Programmer, la carte, la vue 3D et l'export Excel, sur les données de la base.

## Contrainte de départ : SharePoint n'affiche pas les pages HTML

SharePoint Online n'affiche pas un fichier .html dans le navigateur : un clic sur le fichier le **télécharge**, puis
il s'ouvre en local (`file://`), sans serveur. On peut aussi l'ouvrir depuis le dossier OneDrive synchronisé. Dans ce
mode, le navigateur :

- refuse `fetch()` sur un fichier local : la page ne peut lire ni `benchmark.json`, ni `carte-suisse.json`, ni les
  `MAQ-*.json.gz` posés à côté d'elle ;
- refuse les modules ES chargés depuis un fichier, comme `vue3d.js`, `three.module.min.js` et `OrbitControls.js` ;
- ne permet pas de connexion Microsoft (MSAL / Graph), qui exige une page servie en http(s) avec une adresse de
  retour déclarée.

La page actuelle ne fonctionne donc pas telle quelle hors d'un serveur.

## Décisions prises (18.11.2026)

| Sujet | Décision |
|---|---|
| Forme | **Un seul fichier HTML autonome**, qui intègre styles, scripts, bibliothèques (Leaflet, three.js), fond de carte hors ligne, données et maquettes. Pas d'hébergement et pas de connexion Microsoft. La piste Static Web Apps du 02.11 reste en réserve. |
| Maquettes 3D | **Toutes intégrées** : la vue 3D fonctionne comme dans SIA Check. Compter environ 0,6 Mo par projet. |
| Production | Un **bouton « Version HTML »**, discret, à côté de « Ouvrir le benchmark » sur l'accueil. Chaque clic régénère le fichier à côté de benchmark.json (`%LOCALAPPDATA%\SiaCheckViewer\benchmark\SIA Check - Benchmark.html`) puis l'ouvre dans le navigateur par défaut, sans dialogue (choix du 18.11.2026). Le dépôt dans SharePoint reste à faire à la main. |
| Accès | Les droits de la bibliothèque SharePoint. Une fois téléchargé ou transféré, le fichier est une copie complète des données : la page l'affiche clairement. |

## Partie 1 — Une page qui fonctionne sans serveur

On ne crée pas de seconde page : la même `dashboard/` doit fonctionner dans trois contextes. Ce sont SIA Check
(WebView2), un serveur (`?data=`) et la version intégrée.

- **Source des données intégrée.** Au démarrage, `charger()` cherche d'abord un bloc
  `<script type="application/json" id="sia-donnees">`. S'il existe, il le lit à la place de `fetch`. Viennent
  ensuite WebView2, puis `fetch` comme aujourd'hui.
- **Maquettes.** Un bloc par maquette, `<script type="application/octet-stream" id="MAQ-<id>">`, contient le gzip
  en base64. `vue3d.js` le décode puis le décompresse avec le `DecompressionStream` qu'il utilise déjà. L'icône
  cube suit la présence du bloc.
- **Fond de carte.** `carte-suisse.json` intégré de la même façon, lu par `carte.js` à la place de son `fetch`.
- **Modules.** `three`, `OrbitControls` et `vue3d.js` sont intégrés en texte. L'import map pointe vers des URL `blob:`
  créées au chargement, et l'import dynamique de `vue3d.js` aussi. Ce mécanisme est à valider en premier sur Edge et Chrome en `file://`.
- **Leaflet** : script et feuille de style intégrés en ligne, à la place de `chargerScript` et du `<link>`.
- **Réseau.** Les fonds swisstopo et les calques et clics geo.admin.ch restent en ligne, comme dans SIA Check. Les
  requêtes partent d'une origine `null` : il faut vérifier que l'API identify de geo.admin.ch répond bien
  (`Access-Control-Allow-Origin: *`). Sans réseau, la carte se rabat sur le fond hors ligne.
- **Fonctions propres à SIA Check** : la réception de « Mon projet » depuis l'application disparaît. La saisie
  manuelle de « Mon projet » reste.
- **Stockage local.** La sélection et les réglages de la carte restent dans `localStorage`. En `file://`, il est
  partagé par toutes les pages locales du navigateur : il faut préfixer les clés.
- **Pas de bandeau** : retiré à la demande de l'utilisateur (18.11.2026). La confidentialité est rappelée dans
  l'infobulle du bouton de SIA Check.

## Partie 2 — Assemblage et export depuis SIA Check

- **Assembleur** (C#, dans la visionneuse) : il lit `index.html` et ses fichiers dans le `dashboard/` livré avec
  l'exécutable, remplace chaque `<link>` et `<script src>` par son contenu, puis ajoute les blocs de données,
  `benchmark.json` et les `MAQ-*.json.gz` du dossier de la base.
  - Le contenu intégré est échappé : `</` devient `<\/` dans les scripts et le JSON.
  - Les paramètres `?v=` sont retirés.
  - Seuls les fichiers attendus sont lus, avec le même filtre de nom que `WebModel` pour les maquettes.
- **Écriture** dans un fichier temporaire du dossier choisi, puis remplacement du fichier : OneDrive ne synchronise
  jamais une version à moitié écrite.
- **Bouton** « Version HTML » (transparent, icône globe) à côté de « Ouvrir le benchmark ». Il régénère
  `SIA Check - Benchmark.html` à côté de benchmark.json, puis l'ouvre dans le navigateur par défaut.
- **Tests** : l'assembleur sur un petit dashboard de test. Il ne doit rester aucune référence externe locale, les
  blocs doivent être présents et l'échappement correct. La page assemblée doit aussi s'ouvrir en `file://` dans le
  navigateur intégré, avec Tendances, la carte, la 3D et l'export Excel.

## Partie 3 — Versions partagées par groupe d'utilisateurs (18.11.2026)

Demande : les versions HTML représentent la base à tout instant, sont mises à jour dès qu'un utilisateur de l'app la
modifie, et on contrôle qui voit quoi, avec plusieurs versions dans des dossiers côte à côte aux droits distincts.

| Sujet | Décision |
|---|---|
| Base | Dans SharePoint, pour que tous les utilisateurs de l'app l'alimentent. Test : `DEV DET\Base` (copie de la base locale). |
| Groupes | Champ « Groupe d'utilisateurs » de la fiche identité, écrit dans InfosProjet du MDP (le MDP fait foi). Valeurs : Admin, Light (`ProjectIdentity.UserGroups`). Sans groupe : Admin. |
| Contenu | Version Admin : tous les projets. Version Light : les seuls projets du groupe Light, et plus tard sans les données SIG. Le moteur recalcule la version Light sur ses projets (`--benchmark-groupe`) : médianes, typologies et distances ne trahissent pas les autres projets, et les erreurs (noms de fichiers) n'y vont pas. |
| Dossiers | `Benchmark Admin` et `Benchmark Light`, à côté du dossier de la base. Les droits se gèrent sur chaque dossier dans SharePoint. Les utilisateurs de l'app doivent pouvoir écrire dans tous. |
| Mise à jour | Après chaque lecture de la base (ajout, republication, identité, relecture, ouverture de l'app quand un autre utilisateur a modifié la base), l'app republie chaque version. Une empreinte (balise `sia-empreinte`, tout le contenu sauf l'heure de lecture) évite de réécrire une version inchangée. Une version sans projet est publiée aussi : la page le dit, et elle ne garde pas de projet retiré du groupe. |
| Bouton de l'app | « Version HTML » ouvre la version Admin partagée, publiée d'abord si elle manque. |
| Journal | `%LOCALAPPDATA%\SiaCheckViewerenchmark\publication.log` : lectures de la base et publications de ce poste. |

Limites connues :
- deux utilisateurs qui publient au même moment : le dernier écrit gagne, sans dommage (même base) ;
- la version Light ne contient pas encore de données SIG (la collecte n'existe pas) : à exclure quand elle arrivera ;
- un utilisateur de l'app sans droit d'écriture sur un dossier de version : échec signalé, la version ne suit plus.

## Partie 4 — Collecte des données SIG à l'intégration (18.11.2026)

Étape 1 de « Données SIG des projets du benchmark » (docs/ROADMAP.md). Les 11 projets de la base ont désormais une
adresse exacte (10 à l'adresse, Côté Gare L04 à la rue) : la collecte peut partir de leur position.

| Sujet | Décision |
|---|---|
| Quand | À chaque lecture de la base par l'app : tout projet sans fiche, ou qui a changé de place (> 10 m), est collecté. Couvre l'ajout, la republication, le rattrapage et les ajouts des autres utilisateurs. |
| Mise à jour | Fiche figée à la collecte, datée, chaque valeur avec son année et sa source. Refaite seulement si l'adresse change (ou si le format de fiche change). |
| Rayon | Au point du projet : zone à bâtir, ISOS, radon, sol de fondation, desserte, accessibilité, temps jusqu'au centre, arrêt desservi le plus proche, bâtiment RegBL le plus proche et son besoin de chaleur. Dans 300 m : habitants, logements et emplois à l'hectare (total du disque / 28,3 ha). |
| Réseau | Seules les coordonnées LV95 partent vers geo.admin.ch (API identify). Sans réseau : collecte reportée, signalée par l'app, reprise à la lecture suivante ; la lecture de la base n'est jamais bloquée. |
| Fiche | `SIG-<id>.json` à côté du MDP (format `sia-check-sig`, version 1), relue par le moteur dans `benchmark.json` (champ `sig` de chaque projet). |
| Groupes | Version Admin : avec les données SIG. Version Light : sans (`sig` vide), comme décidé en partie 3. |

Moteur : `sia_check/sig.py`, option `--benchmark-sig` (avec `--benchmark`). App : la lecture de la base passe l'option,
journalise la ligne « SIG : … » et signale une collecte reportée.

Constats sur geo.admin.ch, pris en compte :
- une réponse est plafonnée vers 200 résultats, toutes années mêlées : les densités sont demandées année par année
  (`timeInstant`), de la plus récente à la plus ancienne ;
- une année publiée incomplète (STATENT 2024 : 56 emplois là où 2023 en compte 865) est écartée : une année qui perd
  plus de la moitié du total de la précédente cède la place à celle-ci ;
- le calque des arrêts compte des points d'exploitation sans voyageurs (raccordements) : seuls les arrêts desservis
  et nommés sont retenus ;
- bruit routier et ferroviaire, fibre et ruissellement ne répondent pas point par point (calques image) : exclus ;
- le calque « quartiers statistiques » renvoie en fait les zones de transport de l'ARE : exclu en attendant mieux.

Non fait à cette étape : l'affichage (onglet « Contexte », étape suivante), les plans d'urbanisme cantonaux.

## Partie 5 — Onglet « Contexte » et type de site (18.11.2026)

Affichage des fiches SIG de la partie 4. Une première version (nuage de points, tableau de 15 colonnes) a été
remplacée le jour même, après une analyse des données qui comptent pour un développeur immobilier.

**Question de départ.** Le benchmark doit dire quels ratios espérer pour un site semblable au mien. Les données SIG
servent donc à comparer des projets de contexte comparable et à expliquer les écarts, pas à décrire chaque projet.

| Donnée | Valeur | Usage |
|---|---|---|
| Classe de desserte TP | Forte | Fixe le parking exigé (norme VSS), donc le sous-sol. Groupes A-B / C-D. |
| Densité alentour (habitants + emplois / ha, 300 m) | Forte | Donne le type de site. |
| Zone à bâtir | Moyenne | Groupes : habitation, centrale ou mixte, autre. |
| Site ISOS, radon ≥ 10 %, sol D-E-F | Alerte | Badges de vigilance, pas de chiffre. |
| Temps jusqu'au centre, arrêt | Faible | Fiche du projet seulement. |
| Accessibilité, logements / ha | Doublons | Plus affichés. Ils restent dans les fiches. |
| Bâtiment RegBL, besoin de chaleur | Peu fiables | Plus affichés. Ils sont pris sur le bâtiment le plus proche, parfois un voisin. |

**Type de site.**
- Classes :
  - « Urbain dense » dès 150 habitants + emplois / ha ;
  - « Urbain » dès 60 ;
  - « Périurbain » dès 20 ;
  - « Rural » en dessous.
- Calculé par le moteur (`sig.type_site`) à la construction de benchmark.json, champ `sig.site`. Il n'est pas figé
  dans la fiche : les seuils peuvent évoluer sans recollecter.
- La typologie officielle des communes (OFS) n'est pas interrogeable sur geo.admin.ch, et elle classe une commune
  entière.
- Base au 18.11 : 2 urbain dense, 6 urbain, 2 périurbain, 1 rural.

**Pré-filtre.**
- Quatrième critère « Type de site », à côté de Typologie, Canton et Intervention.
- Tous les onglets répondent alors pour un site semblable.
- Il est masqué sans fiche SIG (version Light).
- Il est aussi proposé en premier dans « Élargir ».

**Onglet.**
- **Synthèse** : quatre cartes.
  - Répartition par type de site.
  - Part bien desservie.
  - Part en zone centrale ou mixte.
  - Points de vigilance.
- **Le contexte change-t-il les ratios ?**
  - Un ratio au choix, par défaut SP sous-sol / SUP. Pour chacun des trois groupements, une ligne par groupe :
    médiane, bande de la moitié centrale, un point par projet, maquettes comparées en couleur.
  - Échelle commune cadrée par la règle de Tukey : un projet extrême est posé au bord, en rond vide.
  - Phrase de lecture seulement entre groupes d'au moins 3 projets. Sinon : « pas assez de projets pour conclure ».
  - Le choix est mémorisé sous `benchmark.contexte`.
- **Fiches de contexte** : une carte par projet.
  - Type de site, desserte, arrêt, zone, densité alentour, temps jusqu'au centre, badges de vigilance.
  - Survol : source et année.
  - Clic : le projet dans les Tendances.

**App.**
- Les versions HTML sont aussi reconstruites à l'ouverture quand la base est inchangée.
- Avant, une nouvelle version de l'app ne republiait rien tant que personne ne modifiait la base.
- L'empreinte évite toute réécriture inutile.

**Constat.** Avec 7 projets de référence, aucun groupement n'a deux groupes d'au moins 3 projets : la page le dit.
Sur le sous-sol, les premières valeurs vont à l'inverse de l'hypothèse sur la desserte (plus de sous-sol en desserte
A-B qu'en C-D), sur trop peu de projets pour conclure. C'est à revoir quand la base aura grossi.

**Non fait.**
- Surface de parcelle et indice d'utilisation du sol : la donnée de plus forte valeur, à chercher dans les cadastres
  cantonaux.
- Colonnes de contexte dans l'export Excel.
- Carte en grand dans l'onglet.
- Contexte de « Mon projet » depuis son adresse.

## Partie 6 — Contexte : trouver les projets similaires au mien (18.11.2026)

Nouvel usage de l'onglet, demandé après essai de la partie 5. La synthèse et les comparaisons par groupe étaient
vides en pratique : elles ne comptaient que les projets de référence cochés, et ces groupes avaient trop peu de
projets.

**Usage.** En amont d'un projet, sans aucune surface :
1. on saisit son adresse et sa typologie ;
2. l'onglet classe les projets de la base du plus au moins semblable par le contexte ;
3. un bouton prend les projets cochés comme référence et ouvre les Tendances : Tendances et Programmer travaillent
   alors sur des projets de contexte semblable.

**Adresse.** Le texte de l'adresse est envoyé au service de recherche de geo.admin.ch (SearchServer), puis ses
coordonnées à l'API identify. C'est une décision de l'utilisateur du 18.11.2026 : jusque-là, seules des coordonnées
partaient.
- Plusieurs adresses possibles : la page propose de choisir.
- La recherche (adresse, contexte lu) est mémorisée dans le navigateur seulement (`benchmark.contexte.projet`).

**Collecte dans la page.** `collecterContexte` (app.js) reprend `sia_check.sig.collecter` pour les seules données
qui servent à comparer :
- zone, ISOS, radon, sol, desserte, temps jusqu'au centre, arrêt ;
- habitants et emplois dans 300 m, avec la même règle d'année incomplète.

Les seuils du type de site sont recopiés (`SEUILS_SITE`) : à garder alignés avec `sig.TYPES_SITE`.

**Similarité.** Chaque critère donne un écart de 0 (identique) à 1 (opposé). Similarité = 1 − moyenne pondérée des
écarts, sur les critères connus des deux côtés.

| Critère | Poids | Écart |
|---|---|---|
| Densité alentour (habitants + emplois / ha) | 3 | écart des logarithmes : un facteur 10 = écart maximal |
| Classe de desserte | 3 | A à D : 1/3 par classe |
| Zone (habitation, centrale ou mixte, autre) | 2 | identique ou non |
| Canton (règlements, normes de stationnement) | 2 | identique ou non |
| Temps jusqu'au centre | 1 | 45 min d'écart = maximal |
| Mixité (part des emplois alentour) | 1 | 50 points d'écart = maximal |
| Site ISOS | 1 | identique ou non |

**Résultats.**
- Toute la base est classée, quels que soient le pré-filtre et les cases cochées.
- La typologie choisie filtre ; « Toutes » garde tout.
- Chaque ligne donne la similarité en %, puis une pastille par critère :
  - verte : proche ;
  - orange : assez proche ;
  - grise : différent, avec la valeur de mon projet.
- Les 5 premiers projets aux surfaces fiables sont cochés d'office. Les projets non fiables sont listés mais ne
  peuvent pas servir de référence.
- La fiche de mon projet est à gauche, les fiches de tous les projets de la base en dessous.

**Vérifié.**
- L'adresse de L'Orée retrouve L'Orée à 100 % : la collecte de la page rejoint celle du moteur.
- Avenue de Morges 26, Lausanne (urbain dense, desserte A) : Sauvabelines 87 %, Côté Gare 86 %, Le Clos des
  Hêtres 79 %…
- Le bouton prend les 5 projets cochés comme référence.

**Retirés de l'onglet** (partie 5) : la synthèse en 4 cartes et les comparaisons par groupe. Le critère « Type de
site » du pré-filtre reste.

**Non fait.** Placer le projet d'un clic sur la carte. Rattacher le contexte saisi à « Mon projet » des Tendances.

## Partie 7 — Terrain, indice d'utilisation et contexte dans l'export (18.11.2026)

**Source.** La parcelle sous le point du projet est lue sur geo.admin.ch (calque `ch.kantone.cadastralwebmap-farbe`,
mensuration officielle publiée par les cantons) : numéro, EGRID et polygone.
- La surface est calculée sur le polygone, trous déduits.
- Quand plusieurs immeubles se superposent (droit de superficie posé sur un bien-fonds), on garde le plus grand,
  qui est le bien-fonds. Le nombre d'immeubles superposés est noté (`superposes`).
- Vérifié sur les 11 projets de la base : une parcelle pour chacun, et la même que celle du registre des bâtiments
  pour L'Orée (2015).

**Fiche SIG version 2.** La fiche porte la parcelle (`parcelle` : valeur en m², numéro, EGRID, canton). Le changement
de version recollecte toutes les fiches à la lecture suivante de la base.
- Une connexion coupée par le serveur est réessayée deux fois (`ESSAIS`, `PAUSE`) avant de conclure au réseau absent.
- Avant ce correctif, une seule coupure reportait toute la collecte : constaté sur la base réelle, 3 fiches sur 11.

**Terrain du projet.** C'est le dénominateur de l'indice, dans les totaux sous la clé `TERRAIN` (`benchmark.terrain`).
Ordre de priorité :
1. la saisie « Surface du terrain (m²) » de la fiche identité, nouveau champ du MDP et du formulaire d'identité de
   l'app. Elle sert quand le projet couvre plusieurs parcelles, ou une partie seulement ;
2. sinon, la parcelle de la fiche SIG.

L'origine est donnée dans `infos.terrain_source`. Version Light : seule la saisie du MDP compte, sans données SIG.

**Indice d'utilisation.** Nouveau KPI `SP_HS/TERRAIN`, groupe « Terrain », neutre (dicté par le règlement).
- Il apparaît partout comme les autres ratios : Tendances, Base, Excel.
- C'est une approximation de l'IUS réglementaire, sans ses déductions.

Base au 18.11 : des indices plausibles pour la plupart des projets. Deux indices élevés sont à vérifier : le projet
couvre sans doute plusieurs parcelles, et sa surface de terrain est à saisir dans le MDP. Un projet n'a pas d'indice,
faute de SP hors-sol dans son MDP. Les valeurs par projet restent dans la base : elles ne sont pas reprises ici.

**Onglet Contexte.**
- La recherche lit aussi la parcelle de l'adresse saisie.
- La colonne de gauche ajoute le **potentiel de la parcelle** : SP hors-sol = IUS médian des projets cochés ×
  surface de la parcelle, avec la moitié centrale (dès 3 projets), sinon le minimum et le maximum.
- Le bouton « Programmer avec cette SP » prend les projets cochés comme référence, reporte la SP dans Programmer et
  ouvre l'onglet.
- Chaque fiche affiche son terrain (et son origine) et son IUS. La liste des similaires affiche l'IUS de chaque projet.
- Vérifié avec une adresse de test à Lausanne : parcelle trouvée, SP hors-sol estimée, puis reportée dans Programmer,
  qui en déduit la SUP et le nombre de logements attendus.

**Export Excel (point 3 de la roadmap).**
- Feuille « Projets de référence » : colonne Terrain (m²), avec son total et sa médiane.
- Avec des fiches SIG : colonnes Type de site, Desserte TP, Zone à bâtir, et une légende.
- L'IUS figure dans les feuilles des ratios, comme tout KPI.

**Non fait.**
- Les IUS réglementaires (plans d'affectation cantonaux).
- L'effacement d'une saisie de terrain depuis l'app : un champ vidé n'efface rien dans le MDP, règle commune à la
  fiche identité.

## Partie 8 — Module « Données SIG » (18.11.2026)

Un module à part, à côté du benchmark : la carte de toute la base, avec à gauche la fiche SIG de chaque projet et des
filtres pour trouver les projets selon leur contexte.

**Accès.**
- Version HTML : une tuile « Données SIG » sur l'accueil, à côté de « Benchmark ». Elle est désactivée sans données
  SIG (version Light : « Pas de données SIG dans cette version »).
- SIA Check : un bouton « Données SIG » en haut à droite de la colonne Benchmark de l'accueil.
  - Il ouvre la page du dashboard avec `?module=sig`.
  - Le titre de l'écran suit le module affiché : la page envoie `module:sig` ou `module:` à l'app, sans recharger.

**Page.**
- Écran à part (`#module-sig`, classe `mode-sig`). La barre d'onglets et le pré-filtre du benchmark sont masqués.
- En-tête : maison (version HTML), titre, nombre de projets filtrés, « Cadrer », « Ouvrir le benchmark ».
- La vue carte des Tendances (`#vue-carte`) est déplacée dans le module, puis rendue à son emplacement en sortant :
  même carte, mêmes fonds et calques.
- Masqués dans le module : la croix, les outils de zone (référence), les filtres de la carte, le rayon et « Sans
  position » (classe `hors-module`).
- `projetsCarte()` rend les projets filtrés par le module : toute la base, sans pré-filtre ni référence.
- Clic sur un point : la fiche du projet est mise en évidence et amenée à l'écran. Clic sur une fiche : la carte se
  centre sur le projet.

**Filtres** (`CRITERES_SIG`, `PLAGES_SIG`, dans carte.js).
- Recherche (ID, nom, commune, adresse).
- Critères à cocher, avec le nombre de projets de chaque valeur selon les autres filtres :
  - typologie, canton, type de site, desserte TP (A à D), zone à bâtir ;
  - points de vigilance (site ISOS, radon, sol meuble).
- Les valeurs d'un même critère s'additionnent ; les critères se cumulent.
- Plages min–max : habitants + emplois à l'hectare, temps jusqu'au centre, distance à l'arrêt, terrain, indice
  d'utilisation.
- « Surfaces fiables seulement ».

**Fiches.**
- L'essentiel : terrain et IUS, desserte, arrêt, zone, densité alentour, centre, badges de vigilance.
- Un dépliant « Toutes les données SIG » donne chaque valeur de la fiche, avec son année et sa source : parcelle et
  EGRID, accessibilité, habitants, logements et emplois à l'hectare, bâtiment le plus proche, besoin de chaleur.

**Correctifs au passage.**
- Le dashboard démarrait parfois avant le chargement de carte.js (`brancherOutilsCarte` introuvable), en mode serveur
  et dans SIA Check. Il attend désormais la page entière (`quandPret`), comme la version HTML.
- La carte se remesure quand son cadre change (`ResizeObserver`). Sans cela, ses tuiles ne couvraient qu'une partie
  de la vue après un déplacement.

**Vérifié.**
- Navigateur : filtres (desserte A → 5 projets, puis zone mixte → 2, densité ≥ 100 → 6), clic sur un point, fiche
  dépliée, retour au benchmark avec la carte rendue aux Tendances.
- Version HTML publiée : tuile, ouverture, maison, retour au benchmark ; Light avec la tuile désactivée.
- SIA Check : bouton, ouverture du module, titre de l'écran.

## Points ouverts

- Dossier SharePoint de destination et liste des personnes qui y ont accès. Le groupe envisagé le 02.11 :
  développement immobilier et équipe BIM.
- Raccourci pour les utilisateurs sans SIA Check (public principal de la version HTML) : il doit viser la copie
  synchronisée de la bibliothèque SharePoint, dont le chemin dépend de chaque poste. Le bouton de SIA Check ne crée
  pas de raccourci (décision du 18.11.2026). À définir avec la bibliothèque : marche à suivre pour le créer soi-même,
  ou petit outil déposé à côté du fichier.
- Informer l'IT ou non. Poser un fichier dans une bibliothèque interne est un usage courant de SharePoint, sans
  hébergement ni ressource Azure.
- Taille au-delà de 50 projets : vérifier le temps d'ouverture, et choisir entre maquettes à la demande et maquettes intégrées.
- Aucune donnée de la base n'entre dans le dépôt : le HTML exporté est ajouté au `.gitignore` par précaution.

## Journal

- 18.11.2026 : choix du fichier autonome, des maquettes intégrées et du bouton d'export dans SIA Check.
- 18.11.2026, partie 1 faite :
  - **Blocs intégrés.** Les fichiers sont dans des blocs `<script type="application/…" data-fichier="nom">`, lus par
    `fichierIntegre`, `jsonIntegre` et `octetsIntegres` (app.js). `INTEGRE` vaut vrai quand `benchmark.json` est
    intégré.
  - **Modules nommés par l'import map** (`three`, `three/orbit`, `sia/vue3d`) : la version autonome les fait pointer
    vers des URL `data:text/javascript;base64,…`. C'est validé en `file://` sur Edge et Chrome, et les URL `blob:` sont
    inutiles. `VERSION_PAGE` disparaît : la version des fichiers est portée par l'import map.
  - **Démarrage.** En version autonome, il attend `DOMContentLoaded`, car les données sont disponibles avant
    `carte.js`.
  - **Projets sans maquette intégrée** : ils perdent leur icône cube.
  - **Stockage.** Les clés sont préfixées `sia-check.` en version autonome seulement, pour que SIA Check garde la
    sélection déjà mémorisée.
  - **geo.admin.ch** répond aux requêtes d'origine `null`. Les fonds de carte et les calques fonctionnent.
  - **Vérifié** avec un prototype d'assembleur, en `file://` dans Edge et Chrome sans fenêtre : 11 projets,
    vue 3D, carte avec ses tuiles, export Excel, aucune erreur. Le mode serveur ne régresse pas.
  - **Pour la partie 2.**
    - Dans les scripts, n'échapper que `</script` en `<\/script` : remplacer `</` tout court casserait le code. Dans le
      JSON, `</` devient `<\/`.
    - Placer Leaflet (script et feuille de style) avant `app.js`, et `xlsx.js` après `carte.js`, car il était chargé
      en `defer`.
    - Fichier de test : 3,3 Mo pour 11 projets et 2 maquettes.
- 18.11.2026, partie 2 faite :
  - `Services/StandaloneDashboard.cs` assemble la page. Si la page du dashboard ne correspond pas à ce qu'il attend,
    il s'arrête au lieu de produire une page cassée.
  - La commande `OpenBenchmarkHtml` et le bouton sont sur l'accueil.
  - Tests : `StandaloneDashboardTests`, 157 tests verts.
  - Vérifié : l'export de la vraie base par l'assembleur C# fait 3,3 Mo. Ouvert en `file://` dans Edge, il affiche
    les données, la 3D, la carte et l'export Excel, sans erreur.
- 18.11.2026 : bandeau retiré. Mode application (fenêtre sans barre d'adresse, installation) abandonné : impossible
  pour un fichier local dans Chrome, seul navigateur utilisé.
- 18.11.2026 : **page de garde** de la version HTML.
  - Elle reprend l'accueil de SIA Check : « Benchmark », le titre, le bouton « Ouvrir le benchmark » et le nombre de
    projets de référence avec la date de la base.
  - Un bouton thème, en haut à droite, propose les six thèmes de SIA Check.
  - Le thème par défaut est **Amber clair** (orange clair). Il est propre à chaque poste : gardé dans le stockage
    local du navigateur, sous `sia-check.benchmark.theme`.
  - Un script d'en-tête d'index.html applique le thème avant tout affichage. Il n'agit que si la page porte la balise
    `<meta name="sia-autonome">`, ajoutée par l'assembleur : SIA Check et le mode serveur ne changent pas.
  - Le dashboard ne démarre qu'au clic sur « Ouvrir le benchmark ».
  - Vérifié dans Chrome en `file://` : Amber clair par défaut, le thème choisi est retrouvé après réouverture, le
    benchmark s'ouvre sans erreur.
- 18.11.2026 : **vraie page d'accueil**.
  - **Bandeau SIA Check** : le nom, une ligne de présentation et le bouton thème.
  - **Grille de tuiles**, une par outil. Elle est générée depuis `TUILES` (app.js) : un outil de plus, c'est une
    entrée de plus, avec icône, titre, description, détail et action.
  - **Pied de page** : la date de la base et la mention de confidentialité.
  - **Bouton maison**, en tête de la barre du benchmark (version autonome seulement, classe `autonome`) : il ramène
    à l'accueil. Le benchmark reprend ensuite où on l'a laissé, avec la sélection et le défilement.
  - Vérifié dans Chrome en `file://`.
- 18.11.2026 : **partie 3**, versions Admin et Light partagées, mises à jour à chaque lecture de la base. Moteur :
  champ « Groupe d'utilisateurs » et option `--benchmark-groupe`. App : groupe dans la fiche identité, publication
  dans `Benchmark <groupe>` à côté de la base, empreinte, journal. Tests : 3 tests Python, 3 tests C#.
- 18.11.2026 : adresses exactes des 11 projets écrites dans leurs MDP (canton de 1023 corrigé VS → VD ; canton et
  commune ajoutés pour 1280, 1746, 1778, 1784). Correctifs : registre des adresses téléchargé quand une relecture
  révèle des adresses ; NPA couvrant deux communes (1213).
- 18.11.2026 : **partie 4**, collecte SIG. 11 fiches collectées dans DEV DET\Base, version Admin republiée avec le
  contexte, version Light sans. Tests : 5 tests Python (geo.admin.ch simulé).
- 18.11.2026 : **partie 5**, onglet Contexte, puis refondu le même jour : type de site au pré-filtre, comparaisons par groupe, fiches courtes ; publication des versions HTML à chaque ouverture de l'app. Tests : 2 tests Python.
- 18.11.2026 : **partie 6**, l'onglet Contexte devient la recherche de projets similaires à une adresse (adresse envoyée à geo.admin.ch, décision de l'utilisateur).
- 18.11.2026 : **partie 7**, parcelle et indice d'utilisation (fiche SIG v2, champ « Surface du terrain »), potentiel de la parcelle et passage au Programmer, contexte dans l'export Excel. Tests : 4 tests Python.
- 18.11.2026 : **partie 8**, module « Données SIG » (carte de toute la base, fiches et filtres SIG), accès par l'accueil HTML et par l'accueil de SIA Check.
