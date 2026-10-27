# V3_PLAN — Benchmark des surfaces

> Statut : ☑ Brouillon · ☐ Validé par l'utilisateur
> Version : 0.3 — 27.10.2026 · référence = projets similaires, pas de ratios idéaux ; phase 9 livrée

## 1. Objectif

La V1 et la V2 fiabilisent les surfaces Treegram et produisent des MDP propres. La V3 **exploite** cette base : un benchmark qui permet au développement immobilier de vérifier, dès la conception, qu'un projet de logement tient la comparaison avec les projets qui lui ressemblent.

Il n'y a pas de ratios idéaux fixés (27.10.2026) : **la référence d'un projet, ce sont les ratios combinés des projets qui partagent ses caractéristiques** (§4.4). La référence se précise à mesure que la base grandit.

Le benchmark démarre dans SIA Check (module Dashboard) et doit pouvoir passer sur le web sans être réécrit : il est donc **écrit en HTML/JS dès le départ** et affiché dans l'application par WebView2 (§6).

## 2. Le Power BI existant : ce qu'il fait, ce qui ne va pas

Le rapport `Benchmark projets surfaces SIA416-KPI.pbix` a deux pages (*SIA416*, *Logements*). C'est une **fiche projet** : on choisit un projet, on lit ses surfaces, une dizaine de ratios et ses caractéristiques techniques. Il ne compare pas les projets entre eux et n'affiche aucune cible.

Le modèle ne contient qu'un projet (1467, La Bâtie). En lisant les mesures DAX :

| Mesure | Problème |
|---|---|
| `SPD Hors-Sol`, `Ratio_SP_SPD_HorsSol`, `Ratio_SUP_SPD_HorsSol`, `Ratio_Pièces GE/SP` | Filtre `NOT CONTAINSSTRING(Etage, "N")` : ce sont les **sous-sols** qui sont retenus, pas le hors-sol. |
| `SPD = SC + SUP + SD` | Grandeur hors SIA 416 (SP = SN + SC, SN = SU + SD + SI) : ni SUS ni SI. |
| `Ratio_Caves/SUP`, `Ratio_Parking/SUP`, `Ratio_E.Communs/SUP`, `LocauxTech/SP` | Reposent sur le libellé d'affectation (« Caves », « Parking »…), qui varie d'un MDP à l'autre : 0 sur la plupart des projets. |
| `Moyenne Hauteur étages S` | Filtre sur « Volume Bâti (VB) », alors que l'autre mesure écrit « Volume Bâtie (VB) ». |
| `SUP/SP(hs)` | Numérateur sur tous les étages, dénominateur sur le hors-sol seul. |
| `InfosProjet[Nbr de bâtiments]` | Typé date (`1900-01-02` pour 2). |

Le benchmark V3 recalcule tout en SIA 416 strict, au même endroit que le contrôle (Python), avec des tests.

## 3. Ce que la base nous dit (10 MDP du dossier `03-DataBase-DonneesProjets`)

| Projet | Nettes | Brutes (SP) | SP hors-sol / sous-sol | Logements + chambres | USPI | Enveloppe | Canton |
|---|---|---|---|---|---|---|---|
| 1023 Côté Gare | ✓ | ✗ | ✗ | ✗ | SVN seule | ✗ | « Valais » (commune Bussigny) |
| 1280 Les Patios | ✓ (affectation vide) | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| 1399 Quartier de l'Étang C | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | GE |
| 1467 La Bâtie | ✓ | ✓ | ✗ (découpage vide) | ✓ | ✗ | partielle | GE |
| 1712 Myonaz | ✓ | ✓ | ✗ (découpage vide) | sans chambres | partielle | ✗ | VD |
| 1714 Le Clos des Hêtres | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | VD |
| 1746 Les Avallons | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| 1747 Gare-Casino | ✓ | partielle (SP < SN) | ✗ | sans chambres | ✗ | ✗ | FR |
| 1778 L'Orée | tronquée (ancien copier-coller) | ✓ | ✓ | sans chambres | ✗ | ✗ | ✗ |
| 1784 Sauvabelines | ✓ (étage « Attique » non codé) | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |

Constats :

