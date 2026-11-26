# Roadmap SIA Check

Idées validées pour les prochaines versions, pas encore développées. Les versions livrées ont leur plan propre
(docs/V2_PLAN.md à docs/V6_PLAN.md). La cible à long terme (outil de préconception du DEV) est en fin de fichier ;
elle s'appuie sur la carte d'identité des projets, docs/CARTE_IDENTITE.md.

## V6 (idées du 17.11.2026)

### Version locale HTML, ouverte depuis SharePoint

> Faite le 18.11.2026 (branche v6-html-sharepoint), voir docs/V6_PLAN.md : HTML autonome avec accueil, versions
> partagées Admin et Light publiées à chaque lecture de la base. Restent les points ouverts du plan (bibliothèque
> définitive, droits, raccourci des utilisateurs sans SIA Check).

- **But :** consulter le benchmark sans installer SIA Check. Un fichier HTML déposé dans une bibliothèque
  SharePoint lance l'interface du dashboard dans le navigateur (Tendances, Programmer, carte, vue 3D, export
  Excel), avec les données de la base.
- **Point de départ :** le dashboard est déjà une page web autonome (dashboard/), qui fonctionne sur un serveur
  en lisant benchmark.json à côté d'elle (`?data=`), et les maquettes 3D sur un autre hôte (`?maquettes=`).
- **À trancher :**
  - comment la page lit benchmark.json et les maquettes MAQ-*.json.gz dans SharePoint (Microsoft Graph avec
    les droits de l'utilisateur, ou fichiers posés à côté de la page) ;
  - qui y a accès ;
  - un fichier HTML seul (scripts et données intégrés) ou un dossier.
  - Rejoint la piste de mise en ligne étudiée le 02.11.2026 (Static Web Apps, groupe Entra, données SharePoint).
- **Contraintes :** les surfaces des projets sont confidentielles. benchmark.json ne va jamais dans le dépôt
  public ni sur un hébergement public ; rien n'est déployé sans feu vert explicite, ni sans l'accord de l'IT.

### Onglet « Contexte » du benchmark (cartes et données SIG)

> Fait le 18.11.2026, voir docs/V6_PLAN.md parties 5 à 7 : type de site au pré-filtre ; l'onglet trouve les
> projets de la base au contexte le plus proche d'une adresse, estime la SP de sa parcelle (indice d'utilisation)
> et la passe au Programmer ; contexte et terrain dans l'export Excel ; module « Données SIG » (partie 8 : carte
> de toute la base, fiches et filtres SIG). Restent les plans d'affectation.

- **But :** un onglet à part, dédié aux données SIG des projets (voir « Données SIG des projets du benchmark »
  ci-dessous, qui en est la source).
- **Contenu envisagé :**
  - la carte, en grand, avec les projets et leurs calques ;
  - pour chaque projet, sa fiche de contexte : zone, quartier, densités, bruit, desserte, énergie, plan
    d'affectation ;
  - les ratios du benchmark croisés avec ces données (KPI par contexte, nuages de points ratio × densité ou
    desserte) ;
  - les indicateurs du portefeuille (part en pleine ville, en site ISOS, en zone bien desservie).
- **Dépend de :** la collecte des données SIG à l'intégration (étape 1 ci-dessous).

## Données SIG des projets du benchmark

Idée du 17.11.2026, née de la carte du benchmark (V5, partie 3) : chaque projet a désormais une position (son
adresse, sinon le centre de sa commune) et la carte interroge déjà une trentaine de jeux de données fédéraux. Ces
données décrivent le contexte du projet ; les conserver permettrait des ratios propres à l'emplacement.

### Étape 1 — Collecte à l'intégration au benchmark

> Faite le 18.11.2026, voir docs/V6_PLAN.md partie 4 (rayon de 300 m pour les densités, fiche figée, collecte à
> chaque lecture de la base).

- **Quand :** à la validation de l'intégration d'un projet à la base (« Ajouter à la base »), et à sa republication
  si sa position a changé. Un rattrapage pour les projets déjà dans la base.
- **Quoi :** les attributs utiles à la position du projet, repris des calques de la carte (dashboard/carte.js,
  `CALQUES`) : commune, district, quartier statistique, zone à bâtir, bâtiment du registre fédéral (RegBL : statut,
  année, niveaux, logements, parcelle), site ISOS, habitants, logements et emplois à l'hectare, bruit routier et
  ferroviaire, ruissellement, radon, sol de fondation, potentiel solaire, demande de chaleur, classe de desserte et
  accessibilité TP, temps jusqu'au centre, arrêt le plus proche, fibre, antennes. Chaque valeur avec son année et
  sa source.
