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
| 12 | Mon projet : positionnement face aux projets similaires, écarts en m² et CHF | Comparaison |
| 13 | Programmation inverse | Outil de faisabilité |
| 14 | Préparation web : hébergement, accès, mise à jour de la base | Hors V3 si besoin |

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