1. **Le ratio maître SUP / SP hors-sol n'est calculable que sur 4 projets sur 10** (Patios 0,57 ; Avallons 0,70 ; Sauvabelines 0,69 ; Clos des Hêtres 0,81, ce dernier suspect : 24 m² de SD hors-sol). La valeur du benchmark dépend d'abord de la qualité de la base : c'est le lien naturel entre Fiabilisation et Dashboard.
2. La SC n'est jamais dans les nettes : elle se déduit (SP − SN), ce qui exige les brutes.
3. Les libellés (catégories en code ou en toutes lettres, affectations, étages) varient : il faut une normalisation à l'import, pas dans les formules.
4. 10 projets, c'est peu : pas de moyenne seule, toujours les points individuels, la médiane, les quartiles et le nombre de projets derrière chaque chiffre.

## 4. Conception du benchmark

### 4.1 Les questions des équipes

| Moment | Question | Réponse attendue |
|---|---|---|
| Faisabilité / acquisition | « Sur ce terrain, avec X m² de SP, combien de m² vendables et de logements ? » | Fourchette P25–médiane–P75 tirée des projets comparables |
| Conception (concours, avant-projet) | « Mon plan est-il efficace ? Où perd-il des m² ? » | Positionnement du projet en cours face aux ratios combinés des projets similaires, écart en m² |
| Programmation | « Quelle surface pour un 3,5 pièces ? Quel mix ? » | Bibliothèque des typologies réelles : surface par nombre de chambres, min–médiane–max |
| Pilotage | « Nos projets s'améliorent-ils ? » | Évolution des ratios par date ou phase |

### 4.2 L'arbre du m² (fil conducteur)

Tout se lit comme une cascade : chaque m² construit (coût) est suivi jusqu'au m² vendu ou loué (revenu).

```
SP hors-sol ─┬─ SC  (murs, structure)
             ├─ SD  (circulations)
             ├─ SI  (gaines, technique)
             ├─ SUS hors-sol
             └─ SUP (+ SUT) ── SVN / SVB (USPI)   ← le m² qui rapporte
SP sous-sol ── surtout SUS (parking, caves)         ← le m² qui coûte le plus par m² vendu
```

| Famille | KPI | Pourquoi |
|---|---|---|
| Rendement (le cœur) | SUP / SP hors-sol, SVN / SP hors-sol, SN / SP | Revenu par m² construit |
| Pertes | SC / SP, SD / SP, SI / SP (hors-sol, étages types) | Où partent les m² |
| Sous-sol | SP sous-sol / SUP, m² de parking par place | Coût caché par m² vendu |
| Compacité | Façade / SP hors-sol, VB / SP (hauteur moyenne), vitrage / façade | Coût d'enveloppe |
| Distribution | Logements par cage et par étage, SP par cage | Efficacité des circulations verticales |
| Programme | Mix typologique, SUP moyenne par nombre de chambres, SUP par logement | Bibliothèque de programmation |

### 4.3 Ce qui fait la valeur ajoutée (par rapport au Power BI)

1. **Mon projet** : on positionne un projet en cours, soit depuis un projet SIA Check ouvert, soit par une saisie rapide (SP hors-sol, SP sous-sol, SUP, nombre de logements, mix). Chaque KPI s'affiche sur la distribution des projets similaires, avec leur ratio combiné comme référence, et l'écart est traduit en m² (« 6 points de SD en trop = 310 m² de SUP perdus »), puis en CHF si on renseigne un prix de vente au m².
2. **Projets similaires** : le groupe de référence se construit sur les caractéristiques communes (§4.4), réglables à la main ; le dashboard dit toujours sur quels projets repose la référence.
3. **Programmation inverse** : « pour 4 000 m² de SP hors-sol » → SUP et SVN attendues (fourchette), nombre de logements selon le mix choisi, SP sous-sol probable.
4. **Fiabilité visible** : chaque projet a un score (feuilles complètes, cohérence SP ≥ SN, statut « Traité » dans SIA Check) ; un KPI n'utilise que les projets qui ont les données nécessaires et affiche son *n*. Un clic sur un point ouvre le projet et sa source.
5. **Un seul dictionnaire SIA 416** : définitions affichées au survol, identiques au contrôle (config.yaml).

