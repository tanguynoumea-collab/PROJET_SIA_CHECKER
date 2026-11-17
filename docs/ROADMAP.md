# Roadmap SIA Check

Idées validées pour les prochaines versions, pas encore développées. Les versions livrées ont leur plan propre
(docs/V2_PLAN.md à docs/V5_PLAN.md).

## V6 (idées du 17.11.2026)

### Version locale HTML, ouverte depuis SharePoint

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
- **Dans les exports :** colonnes de contexte dans l'Excel du benchmark et dans les fiches projet.
