"""Carte d'identité d'un projet de la base (docs/CARTE_IDENTITE.md).

`CHAMPS` est la source unique de la carte : chaque donnée avec son bloc, son type, son unité, sa source, son mode
d'extraction, la façon de l'obtenir et son statut dans le modèle de données. docs/carte_identite.py en tire les tableaux
du document et la page publiée ; `carte` en tire la carte d'un projet, valeurs comprises, que benchmark.json porte pour
la visionneuse (clic droit sur un projet, « Carte d'identité »).

Valeurs : lues dans le projet (MDP), sa fiche SIG et sa maquette 3D de la base (MAQ-<id>.json.gz : emprise, hauteur,
épaisseur, orientation, d'après emprise.py). Une donnée pas encore collectée a la valeur None : la visionneuse l'affiche
« à collecter », avec la source qui doit la fournir. Les données reléguées vont dans l'annexe ; les retirées n'y sont pas.
"""

from __future__ import annotations

import gzip
import json
import math
import statistics
from pathlib import Path

SOURCES = {
    "MAQ": ("Maquette (calcul SIA Check)", "Déduit par nos soins de la maquette Treegram ou IFC, à la lecture du projet. Automatique."),
    "FICHE": ("Fiche projet (saisie)", "Saisi dans la fiche « Identité du projet » de la visionneuse (feuille InfosProjet du MDP). Certains champs sont proposés par l'IA puis confirmés."),
    "SIG": ("SIG fédéral (geo.admin.ch)", "Interrogé automatiquement à partir de la position du projet, à chaque lecture de la base (fiche SIG-<id>.json)."),
    "CAD": ("Cadastre et RDPPF cantonal", "Extrait officiel des restrictions de droit public, interrogé par le numéro EGRID de la parcelle. Automatique, une fois."),
    "REGL": ("Règlements communaux", "Lus par l'IA dans le règlement de la commune (souvent en PDF), puis validés par une personne. Stockés par commune et par zone."),
    "TRAV": ("Équipes travaux / réalisation", "Fournis par la réalisation à la fin du chantier : décomptes, choix constructifs. Import d'un tableau type ou saisie."),
    "DEV": ("Service DEV / gérance", "Fournis par le développement immobilier ou la gérance : commercialisation, loyers, prix. Confidentiel, version Admin."),
    "OFS": ("Statistiques publiques (OFS)", "Séries publiques de l'Office fédéral de la statistique, mises à jour une fois par an."),
    "CALC": ("Calcul SIA Check (dérivé)", "Calculé à partir des autres champs de la carte. Automatique, rien à collecter."),
}
BLOCS = {0: ("Identification", "Identification"), 1: ("Terrain", "Contraintes"), 2: ("Règles d'urbanisme", "Contraintes"),
         3: ("Contexte", "Contraintes"), 4: ("Implantation et forme", "Réponse"), 5: ("Distribution", "Réponse"),
         6: ("Programme", "Réponse"), 7: ("Surfaces SIA 416 et USPI", "Performance"), 8: ("Ratios, coûts, revenus", "Performance")}
MODES = {"A": "Automatique", "S": "Proposé puis confirmé", "M": "Saisie", "I": "Import"}