### 4.4 Projets similaires et ratios combinés

**Les similitudes.** Deux familles de caractéristiques, toutes lues dans le MDP :

| Type | Caractéristiques | Usage |
|---|---|---|
| Filtres (même valeur) | Catégorie d'ouvrage, type d'intervention, canton | Le groupe ne garde que les projets identiques sur les filtres cochés |
| Proximité (valeur voisine) | SP hors-sol, nombre de logements, étages hors-sol, part de sous-sol (SP sous-sol / SP hors-sol), part de grands logements (3 chambres et plus) | Distance normalisée ; les projets les plus proches entrent dans le groupe |

On part soit d'un projet (de la base ou en cours), soit de filtres seuls. Par défaut : même catégorie d'ouvrage et même type d'intervention, puis les plus proches en taille. Avec 10 projets, le groupe garde au moins 3 projets ; en dessous, le dashboard le signale au lieu d'afficher une référence.

**Le ratio combiné.** Pour un groupe, chaque ratio est donné de deux façons :

- **combiné** = Σ numérateurs / Σ dénominateurs : le ratio du groupe vu comme un seul grand projet, pondéré par la surface ; c'est la référence ;
- **dispersion** = médiane, quartiles et valeur de chaque projet : montre si la référence est solide ou tirée par un seul projet.

Un projet n'entre dans un ratio que s'il en a les deux termes (ex. pas de SUP / SP hors-sol sans découpage des brutes) : chaque ratio a son propre *n*.

## 5. Page d'accueil

Deux colonnes :

| Fiabilisation | Benchmark |
|---|---|
| Ouvrir un dossier de projet | Lancer le dashboard |
| Projets actifs et statuts (existant) | Projets de la base : nom, canton, date, score de fiabilité, KPI manquants |
| | Ajouter un MDP / changer le dossier de la base |

Un projet « Traité » propose d'envoyer son MDP dans la base.

## 6. Architecture

```
MDP *.xlsx (dossier base) ──► sia_check.benchmark (Python)
                               lecture, normalisation, fiabilité, KPI
                               ──► benchmark.json (projets, KPI, logements)
                                        │
             ┌──────────────────────────┴──────────────────────────┐
     SIA Check (WPF + WebView2)                          plus tard : serveur web
     dashboard/ HTML + JS, hors ligne                   mêmes fichiers dashboard/
```

