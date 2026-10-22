# L'Orée — que contient le code Treegram SUT ?

> **Décision du 22.10.2026.** SUT n'est pas reclassé en SUP/SUS. On l'accepte comme troisième sous-catégorie de la surface utile créée par Treegram : **règle personnalisée P1, SU = SUP + SUS + SUT** (`config.yaml > custom_rules`). La recherche ci-dessous reste la référence sur le contenu réel de SUT. La « mise en œuvre proposée » en fin de document (table de reclassement) n'est pas retenue.

> Recherche du 22.10.2026. Sources : plans d'exécution de l'architecte (Itten+Brechbühl, `Treegram/Projects/L OREE/pdf/*.pdf`, texte vectoriel et rendu visuel), appariés aux 47 surfaces SUT par l'aire et le niveau (`scripts/affectations_plans.py`), puis vérifiés à l'œil sur les plans.
> Détail surface par surface : `L_OREE_SUT.csv` (id Treegram, aire, local du plan, code SIA proposé, justification, confiance).

## Constat : SUT n'est pas « commerce »

Treegram donne aux 47 surfaces le même type `Commerce`, mais les plans montrent cinq affectations différentes :

| Bâtiment · niveau | Ce que dit le plan | Surface SUT |
|---|---|---:|
| E09 · N00 | 3 lots d'**activité** (Activité 1–4 + hall, « surface totale » 323 / 316 / 209 m²) et un lot de 59 m² | 908 m² |
| H16 · N00–N03 | **Bureaux** (Bureau 1–3, « surface totale » 205 et 239 m²) | 920 m² |
| G12 · N00–N03 | **École** : salles de classe de 82,5 m² (×2 par niveau), « salle dégagement » de 40 m², et un lot « Activités » de 194 m² au RDC | 972 m² |
| G12 · S01 | **UAPE** (accueil parascolaire) : salle UAPE, salle ACT/ACM, local sieste, salle des éducateurs, WC, économat | 237 m² |
| I14 · N00 | 5 lots **commerce / activité** (48 à 149 m²) et **leurs WC et réduits** (1,6 à 2,6 m², ×10) | 452 m² |
| I18 · N00 | Un **commerce** de 275 m² et **ses WC** (WC PMR 5,6 m², 2 WC de 2,9 m²) | 284 m² |

## Classement SIA 416 proposé

| Code | Surface | Surfaces | Pourquoi |
|---|---:|---:|---|
| **SUP** | 3 711,6 m² | 30 | Fonction principale de chaque lot ou de chaque usage : activité, commerce, bureau, enseignement, accueil parascolaire (SIA 416 §2.1.1.1, destination au sens strict) |
| **SUS** | 48,5 m² | 16 | WC, réduits et économat des lots non résidentiels : fonctions qui complètent la SUP (§2.1.1.2, « déterminée en fonction de la destination particulière ») |
| ? | 16,1 m² | 1 | G12 S01 : aucun local de 16 m² sur le plan en dehors du local sieste (le couloir de fuite fait 15 m², ce serait alors du SD) — à voir dans Treegram |

**Effet sur le contrôle.** Avec ce classement, les 13 niveaux qui sortent aujourd'hui en R1 ou R5 retombent dans la plage normale de surface de construction (11–16 %). La SUP du projet augmente d'environ 3 710 m².

## Ce qui reste à décider ou à confirmer

1. **Convention pour les sanitaires** *(décision)*. La SIA 416 ne tranche pas explicitement. Treegram classe les salles de bain des logements en SUP (types `PieceSecondaire_2/3/4PointsEau`), ce qui est cohérent avec l'exemple de logement de la norme. Pour les lots non résidentiels, la proposition est de classer les WC en SUS, comme le veut la pratique courante (ils complètent l'activité sans en être la fonction). Si l'on préfère une seule règle « sanitaires = SUP partout », ces 48,5 m² passent en SUP ; l'effet sur les contrôles est négligeable.
2. **« Salle dégagement » de l'école G12** (40 m², N01–N03) *(à confirmer)*. Dans une école, c'est d'ordinaire une salle de travail en groupe attenante aux classes, donc de la SUP. Si c'est en fait un couloir élargi, c'est du SD.
3. **Salle UAPE de G12 S01** (91 m²) *(à confirmer)*. Treegram en fait une seule surface, qui recouvre la salle (72 m²), la cuisine (7 m²) et le vestiaire (13 m²). Si le vestiaire est un local séparé, il faut le sortir en SUS.
4. **Pour Treegram** : renommer le type `Commerce` des surfaces SUT ; la catégorie n'a de sens que si elle porte l'affectation réelle. Mieux encore, classer directement en SUP/SUS.

## Mise en œuvre proposée dans sia-check

Plutôt qu'un alias global `SUT → SUP`, prévoir une **table de reclassement par surface** (ce CSV, une fois validé). Le moteur l'appliquerait avant les contrôles, en conservant le code d'origine pour la traçabilité (« SUT → SUP, plan : Salle de classe »). Les surfaces SUT absentes de la table resteraient ignorées et seraient signalées. Le script `scripts/affectations_plans.py` prépare cette table pour tout nouveau projet ; il reste à la valider à la main.