# (clé, donnée, bloc, type, unité, source, mode, extraction, statut)
CHAMPS = [
    ("id", "ID projet", 0, "Texte", "", "FICHE", "M", "InfosProjet « ID projet », sinon le numéro du fichier MDP-<id>", "existe"),
    ("identite", "Nom, adresse, commune, canton", 0, "Texte", "", "FICHE", "M", "InfosProjet ; canton normalisé en code (VD, GE…)", "existe"),
    ("position", "Position et sa précision", 0, "Point LV95", "m", "CALC", "A", "Géocodage local de l'adresse, sinon centre de la commune ; seule la position part sur le réseau", "existe"),
    ("categorie", "Catégorie d'ouvrage, type d'intervention", 0, "Liste", "", "FICHE", "M", "Listes déroulantes du gabarit MDP", "existe"),
    ("phase", "Phase du projet", 0, "Liste", "", "FICHE", "M", "Liste du gabarit ; références limitées aux projets réalisés ou autorisés", "existe"),
    ("annee", "Année d'achèvement", 0, "Date", "année", "TRAV", "M", "Date de réception de l'ouvrage (aujourd'hui « date fin projet » ou « date de la source », à clarifier)", "existe"),
    ("commercialisation", "Mode de commercialisation", 0, "Liste", "", "DEV", "M", "Location, PPE, mixte, utilité publique", "existe"),
    ("architecte", "Architecte (bureau)", 0, "Texte", "", "FICHE", "M", "Champ AUTORES / AUTHORS des fiches a+t ; nouveau champ de la fiche", "existe"),
    ("maitre_ouvrage", "Maître d'ouvrage", 0, "Texte", "", "DEV", "M", "Absent des fiches a+t (seulement dans leurs textes), indispensable au DEV", "existe"),
    ("plan_parent", "Opération d'ensemble (plan de quartier) et sa densité", 0, "Texte et nombre", "log. / ha", "FICHE", "M", "a+t rattache chaque bâtiment à son plan urbain (n° 3 → 3.1) et classe par la densité du plan : nom du PQ / PPA / PLQ, logements, surface, densité", "existe"),
    ("plan_parent_log", "Logements de l'opération d'ensemble", 0, "Nombre", "", "FICHE", "M", "Tous les logements du plan de quartier, pour sa densité", "existe"),
    ("plan_parent_surface", "Surface de l'opération d'ensemble", 0, "Nombre", "m²", "FICHE", "M", "Périmètre du plan de quartier, pour sa densité", "existe"),
    ("groupe", "Groupe de diffusion", 0, "Liste", "", "FICHE", "M", "Admin ou Light", "existe"),
    ("fiabilite", "Score de fiabilité", 0, "Nombre", "%", "CALC", "A", "Contrôles du benchmark (cohérence SP / SN, plausibilité)", "existe"),
    ("origines", "Origine de chaque valeur", 0, "Liste par champ", "", "CALC", "A", "Saisie, IA, proposé, calcul, maquette, SIG, MDP : « Forme (origine) » généralisée à tous les champs", "existe"),

    ("terrain", "Surface du terrain", 1, "Nombre", "m²", "SIG", "A", "Parcelle sous le point (cadastre geo.admin), aire du polygone ; la saisie de la fiche prime (plusieurs parcelles)", "existe"),
    ("egrid", "EGRID et numéro de parcelle", 1, "Texte", "", "SIG", "A", "Même requête que la surface ; clé de l'extrait RDPPF", "existe"),
    ("geom_parcelle", "Géométrie de la parcelle", 1, "Polygone", "", "SIG", "A", "Conserver le polygone déjà reçu dans la fiche SIG", "existe"),
    ("forme_parcelle", "Forme de la parcelle", 1, "Nombres", "m, –", "CALC", "A", "Rectangle minimal, élancement, compacité, largeur utile : emprise.decrire appliqué au polygone", "existe"),
    ("orientation_parcelle", "Orientation de la parcelle", 1, "Nombre", "°", "CALC", "A", "Axe long du rectangle minimal", "existe"),
    ("fronts", "Fronts sur le domaine public", 1, "Nombre et longueur", "m", "CAD", "A", "Côtés de la parcelle contre une parcelle du domaine public (mensuration officielle)", "ajouter"),
    ("pente", "Altitude, pente moyenne, dénivelé", 1, "Nombres", "m, %", "SIG", "A", "swissALTI3D : service de hauteur de geo.admin, échantillonné sur la parcelle", "ajouter"),
    ("mitoyennete", "Mitoyenneté", 1, "Liste", "", "SIG", "S", "swissBUILDINGS3D : bâtiments voisins en contact (isolé, contigu d'un ou deux côtés)", "ajouter"),

    ("zone", "Zone à bâtir harmonisée", 2, "Liste", "", "SIG", "A", "Calque ch.are.bauzonen ; trop grossière pour concevoir", "existe"),
    ("isos", "Site ISOS", 2, "Texte", "", "SIG", "A", "Calque de l'inventaire ISOS (OFC)", "existe"),
    ("zone_communale", "Zone communale et plan applicable", 2, "Texte", "", "CAD", "A", "Extrait RDPPF par EGRID (service ÖREB, JSON) : PGA, PPA, PQ, PLQ", "ajouter"),
    ("ds_opb", "Degré de sensibilité au bruit (OPB)", 2, "Liste", "I à IV", "CAD", "A", "Extrait RDPPF", "ajouter"),
    ("restrictions", "Restrictions particulières", 2, "Liste", "", "CAD", "A", "Extrait RDPPF : patrimoine, forêt, eaux, dangers naturels, alignements", "ajouter"),
    ("indices", "Indices réglementaires (IUS, IOS, masse…)", 2, "Nombres", "–", "REGL", "S", "Lus par l'IA dans le règlement, validés ; une notion par champ, nom cantonal à côté", "ajouter"),
    ("hauteur_max", "Hauteur et niveaux maximaux", 2, "Nombres", "m, niveaux", "REGL", "S", "Règlement communal ou plan spécial", "ajouter"),
    ("distances", "Distances aux limites et entre bâtiments", 2, "Nombres", "m", "REGL", "S", "Règlement communal", "ajouter"),
    ("stationnement_regle", "Exigences de stationnement", 2, "Nombres", "places / log.", "REGL", "S", "Règlement communal ou cantonal (minimum et maximum)", "ajouter"),
    ("quotas", "Quotas imposés (LUP, part de logement)", 2, "Nombres", "%", "REGL", "S", "Règlement ou loi cantonale (Genève : zones de développement)", "ajouter"),
    ("densite_imposee", "Densité ou programme imposés par le plan", 2, "Nombres", "log. / ha, %", "REGL", "S", "a+t : densité fixée d'avance (Venise, 120 log./ha), ratio logement / travail, hauteurs du rez imposées (IJburg)", "ajouter"),
    ("derogation", "Dérogation ou bonus obtenu", 2, "Texte", "", "DEV", "M", "Permis de construire", "existe"),
    ("exploitation", "Taux d'exploitation des droits à bâtir", 2, "Nombre", "%", "CALC", "A", "Indice réalisé / indice permis", "ajouter"),

    ("site", "Type de site", 3, "Liste", "", "SIG", "A", "Seuils sur habitants + emplois à l'hectare dans 300 m (STATPOP, STATENT)", "existe"),
    ("desserte", "Classe de desserte TP", 3, "Liste", "A à D", "SIG", "A", "Calque ch.are.gueteklassen_oev", "existe"),
    ("arret", "Arrêt le plus proche et sa distance", 3, "Texte et nombre", "m", "SIG", "A", "Calque des arrêts (OFT), arrêts desservis seulement", "existe"),
    ("bruit", "Bruit routier et ferroviaire", 3, "Nombres", "dB(A)", "SIG", "A", "sonBASE (OFEV) : service à identifier, la carte n'en a que l'image", "ajouter"),
    ("vacance", "Taux de vacance de la commune", 3, "Nombre", "%", "OFS", "A", "Dénombrement des logements vacants, par commune", "ajouter"),
    ("marche", "Niveau de loyers ou de prix de la commune", 3, "Nombre", "CHF / m²", "DEV", "I", "Données internes, sinon fournisseur payant (Wüest Partner, IAZI…)", "ajouter"),
    ("densites", "Densités brutes à 300 m (habitants, logements, emplois)", 3, "Nombres", "/ ha", "SIG", "A", "STATPOP, StatBL, STATENT ; résumées par le type de site", "reléguer"),
    ("accessibilite", "Accessibilité TP, temps jusqu'au centre", 3, "Nombres", "pers., min", "SIG", "A", "Calques ARE ; la classe de desserte suffit sur la carte", "reléguer"),
    ("radon_sol", "Radon, sol de fondation", 3, "Nombre, liste", "%", "SIG", "A", "Calques OFSP, OFEV ; annexe technique", "reléguer"),
    ("regbl", "Bâtiment RegBL, demande de chaleur", 3, "Divers", "", "SIG", "A", "Décrivent le bâtiment le plus proche (souvent l'ancien) : contrôle, pas identité", "reléguer"),

    ("batiments", "Nombre de bâtiments", 4, "Nombre", "", "MAQ", "A", "Bâtiments de la maquette, sinon de la feuille InfosBatiment", "existe"),
    ("implantation", "Forme bâtie (classement a+t)", 4, "Liste (5 familles, 33 types)", "", "FICHE", "S", "« Formalizaciones » de Density (a+t) : Maisons, Blocs, Îlots, Immeubles hauts, Solutions mixtes ; proposée d'après les formes, les axes et la hauteur, à confirmer", "existe"),
    ("formes", "Forme de chaque bâtiment", 4, "Liste (13 formes)", "", "FICHE", "S", "Proposée par l'IA d'après l'emprise (emprise.estimer), confirmée", "existe"),
    ("emprise", "Emprise au sol", 4, "Nombre", "m²", "MAQ", "A", "emprise.py : union des SP hors-sol projetées en plan, somme des bâtiments", "existe"),
    ("gsi", "GSI (emprise / terrain)", 4, "Nombre", "–", "CALC", "A", "Emprise / surface du terrain (Spacematrix)", "existe"),
    ("fsi", "FSI (SP hors-sol / terrain)", 4, "Nombre", "–", "CALC", "A", "KPI « Indice d'utilisation »", "existe"),
    ("l", "L (niveaux moyens)", 4, "Nombre", "niveaux", "CALC", "A", "FSI / GSI", "existe"),
    ("osr", "OSR (espace libre)", 4, "Nombre", "m² / m²", "CALC", "A", "(1 − GSI) / FSI", "existe"),
    ("log_ha", "Logements à l'hectare et tranche a+t", 4, "Nombre", "log. / ha", "CALC", "A", "Logements / terrain ; tranches de Density : moins de 50, 50–100, 100–200, 200–300, plus de 300", "existe"),
    ("hauteur", "Hauteur hors-sol estimée", 4, "Nombre", "m", "MAQ", "A", "Du plancher du rez au dernier plancher, plus une hauteur d'étage moyenne, sur la maquette 3D", "existe"),
    ("niveaux_hs", "Niveaux hors-sol", 4, "Nombre", "", "MAQ", "A", "Étages hors-sol distincts portant de la SP", "existe"),
    ("hauteur_rez", "Hauteur du rez", 4, "Nombre", "m", "MAQ", "A", "Écart entre le plancher du rez et celui du 1er étage, sur la maquette 3D (a+t : rez de 3,5 m habitable ou commercial)", "existe"),
    ("niveaux_ss", "Niveaux de sous-sol", 4, "Nombre", "", "MAQ", "A", "Niveaux de rang négatif de la maquette", "existe"),
    ("epaisseur", "Épaisseur du bâtiment", 4, "Nombre", "m", "MAQ", "A", "Largeur du rectangle minimal (emprise rectangulaire), sinon 2 × aire / périmètre de l'emprise", "existe"),
    ("orientation", "Orientation de l'axe principal", 4, "Nombre", "°", "MAQ", "A", "Axe long du rectangle minimal de l'emprise, dans le repère de la maquette", "existe"),
    ("socle", "Socle", 4, "Oui / non", "", "MAQ", "A", "Rez au moins 15 % plus étendu que l'étage courant (médiane des étages)", "existe"),
    ("exterieurs", "Statut des espaces extérieurs", 4, "Liste", "", "FICHE", "M", "Cour ou jardin privé, commun, semi-public, public ; toit-jardin (vocabulaire des plans a+t)", "existe"),
    ("pleine_terre", "Pleine terre, toitures végétalisées", 4, "Nombres", "m²", "FICHE", "M", "Plan des aménagements extérieurs", "existe"),

    ("distribution", "Type de distribution", 5, "Liste", "", "FICHE", "S", "Cage à 2, 3, 4, 5+ logements par palier, coursive, couloir central, accès individuels ; proposé d'après LOG/CAGE", "existe"),
    ("cages", "Cages, logements et SUP par cage et par étage", 5, "Nombres", "", "MAQ", "A", "Cages d'escalier des étages de logements (comme la fiabilisation)", "existe"),
    ("traversants", "Part de logements traversants", 5, "Nombre", "%", "MAQ", "A", "Façades touchées par chaque logement, sur la maquette (IFC d'abord)", "ajouter"),
    ("duplex", "Simplex ou duplex", 5, "Liste", "", "MAQ", "A", "Logement réparti sur deux étages", "ajouter"),
    ("types_logements", "Nombre de types de logements", 5, "Nombre", "", "MAQ", "A", "Diversité typologique (a+t : 26 à 36 types dans les projets les plus mixtes) ; à tirer des logements de la maquette", "ajouter"),
    ("stationnement", "Type de stationnement", 5, "Liste", "", "FICHE", "M", "Sous-sol, surface, silo, aucun", "existe"),

    ("affectations", "Répartition des affectations", 6, "Nombres", "% de la SUP", "MAQ", "A", "SUP par affectation des surfaces nettes", "existe"),
    ("logements", "Nombre de logements", 6, "Nombre", "", "MAQ", "A", "Comptage des logements de la maquette (ListeLogements)", "existe"),
    ("mix", "Mix typologique", 6, "Nombres", "par nb de chambres", "MAQ", "A", "Chambres de chaque logement (ListeLogements)", "existe"),
    ("sup_typo", "SUP moyenne par typologie", 6, "Nombre", "m²", "CALC", "A", "Médiane de la SUP des logements, par nombre de chambres", "existe"),
    ("places", "Places voiture", 6, "Nombre", "", "FICHE", "M", "InfosProjet", "existe"),
    ("public_cible", "Public cible", 6, "Liste", "", "DEV", "M", "Familles, seniors, étudiants, mixte (a+t le donne dans ses textes : Benny Farm, EM2N à Zurich)", "existe"),
    ("velos", "Places vélo", 6, "Nombre", "", "FICHE", "M", "Nouveau champ de la fiche", "existe"),
    ("places_log", "Places par logement", 6, "Nombre", "places / log.", "CALC", "A", "Places / logements, à comparer à l'exigence", "existe"),
    ("sep_log", "SEP par logement", 6, "Nombre", "m²", "CALC", "A", "Surface externe de plancher (balcons, loggias) / logements", "existe"),

    ("sp", "SP, SP hors-sol, SP sous-sol", 7, "Nombres", "m²", "MAQ", "A", "Surfaces brutes, découpage hors-sol et sous-sol", "existe"),
    ("nettes", "SUP, SUS, SD, SI", 7, "Nombres", "m²", "MAQ", "A", "Surfaces nettes par catégorie SIA 416", "existe"),
    ("sn_sc", "SN et SC", 7, "Nombres", "m²", "CALC", "A", "SN = SUP + SUS + SD + SI ; SC = SP − SN", "existe"),
    ("sep_vb", "SEP, VB", 7, "Nombres", "m², m³", "MAQ", "A", "Surface externe de plancher, volume bâti", "existe"),
    ("uspi", "SVN, SVB, SNH (USPI)", 7, "Nombres", "m²", "MAQ", "A", "Somme des lots", "existe"),
    ("enveloppe", "Façade, vitrage, toitures", 7, "Nombres", "m²", "MAQ", "A", "Enveloppe hors-sol (SurfacesEnveloppe)", "existe"),

    ("ratios", "Ratios de rendement, pertes, sous-sol, enveloppe, programme", 8, "Nombres", "%, –", "CALC", "A", "KPI du benchmark, comparés aux projets similaires", "existe"),
    ("doublons", "SN / SP, vitrée / pleine, façade / SP hors-sol", 8, "Nombres", "", "CALC", "A", "Doublons de SC / SP, de la part vitrée et du coefficient de forme : hors des KPI affichés", "retirer"),
    ("svn_sp", "SVN / SP hors-sol", 8, "Nombre", "%", "CALC", "A", "Affiché seulement pour les projets en PPE ou en vente", "existe"),
    ("couts", "Coût par CFC (1 à 9) ou eBKP-H", 8, "Nombres", "CHF", "TRAV", "I", "Décompte final, tableau type par CFC", "ajouter"),
    ("indice_prix", "Indice suisse des prix de la construction", 8, "Nombre", "indice", "OFS", "A", "Série OFS par région, pour actualiser les coûts", "ajouter"),
    ("couts_ratios", "CHF / m³ VB, CHF / m² SP, CHF / logement", 8, "Nombres", "CHF", "CALC", "A", "Coûts actualisés / VB, SP, logements", "ajouter"),
    ("construction", "Système constructif", 8, "Liste", "", "TRAV", "M", "Béton, bois, mixte, préfabriqué", "existe"),
    ("energie", "Label énergétique, chauffage", 8, "Liste", "", "TRAV", "M", "Minergie, SNBS… ; pompe à chaleur, CAD…", "existe"),
    ("chantier", "Durée du chantier", 8, "Nombre", "mois", "TRAV", "M", "Ouverture du chantier à la réception", "existe"),
    ("revenus", "État locatif ou prix de vente", 8, "Nombre", "CHF / m²", "DEV", "I", "Loyers par m² SUP et par an, ou prix par m² SVN ; version Admin", "ajouter"),
    ("rendement", "Rendement brut", 8, "Nombre", "%", "CALC", "A", "État locatif / coût total", "ajouter"),
]