- Le calcul reste en Python (testé, réutilisable côté serveur) ; le front ne fait que filtrer et afficher.
- `dashboard/` : HTML/JS sans étape de build, bibliothèque de graphiques embarquée (pas de CDN : l'app doit marcher hors ligne).
- WPF : un contrôle WebView2 qui charge `dashboard/index.html` et lui passe `benchmark.json` ; « Mon projet » lui transmet les totaux du projet ouvert.

## 7. Phases proposées

| Phase | Contenu | Livrable |
|---|---|---|
| 9 ✓ | Moteur de base : lecture et normalisation des MDP, score de fiabilité, KPI SIA 416, projets similaires, ratios combinés, `benchmark.json`, tests sur les 10 MDP | `sia-check --benchmark <dossier>` (`sia_check/benchmark.py`) |
| 10 ✓ | Accueil en deux sections (Fiabilisation / Benchmark), empreinte de fiabilité, « Ajouter à la base » | Accueil WPF (DESIGN_PLAN, Évolution 3.0) |
| 11 ✓ | Dashboard v1 dans WebView2 : Comparer (règles, projets similaires, écarts en m²), Base, Typologies | `dashboard/` (HTML sans dépendance, servi tel quel sur le web) |
| 12 ✓ | Mon projet : saisie rapide ou projet ouvert dans SIA Check, positionnement face aux projets similaires, écarts en m² et CHF (rendement) | Comparaison (`--benchmark-projet`, DESIGN_PLAN Évolution 3.2) |
| 13 ✓ | Programmation inverse : d'une SP hors-sol, des étages et d'un mix au programme attendu (bas / central / haut) | Onglet Programmer (DESIGN_PLAN Évolution 3.3) |
| 14 | Mise en ligne web : reportée (27.10.2026) — rien n'est publié avant la fin du cycle de développement et de validation. Décidé : accès limité à un groupe restreint. Ouverts : hébergement (piste Azure Static Web Apps), mode de mise à jour de la base | Après validation de la V3 |

### Phase 9 livrée (27.10.2026)

- Un projet n'entre dans les références que si SP ≥ SN et SC / SP est entre 8 et 30 % : au-delà, SP et SN ne couvrent pas le même périmètre. Il reste affiché, signalé « écarté ».
- Sur la base actuelle : **5 projets fiables sur 10** (1467, 1712, 1714, 1746, 1784). Écartés : 1023 et 1399 (pas de brutes), 1280 (SC 33 %), 1747 (SC 55 %), 1778 (SC 56 %, nettes tronquées).
- Ratio combiné SUP / SP hors-sol des 5 : 0,73 (médiane 0,73) ; SC / SP : 0,16 ; SD hors-sol / SP hors-sol : 0,07 ; SUP par logement : 75 m².
- À vérifier dans les données : 1714 a 1 % de SD hors-sol et une SVN supérieure à la SP hors-sol.

En parallèle (hors code) : ré-exporter par SIA Check les MDP anciens (L'Orée en premier) pour faire passer la base de 4 à 8 projets exploitables.

## 8. Questions ouvertes

1. ~~Ratios idéaux VD~~ : il n'y en a pas, la référence vient des projets similaires (27.10.2026).
2. Hypothèses financières (prix de vente au m² SVN, coût au m³ VB) : à afficher en CHF ou rester en m² ?
3. Emplacement de la base : dossier local, partage réseau ou SharePoint ?
4. Les MDP incomplets : les ré-exporter via SIA Check, ou les garder avec un score de fiabilité bas ?

## 9. Révision — un benchmark multi-typologies (27.10.2026)

### Ce que l'équipe a précisé

- **Utilisateurs** : les chefs de projet du développement et la prospection.
- **Deux usages** : sortir rapidement des ratios pour établir un plan financier (onglet Programmer) ; comparer le projet dessiné par l'architecte aux benchmarks, « pour savoir si on est dans le tir » (onglet Comparer).
- **KPI clés** : SUP / SP d'abord ; puis la surface vitrée rapportée à la surface pleine et le coefficient de forme. D'autres ratios pourront s'ajouter s'ils s'avèrent significatifs.
- **Pas seulement du logement** : bureaux, hôtellerie, santé, EMS, écoles… Le benchmark part d'une **sélection** : « nouveau projet de santé dans le canton de Vaud → je choisis la typologie Santé, je vois ses ratios, puis j'affine sur Vaud ». Chaque projet doit donc être **clairement identifié**.

### Ce qui ne colle pas dans l'existant

| Sujet | Aujourd'hui | Conséquence |
|---|---|---|
| Identité des projets | SIA Check n'écrit ni canton, ni catégorie d'ouvrage, ni type d'intervention dans le MDP exporté ; 4 MDP sur 10 n'ont pas de canton ; la catégorie manquante est **déduite des affectations**, avec une logique pensée pour le logement | Un immeuble de bureaux serait classé « Logement mixte ». La sélection par typologie est impossible à fiabiliser |
| Navigation | Tout part d'un projet (Comparer) ou d'une constructibilité (Programmer) ; la typologie n'est qu'un filtre de similarité | Pas de réponse directe à « montre-moi les ratios des projets de santé vaudois » |
| KPI | Pensés pour le logement (SUP par logement, mix, onglet Typologies, similarité par nombre de logements) ; vitrage rapporté à la façade totale ; « façade / SP » comme seule compacité | Les KPI clés de l'équipe ne sont pas tous là, et ceux du logement n'ont pas de sens pour un hôpital |
| Fiabilité | Fourchette SC / SP 8–30 % calée sur le logement | À vérifier sur les autres typologies |

### Phases ajoutées

| Phase | Contenu |
|---|---|
| 15 ✓ | **Identifier chaque projet.** Une fiche « Identité du projet » dans SIA Check : ID HRS, nom, canton, commune, catégorie d'ouvrage et type d'intervention (listes du gabarit MDP), phase, date. Obligatoire avant « Ajouter à la base », écrite dans `InfosProjet`. Les MDP déjà dans la base se complètent depuis l'accueil. Fin de la déduction automatique : une catégorie absente reste « Non identifiée » |
| 16 ✓ | **Sélectionner, puis lire les ratios.** Une barre de sélection commune à tout le dashboard (typologie, canton, type d'intervention ; plus tard phase, période, taille). Un onglet d'entrée « Ratios » : les KPI clés de la sélection en tête (n, ratio combiné, chaque projet sur la règle), puis les autres familles, et la liste des projets retenus. Comparer et Programmer cherchent leurs projets similaires **dans** la sélection |
| 17 | **Des KPI par typologie.** Ajout de « surface vitrée / surface pleine » et du coefficient de forme (définition à fixer). Les ratios propres au logement (par logement, mix, Typologies) ne s'affichent que pour le logement ; les autres typologies auront plus tard leurs unités (chambres, lits, postes de travail…), à définir avec l'équipe. Fourchette de fiabilité revue par typologie si besoin |

Décisions (27.10.2026) : ordre 15 → 16 → 17 ; l'identité des MDP déjà dans la base s'écrit **dans le MDP** (feuille `InfosProjet`), seule source de vérité ; la définition du coefficient de forme est demandée à l'équipe (ouvert).

### Indice de performance par projet

Pas de note unique pour l'instant : mélanger des ratios de sens différents dans un seul chiffre masquerait ce qui fait la différence. À la place, chaque projet sera **situé dans sa typologie** sur les KPI clés (rang ou quartile : « dans le meilleur quart pour SUP / SP »). Un indice composite pourra venir quand la base sera assez grande pour pondérer les KPI de façon défendable.

## 10. Façades et vitrages de Treegram (SFN, SRV) — 27.10.2026

### Ce que Treegram produit (relevé sur L'Orée)

Dans l'arbre des surfaces SIA, chaque niveau porte, juste après sa SPT, deux totaux **verticaux** avec leur géométrie :

| Code | Contenu | L'Orée (80 niveaux) | Géométrie (cache VWR) |
|---|---|---:|---|
| SFN | Façade du niveau : brute, nette, réservations (ouvertures), périmètre, hauteur | brute 30 138 m², nette 23 076 m², réservations 7 062 m² (brute = nette + réservations au m² près) | 71 niveaux |
| SRV | Toutes les vitres du niveau | 7 108 m² (écart aux réservations : 2,6 m² au plus par niveau) | 56 niveaux |

Un second jeu de 80 SRV (5 271 m²) existe dans un autre arbre de quantités Treegram (codes SFB2, SR, MIB…) : hors surfaces SIA, il est laissé de côté.

### Ce que l'outil en fait aujourd'hui

- **Fiabilisation** : la SFN est lue comme un total de niveau « ignoré » (rangé avec les codes maison), sans contrôle ni rendu propre ; **la SRV n'est pas lue du tout** (elle n'a pas de catégorie SIA). Le MDP exporte comme « surface vitrée » les réservations de la SFN.
- **Benchmark** : « Vitrage / façade » rapporte ces réservations à la façade brute ; aucun ratio vitrée / pleine.

### Décisions (27.10.2026)

- **Surface vitrée = SRV** (les vitres réelles, avec leur géométrie) ; les réservations de la SFN servent de contrôle de cohérence.
- **Surface pleine = façade brute − vitrée** : vitrée + pleine = façade.

### Phases

| Phase | Contenu |
|---|---|
| 17a ✓ | **Fiabilisation de l'enveloppe.** Lecture de la SRV de l'arbre SIA ; SFN et SRV dans une famille « Enveloppe » (surfaces verticales), hors des sommes horizontales ; calques et rendu 3D propres ; contrôles : brute = nette + réservations, SRV ≈ réservations, façade ≈ périmètre × hauteur brute, vitres ≤ façade, niveau hors-sol sans façade ; ratios d'enveloppe dans l'espace de revue ; MDP : « Surface vitrée » = SRV |
| 17b | **Enveloppe dans le benchmark.** KPI « Vitrée / pleine » et « Part vitrée » à la place du ratio provisoire ; KPI clés mis à jour ; coefficient de forme dès que sa définition est connue ; ratios propres au logement réservés au logement (reste de la phase 17) |