- **Comment :** API d'interrogation de geo.admin.ch (identify, comme un clic sur la carte). Seules les
  coordonnées LV95 du projet partent sur le réseau ; l'adresse reste géocodée en local (accord de l'utilisateur
  du 17.11.2026). Sans réseau, la collecte est reportée et signalée, jamais bloquante pour l'intégration.
- **Où :** une fiche `SIG-<id>.json` à côté du MDP dans le dossier de la base (comme `MAQ-<id>.json.gz`), datée,
  avec la position et sa précision (adresse ou commune), relue par le moteur pour benchmark.json.
- **À trancher :** rayon autour du point (parcelle seule, ou 100–300 m pour la densité et le bruit) ; quelle
  valeur retenir quand le projet couvre plusieurs parcelles ou zones ; mise à jour des jeux annuels (STATPOP,
  STATENT) : figer à la date d'intégration ou rafraîchir.

### Étape 2 — Exploitation

- **Filtres et ratios par contexte :** pré-filtre ou volet « contexte » (centre-ville, périphérie, rural ; classe
  de desserte TP ; zone d'habitation ou mixte), et KPI comparés par contexte : par exemple SUP / SP hors-sol
  des projets en zone centre face à ceux de périphérie.
- **Indicateurs de portefeuille :** part des projets (en nombre et en SP) construits en pleine ville, en zone bien
  desservie, en site ISOS, en zone de bruit ; évolution dans le temps.
- **Plans d'urbanisme :** répertorier les plans que chaque projet a dû respecter (plan d'affectation communal,
  plan de quartier, PPA, degré de sensibilité au bruit, indices d'utilisation). Les plans d'affectation cantonaux
  ne sont pas tous sur geo.admin.ch : sources cantonales à recenser (Vaud : géoportail cantonal ; Genève : SITG).
  Rapprocher les indices réglementaires des surfaces réellement construites (SP / surface de parcelle).
- **Dans les exports :** colonnes de contexte dans l'Excel du benchmark et dans les fiches projet. *(Excel du benchmark fait le 18.11.2026, partie 7.)*

## Vers l'outil de préconception du DEV (idée du 20.11.2026)

**But final :** partir des contraintes d'une parcelle (terrain, règles d'urbanisme, contexte) et sortir une
préconisation : formes d'implantation possibles, puis un préprojet (maquette, plans, chiffrage) sur lequel on itère avec
l'IA, les contraintes et les ratios vérifiés en permanence. Exemple : « ajoute deux étages » → « demande impossible :
hauteur maximale de la zone dépassée ».

**Base :** la carte d'identité des projets (docs/CARTE_IDENTITE.md), rangée en contraintes → réponse → performance.

### Principes

- **Les règles sont vérifiées par un moteur déterministe, pas par l'IA.** L'IA extrait les règles des règlements,
  propose des variantes et explique ; la conformité est calculée et traçable (« article X du règlement Y »). Une IA qui
  dit « c'est conforme » sans preuve n'est pas acceptable pour un permis.
- **Du plus simple au plus riche :** 2D (implantation) avant 3D (volumes), volumes avant Revit. Chaque étape est utile
  seule au DEV.
- **Un canton d'abord** pour les règles d'urbanisme, puis extension.
- **Acheter ou construire :** des outils du marché font déjà l'étude de capacité d'une parcelle (Autodesk Forma,
  TestFit, Archistar…). À évaluer avant l'étape 4 : notre valeur propre est la base de projets HRS et ses ratios
  réels, pas le générateur de volumes.

### Étape 1 — Carte d'identité v1 (V7)