# --- remplissage : qui fournit chaque donnée manquante, et comment ----------------------------------------------
#
# Chaque champ de la carte a un mode de remplissage, que la fenêtre « Compléter la carte » regroupe :
#   vous         à saisir par l'utilisateur (SAISIES : écrit dans InfosProjet du MDP de la base, comme la forme) ;
#   identite     champ de la fiche « Identité du projet » existante (adresse, catégorie, phase…) ;
#   proposition  proposé par SIA Check (forme bâtie, distribution), confirmé par l'utilisateur dans la même saisie ;
#   auto         calculé ou collecté par SIA Check dès que ses prérequis sont là (PREREQUIS) ;
#   demande      fourni par une autre équipe (coûts, revenus, marché) ;
#   module       automatique, mais le module qui le récupère n'existe pas encore (MODULES, docs/ROADMAP.md).

LISTE_COMMERCIALISATION = ("Location", "PPE", "Mixte location et PPE", "Utilité publique / coopérative")
LISTE_DISTRIBUTION = ("Cage, 2 logements par palier", "Cage, 3 logements par palier", "Cage, 4 logements par palier",
                      "Cage, 5 logements et plus par palier", "Coursive", "Couloir central", "Accès individuels", "Mixte")
LISTE_STATIONNEMENT = ("Sous-sol", "Surface", "Silo", "Mixte", "Aucun")
LISTE_EXTERIEURS = ("Cour ou jardin privé", "Cour ou jardin commun", "Semi-public", "Public", "Toit-jardin", "Mixte")
LISTE_PUBLIC = ("Tout public", "Familles", "Seniors", "Étudiants", "Mixte")
LISTE_CONSTRUCTION = ("Béton", "Bois", "Mixte bois-béton", "Maçonnerie", "Métal", "Préfabriqué")

# clé de champ → (description dans InfosProjet du MDP, type de saisie, valeurs proposées)
SAISIES = {
    "architecte": ("Architecte", "texte", ()),
    "maitre_ouvrage": ("Maître d'ouvrage", "texte", ()),
    "commercialisation": ("Mode de commercialisation", "liste", LISTE_COMMERCIALISATION),
    "annee": ("Année d'achèvement", "nombre", ()),
    "plan_parent": ("Opération d'ensemble (plan de quartier)", "texte", ()),
    "plan_parent_log": ("Logements de l'opération d'ensemble", "nombre", ()),
    "plan_parent_surface": ("Surface de l'opération d'ensemble (m²)", "nombre", ()),
    "derogation": ("Dérogation ou bonus obtenu", "texte", ()),
    "implantation": ("Forme bâtie (a+t)", "liste", ()),      # les 33 formes a+t, ajoutées après FORMALISATIONS
    "exterieurs": ("Statut des espaces extérieurs", "liste", LISTE_EXTERIEURS),
    "pleine_terre": ("Pleine terre (m²)", "nombre", ()),
    "distribution": ("Type de distribution", "liste", LISTE_DISTRIBUTION),
    "stationnement": ("Type de stationnement", "liste", LISTE_STATIONNEMENT),
    "public_cible": ("Public cible", "liste", LISTE_PUBLIC),
    "velos": ("Places vélo", "nombre", ()),
    "construction": ("Système constructif", "liste", LISTE_CONSTRUCTION),
    "energie": ("Label énergétique et chauffage", "texte", ()),
    "chantier": ("Durée du chantier (mois)", "nombre", ()),
}
# Champs de la fiche « Identité du projet » existante : complétés en l'ouvrant depuis « Compléter la carte »
IDENTITE = {"id", "identite", "categorie", "phase", "groupe", "formes"}

# Prérequis d'un champ automatique : ce qui doit exister pour que SIA Check le remplisse seul
_MAQUETTE = "Maquette 3D du projet dans la base"
# comment l'obtenir, affiché dans « Compléter la carte » (la visionneuse publie la maquette à la lecture de la base)
AIDES = {_MAQUETTE: "Ouvrir ou importer le projet dans SIA Check (module 1) avec le même ID dans sa fiche projet : sa maquette 3D "
                     "est publiée dans la base à la prochaine lecture.",
         "Adresse exacte du projet (fiche identité), puis relecture de la base":
             "Compléter l'adresse dans la fiche identité : la position et le contexte SIG sont collectés à la relecture "
             "de la base (réseau requis)."}
_SIG = "Adresse exacte du projet (fiche identité), puis relecture de la base"
PREREQUIS = {
    "position": ["Adresse ou commune du projet (fiche identité)"],
    "terrain": [_SIG], "egrid": [_SIG], "zone": [_SIG], "isos": [_SIG], "site": [_SIG], "desserte": [_SIG],
    "arret": [_SIG], "densites": [_SIG], "accessibilite": [_SIG], "radon_sol": [_SIG], "regbl": [_SIG],
    "batiments": [_MAQUETTE], "emprise": [_MAQUETTE], "hauteur": [_MAQUETTE], "hauteur_rez": [_MAQUETTE],
    "niveaux_ss": [_MAQUETTE], "epaisseur": [_MAQUETTE], "orientation": [_MAQUETTE], "socle": [_MAQUETTE],
    "niveaux_hs": ["MDP avec ses étages"], "cages": ["MDP avec les cages d'escalier (projet Treegram ou IFC)"],
    "affectations": ["MDP avec la colonne Affectation des surfaces nettes"],
    "logements": ["MDP avec la liste des logements"], "mix": ["MDP avec le nombre de chambres de chaque logement"],
    "gsi": ["Emprise au sol", "Surface du terrain"], "fsi": ["SP hors-sol", "Surface du terrain"],
    "l": ["GSI", "FSI"], "osr": ["GSI", "FSI"], "log_ha": ["Nombre de logements", "Surface du terrain"],
    "sup_typo": ["MDP avec la liste des logements et leurs chambres"], "places": ["Places voiture (MDP)"],
    "places_log": ["Places voiture (MDP)", "Nombre de logements"], "sep_log": ["SEP", "Nombre de logements"],
    "fiabilite": ["MDP de la base"], "ratios": ["MDP de la base"], "svn_sp": ["Lots USPI du MDP"],
    "sp": ["MDP de la base"], "nettes": ["MDP de la base"], "sn_sc": ["MDP de la base"], "sep_vb": ["MDP de la base"],
    "uspi": ["Lots USPI du MDP"], "enveloppe": ["Surfaces d'enveloppe du MDP"],
    "origines": ["Au moins une donnée renseignée"],
    "geom_parcelle": [_SIG], "forme_parcelle": [_SIG], "orientation_parcelle": [_SIG],
}
# Modules prévus (docs/ROADMAP.md) : ce qui sera récupéré seul quand ils existeront
MODULES = {
    "CAD": "Extrait RDPPF par EGRID (cadastre cantonal)",
    "REGL": "Lecture des règlements communaux par l'IA, validée par une personne",
    "OFS": "Séries publiques de l'OFS",
    "pente": "Altitude swissALTI3D",
    "mitoyennete": "Bâtiments voisins swissBUILDINGS3D", "bruit": "Bruit sonBASE (OFEV)",
    "traversants": "Analyse des logements sur la maquette", "duplex": "Analyse des logements sur la maquette",
    "types_logements": "Analyse des logements sur la maquette",
    "exploitation": "Règles chiffrées (indice permis)", "couts_ratios": "Coûts par CFC", "rendement": "Coûts et revenus",
}
# Données fournies par une autre équipe : à qui les demander
DEMANDES = {"couts": "Équipe travaux / réalisation (décompte final par CFC)",
            "revenus": "Service DEV / gérance (états locatifs ou prix de vente)",
            "marche": "Service DEV (niveau de loyers ou de prix de la commune)"}


