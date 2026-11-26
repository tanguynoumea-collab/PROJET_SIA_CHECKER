# Carte d'identité d'un projet

Proposition du 20.11.2026, à valider avec le service de développement immobilier (DEV). Elle définit les données que
la base doit tenir pour chaque projet, ce qu'il faut ajouter, ce qu'il faut retirer, et où aller chercher ce qui manque.
La suite (outil de préconception) est dans docs/ROADMAP.md, partie « Vers l'outil de préconception du DEV ».

> **Dans SIA Check depuis le 20.11.2026 :** clic droit sur un projet de l'accueil (retrouvé dans la base par son ID)
> ou de la liste « Base de données », puis « Carte d'identité ». Le moteur calcule la carte à chaque lecture de la base
> (src/sia_check/carte.py, porté par benchmark.json, version complète seulement) : valeurs du MDP, de la fiche SIG et de
> la maquette 3D de la base (emprise, GSI, L, OSR, hauteur, épaisseur, orientation, socle). Ce qui manque est affiché
> « à collecter » avec la source qui doit le fournir. En tête de la carte : le volume du projet en rouge, en
> axonométrie, à la manière des pictogrammes de forme de Density (tiré de la maquette 3D de la base, sinon schéma
> d'après la forme saisie), puis sa forme bâtie, sa densité avec la tranche a+t, et sa typologie.
>
> **Compléter la carte** (20.11.2026) : une jauge circulaire donne le taux de remplissage, en quatre couleurs (une par
> rôle). Le bouton « Compléter la carte » range ce qui manque par qui doit agir : **à renseigner par vous** (saisies
> écrites dans InfosProjet du MDP de la base, propositions de SIA Check pré-remplies, fiche identité), **automatique dès
> que…** (groupé par prérequis manquant : maquette 3D dans la base, adresse exacte…), **à demander** (coûts, revenus :
> demande prête à copier), **module à venir** (RDPPF, règlements, OFS…). Chaque champ porte son mode de remplissage
> dans carte.py (`SAISIES`, `PREREQUIS`, `MODULES`, `DEMANDES`).
>
> **Remplir avec une IA** : « Copier le prompt IA » prépare un prompt (projet, données, valeurs permises, règles : rien
> d'inventé, « ? » si absent, source citée) qui impose un bloc de réponse « === SIA CHECK · CARTE D'IDENTITÉ · ID … === ».
> On l'envoie à l'IA de son choix avec les documents du projet, on copie le bloc rendu, puis « Coller la réponse de
> l'IA » le lit (app/SiaCheck.Viewer/Services/CardPrompt.cs) : valeurs de liste normalisées, nombres relus sans unité,
> ID du projet contrôlé, valeurs refusées signalées. Les champs sont pré-remplis et marqués ; rien n'est écrit dans le
> MDP avant « Enregistrer ». La liste des champs vit dans carte.py (`CHAMPS`) ; la partie 3
> ci-dessous et la page publiée en sont tirées par docs/carte_identite.py.
>
> **Exploitée au benchmark (V7, 26.11.2026, docs/V7_PLAN.md)** : origine de chaque valeur (saisie, IA, proposé, MDP,
> maquette, calcul, SIG), polygone de la parcelle gardé dans la fiche SIG (forme, orientation, plan d'implantation),
> vignette d'implantation au 1:5000, opération d'ensemble et sa densité. Le dashboard reçoit un résumé de la carte pour
> chaque projet (`carte.resume`) : pré-filtres forme bâtie et distribution, onglet Formes (Spacematrix et planche des
> implantations à échelle constante), similarité qui compte le GSI, la forme bâtie et le type de site.

## 1. Le principe : contraintes → réponse → performance

Le benchmark sert aujourd'hui à dire « quels ratios viser ». L'outil visé doit partir d'une **parcelle** dont on ne
connaît que les contraintes, et proposer un projet. Pour cela, chaque projet de la base doit décrire, avec **les mêmes
champs qu'une parcelle nue**, les contraintes qu'il a reçues. Sinon on ne peut pas retrouver « les projets qui ont
reçu les mêmes contraintes que ma parcelle » et regarder ce qu'ils en ont fait.

La carte est donc rangée en trois rôles :

| Rôle | Question | Connu sur une parcelle nue ? | Exemples |
|---|---|---|---|
| **Contraintes** (entrées) | Qu'est-ce qu'on a reçu ? | Oui | parcelle, pente, zone, indices, hauteur max, contexte, marché |
| **Réponse** (choix de conception) | Qu'est-ce qu'on en a fait ? | Non : c'est ce que l'outil doit proposer | implantation, forme, hauteur, épaisseur, distribution, programme |
| **Performance** (résultats) | Combien ça a rendu, combien ça a coûté ? | Non : c'est ce que l'outil doit prédire | surfaces SIA 416, ratios, coûts, revenus |

Le raisonnement du futur outil suit cet ordre : contraintes de ma parcelle → projets aux contraintes proches → leurs
réponses (formes, épaisseurs, distribution) → leurs performances (ratios, coûts), qui servent de cible.

Aujourd'hui la base est forte sur la **performance** (surfaces et ratios), a commencé les **contraintes** (fiche SIG)
et ne décrit la **réponse** que par la forme des bâtiments. C'est le bloc à construire en premier.

## 2. Ce que nous reprenons de *Density* (a+t) et du *Spacematrix*

> Vérifié le 20.11.2026 sur le scan de *Density: New Collective Housing* (a+t, Fernández Per et Mozas, édition revue et
> augmentée ; 00_RESSOURCES, 131 pages lues). Le scan couvre environ 40 % du livre : la « Guía del usuario » (p. 6-8,
> définitions officielles) et les quatre essais manquent. Les numéros « scan pNNN » renvoient aux pages du PDF.

### Comment le livre est construit

- **Classement principal par densité**, en logements par hectare : moins de 50, 50 à 100, 100 à 200, 200 à 300, plus de
  300 (sommaire, scan p002-p003). Chaque tranche a sa couleur et se termine par un essai. La densité est le nombre de
  logements divisé par la surface du terrain (vérifié sur les plans urbains : 11 937 / 340 ha = 35).
- **Un bâtiment situé dans un plan urbain est classé à la densité du plan**, pas à la sienne : un projet d'Ypenburg à
  près de 290 log./ha sur sa parcelle est rangé avec son quartier, à 35 (scan p021-p025). Le livre distingue densité
  brute du plan et densité nette des parcelles (Borneo-Sporenburg, scan p099) sans définir le passage de l'une à l'autre.
- **Deux planches comparatives à échelle constante** : toutes les implantations au 1:5000, rangées par surface de
  terrain croissante (scan p004-p006), puis les grands ensembles au 1:20 000 (scan p007-p008). Plans d'étage au 1:500,
  détails au 1:20.
- **Un classement des formes bâties, « Formalizaciones / Housing forms »** (scan p009-p012), voir plus bas.
- Une partie des projets est suisse : E2A et Gigon & Guyer à Kilchberg, EM2N à Zurich (coopérative, 2,5 à 5,5 pièces),
  Baumschlager & Eberle à Saint-Gall, Kraftwerk 1 à Zurich.

### La fiche projet du livre, comparée à notre carte

Chaque projet a le même bandeau de 11 champs (scan p013, p035, p101…). Les plans urbains ont un bandeau réduit qui
ajoute la densité.

| Champ a+t (es / en) | Format dans le livre | Chez nous |
|---|---|---|
| AUTORES / AUTHORS | bureau d'architectes | **ajouté** : Architecte (bureau), à saisir |
| SITUACIÓN / LOCATION | adresse, ville, pays | existe (adresse, commune, canton, position) |
| FECHA / DATE | année d'achèvement, ou « 1995- » en cours | existe (année d'achèvement, à clarifier) |
| VIVIENDAS / DWELLINGS | nombre | existe |
| SUPERFICIE / SITE AREA | ha, deux décimales, « no disponible » admis | existe (m², saisie ou cadastre) |
| SUPERFICIE CONSTRUIDA / FLOOR AREA | m² bruts, tous usages confondus | existe et plus précis : SP SIA 416, hors-sol et sous-sol |
| OTROS USOS / OTHER USES | NO, ou liste (commerces, bureaux, crèche), parfois en m² | existe : répartition des affectations en % de la SUP |
| APARCAMIENTO / PARKING | places (« pp »), ou m², ou NO | existe (places), type de stationnement à saisir |
| ALTURAS / FLOORS | niveaux, plage « 3-6 », « 3+ », « 4,5 » | existe, avec la plage par bâtiment depuis la maquette |
| SÓTANOS / BASEMENTS | nombre ou NO | existe (niveaux de sous-sol) |
| Forme bâtie et pictogramme | une des 33 formes | **ajouté** : Forme bâtie (classement a+t), proposée puis confirmée |
| DENSIDAD / DENSITY (plans urbains) | log./ha | existe, avec la tranche a+t ; **ajouté** : opération d'ensemble et sa densité |

Ce que le livre **ne mesure pas** et que notre carte porte déjà ou prévoit : surfaces normées (SIA 416, USPI), emprise et
indices de sol, ratios de rendement, mix chiffré, distribution et logements par palier, coûts, maître d'ouvrage,
statut d'occupation, règles d'urbanisme, énergie, loyers et prix. Sur ces points, notre carte va plus loin que le
livre. Ce que le livre nous apporte : le classement des formes, la densité comme clé de lecture et la comparaison
graphique à échelle constante.

### Le classement des formes bâties (« Formalizaciones »)

Cinq familles, 33 types, traduits du livre. « Contre mitoyen » : bâtiment adossé à un mitoyen existant (en gris dans
les pictogrammes). Repris tel quel dans src/sia_check/carte.py (`FORMALISATIONS`).

| Famille | Types |
|---|---|
| **Maisons** | maisons accolées · rangée pliée · rangée en gradins · maisons accolées autour d'une cour · rangée · rangée avec patios |
| **Blocs** | bloc linéaire · blocs parallèles · bloc en L · bloc en L contre mitoyen · bloc en T · bloc linéaire avec cours · bloc superposé · bloc en U · blocs parallèles perforés · blocs parallèles contre mitoyens · blocs en épi · blocs groupés |
| **Îlots** | demi-îlot · îlot semi-ouvert · îlot ouvert · îlot fermé · îlot en U · îlot plié · îlot en gradins · îlot perforé |
| **Immeubles hauts** | bloc isolé · immeubles hauts groupés · bloc perforé · bloc allongé |
| **Solutions mixtes** | bloc en gradins et rangée · bloc linéaire contre mitoyen et maisons à patio · bloc linéaire et îlot fermé |

Deux niveaux restent distincts : nos **13 formes** décrivent le plan de chaque bâtiment (emprise vue d'avion) ; la
**forme bâtie a+t** décrit le projet entier, volume et implantation compris. La carte propose la seconde d'après la
première : une barre seule donne un bloc linéaire, des barres de même orientation des blocs parallèles, un bâtiment de
30 m ou de 10 niveaux et plus un immeuble haut (seuil suisse des immeubles de grande hauteur). Les familles Maisons et
Solutions mixtes ne sont jamais proposées : elles dépendent des accès (chaque maison a son entrée), que la maquette ne
dit pas.

### Autres idées du livre reprises dans la carte

- **Hauteur du rez** (rez de 3,5 m, habitable ou commercial : Borneo, règles d'IJburg) : calculée depuis la maquette.
- **Densité ou programme imposés par le plan** (densité fixée d'avance à Venise, ratio logement / travail à IJburg) :
  bloc Règles.
- **Statut des espaces extérieurs** (cour privée, commune, semi-publique ; toit-jardin) et **public cible** (seniors,
  familles, mixte) : à saisir.
- **Diversité typologique** (nombre de types de logements : 26 à 36 dans les projets les plus mixtes) : à tirer des
  logements de la maquette.
- **Une valeur « non disponible »** distincte de zéro et de « aucun » : le livre l'assume ; la carte l'affiche « à
  collecter ».

### Le Spacematrix

Le **Spacematrix** (Berghauser Pont et Haupt, *Spacematrix: Space, Density and Urban Form*, 2010) complète le livre :
a+t montre que la densité ne dit pas la forme, le Spacematrix le mesure avec quatre indicateurs, calculés par la carte.

| Indicateur | Définition | Chez nous |
|---|---|---|
| **FSI** (densité bâtie) | SP hors-sol / surface du terrain | KPI « Indice d'utilisation » |
| **GSI** (emprise) | emprise au sol / surface du terrain | calculé depuis la maquette (emprise.py) |
| **L** (niveaux moyens) | FSI / GSI | calculé |
| **OSR** (espace libre) | (1 − GSI) / FSI : m² de terrain libre par m² de plancher | calculé |

Le couple GSI × FSI place chaque projet sur un graphe où les formes se regroupent : c'est la carte de lecture qui
manque au benchmark pour dire « sur cette parcelle, avec ce FSI permis, voici les formes qui ont marché ».

## 3. La carte, par source de données

Chaque tableau regroupe les données qui viennent d'une même source : on voit ainsi qui doit les fournir et comment on les extrait. Colonnes : **Rôle** (contraintes, réponse ou performance, voir partie 1), **Type** et **unité** de la donnée, **Extraction** (comment on l'obtient), **Mode** (automatique, proposé puis confirmé, saisie, import) et **Statut** (existe, ajouter, modifier, reléguer hors de la carte, retirer).

### Vue d'ensemble

| Source | Qui fournit, comment | Existe | À ajouter ou modifier |
|---|---|---|---|
| Maquette (calcul SIA Check) | Déduit par nos soins de la maquette Treegram ou IFC, à la lecture du projet. Automatique. | 18 | 3 |
| Fiche projet (saisie) | Saisi dans la fiche « Identité du projet » de la visionneuse (feuille InfosProjet du MDP). Certains champs sont proposés par l'IA puis confirmés. | 17 | 0 |
| SIG fédéral (geo.admin.ch) | Interrogé automatiquement à partir de la position du projet, à chaque lecture de la base (fiche SIG-<id>.json). | 8 | 3 |
| Cadastre et RDPPF cantonal | Extrait officiel des restrictions de droit public, interrogé par le numéro EGRID de la parcelle. Automatique, une fois. | 0 | 4 |
| Règlements communaux | Lus par l'IA dans le règlement de la commune (souvent en PDF), puis validés par une personne. Stockés par commune et par zone. | 0 | 6 |
| Équipes travaux / réalisation | Fournis par la réalisation à la fin du chantier : décomptes, choix constructifs. Import d'un tableau type ou saisie. | 4 | 1 |
| Service DEV / gérance | Fournis par le développement immobilier ou la gérance : commercialisation, loyers, prix. Confidentiel, version Admin. | 4 | 2 |
| Statistiques publiques (OFS) | Séries publiques de l'Office fédéral de la statistique, mises à jour une fois par an. | 0 | 2 |
| Calcul SIA Check (dérivé) | Calculé à partir des autres champs de la carte. Automatique, rien à collecter. | 16 | 3 |

### Maquette (calcul SIA Check)

Déduit par nos soins de la maquette Treegram ou IFC, à la lecture du projet. Automatique.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Nombre de bâtiments | Implantation et forme | Réponse | Nombre | – | Bâtiments de la maquette, sinon de la feuille InfosBatiment | Automatique | existe |
| Emprise au sol | Implantation et forme | Réponse | Nombre | m² | emprise.py : union des SP hors-sol projetées en plan, somme des bâtiments | Automatique | existe |
| Hauteur hors-sol estimée | Implantation et forme | Réponse | Nombre | m | Du plancher du rez au dernier plancher, plus une hauteur d'étage moyenne, sur la maquette 3D | Automatique | existe |
| Niveaux hors-sol | Implantation et forme | Réponse | Nombre | – | Étages hors-sol distincts portant de la SP | Automatique | existe |
| Hauteur du rez | Implantation et forme | Réponse | Nombre | m | Écart entre le plancher du rez et celui du 1er étage, sur la maquette 3D (a+t : rez de 3,5 m habitable ou commercial) | Automatique | existe |
| Niveaux de sous-sol | Implantation et forme | Réponse | Nombre | – | Niveaux de rang négatif de la maquette | Automatique | existe |
| Épaisseur du bâtiment | Implantation et forme | Réponse | Nombre | m | Largeur du rectangle minimal (emprise rectangulaire), sinon 2 × aire / périmètre de l'emprise | Automatique | existe |
| Orientation de l'axe principal | Implantation et forme | Réponse | Nombre | ° | Axe long du rectangle minimal de l'emprise, dans le repère de la maquette | Automatique | existe |
| Socle | Implantation et forme | Réponse | Oui / non | – | Rez au moins 15 % plus étendu que l'étage courant (médiane des étages) | Automatique | existe |
| Cages, logements et SUP par cage et par étage | Distribution | Réponse | Nombres | – | Cages d'escalier des étages de logements (comme la fiabilisation) | Automatique | existe |
| Part de logements traversants | Distribution | Réponse | Nombre | % | Façades touchées par chaque logement, sur la maquette (IFC d'abord) | Automatique | ajouter |
| Simplex ou duplex | Distribution | Réponse | Liste | – | Logement réparti sur deux étages | Automatique | ajouter |
| Nombre de types de logements | Distribution | Réponse | Nombre | – | Diversité typologique (a+t : 26 à 36 types dans les projets les plus mixtes) ; à tirer des logements de la maquette | Automatique | ajouter |
| Répartition des affectations | Programme | Réponse | Nombres | % de la SUP | SUP par affectation des surfaces nettes | Automatique | existe |
| Nombre de logements | Programme | Réponse | Nombre | – | Comptage des logements de la maquette (ListeLogements) | Automatique | existe |
| Mix typologique | Programme | Réponse | Nombres | par nb de chambres | Chambres de chaque logement (ListeLogements) | Automatique | existe |
| SP, SP hors-sol, SP sous-sol | Surfaces SIA 416 et USPI | Performance | Nombres | m² | Surfaces brutes, découpage hors-sol et sous-sol | Automatique | existe |
| SUP, SUS, SD, SI | Surfaces SIA 416 et USPI | Performance | Nombres | m² | Surfaces nettes par catégorie SIA 416 | Automatique | existe |
| SEP, VB | Surfaces SIA 416 et USPI | Performance | Nombres | m², m³ | Surface externe de plancher, volume bâti | Automatique | existe |
| SVN, SVB, SNH (USPI) | Surfaces SIA 416 et USPI | Performance | Nombres | m² | Somme des lots | Automatique | existe |
| Façade, vitrage, toitures | Surfaces SIA 416 et USPI | Performance | Nombres | m² | Enveloppe hors-sol (SurfacesEnveloppe) | Automatique | existe |

### Fiche projet (saisie)

Saisi dans la fiche « Identité du projet » de la visionneuse (feuille InfosProjet du MDP). Certains champs sont proposés par l'IA puis confirmés.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| ID projet | Identification | Identification | Texte | – | InfosProjet « ID projet », sinon le numéro du fichier MDP-<id> | Saisie | existe |
| Nom, adresse, commune, canton | Identification | Identification | Texte | – | InfosProjet ; canton normalisé en code (VD, GE…) | Saisie | existe |
| Catégorie d'ouvrage, type d'intervention | Identification | Identification | Liste | – | Listes déroulantes du gabarit MDP | Saisie | existe |
| Phase du projet | Identification | Identification | Liste | – | Liste du gabarit ; références limitées aux projets réalisés ou autorisés | Saisie | existe |
| Architecte (bureau) | Identification | Identification | Texte | – | Champ AUTORES / AUTHORS des fiches a+t ; nouveau champ de la fiche | Saisie | existe |
| Opération d'ensemble (plan de quartier) et sa densité | Identification | Identification | Texte et nombre | log. / ha | a+t rattache chaque bâtiment à son plan urbain (n° 3 → 3.1) et classe par la densité du plan : nom du PQ / PPA / PLQ, logements, surface, densité | Saisie | existe |
| Logements de l'opération d'ensemble | Identification | Identification | Nombre | – | Tous les logements du plan de quartier, pour sa densité | Saisie | existe |
| Surface de l'opération d'ensemble | Identification | Identification | Nombre | m² | Périmètre du plan de quartier, pour sa densité | Saisie | existe |
| Groupe de diffusion | Identification | Identification | Liste | – | Admin ou Light | Saisie | existe |
| Forme bâtie (classement a+t) | Implantation et forme | Réponse | Liste (5 familles, 33 types) | – | « Formalizaciones » de Density (a+t) : Maisons, Blocs, Îlots, Immeubles hauts, Solutions mixtes ; proposée d'après les formes, les axes et la hauteur, à confirmer | Proposé puis confirmé | existe |
| Forme de chaque bâtiment | Implantation et forme | Réponse | Liste (13 formes) | – | Proposée par l'IA d'après l'emprise (emprise.estimer), confirmée | Proposé puis confirmé | existe |
| Statut des espaces extérieurs | Implantation et forme | Réponse | Liste | – | Cour ou jardin privé, commun, semi-public, public ; toit-jardin (vocabulaire des plans a+t) | Saisie | existe |
| Pleine terre, toitures végétalisées | Implantation et forme | Réponse | Nombres | m² | Plan des aménagements extérieurs | Saisie | existe |
| Type de distribution | Distribution | Réponse | Liste | – | Cage à 2, 3, 4, 5+ logements par palier, coursive, couloir central, accès individuels ; proposé d'après LOG/CAGE | Proposé puis confirmé | existe |
| Type de stationnement | Distribution | Réponse | Liste | – | Sous-sol, surface, silo, aucun | Saisie | existe |
| Places voiture | Programme | Réponse | Nombre | – | InfosProjet | Saisie | existe |
| Places vélo | Programme | Réponse | Nombre | – | Nouveau champ de la fiche | Saisie | existe |

### SIG fédéral (geo.admin.ch)

Interrogé automatiquement à partir de la position du projet, à chaque lecture de la base (fiche SIG-<id>.json).

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Surface du terrain | Terrain | Contraintes | Nombre | m² | Parcelle sous le point (cadastre geo.admin), aire du polygone ; la saisie de la fiche prime (plusieurs parcelles) | Automatique | existe |
| EGRID et numéro de parcelle | Terrain | Contraintes | Texte | – | Même requête que la surface ; clé de l'extrait RDPPF | Automatique | existe |
| Géométrie de la parcelle | Terrain | Contraintes | Polygone | – | Conserver le polygone déjà reçu dans la fiche SIG | Automatique | existe |
| Altitude, pente moyenne, dénivelé | Terrain | Contraintes | Nombres | m, % | swissALTI3D : service de hauteur de geo.admin, échantillonné sur la parcelle | Automatique | ajouter |
| Mitoyenneté | Terrain | Contraintes | Liste | – | swissBUILDINGS3D : bâtiments voisins en contact (isolé, contigu d'un ou deux côtés) | Proposé puis confirmé | ajouter |
| Zone à bâtir harmonisée | Règles d'urbanisme | Contraintes | Liste | – | Calque ch.are.bauzonen ; trop grossière pour concevoir | Automatique | existe |
| Site ISOS | Règles d'urbanisme | Contraintes | Texte | – | Calque de l'inventaire ISOS (OFC) | Automatique | existe |
| Type de site | Contexte | Contraintes | Liste | – | Seuils sur habitants + emplois à l'hectare dans 300 m (STATPOP, STATENT) | Automatique | existe |
| Classe de desserte TP | Contexte | Contraintes | Liste | A à D | Calque ch.are.gueteklassen_oev | Automatique | existe |
| Arrêt le plus proche et sa distance | Contexte | Contraintes | Texte et nombre | m | Calque des arrêts (OFT), arrêts desservis seulement | Automatique | existe |
| Bruit routier et ferroviaire | Contexte | Contraintes | Nombres | dB(A) | sonBASE (OFEV) : service à identifier, la carte n'en a que l'image | Automatique | ajouter |
| Densités brutes à 300 m (habitants, logements, emplois) | Contexte | Contraintes | Nombres | / ha | STATPOP, StatBL, STATENT ; résumées par le type de site | Automatique | reléguer |
| Accessibilité TP, temps jusqu'au centre | Contexte | Contraintes | Nombres | pers., min | Calques ARE ; la classe de desserte suffit sur la carte | Automatique | reléguer |
| Radon, sol de fondation | Contexte | Contraintes | Nombre, liste | % | Calques OFSP, OFEV ; annexe technique | Automatique | reléguer |
| Bâtiment RegBL, demande de chaleur | Contexte | Contraintes | Divers | – | Décrivent le bâtiment le plus proche (souvent l'ancien) : contrôle, pas identité | Automatique | reléguer |

### Cadastre et RDPPF cantonal

Extrait officiel des restrictions de droit public, interrogé par le numéro EGRID de la parcelle. Automatique, une fois.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Fronts sur le domaine public | Terrain | Contraintes | Nombre et longueur | m | Côtés de la parcelle contre une parcelle du domaine public (mensuration officielle) | Automatique | ajouter |
| Zone communale et plan applicable | Règles d'urbanisme | Contraintes | Texte | – | Extrait RDPPF par EGRID (service ÖREB, JSON) : PGA, PPA, PQ, PLQ | Automatique | ajouter |
| Degré de sensibilité au bruit (OPB) | Règles d'urbanisme | Contraintes | Liste | I à IV | Extrait RDPPF | Automatique | ajouter |
| Restrictions particulières | Règles d'urbanisme | Contraintes | Liste | – | Extrait RDPPF : patrimoine, forêt, eaux, dangers naturels, alignements | Automatique | ajouter |

### Règlements communaux

Lus par l'IA dans le règlement de la commune (souvent en PDF), puis validés par une personne. Stockés par commune et par zone.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Indices réglementaires (IUS, IOS, masse…) | Règles d'urbanisme | Contraintes | Nombres | – | Lus par l'IA dans le règlement, validés ; une notion par champ, nom cantonal à côté | Proposé puis confirmé | ajouter |
| Hauteur et niveaux maximaux | Règles d'urbanisme | Contraintes | Nombres | m, niveaux | Règlement communal ou plan spécial | Proposé puis confirmé | ajouter |
| Distances aux limites et entre bâtiments | Règles d'urbanisme | Contraintes | Nombres | m | Règlement communal | Proposé puis confirmé | ajouter |
| Exigences de stationnement | Règles d'urbanisme | Contraintes | Nombres | places / log. | Règlement communal ou cantonal (minimum et maximum) | Proposé puis confirmé | ajouter |
| Quotas imposés (LUP, part de logement) | Règles d'urbanisme | Contraintes | Nombres | % | Règlement ou loi cantonale (Genève : zones de développement) | Proposé puis confirmé | ajouter |
| Densité ou programme imposés par le plan | Règles d'urbanisme | Contraintes | Nombres | log. / ha, % | a+t : densité fixée d'avance (Venise, 120 log./ha), ratio logement / travail, hauteurs du rez imposées (IJburg) | Proposé puis confirmé | ajouter |

### Équipes travaux / réalisation

Fournis par la réalisation à la fin du chantier : décomptes, choix constructifs. Import d'un tableau type ou saisie.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Année d'achèvement | Identification | Identification | Date | année | Date de réception de l'ouvrage (aujourd'hui « date fin projet » ou « date de la source », à clarifier) | Saisie | existe |
| Coût par CFC (1 à 9) ou eBKP-H | Ratios, coûts, revenus | Performance | Nombres | CHF | Décompte final, tableau type par CFC | Import | ajouter |
| Système constructif | Ratios, coûts, revenus | Performance | Liste | – | Béton, bois, mixte, préfabriqué | Saisie | existe |
| Label énergétique, chauffage | Ratios, coûts, revenus | Performance | Liste | – | Minergie, SNBS… ; pompe à chaleur, CAD… | Saisie | existe |
| Durée du chantier | Ratios, coûts, revenus | Performance | Nombre | mois | Ouverture du chantier à la réception | Saisie | existe |

### Service DEV / gérance

Fournis par le développement immobilier ou la gérance : commercialisation, loyers, prix. Confidentiel, version Admin.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Mode de commercialisation | Identification | Identification | Liste | – | Location, PPE, mixte, utilité publique | Saisie | existe |
| Maître d'ouvrage | Identification | Identification | Texte | – | Absent des fiches a+t (seulement dans leurs textes), indispensable au DEV | Saisie | existe |
| Dérogation ou bonus obtenu | Règles d'urbanisme | Contraintes | Texte | – | Permis de construire | Saisie | existe |
| Niveau de loyers ou de prix de la commune | Contexte | Contraintes | Nombre | CHF / m² | Données internes, sinon fournisseur payant (Wüest Partner, IAZI…) | Import | ajouter |
| Public cible | Programme | Réponse | Liste | – | Familles, seniors, étudiants, mixte (a+t le donne dans ses textes : Benny Farm, EM2N à Zurich) | Saisie | existe |
| État locatif ou prix de vente | Ratios, coûts, revenus | Performance | Nombre | CHF / m² | Loyers par m² SUP et par an, ou prix par m² SVN ; version Admin | Import | ajouter |

### Statistiques publiques (OFS)

Séries publiques de l'Office fédéral de la statistique, mises à jour une fois par an.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Taux de vacance de la commune | Contexte | Contraintes | Nombre | % | Dénombrement des logements vacants, par commune | Automatique | ajouter |
| Indice suisse des prix de la construction | Ratios, coûts, revenus | Performance | Nombre | indice | Série OFS par région, pour actualiser les coûts | Automatique | ajouter |

### Calcul SIA Check (dérivé)

Calculé à partir des autres champs de la carte. Automatique, rien à collecter.

| Donnée | Bloc | Rôle | Type | Unité | Extraction | Mode | Statut |
|---|---|---|---|---|---|---|---|
| Position et sa précision | Identification | Identification | Point LV95 | m | Géocodage local de l'adresse, sinon centre de la commune ; seule la position part sur le réseau | Automatique | existe |
| Score de fiabilité | Identification | Identification | Nombre | % | Contrôles du benchmark (cohérence SP / SN, plausibilité) | Automatique | existe |
| Origine de chaque valeur | Identification | Identification | Liste par champ | – | Saisie, IA, proposé, calcul, maquette, SIG, MDP : « Forme (origine) » généralisée à tous les champs | Automatique | existe |
| Forme de la parcelle | Terrain | Contraintes | Nombres | m, – | Rectangle minimal, élancement, compacité, largeur utile : emprise.decrire appliqué au polygone | Automatique | existe |
| Orientation de la parcelle | Terrain | Contraintes | Nombre | ° | Axe long du rectangle minimal | Automatique | existe |
| Taux d'exploitation des droits à bâtir | Règles d'urbanisme | Contraintes | Nombre | % | Indice réalisé / indice permis | Automatique | ajouter |
| GSI (emprise / terrain) | Implantation et forme | Réponse | Nombre | – | Emprise / surface du terrain (Spacematrix) | Automatique | existe |
| FSI (SP hors-sol / terrain) | Implantation et forme | Réponse | Nombre | – | KPI « Indice d'utilisation » | Automatique | existe |
| L (niveaux moyens) | Implantation et forme | Réponse | Nombre | niveaux | FSI / GSI | Automatique | existe |
| OSR (espace libre) | Implantation et forme | Réponse | Nombre | m² / m² | (1 − GSI) / FSI | Automatique | existe |
| Logements à l'hectare et tranche a+t | Implantation et forme | Réponse | Nombre | log. / ha | Logements / terrain ; tranches de Density : moins de 50, 50–100, 100–200, 200–300, plus de 300 | Automatique | existe |
| SUP moyenne par typologie | Programme | Réponse | Nombre | m² | Médiane de la SUP des logements, par nombre de chambres | Automatique | existe |
| Places par logement | Programme | Réponse | Nombre | places / log. | Places / logements, à comparer à l'exigence | Automatique | existe |
| SEP par logement | Programme | Réponse | Nombre | m² | Surface externe de plancher (balcons, loggias) / logements | Automatique | existe |
| SN et SC | Surfaces SIA 416 et USPI | Performance | Nombres | m² | SN = SUP + SUS + SD + SI ; SC = SP − SN | Automatique | existe |
| Ratios de rendement, pertes, sous-sol, enveloppe, programme | Ratios, coûts, revenus | Performance | Nombres | %, – | KPI du benchmark, comparés aux projets similaires | Automatique | existe |
| SN / SP, vitrée / pleine, façade / SP hors-sol | Ratios, coûts, revenus | Performance | Nombres | – | Doublons de SC / SP, de la part vitrée et du coefficient de forme : hors des KPI affichés | Automatique | retirer |
| SVN / SP hors-sol | Ratios, coûts, revenus | Performance | Nombre | % | Affiché seulement pour les projets en PPE ou en vente | Automatique | existe |
| CHF / m³ VB, CHF / m² SP, CHF / logement | Ratios, coûts, revenus | Performance | Nombres | CHF | Coûts actualisés / VB, SP, logements | Automatique | ajouter |
| Rendement brut | Ratios, coûts, revenus | Performance | Nombre | % | État locatif / coût total | Automatique | ajouter |

## 4. Ce qu'on retire ou relègue

L'objectif est une carte lisible : chaque champ doit servir une décision du DEV ou le calcul d'un autre champ.

**Ratios en double** (le calcul reste possible, ils sortent des KPI affichés) :
- **SN / SP** est le complément de **SC / SP** (SC = SP − SN) : garder un seul des deux. SC / SP est plus parlant
  (« ce qu'on perd en construction »).
- **Vitrée / pleine** dit la même chose que **Part vitrée** : garder la part vitrée, plus facile à lire.
- **Façade / SP hors-sol** recoupe le **coefficient de forme** : garder le coefficient de forme, plus complet
  (il compte les toitures).
- **SVN / SP hors-sol** : ne l'afficher que pour les projets en PPE ou en vente, comme les KPI de logement le sont
  déjà pour la typologie logement.

**Données SIG qui ne décrivent pas le projet** (gardées dans la fiche SIG, hors de la carte) :
- **Demande de chaleur** et **bâtiment RegBL** : ils décrivent le bâtiment du registre le plus proche du point, souvent
  l'ancien bâtiment ou un voisin. Ils servent de **contrôle** (année, logements, niveaux à comparer au MDP), pas
  d'identité.
- **Radon, sol de fondation** : annexe technique.
- **Accessibilité TP et temps jusqu'au centre** : la classe de desserte et la distance à l'arrêt suffisent sur la carte ;
  les deux autres restent en annexe.
- **Densités brutes** (habitants, logements, emplois à 300 m) : le type de site et la densité humaine les résument ;
  les valeurs restent dans la fiche.

**Formes : deux niveaux à séparer.**
- La liste des 13 formes décrit le **plan d'un bâtiment** ; elle reste.
- La **forme bâtie a+t** (partie 2) décrit le **projet** et s'ajoute au-dessus.
- *(Fait en V7 : « Plusieurs bâtiments ».)* Le libellé « Îlot de bâtiments » pour un projet à plusieurs bâtiments prêtait à confusion : chez a+t, un îlot
  est une forme précise (îlot fermé, ouvert, en U…). Le remplacer par la forme bâtie a+t du projet (le plus souvent
  « blocs groupés » ou « blocs parallèles »).

**Projets non réalisés** : filtre « réalisés et autorisés » (phase SIA 41 et plus) dans le pré-filtre du benchmark.
Décoché par défaut en V7 : la phase des MDP de la base est le plus souvent celle de l'étude (avant-projet), pas l'état
actuel du projet ; l'activer par défaut viderait la référence. À revoir quand la phase sera tenue à jour.

## 5. Données à aller chercher

Par ordre de priorité. « Effort » estime le travail de développement, pas la disponibilité de la donnée.

| # | Donnée | Source | Accès | Effort | Priorité |
|---|---|---|---|---|---|
| 1 | Indicateurs de forme et d'implantation (emprise, GSI, L, OSR, épaisseur, hauteur, orientation) | nos maquettes | calcul local (emprise.py, moteur IFC) | faible | P1 |
| 2 | Coûts par CFC ou eBKP-H | DEV, réalisation, décomptes finaux | import d'un tableau type | moyen (collecte humaine) | P1 |
| 3 | Indice suisse des prix de la construction | OFS | public, annuel | faible | P1 |
| 4 | Géométrie de la parcelle, EGRID | cadastre (geo.admin.ch, geodienste.ch) | API publique, déjà interrogée pour la surface | faible | P1 |
| 5 | Extrait RDPPF (zone communale, DS OPB, restrictions) | cadastres cantonaux RDPPF / ÖREB | API standard fédérale par EGRID (extrait JSON ou XML) | moyen | P1 |
| 6 | Revenus : états locatifs, prix de vente | DEV, gérance | saisie ou import, version Admin | moyen | P2 |
| 7 | Règles chiffrées : indices, hauteurs, distances, stationnement | règlements communaux (PDF) | extraction par IA puis validation humaine, commune par commune | **élevé** | P2 |
| 8 | Altitude et pente | swissALTI3D | API publique geo.admin (hauteur, profil) | faible | P2 |
| 9 | Bruit en dB | sonBASE (OFEV) | service à identifier : la carte n'a que l'image | moyen | P2 |
| 10 | Mix typologique, traversants | nos maquettes | calcul local | moyen | P2 |
| 11 | Bâtiments voisins en 3D (gabarits, ombres, mitoyenneté) | swissBUILDINGS3D | téléchargement par tuile | moyen | P3 |
| 12 | Marché : vacance (OFS, public) ; loyers et prix (Wüest Partner, IAZI, Fahrländer, PriceHubble : payants) | OFS, fournisseurs | public ou abonnement | variable | P3 |

Remarques :
- **Les règlements communaux sont le vrai verrou** de l'outil final. Ils ne sont pas harmonisés, souvent en PDF, et
  chaque commune a ses notions. Commencer par **un canton** (celui où le DEV a le plus de projets) et par les communes
  de la base.
- **Coûts et revenus** dépendent d'une collecte humaine. À organiser tôt avec le DEV : c'est ce qui prend le plus de
  temps calendaire, pas de développement.
- Rien ne change à la règle actuelle : seules les coordonnées partent sur le réseau, les données de la base restent
  confidentielles.

## 6. Questions à trancher avec le DEV

1. **Combien de projets** la base peut-elle atteindre ? Les comparaisons par contexte et par forme demandent plusieurs
   projets par groupe. Avec quelques dizaines de projets, il faut peu de catégories.
2. **Quel canton** pour démarrer les règles d'urbanisme ?
3. **Qui fournit les coûts et les revenus**, sous quelle forme (CFC à 1 ou 3 chiffres, eBKP-H) et avec quelle
   confidentialité ?
4. **Formes bâties a+t et types de distribution** : valider les 33 formes du livre avec le vocabulaire du DEV (les
   garder toutes, ou regrouper par famille tant que la base est petite).
5. **Densité de quel périmètre** : la parcelle du projet, ou le plan de quartier dont il fait partie (choix d'a+t) ?
6. **Projets non réalisés** (concours, études) : les garder comme références de réponse (formes, programmes) même
   sans coûts réels ?