> Terminée le 26.11.2026, voir docs/V7_PLAN.md : carte d'identité dans la visionneuse, KPI en double sortis, origine
> de chaque valeur, filtre « réalisés et autorisés » (décoché par défaut : la phase des MDP est celle de l'étude),
> forme et contexte dans la similarité, pré-filtres forme bâtie et distribution, onglet Formes (Spacematrix, planche
> des implantations à échelle constante), vignette d'implantation au 1:5000, opération d'ensemble et sa densité.
> Restent à valider avec le DEV : les listes de formes a+t et de distribution, le périmètre de la densité. Les nouveaux
> champs vivent dans InfosProjet du MDP de la base.

- **Calculs depuis les maquettes :** emprise, GSI, L, OSR, logements à l'hectare, hauteur, épaisseur, orientation,
  socle, nombre de bâtiments, mix d'affectations, mix typologique.
- **Saisies nouvelles :** type d'implantation, type de distribution, mode de commercialisation, stationnement, système
  constructif ; proposées par l'IA ou le calcul, confirmées par l'utilisateur (comme la forme).
- **Tri :** ratios en double sortis des KPI, données SIG de contrôle sorties de la carte, « Îlot de bâtiments »
  renommé (CARTE_IDENTITE.md, partie 4).
- **Origine de chaque valeur** (saisie, IA, calcul, SIG, interne) et filtre « réalisés et autorisés ».
- **Benchmark :** graphe GSI × FSI (Spacematrix), filtres par implantation, distribution et forme ; « projets
  similaires » qui tiennent compte de la forme et du contexte.
- **Repris de Density (a+t), vérifié sur le livre le 20.11.2026** (CARTE_IDENTITE.md, partie 2) :
  - la forme bâtie a+t (5 familles, 33 types) proposée par la carte, à confirmer dans la fiche projet, et un filtre
    par famille au benchmark ;
  - la tranche de densité (log./ha) comme clé de tri et de couleur ;
  - une **planche comparative à échelle constante** : l'emprise de chaque projet de la base au 1:5000, avec sa
    parcelle, rangée par surface de terrain ou par densité, comme les planches « Implantaciones » du livre (emprises
    déjà calculées depuis les maquettes, parcelle à garder dans la fiche SIG) ;
  - la vignette d'implantation dans la carte d'identité, à la même échelle ;
  - le rattachement à une opération d'ensemble (plan de quartier), avec sa densité propre.
- **À trancher :** les listes d'implantation et de distribution (à caler sur a+t avec le DEV) ; où vivent les nouveaux
  champs (MDP InfosProjet ou fiche à part, comme SIG-<id>.json).

### Étape 2 — Coûts et revenus (V8)

- Import des coûts par CFC ou eBKP-H, actualisés par l'indice OFS des prix de la construction ; ratios CHF / m³ VB,
  CHF / m² SP, CHF / logement, comparables par forme et contexte.
- États locatifs et prix de vente, version Admin seulement.
- **Dépend de :** une collecte organisée avec le DEV et la réalisation (à lancer dès l'étape 1, c'est le plus long).

### Étape 3 — Analyse de parcelle (V9)

- Saisie d'une adresse ou d'un EGRID → géométrie, forme, fronts sur rue, pente, voisins, extrait RDPPF, zone, type de
  site, desserte, bruit : la partie « contraintes » de la carte, pour une parcelle nue.
- **Règlement structuré :** indices, hauteurs, distances, stationnement, extraits du règlement communal par l'IA puis
  validés par l'utilisateur, conservés par commune et réutilisés.
- **Enveloppe constructible :** le volume légal en 3D (distances, hauteurs, gabarits) et la SP maximale permise.
- **Projets de référence :** ceux de la base aux contraintes les plus proches, avec leurs réponses et leurs
  performances. Prolonge l'onglet Contexte actuel (projets similaires à une adresse).
- **À trancher :** le canton pilote ; la granularité des règles (le cas général d'abord, les exceptions ensuite).

### Étape 4 — Esquisses d'implantation 2D (V10)

- Un générateur de variantes sur l'enveloppe constructible : barres, L, U, plots, îlot, avec épaisseurs et
  orientations tirées des projets de référence.
- Chaque variante est notée : SP obtenue, taux d'exploitation des droits, logements estimés (SUP par logement des
  références), coefficient de forme, coût estimé (ratios de l'étape 2), espace libre.
- Algorithme déterministe pour générer et vérifier ; l'IA classe, explique et répond aux demandes (« plus compact »,
  « un jardin au sud »).

### Étape 5 — Préprojet 3D et Revit (V11)

- La variante retenue devient un volume par niveau, avec noyaux, cages et logements types, puis une maquette Revit
  (API Revit, comme les autres outils HRS) : niveaux, murs de façade, dalles, noyaux.
- Plans, surfaces SIA 416 (relues par notre propre moteur : la boucle se referme sur SIA Check) et chiffrage par
  ratios.

### Étape 6 — Assistant itératif (V12)

- Conversation avec l'IA sur le préprojet : chaque demande modifie les paramètres, le modèle est régénéré, puis le
  moteur de règles et les ratios sont recalculés avant de répondre.
- Une demande hors règles est refusée avec la règle en cause ; une demande hors des ratios habituels est signalée
  (« SUP / SP sous le premier quartile des projets comparables »).