def remplissage(cle: str, source: str, statut: str) -> dict:
    """Comment se remplit un champ : mode (voir plus haut), explication, et la saisie quand c'est à l'utilisateur."""
    if cle in SAISIES:
        desc, typ, options = SAISIES[cle]
        mode = "proposition" if cle in ("implantation", "distribution") else "vous"
        return {"mode": mode, "texte": "À renseigner dans « Compléter la carte »",
                "saisie": {"description": desc, "type": typ, "options": list(options)}}
    if cle in IDENTITE:
        return {"mode": "identite", "texte": "À renseigner dans la fiche « Identité du projet »"}
    if cle in DEMANDES:
        return {"mode": "demande", "texte": f"À demander : {DEMANDES[cle]}"}
    module = MODULES.get(cle) or (MODULES.get(source) if statut in ("ajouter", "modifier") or source in ("CAD", "REGL", "OFS") else None)
    if module and cle not in PREREQUIS:
        return {"mode": "module", "texte": f"Automatique quand ce module existera : {module}"}
    pre = PREREQUIS.get(cle, [])
    return {"mode": "auto", "texte": "Rempli automatiquement par SIA Check", "prerequis": pre,
            "aide": next((AIDES[x] for x in pre if x in AIDES), None)}


# KPI affichés dans le bloc Ratios (les doublons retirés n'y sont pas ; SVN / SP hors-sol a sa ligne)
KPI_CARTE = ("SUP/SP_HS", "SC/SP", "SD/SP_HS", "SI/SP", "SUS_HS/SP_HS", "SP_SS/SUP", "FORME", "VITRE/FACADE", "VB/SP",
             "SUP/LOG", "SP_HS/LOG")
SOCLE_MIN = 1.15

# Classement des formes bâties de Density (a+t), « Formalizaciones / Housing forms » (scan p009-p012, livre p. 14-17) :
# 5 familles, 33 types, libellés traduits du livre. « contre mitoyen » : bâtiment adossé à un mitoyen existant.
FORMALISATIONS = {
    "Maisons": ("Maisons accolées", "Rangée pliée", "Rangée en gradins", "Maisons accolées autour d'une cour", "Rangée",
                "Rangée avec patios"),
    "Blocs": ("Bloc linéaire", "Blocs parallèles", "Bloc en L", "Bloc en L contre mitoyen", "Bloc en T",
              "Bloc linéaire avec cours", "Bloc superposé", "Bloc en U", "Blocs parallèles perforés",
              "Blocs parallèles contre mitoyens", "Blocs en épi", "Blocs groupés"),
    "Îlots": ("Demi-îlot", "Îlot semi-ouvert", "Îlot ouvert", "Îlot fermé", "Îlot en U", "Îlot plié", "Îlot en gradins",
              "Îlot perforé"),
    "Immeubles hauts": ("Bloc isolé", "Immeubles hauts groupés", "Bloc perforé", "Bloc allongé"),
    "Solutions mixtes": ("Bloc en gradins et rangée", "Bloc linéaire contre mitoyen et maisons à patio",
                         "Bloc linéaire et îlot fermé"),
}
SAISIES["implantation"] = ("Forme bâtie (a+t)", "liste",
                           tuple(f"{f} · {ty}" for f, tys in FORMALISATIONS.items() for ty in tys))
# Tranches de densité du livre (logements par hectare), dans l'ordre
TRANCHES = ((50, "moins de 50"), (100, "50 à 100"), (200, "100 à 200"), (300, "200 à 300"), (float("inf"), "plus de 300"))
HAUT_M, HAUT_NIVEAUX = 30.0, 10     # immeuble haut : 30 m (seuil suisse des immeubles de grande hauteur) ou 10 niveaux
# Forme du plan d'un bâtiment seul (formes.FORMES) → type a+t, quand la correspondance est directe
_FORME_SEULE = {"Barre": "Bloc linéaire", "En L": "Bloc en L", "En T": "Bloc en T", "En U": "Bloc en U",
                "Cour fermée / îlot": "Îlot fermé"}


def tranche(log_ha: float) -> str:
    return next(nom for borne, nom in TRANCHES if log_ha < borne)


def famille(type_: str) -> str | None:
    return next((f for f, types in FORMALISATIONS.items() if type_ in types), None)


def proposer_formalisation(formes: dict[str, str], axes: list[float], niveaux: float | None,
                           hauteur: float | None) -> tuple[str, str] | None:
    """(type a+t, raison) proposé d'après la forme de chaque bâtiment, leurs axes et la hauteur ; None quand rien ne
    s'impose (les familles Maisons et Solutions mixtes demandent de connaître les accès : jamais proposées)."""
    if not formes:
        return None
    haut = (hauteur or 0) >= HAUT_M or (niveaux or 0) >= HAUT_NIVEAUX
    vals = list(formes.values())
    if len(vals) == 1:
        f = vals[0]
        if haut:
            return ("Bloc allongé", f"un bâtiment haut en {f.lower()}") if f == "Barre" else ("Bloc isolé", "un seul bâtiment haut")
        if f in _FORME_SEULE:
            return _FORME_SEULE[f], f"un bâtiment de forme « {f} »"
        return None
    if haut:
        return "Immeubles hauts groupés", f"{len(vals)} bâtiments hauts"
    barres = sum(f in ("Barre", "Rectangle compact") for f in vals)
    paralleles = len({round(a / 10) % 18 for a in axes}) == 1 if axes else False
    if barres == len(vals) and paralleles:
        return "Blocs parallèles", f"{len(vals)} barres de même orientation"
    return "Blocs groupés", f"{len(vals)} bâtiments"


def schema() -> list[dict]:
    """Les champs de la carte, sans valeurs (tableaux du document et page publiée)."""
    return [dict(cle=k, donnee=d, bloc=BLOCS[b][0], role=BLOCS[b][1], type=t, unite=u, source=s, mode=MODES[m],
                 extraction=e, statut=st) for k, d, b, t, u, s, m, e, st in CHAMPS]


# --- mesures sur la maquette 3D ---------------------------------------------------------------------------------

def mesures(dossier: Path | None, id_projet: str) -> dict | None:
    """Emprise, hauteur, épaisseur, orientation et socle d'après la maquette MAQ-<id>.json.gz de la base ; None sans
    maquette lisible (shapely absent compris : la carte reste sans ces valeurs)."""
    if dossier is None or not (f := Path(dossier) / f"MAQ-{id_projet}.json.gz").is_file():
        return None
    try:
        from shapely import union_all
        from . import emprise
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
    except (ImportError, OSError, ValueError):
        return None
    unite = float(d.get("unite") or 0.01)
    rang = {(n.get("b"), n.get("l")): n.get("rang") for n in d.get("niveaux") or []}
    items, z_niv, aires_niv, niv_bat, z_rang, geo_niv = [], {}, {}, {}, {}, {}
    for lot in d.get("lots") or []:
        if lot.get("code") != "SP" or not lot.get("v"):
            continue
        v = [x * unite for x in lot["v"]]
        g = emprise.polygone(v, lot.get("i") or [])
        b, lvl = lot.get("b"), lot.get("l")
        r = rang.get((b, lvl))
        items.append((b, lvl, r, g, "SP"))
        if g is not None and not emprise.sous_sol(lvl, r):
            z_niv.setdefault(lvl, []).extend(v[2::3])
            aires_niv.setdefault((r, lvl), []).append(g)
            niv_bat.setdefault(b, set()).add(lvl)
            geo_niv.setdefault((b, lvl), []).append(g)
            if r is not None:
                z_rang.setdefault(r, []).extend(v[2::3])
    bats = emprise.emprises(items)
    if not bats:
        return None
    out: dict = {"batiments": {}, "niveaux_ss": len({lvl for (b, lvl), r in rang.items() if r is not None and r < 0})}
    for b, x in bats.items():
        rect = (x.get("rectangularite") or 0) >= 0.85
        perimetre = None
        epaisseur = x.get("largeur_m") if rect else None
        if epaisseur is None:
            perimetre = _perimetre(x)
            epaisseur = round(2 * x["aire_m2"] / perimetre, 1) if perimetre else None
        out["batiments"][b] = {"aire_m2": x["aire_m2"], "epaisseur_m": epaisseur, "axe_deg": x.get("axe_long_deg"),
                               "forme_estimee": x.get("forme_estimee"), "niveaux": len(niv_bat.get(b, ()))}
    if 0 in z_rang and 1 in z_rang:
        out["hauteur_rez_m"] = round(statistics.median(z_rang[1]) - statistics.median(z_rang[0]), 2)
    out["emprise_m2"] = round(sum(x["aire_m2"] for x in bats.values()), 1)
    # hauteur : altitude moyenne de chaque plancher hors-sol ; du plus bas au plus haut, plus un étage moyen
    planchers = sorted(statistics.median(z) for z in z_niv.values() if z)
    if len(planchers) >= 2:
        etage = (planchers[-1] - planchers[0]) / (len(planchers) - 1)
        out["hauteur_m"] = round(planchers[-1] - planchers[0] + etage, 1)
    elif len(planchers) == 1:
        out["hauteur_m"] = None
    # socle : aire du rez (rang 0) face à la médiane des étages au-dessus
    par_rang = {}
    for (r, lvl), gs in aires_niv.items():
        if r is not None:
            par_rang[r] = par_rang.get(r, 0) + union_all(gs).area
    if 0 in par_rang and (hauts := [a for r, a in par_rang.items() if r > 0]):
        out["socle"] = par_rang[0] >= SOCLE_MIN * statistics.median(hauts)
    out["volume"] = _volume(geo_niv, rang, z_niv)
    return out


VOLUME_SIMPLIFY_M = 0.5      # contour du pictogramme, après régularisation
VOLUME_MAX_SOMMETS = 400     # par projet
VOLUME_MEME_ETAGE = 0.10     # deux étages dont l'emprise régularisée diffère de moins de 10 % forment un seul prisme
VOLUME_ENCOCHE_M = 1.5       # demi-largeur des encoches et saillies bouchées (loggias, retraits de moins de 3 m)


def _volume(geo_niv: dict, rang: dict, z_niv: dict) -> list[dict] | None:
    """Le volume hors-sol pour le pictogramme de la carte : des prismes (contour extérieur, cours, altitude basse et
    haute), un par bâtiment et par suite d'étages de même emprise (un attique en retrait ou un socle plus large font
    leur propre prisme). Coordonnées en m, centrées sur le projet. None sans géométrie."""
    from shapely import union_all
    from shapely.geometry.polygon import orient
    from . import emprise
    z_med = {lvl: statistics.median(z) for lvl, z in z_niv.items() if z}
    brut: dict[str, list] = {}
    for (b, lvl), gs in geo_niv.items():
        if lvl in z_med:
            brut.setdefault(b, []).append((rang.get((b, lvl)), z_med[lvl], union_all(gs)))
    par_bat: dict[str, list] = {}
    for b, niveaux in brut.items():
        # axe du bâtiment (rectangle minimal de toutes ses emprises) : la régularisation garde les angles droits
        ang = emprise._angle_axe(union_all([g for _, _, g in niveaux]).minimum_rotated_rectangle)[0]
        for r, z, g in niveaux:
            if not (g := _regulariser(g, ang)).is_empty:
                par_bat.setdefault(b, []).append((r, z, g))
    if not par_bat:
        return None
    prismes = []
    for b, niveaux in par_bat.items():
        niveaux.sort(key=lambda x: (x[0] if x[0] is not None else 0, x[1]))
        zs = [z for _, z, _ in niveaux]
        etage = (zs[-1] - zs[0]) / (len(zs) - 1) if len(zs) > 1 else 3.0
        groupes: list[list] = []
        for i, (_, z, g) in enumerate(niveaux):
            haut = zs[i + 1] if i + 1 < len(zs) else z + etage
            if groupes and g.symmetric_difference(groupes[-1][2]).area <= VOLUME_MEME_ETAGE * max(g.area, 1):
                groupes[-1][1] = haut
            else:
                groupes.append([z, haut, g])
        for z0, z1, g in groupes:
            for poly in emprise._polys(g.simplify(VOLUME_SIMPLIFY_M)):
                if poly.area < emprise.PART_MIN_M2:
                    continue
                poly = orient(poly)       # extérieur anti-horaire, cours horaires
                anneaux = [list(poly.exterior.coords)[:-1]] + [list(h.coords)[:-1] for h in poly.interiors
                                                                if abs(orient(type(poly)(h)).area) >= emprise.COUR_MIN_M2]
                prismes.append({"b": b, "z0": z0, "z1": z1, "anneaux": anneaux})
    if not prismes:
        return None
    xs = [x for pr in prismes for a in pr["anneaux"] for x, _ in a]
    ys = [y for pr in prismes for a in pr["anneaux"] for _, y in a]
    zmin = min(pr["z0"] for pr in prismes)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    total = sum(len(a) for pr in prismes for a in pr["anneaux"])
    pas = max(1, -(-total // VOLUME_MAX_SOMMETS))     # au-delà du plafond, un sommet sur `pas`
    out = []
    for pr in prismes:
        anneaux = []
        for a in pr["anneaux"]:
            a = a[::pas] if pas > 1 and len(a) > 3 * pas else a
            anneaux.append([[round(x - cx, 1), round(y - cy, 1)] for x, y in a])
        out.append({"b": pr["b"], "z0": round(pr["z0"] - zmin, 1), "z1": round(pr["z1"] - zmin, 1), "anneaux": anneaux})
    return out


def _regulariser(g, ang: float):
    """Emprise d'un étage nettoyée pour le pictogramme : tournée dans l'axe du bâtiment, encoches et saillies de moins
    de 2 × VOLUME_ENCOCHE_M bouchées puis rabotées (fermeture puis ouverture à angles vifs), petites parties retirées."""
    from shapely.affinity import rotate
    from . import emprise
    c = g.centroid
    r = rotate(g, -ang, origin=c)
    e = VOLUME_ENCOCHE_M
    r = r.buffer(e, join_style="mitre").buffer(-e, join_style="mitre")      # fermeture : encoches bouchées
    r = r.buffer(-e, join_style="mitre").buffer(e, join_style="mitre")      # ouverture : saillies rabotées
    parts = [x for x in emprise._polys(r) if x.area >= 2 * emprise.PART_MIN_M2]
    if not parts:
        from shapely.geometry import Polygon
        return Polygon()
    from shapely import union_all
    return rotate(union_all(parts), ang, origin=c)


# Schéma d'une forme saisie (formes.FORMES), quand le projet n'a pas de maquette dans la base : contour type en m
def _rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


SCHEMAS = {
    "Carré": [_rect(-10, -10, 10, 10)],
    "Rectangle compact": [_rect(-15, -9, 15, 9)],
    "Barre": [_rect(-25, -6.5, 25, 6.5)],
    "En L": [[[-20, -15], [20, -15], [20, -3], [-8, -3], [-8, 15], [-20, 15]]],
    "En T": [[[-22, 3], [-22, 15], [22, 15], [22, 3], [6, 3], [6, -15], [-6, -15], [-6, 3]]],
    "En U": [[[-20, -15], [-8, -15], [-8, 5], [8, 5], [8, -15], [20, -15], [20, 15], [-20, 15]]],
    "Cour fermée / îlot": [_rect(-20, -20, 20, 20), [[-9, -9], [-9, 9], [9, 9], [9, -9]]],
    "À redans / en Z": [[[-24, -15], [0, -15], [0, -3], [24, -3], [24, 9], [-2, 9], [-2, -3], [-24, -3]]],
    "En peigne / en H": [[[-20, -15], [-8, -15], [-8, -5], [8, -5], [8, -15], [20, -15], [20, 15], [8, 15], [8, 5],
                          [-8, 5], [-8, 15], [-20, 15]]],
    "Rond / ovale": [[[round(14 * math.cos(a * math.pi / 12), 1), round(10 * math.sin(a * math.pi / 12), 1)] for a in range(24)]],
    "Courbe / arc": [[[round(r * math.cos(a), 1), round(r * math.sin(a), 1)] for r, angles in ((24, range(0, 9)), (12, range(8, -1, -1)))
                      for a in [math.pi / 8 * k for k in angles]]],
    "Plusieurs plots": None,
    "Irrégulière": [[[-18, -12], [10, -16], [20, 0], [6, 14], [-14, 10]]],
}


def schema_volume(formes: dict[str, str], niveaux: float | None) -> list[dict] | None:
    """Un volume type pour chaque bâtiment de forme connue, alignés côte à côte (pas de maquette dans la base)."""
    h = 3.0 * (niveaux or 4)
    prismes, x = [], 0.0
    for f in formes.values():
        anneaux = SCHEMAS.get(f)
        if f == "Plusieurs plots":
            for dx, dy in ((-14, -8), (8, -12), (-2, 10)):
                prismes.append({"z0": 0, "z1": h, "anneaux": [[[px + dx + x, py + dy] for px, py in _rect(-6, -6, 6, 6)]]})
            x += 50
            continue
        if not anneaux:
            continue
        prismes.append({"z0": 0, "z1": h, "anneaux": [[[px + x, py] for px, py in a] for a in anneaux]})
        x += 55
    if not prismes:
        return None
    dx = x / 2 - 27.5
    for pr in prismes:
        pr["anneaux"] = [[[round(px - dx, 1), py] for px, py in a] for a in pr["anneaux"]]
    return prismes


def _perimetre(x: dict) -> float | None:
    """Périmètre des contours simplifiés de l'emprise (description d'emprise.decrire)."""
    total = 0.0
    for c in x.get("contours") or []:
        pts = c.get("contour") or []
        total += sum(((pts[i][0] - pts[i - 1][0]) ** 2 + (pts[i][1] - pts[i - 1][1]) ** 2) ** 0.5 for i in range(len(pts)))
    return total or None


# --- valeurs ------------------------------------------------------------------------------------------------------

def _n(v, dec: int = 0) -> str:
    """Nombre à la suisse : 12 345,6 (espace fine insécable pour les milliers)."""
    s = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def _texte(v) -> str:
    """Valeur affichable : un nombre entier sans décimale (5.0 → « 5 »), le reste tel quel."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _pct(v) -> str:
    return f"{_n(100 * v, 1)} %"


def _sv(sig: dict | None, cle: str):
    return ((sig or {}).get(cle) or {}).get("valeur")


def _valeurs(pj: dict, sig: dict | None, mes: dict | None) -> dict[str, tuple[str | None, list]]:
    """{clé: (valeur affichée, détails [[libellé, valeur]])} pour les champs que la base sait déjà remplir."""
    i, t, k = pj.get("infos") or {}, pj.get("totaux") or {}, pj.get("kpis") or {}
    v: dict[str, tuple[str | None, list]] = {}

    def put(cle, valeur, details=None):
        # tout en texte : la visionneuse lit des chaînes (une phase saisie « 5 » arrive en nombre du MDP)
        if valeur not in (None, "") or details:
            v[cle] = (_texte(valeur) if valeur not in (None, "") else None, [[_texte(x) for x in d] for d in details or []])

    def kv(kid):
        return (k.get(kid) or {}).get("valeur")

    s = i.get("saisies") or {}           # saisies de la carte (InfosProjet), par clé de champ
    for cle in SAISIES:
        if s.get(cle) not in (None, "") and cle not in ("implantation", "distribution", "annee", "plan_parent"):
            put(cle, s[cle])
    # opération d'ensemble : son nom, et sa densité quand ses logements et sa surface sont saisis (a+t classe par elle)
    if (dp := densite_plan(s)) is not None or s.get("plan_parent"):
        put("plan_parent", s.get("plan_parent") or "Opération d'ensemble sans nom",
            [["Densité de l'opération", f"{_n(dp)} log./ha · tranche {tranche(dp)}"]] if dp is not None else [])
    put("id", pj.get("id"))
    lieu = ", ".join(str(x) for x in (i.get("adresse"), i.get("commune")) if x)
    put("identite", " · ".join(str(x) for x in (pj.get("nom"), lieu, i.get("canton")) if x))
    if pj.get("position"):
        e, n = pj["position"]
        put("position", f"{_n(e)} / {_n(n)}", [["Précision", "adresse" if pj.get("precision") == "adresse" else
                                                 "centre de la commune" if pj.get("precision") == "commune" else
                                                 str(pj.get("precision") or "")]])
    put("categorie", " · ".join(str(x) for x in (i.get("categorie"), i.get("intervention")) if x))
    put("phase", i.get("phase"))
    put("annee", s.get("annee") or i.get("date"))
    put("groupe", i.get("groupe"))
    manque = [c["label"] for c in pj.get("controles") or [] if not c.get("ok")]
    put("fiabilite", f"{_n(100 * (pj.get('score') or 0))} % · " + ("dans les références" if pj.get("fiable") else "écarté des références"),
        [["Contrôle non passé", m] for m in manque])
    if i.get("forme_origine"):
        put("origines", None, [["Forme", str(i["forme_origine"])]])

    terrain = t.get("TERRAIN")
    if terrain:
        put("terrain", f"{_n(terrain)} m²", [["Origine", str(i.get("terrain_source") or "")]])
    parc = (sig or {}).get("parcelle") or {}
    if parc.get("egrid") or parc.get("numero"):
        put("egrid", parc.get("egrid"), [["Parcelle", str(parc["numero"])]] if parc.get("numero") else [])
    if (fp := forme_parcelle(parc.get("geometrie"))) is not None:
        put("geom_parcelle", f"Polygone de {fp['sommets']} sommets", [["Périmètre", f"{_n(fp['perimetre_m'])} m"]])
        put("forme_parcelle", f"{_n(fp['longueur_m'])} × {_n(fp['largeur_m'])} m (rectangle minimal)",
            [["Élancement", _n(fp["elancement"], 1)], ["Remplissage du rectangle", _pct(fp["rectangularite"])]])
        put("orientation_parcelle", f"axe long à {fp['azimut_deg']}° du nord")

    if sig is not None:
        put("zone", _sv(sig, "zone"))
        put("isos", _sv(sig, "isos") or "Hors inventaire")
        if site := sig.get("site"):
            put("site", site.get("valeur"), [["Habitants + emplois", f"{_n(site.get('densite') or 0, 1)} / ha (300 m)"]])
        put("desserte", _sv(sig, "desserte"))
        if a := sig.get("arret"):
            put("arret", a.get("valeur"), [[str(a.get("moyen") or "Distance"), f"{_n(a['distance'])} m"]] if a.get("distance") is not None else [])
        put("densites", None, [[lab, f"{_n(x, 1)} / ha"] for lab, c in (("Habitants", "habitants"), ("Logements", "logements"),
                                                                        ("Emplois (EPT)", "emplois")) if (x := _sv(sig, c)) is not None])
        put("accessibilite", None, ([["Habitants et emplois accessibles", _n(x)]] if (x := _sv(sig, "accessibilite")) is not None else [])
            + ([["Temps jusqu'au centre", f"{_n(x)} min"]] if (x := _sv(sig, "temps_centre")) is not None else []))
        put("radon_sol", None, ([["Radon", f"{_n(x)} %"]] if (x := _sv(sig, "radon")) is not None else [])
            + ([["Sol de fondation", str(x)]] if (x := _sv(sig, "sol")) is not None else []))
        bat = sig.get("batiment") or {}
        put("regbl", None, [[lab, str(bat[c])] for lab, c in (("Bâtiment du registre", "valeur"), ("Année", "annee_construction"),
                                                               ("Niveaux", "niveaux"), ("Logements", "logements")) if bat.get(c) not in (None, "")]
            + ([["Demande de chaleur", f"{_n(x)} MWh/an"]] if (x := _sv(sig, "chaleur")) is not None else []))

    bats = (mes or {}).get("batiments") or {}
    nb = len(bats) or len(i.get("batiments") or [])
    put("batiments", _n(nb) if nb else None)
    formes = {b: f for b, f in (i.get("formes") or {}).items()} or {b: x["forme_estimee"] for b, x in bats.items() if x.get("forme_estimee")}
    prop = proposer_formalisation(formes, [x["axe_deg"] for x in bats.values() if x.get("axe_deg") is not None],
                                  t.get("ETAGES_HS"), (mes or {}).get("hauteur_m"))
    if s.get("implantation"):
        put("implantation", s["implantation"])
    elif prop:
        put("implantation", None, [["Proposé (à confirmer)", f"{famille(prop[0])} · {prop[0]}"], ["D'après", prop[1]]])
    put("formes", i.get("forme"), [[b, f] for b, f in (i.get("formes") or {}).items() if b] if len(i.get("formes") or {}) > 1 else [])
    emp = (mes or {}).get("emprise_m2")
    put("emprise", f"{_n(emp)} m²" if emp else None, [[b, f"{_n(x['aire_m2'])} m²"] for b, x in bats.items()] if len(bats) > 1 else [])
    gsi = emp / terrain if emp and terrain else None
    fsi = kv("SP_HS/TERRAIN")
    put("gsi", _n(gsi, 2) if gsi else None)
    put("fsi", _n(fsi, 2) if fsi else None)
    put("l", _n(fsi / gsi, 1) if fsi and gsi else None)
    put("osr", _n((1 - gsi) / fsi, 2) if fsi and gsi and gsi < 1 else None)
    log = t.get("LOG")
    if log and terrain:
        lh = log / (terrain / 10_000)
        put("log_ha", f"{_n(lh)} log./ha · tranche {tranche(lh)}",
            [["Échelle du calcul", "terrain du projet (a+t classe un bâtiment d'un plan de quartier par la densité du plan)"]])
    put("hauteur", f"{_n(mes['hauteur_m'], 1)} m" if (mes or {}).get("hauteur_m") else None)
    niv_b = [x["niveaux"] for x in bats.values() if x.get("niveaux")]
    put("niveaux_hs", (_n(t["ETAGES_HS"]) + (f" (de {min(niv_b)} à {max(niv_b)} selon le bâtiment)" if niv_b and min(niv_b) < max(niv_b) else ""))
        if t.get("ETAGES_HS") else None)
    if (mes or {}).get("hauteur_rez_m"):
        put("hauteur_rez", f"{_n(mes['hauteur_rez_m'], 2)} m")
    if mes is not None:
        put("niveaux_ss", _n(mes.get("niveaux_ss") or 0))
    ep = [x["epaisseur_m"] for x in bats.values() if x.get("epaisseur_m")]
    if ep:
        put("epaisseur", f"{_n(statistics.median(ep), 1)} m" + (f" (de {_n(min(ep), 1)} à {_n(max(ep), 1)} m)" if len(ep) > 1 and max(ep) > min(ep) else ""),
            [[b, f"{_n(x['epaisseur_m'], 1)} m"] for b, x in bats.items() if x.get("epaisseur_m")] if len(ep) > 1 else [])
    axes = sorted({x["axe_deg"] % 180 for x in bats.values() if x.get("axe_deg") is not None})
    put("orientation", " · ".join(f"{a}°" for a in axes) if axes else None)
    if (mes or {}).get("socle") is not None:
        put("socle", "Oui" if mes["socle"] else "Non")

    lc = kv("LOG/CAGE")
    if s.get("distribution"):
        put("distribution", s["distribution"])
    elif lc:
        put("distribution", None, [["Indice", f"{_n(lc, 1)} logements par cage et par étage (à confirmer)"]])
    # CAGES compte les cages de chaque étage de logements (sommées) : on affiche les ratios, pas ce total
    put("cages", f"{_n(lc, 1)} logements par cage et par étage" if lc else None,
        [["SUP par cage et par étage", f"{_n(x)} m²"]] if (x := kv("SUP/CAGE")) else [])

    aff = i.get("affectations") or {}
    tot = sum(aff.values())
    if tot:
        put("affectations", " · ".join(f"{a} {_n(100 * m / tot)} %" for a, m in list(aff.items())[:3]),
            [[a, f"{_n(m)} m² ({_n(100 * m / tot)} %)"] for a, m in aff.items()])
    put("logements", _n(log) if log else None)
    mix = pj.get("mix") or {}
    if mix:
        n_mix = sum(mix.values())
        put("mix", " · ".join(f"{c} ch. {_n(100 * m / n_mix)} %" for c, m in sorted(mix.items(), key=lambda x: int(x[0]))),
            [[f"{c} chambre{'s' if int(c) > 1 else ''}", f"{m} logement{'s' if m > 1 else ''}"] for c, m in sorted(mix.items(), key=lambda x: int(x[0]))])
    par_ch: dict[int, list[float]] = {}
    for lg in pj.get("logements") or []:
        par_ch.setdefault(lg["chambres"], []).append(lg["sup"])
    if par_ch:
        put("sup_typo", None, [[f"{c} chambre{'s' if c > 1 else ''}", f"{_n(statistics.median(s))} m² ({len(s)})"] for c, s in sorted(par_ch.items())])
    places = i.get("places_voiture")
    put("places", _n(places) if places is not None else None)
    put("places_log", _n(places / log, 2) if places is not None and log else None)
    put("sep_log", f"{_n(t['SEP'] / log, 1)} m²" if t.get("SEP") and log else None)

    def surf(cles):
        return [[c.replace("_HS", " hors-sol").replace("_SS", " sous-sol"), f"{_n(t[c])} {'m³' if c == 'VB' else 'm²'}"] for c in cles if t.get(c) is not None]
    put("sp", f"{_n(t['SP'])} m²" if t.get("SP") else None, surf(("SP_HS", "SP_SS")))
    put("nettes", None, surf(("SUP", "SUS", "SD", "SI", "SUP_HS", "SUP_SS")))
    put("sn_sc", None, surf(("SN", "SC")))
    put("sep_vb", None, surf(("SEP", "VB")))
    put("uspi", None, surf(("SVN", "SVB", "SNH")))
    put("enveloppe", None, [[lab, f"{_n(t[c])} m²"] for lab, c in (("Façade", "FACADE"), ("Vitrée", "VITRE"), ("Toitures", "TOITURE")) if t.get(c) is not None])

    labels = {kid: kid for kid in KPI_CARTE}
    try:
        from .benchmark import KPI_BY_ID
        labels = {kid: KPI_BY_ID[kid].label for kid in KPI_CARTE if kid in KPI_BY_ID}
        unites = {kid: KPI_BY_ID[kid].unite for kid in KPI_CARTE if kid in KPI_BY_ID}
    except ImportError:     # pragma: no cover
        unites = {}
    put("ratios", None, [[labels[kid], _pct(x) if unites.get(kid) == "%" else f"{_n(x, 2)}{(' ' + unites[kid]) if unites.get(kid) else ''}"]
                         for kid in KPI_CARTE if (x := kv(kid)) is not None])
    loc = s.get("commercialisation") and not str(s["commercialisation"]).lower().startswith(("ppe", "mixte"))
    put("svn_sp", f"sans objet ({str(s['commercialisation']).lower()})" if loc else _pct(kv("SVN/SP_HS")) if kv("SVN/SP_HS") else None)
    return v


def carte(pj: dict, sig: dict | None = None, mes: dict | None = None) -> dict:
    """La carte d'un projet (projet tel que benchmark.projet_json le décrit, sa fiche SIG, ses mesures de maquette) :
    blocs dans l'ordre, chacun avec ses champs ; annexe pour les données reléguées. Les champs retirés n'y sont pas."""
    vals = _valeurs(pj, sig, mes)
    vals.pop("origines", None)
    # origine de chaque valeur, résumée sur la ligne « Origine de chaque valeur » (qui est elle-même un calcul)
    origines = {cle: _origine(cle, src, pj, mes) for cle, _, _, _, _, src, _, _, statut in CHAMPS
                if statut != "retirer" and cle in vals}
    par: dict[str, int] = {}
    for o in origines.values():
        par[o] = par.get(o, 0) + 1
    if par:
        ordre = sorted(par, key=lambda o: (-par[o], o))
        vals["origines"] = (" · ".join(f"{o} {par[o]}" for o in ordre), [[o, ORIGINES[o]] for o in ordre])
        origines["origines"] = "Calcul"
    blocs: dict[str, dict] = {}
    annexe = []
    remplis = total = 0
    for cle, donnee, b, typ, unite, src, mode, extraction, statut in CHAMPS:
        if statut == "retirer":
            continue
        valeur, details = vals.get(cle, (None, []))
        champ = {"cle": cle, "donnee": donnee, "valeur": valeur, "details": details, "unite": unite, "type": typ,
                 "source": src, "mode": MODES[mode], "extraction": extraction, "statut": statut,
                 "origine": origines.get(cle),
                 "remplissage": remplissage(cle, src, statut)}
        if cle in SAISIES:
            saisi = ((pj.get("infos") or {}).get("saisies") or {}).get(cle)
            champ["remplissage"]["saisie"]["valeur"] = _texte(saisi) if saisi not in (None, "") else None
            champ["remplissage"]["saisie"]["propose"] = _proposition(cle, vals)
        if statut == "reléguer":
            annexe.append(champ)
            continue
        total += 1
        remplis += bool(valeur or details)
        nom, role = BLOCS[b]
        blocs.setdefault(nom, {"nom": nom, "role": role, "champs": []})["champs"].append(champ)
    return {"version": 1, "sources": {k: n for k, (n, _) in SOURCES.items()}, "blocs": list(blocs.values()),
            "annexe": annexe, "remplis": remplis, "total": total, "maquette": mes is not None, "sig": sig is not None,
            **_entete(pj, vals, mes, sig)}


def _proposition(cle: str, vals: dict) -> str | None:
    """Valeur proposée par SIA Check pour une saisie, prête à confirmer (forme bâtie a+t, distribution)."""
    details = dict(vals.get(cle, (None, []))[1])
    if cle == "implantation":
        return details.get("Proposé (à confirmer)")
    if cle == "distribution" and (ind := details.get("Indice")):
        try:
            n = float(ind.split(" ")[0].replace(",", "."))
        except ValueError:
            return None
        return LISTE_DISTRIBUTION[0 if n < 2.5 else 1 if n < 3.5 else 2 if n < 4.5 else 3]
    return None


def _entete(pj: dict, vals: dict, mes: dict | None, sig: dict | None = None) -> dict:
    """En tête de la carte : le volume du projet (pictogramme), son plan d'implantation à échelle vraie, sa forme bâtie,
    sa densité et sa typologie."""
    i, t = pj.get("infos") or {}, pj.get("totaux") or {}
    bats = (mes or {}).get("batiments") or {}
    formes = dict(i.get("formes") or {}) or {b: x["forme_estimee"] for b, x in bats.items() if x.get("forme_estimee")}
    volume, origine = (mes or {}).get("volume"), "maquette"
    if not volume:
        volume, origine = schema_volume(formes, t.get("ETAGES_HS")), "schéma"
    prop = dict(vals.get("implantation", (None, []))[1]).get("Proposé (à confirmer)")
    estimees = sorted({f for f in formes.values() if f})
    confirme = (i.get("saisies") or {}).get("implantation")
    forme = confirme or (f"{prop} (proposée)" if prop else None) or i.get("forme") or         (f"{', '.join(estimees)} (forme du plan, estimée)" if estimees else None)
    lh = vals.get("log_ha", (None, []))[0]
    mix = vals.get("mix", (None, []))[0]
    typo = " · ".join(str(x) for x in (i.get("categorie"), mix) if x) or None
    return {"entete": {"forme": forme, "densite": lh, "typologie": typo,
                       "volume": volume, "volume_origine": origine if volume else None,
                       "implantation": implantation(pj, sig, mes)}}


# --- origine de chaque valeur -------------------------------------------------------------------------------------

ORIGINES = {"Saisie": "saisi dans la carte ou la fiche du projet", "IA": "proposé par l'IA, confirmé",
            "Proposé": "proposé par SIA Check, à confirmer", "MDP": "lu dans le MDP du projet",
            "Maquette": "mesuré sur la maquette 3D de la base", "Calcul": "calculé par SIA Check",
            "SIG": "collecté sur geo.admin.ch (fiche SIG)"}
_MESURES = {"batiments", "emprise", "hauteur", "hauteur_rez", "niveaux_ss", "epaisseur", "orientation", "socle"}


def _origine(cle: str, source: str, pj: dict, mes: dict | None) -> str:
    """Qui a fourni la valeur d'un champ renseigné (clé de ORIGINES)."""
    i = pj.get("infos") or {}
    s = i.get("saisies") or {}
    if cle in SAISIES and s.get(cle) not in (None, ""):
        return "Saisie"
    if cle in ("implantation", "distribution"):
        return "Proposé"
    if cle == "formes":
        return "IA" if str(i.get("forme_origine") or "").lower() == "ia" else "Saisie"
    if cle == "terrain":
        return "MDP" if i.get("terrain_source") == "MDP" else "SIG"
    if cle == "batiments" and not (mes or {}).get("batiments"):
        return "MDP"
    if source == "MAQ":
        return "Maquette" if cle in _MESURES else "Calcul"
    if source in ("FICHE", "TRAV", "DEV"):
        return "MDP"
    if source == "SIG":
        return "SIG"
    return "Calcul"


# --- forme bâtie, parcelle, densité : la carte résumée pour le benchmark (dashboard) --------------------------------

def densite_plan(saisies: dict) -> float | None:
    """Logements à l'hectare de l'opération d'ensemble, d'après ses saisies ; None s'il en manque une."""
    try:
        log, surf = float(saisies.get("plan_parent_log")), float(saisies.get("plan_parent_surface"))
    except (TypeError, ValueError):
        return None
    return log / (surf / 10_000) if log > 0 and surf > 0 else None


def _polygones(geometrie):
    """Polygones shapely d'une géométrie de fiche SIG ([polygone][anneau][point]) ; [] sans shapely ou sans géométrie."""
    try:
        from shapely.geometry import Polygon
    except ImportError:     # pragma: no cover
        return []
    out = []
    for poly in geometrie or []:
        if poly and len(poly[0]) >= 3:
            g = Polygon(poly[0], [a for a in poly[1:] if len(a) >= 3])
            g = g if g.is_valid else g.buffer(0)
            if g.area > 0:
                out.append(g)
    return out


def forme_parcelle(geometrie) -> dict | None:
    """Rectangle minimal, élancement, remplissage et orientation (azimut de l'axe long) de la parcelle ; None sans
    polygone."""
    polys = _polygones(geometrie)
    if not polys:
        return None
    from shapely import union_all
    from . import emprise
    g = union_all(polys)
    m = emprise._mesures(g)
    # l'axe du rectangle minimal est mesuré depuis l'est (x LV95), dans le sens trigonométrique : azimut = 90 − angle
    return {"sommets": sum(len(p.exterior.coords) - 1 for p in polys), "perimetre_m": round(g.length),
            "longueur_m": m["longueur_m"], "largeur_m": m["largeur_m"], "elancement": m["elancement"],
            "rectangularite": m["rectangularite"], "azimut_deg": round(90 - m["axe_long_deg"]) % 180}


def forme_at(infos: dict, totaux: dict, mes: dict | None) -> tuple[str, str] | None:
    """(« Famille · type », origine) : la forme bâtie a+t confirmée (« Saisie »), sinon proposée par SIA Check
    (« Proposé ») ; None quand rien ne s'impose."""
    if s := (infos.get("saisies") or {}).get("implantation"):
        return str(s), "Saisie"
    bats = (mes or {}).get("batiments") or {}
    formes = dict(infos.get("formes") or {}) or {b: x["forme_estimee"] for b, x in bats.items() if x.get("forme_estimee")}
    prop = proposer_formalisation(formes, [x["axe_deg"] for x in bats.values() if x.get("axe_deg") is not None],
                                  totaux.get("ETAGES_HS"), (mes or {}).get("hauteur_m"))
    return (f"{famille(prop[0])} · {prop[0]}", "Proposé") if prop else None


def famille_de(forme: str | None) -> str | None:
    """Famille a+t d'une forme « Famille · type » (ou d'un type seul)."""
    if not forme:
        return None
    tete, _, type_ = str(forme).partition(" · ")
    return tete if tete in FORMALISATIONS else famille(type_ or tete)


PLAN_SIMPLIFY_M = 0.5


def implantation(pj: dict, sig: dict | None, mes: dict | None) -> dict | None:
    """Plan d'implantation à échelle vraie (m) : l'emprise hors-sol de la maquette (réunion des prismes du volume) et la
    parcelle de la fiche SIG (nord en haut), centrées sur la parcelle. La maquette n'est pas géoréférencée : son emprise
    est posée au point de l'adresse (sinon au centre de la parcelle), dans son propre repère (« calee » False). None sans
    l'une ni l'autre."""
    try:
        from shapely import union_all
        from shapely.affinity import translate
        from shapely.geometry import Point, Polygon
    except ImportError:     # pragma: no cover
        return None
    emp = None
    vol = (mes or {}).get("volume")
    if vol:
        polys = [Polygon(pr["anneaux"][0], [a for a in pr["anneaux"][1:] if len(a) >= 3])
                 for pr in vol if pr.get("anneaux") and len(pr["anneaux"][0]) >= 3]
        polys = [g if g.is_valid else g.buffer(0) for g in polys]
        if polys:
            emp = union_all(polys).simplify(PLAN_SIMPLIFY_M)
    parcs = _polygones(((sig or {}).get("parcelle") or {}).get("geometrie"))
    parc = union_all(parcs).simplify(PLAN_SIMPLIFY_M) if parcs else None
    if (emp is None or emp.is_empty) and parc is None:
        return None
    out: dict = {"calee": False}
    if emp is not None and not emp.is_empty:
        ex = emp.centroid
        emp = translate(emp, -ex.x, -ex.y)
    if parc is not None:
        c = parc.centroid
        pos = pj.get("position")
        dans = bool(pos) and pj.get("precision") == "adresse" and parc.buffer(5).contains(Point(pos))
        out["parcelle"] = _anneaux(translate(parc, -c.x, -c.y))
        out["parcelle_m2"] = round(parc.area)
        if emp is not None and dans:
            emp = translate(emp, pos[0] - c.x, pos[1] - c.y)
    if emp is not None and not emp.is_empty:
        out["emprise"] = _anneaux(emp)
        out["emprise_m2"] = round(emp.area)
    return out


def _anneaux(g) -> list[list[list[list[float]]]]:
    """[polygone][anneau][point] arrondis au décimètre, extérieur puis cours."""
    from . import emprise
    return [[[[round(x, 1), round(y, 1)] for x, y in list(r.coords)[:-1]] for r in (p.exterior, *p.interiors)]
            for p in emprise._polys(g)]


def resume(pj: dict, sig: dict | None, mes: dict | None) -> dict:
    """La carte en quelques valeurs pour le benchmark (dashboard : filtres, Spacematrix, planche des implantations),
    dans toutes les versions de la base. Seules les valeurs connues y sont."""
    from .benchmark import realise
    i, t = pj.get("infos") or {}, pj.get("totaux") or {}
    s = i.get("saisies") or {}
    fa = forme_at(i, t, mes)
    terrain = t.get("TERRAIN")
    emp = (mes or {}).get("emprise_m2") or t.get("EMPRISE")
    gsi = emp / terrain if emp and terrain else None
    fsi = t["SP_HS"] / terrain if t.get("SP_HS") and terrain else None
    lh = t["LOG"] / (terrain / 10_000) if t.get("LOG") and terrain else None
    dp = densite_plan(s)
    out = {
        "forme_at": fa[0] if fa else None, "forme_at_origine": fa[1] if fa else None,
        "famille": famille_de(fa[0]) if fa else None,
        "distribution": s.get("distribution"), "commercialisation": s.get("commercialisation"),
        "realise": realise(i.get("phase")),
        "terrain": terrain, "emprise": emp,
        "gsi": round(gsi, 4) if gsi else None, "fsi": round(fsi, 4) if fsi else None,
        "l": round(fsi / gsi, 2) if fsi and gsi else None,
        "osr": round((1 - gsi) / fsi, 3) if fsi and gsi and gsi < 1 else None,
        "log_ha": round(lh, 1) if lh else None, "tranche": tranche(lh) if lh else None,
        "plan": s.get("plan_parent"), "log_ha_plan": round(dp, 1) if dp else None,
        "tranche_plan": tranche(dp) if dp else None,
        "implantation": implantation(pj, sig, mes),
    }
    return {k: v for k, v in out.items() if v is not None}
