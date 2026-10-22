# Schéma des données de surfaces Treegram — phase 0

> **Statut : validé le 21.10.2026.** Projet de référence : L'Orée (`OneDrive…\Documents\Treegram\Projects\L OREE`).
> Décisions : lecteur double `.tgm` + `.ifc` ; SUT ignoré comme le prévoit le brief (les RDC à commerces sortent en R1, I18 N00 en R5).

## 0. Résumé

- **Il n'existe pas d'IFC de surfaces SIA pour L'Orée.** Les deux IFC exportés par Treegram (`Exports/L OREE - Export Surfaces.ifc` et `… Surfaces Carbone.ifc`, du 10.06.2026) portent les nomenclatures *promoteur* et *carbone*, pas la SIA 416 (§2.1). Les surfaces SIA ont été créées le 11.06 par l'action `BOOMER :: Create : SIA Surfaces` et n'ont jamais été exportées.
- **Les surfaces SIA existent dans le fichier projet `L OREE.tgm`** (format binaire Treegram non documenté, non compressé, 97 Mo). Le format a été décodé (§2.2) : **6 090 / 6 090** surfaces portant `Catégorie SIA` ont été extraites, en 3 s.
- Les compteurs du viewer sont retrouvés : **80 SP, 80 SEP**, soit 1 nœud par code et par niveau sur 9 bâtiments et 80 niveaux.
- Les trois anomalies connues ressortent d'un calcul exploratoire (§5).

## 1. Rappels normatifs utiles aux règles

Sources : `docs/reference/SIA-Reader - 416_2003_dfiSIA.srd.pdf` (texte français p. 17–30) et `docs/reference/USPI Calcul surface appartement PPE 20140830 (3).pdf`.

| Chiffre | Contenu | Conséquence pour l'outil |
| --- | --- | --- |
| SIA 416 §0.4 | Surfaces horizontales en dimensions effectives, surfaces obliques en **projection verticale**, décomposition **par niveau**. | Sommations par niveau. |
| SIA 416 §2 | SP = SN + SC. Espaces accessibles **fermés de toute part**. | R1. |
| SIA 416 §2.1 | SN = SU + SD + SI. | R1 (SN absente : on somme les feuilles). |
| SIA 416 §2.1.1 | SU = SUP + SUS. SUP = fonctions « au sens strict » de la destination. | R2, R5. |
| SIA 416 §2.2 | SC = SCP + SCN. | SC absente : résidu R1 attendu ≈ SC (« SC implicite »). |
| SIA 416 §3 | SEP = SEN + SEC : balcons, terrasses, terrasses de combles, toitures-jardins, garages ouverts, **pour autant qu'ils ne communiquent pas directement avec la surface des abords ; sinon SA (§1.2)**. | R3. Fonde l'alerte A1. |
| SIA 416 §3.1 | SEN = SEU + SED + SEI. | R3. |
| SIA 416 §3.2 | SEC = SECP + SECN. | |
| SIA 416 §1 | ST = SB + SA ; SA = SAA + SAN. | Catégories prévues en config, absentes. |
| USPI 2014 p. 4 | SH = SNH + SCI ; SBH = SH + MEM ; SVB = SBH + SE ; SVN = SH + SE. | SVB − SVN = MEM ; SHA ≥ SNH, SBH ≥ SHA, SVB ≥ SVN. |

Une toiture **non accessible** n'entre ni dans SP (elle n'est pas fermée) ni dans SEP (§3 ne vise que des espaces utilisables). C'est le fondement de l'alerte A2.

## 2. Où sont les données

### 2.1 Les IFC exportés : pas de SIA

`Exports/L OREE - Export Surfaces.ifc` : IFC2X3, `Treegram Export IFC Advanced 2.7.1.0` (Xbim). L'inventaire complet est dans `docs/inventaire_loree.md`.

- Spatial : `IfcSite` → 9 `IfcBuilding` (A01, B03, B04, E09, G12, H16, I14, I17, I18) → 80 `IfcBuildingStorey` (S03…N07, Toiture), sans `Elevation`.
- Par niveau : 11 `IfcSlab`, 1 `IfcWall`, 1 `IfcWindow`. La catégorie est dans **`Name`**, l'aire dans le Pset **`Treegram`** (`Area`, `GrossArea`).
- Codes : `SHAB, SHO, SHOB, SHOBh, ST, SDP, SUext, SUbl, SUt, SUc, PARK` (slabs), `SFB` (wall), `SRV` (window). C'est la nomenclature française promoteur ; `ST` y est la surface taxable, pas la surface de terrain SIA.
- Export Carbone : `SCC2, TER, BLC, PAF, SPIN` (slabs), `SFB2, SFN, MIB, MIN` (walls), `SR` (window).

Si Treegram exporte un jour la nomenclature SIA, on peut supposer le même encodage (`Name` = code, Pset `Treegram.Area`, une entité par code et par niveau). **Dans ce cas, l'IFC ne contiendrait que les totaux par niveau, sans le détail par pièce.**

### 2.2 Le fichier projet `.tgm` : la source SIA

Décodeur exploratoire : `scripts/tgm_dump.py`. Chaque élément du `.tgm` porte un sac de propriétés :

```
int32 nprops
nprops × ( int32 len, nom UTF-8, tag 4 octets [x 00 00 T], valeur, 00 00 00 00 )
     T=02 chaîne (int32 len + UTF-8) · T=04 double · T=08 int32
int64 len, nom de l'élément UTF-8
```

Exemple réel (élément élémentaire) :

```
Catégorie SIA = "SUP"   Area = 55.71   Type = "PieceDeVie"   ApartmentByTgm = "E09_N03_Apart-01"
nom : E09_N03_ShellByTgm-10_SpaceByTgm-3_SUP
```

L'arbre SIA a deux étages.

**a) Nœuds agrégés : un par code et par niveau, 17 codes × 80 niveaux.**
Ils sont nommés uniquement par le code (`SP`, `SUP`…), dans un ordre fixe : `SFN, SRV, SUP, SUS, SD, SED, SI, SUT, SEU, SNH, SHA, SBH, SVN, SVB, SP, SEP, SPT`. Ils portent `Area`, sauf `SFN` qui porte `GrossArea`, `NetArea`, `Perimeter` et `GrossHeight`.
**SP et SEP n'existent qu'à cet étage** : il n'y a aucune surface élémentaire SP ou SEP. Le nom du nœud ne contient ni bâtiment ni niveau. On les rattache par l'ordre du fichier : chaque bloc commence par `SFN`, et le niveau est celui des enfants du bloc. Les 80 blocs sont résolus sans ambiguïté.

**b) Surfaces élémentaires (4 890).**
- Bâtiment et niveau : **préfixe du nom** (`E09_N03_…`). C'est fiable, alors que l'ordre du fichier ne l'est pas : les éléments modifiés après coup sont ajoutés en fin de fichier (16 balcons SEU modifiés le 19.06.2026 ; chaque sac est précédé de deux horodatages .NET, création et modification).
- Catégorie : propriété `Catégorie SIA`, identique au suffixe du nom dans 100 % des cas.
- Aire : `Area` (m²).
- Trois familles de noms :

| Motif | Catégories | Remarque |
| --- | --- | --- |
| `Bât_Niv_ShellByTgm-n_SpaceByTgm-m_CODE` | SUP, SUS, SD, SI, SUT | espaces intérieurs |
| `Bât_Niv_ExtShellByTgm-n_CODE` | SEU, SED, SPT | espaces extérieurs |
| `Bât_Niv_Apart-n_CODE` | SNH, SHA, SBH, SVN, SVB | chaîne USPI **par lot** |

Pour chaque nœud qui a des enfants, `aire du nœud = Σ enfants` à 0,05 m² près, avec les exceptions listées au §4.

### 2.3 Autres fichiers examinés

- `DB/*.db3` (SQLite) : seulement le journal des actions Treegram (`ProdAction`, `Association`), sans valeurs de surfaces.
- `Cache/Trees/*.json` : arbres datés du 09.06, antérieurs aux surfaces SIA.
- `VWR/**/*.3drtgm` : géométries binaires du viewer ; seules les `*-SiaSurface*` sont décodées (§2.4).

### 2.4 Géométrie des surfaces SIA (cache du viewer) — ajout du 21.10.2026

Le viewer Treegram met en cache, par niveau, les maillages des surfaces SIA :
`VWR/<dossier>/_Data/<Bât>_<Niv>-SiaSurface.3drtgm`, plus des variantes `…SiaSurface1/2.3drtgm`. Il y a 80 jeux pour L'Orée. Le décodeur est `src/sia_check/geom.py`, où le format est détaillé.

- **Lien surface → maillage** : chaque objet du fichier porte l'identifiant interne de l'élément du `.tgm`. Cet identifiant se lit dans l'en-tête d'enregistrement qui précède chaque sac de propriétés : `<int32 conteneur> 04 <int32 id> 04 01 00×7` (`tgm.Bag.element_id`, `container_id`). Le couple forme l'« ID TGM » des exports Excel Treegram, `H<conteneur>::H<id>` (L'Orée : conteneur 170 pour toutes les surfaces SIA).
- **Couverture L'Orée** :
  - 4 890 / 4 890 surfaces élémentaires ont une géométrie ;
  - 707 / 1 200 totaux de niveau en ont une ;
  - les totaux sans géométrie sont d'aire nulle ;
  - 8 832 maillages, aucun octet non décodé.
- **Coordonnées** : en mètres, dans le repère du projet. Les altitudes sont cohérentes : S01 −3,62, N00 0,02, N01 3,17… N07 20,21.
- **Limite** : le cache n'est régénéré que lorsque le projet est ouvert dans le viewer Treegram. Pour L'Orée, le cache date du 11.06 et le `.tgm` du 19.06 : la visionneuse le signale (« cache 3D antérieur au projet »).

## 3. Réponses aux questions du brief (§4 et §11)

| Question | Réponse | Exemple |
| --- | --- | --- |
| Format | **`.tgm` binaire** (pas d'IFC SIA disponible) | |
| Où est la catégorie | Propriété `Catégorie SIA` ; suffixe du nom | `…_SpaceByTgm-3_SUP` |
| Subdivision « par pièce » de SUP | **Oui**, propriété `Type` : `PieceDeVie` 314, `Chambre` 620, `PieceSecondaire_{2,3,4}PointsEau` 514, `Distribution` 27 | |
| `Type` des autres codes | SD : `Ascenseur`, `CirculationH`, `Escalier` ; SI : `Gaine`, `Local` ; SEU : `Balcon`, `Terrasse` ; SED : `CirculationExt` ; SUT : `Commerce` ; SPT : `Toiture` | |
| Aire | Propriété `Area`. Nette ou brute : **non précisé** par Treegram | |
| Niveau / bâtiment | Préfixe du nom pour les éléments, bloc du fichier pour les nœuds | `A01_N00` |
| GlobalId de l'IfcSpace source | **Pas trouvé.** Les identifiants sont internes (`ShellByTgm-n`, `SpaceByTgm-m`). Le lien vers l'IFC architecte est à chercher en phase 2 | |
| Identifiant de lot USPI | **Oui** : `Apart-n` dans le nom, propriété `ApartmentByTgm`, et `Bedrooms` sur SNH | `A01_N00_Apart-02_SNH` |
| Aire déclarée vs géométrie | Impossible à vérifier pour l'instant (`.3drtgm` non décodé). **L'aire déclarée fait foi** | |

### Codes « maison » : sens déduit du contenu (à confirmer avec Treegram)

| Code | Contenu observé | Hypothèse | Traitement proposé |
| --- | --- | --- | --- |
| **SUT** | 47 surfaces `Type = Commerce`, 3 776 m², surtout aux N00 | surface utile « tertiaire » / commerces | **À décider** (voir §6) |
| **SPT** | 25 surfaces `ExtShellByTgm`, `Type = Toiture`, 7 279 m² (attiques et niveaux Toiture) | surfaces de toiture | hors SEP, sert à A2 |
| **SFN** | nœuds `GrossArea` 30 138 m² ; `IfcWall` dans l'export carbone | surface de façade nette | ignorer (pas une surface de plancher) |
| **SRV** | nœuds 7 108 m² ; `IfcWindow` dans les exports | surface de vitrage | ignorer |

## 4. Incohérences internes déjà visibles

1. ~~**SEU : le nœud dépasse la somme de ses enfants**~~ — **affirmation retirée le 22.10.2026.** L'écart venait de la première version du décodeur, qui ne lisait pas les 16 balcons modifiés le 19.06 (variante de tag de chaîne). Depuis la correction, le total SEU égale la somme du détail sur tous les niveaux.
2. **USPI : les totaux SBH, SVN et SVB du niveau dépassent la somme des lots** de 5 à 39 m², sur presque tous les niveaux d'habitation. Pour SHA, l'écart est inférieur à 2 m², dans l'autre sens.
3. **Le nœud SNH vaut SUP + SUS du niveau**, alors que la somme des lots SNH vaut SUP seule : le SUS commun (caves, etc.) entre dans le total SNH.

Ces trois points sortent du périmètre des règles R1 à R5. Ils se prêtent à une règle de cohérence « nœud = Σ enfants », bon marché à ajouter.

## 5. Calcul exploratoire (non contractuel)

Totaux : **SP 56 210,1 m², SEP 17 820,1 m²** (80 nœuds chacun).

- **R1** (SP − SUP − SUS − SD − SI) : résidu stable de **14 à 18 % aux étages et de 4 à 9 % aux sous-sols**, cohérent avec une « SC implicite ». Sur les RDC à commerces, le résidu monte à 72–89 % (E09, G12, H16 N00–N03, I14, I18 N00) **si l'on ignore SUT**. En comptant SUT, plus aucun niveau ne dépasse 20 %.
- **R3 + A1** : SEP du N00 très peu sous-classifiée, par exemple B03 1 962 m² de SEP pour 149 m² de SEU + SED, ou E09 1 863 m² pour 124 m². Ce sont les abords, qui relèvent de SA.
- **R3 + A2** : de la SEP sur tous les niveaux `Toiture` (sans SP), et une forte SEP non classée sur les attiques (N05, N07). Elle recouvre les surfaces SPT.

## 6. Décisions à prendre avant la phase 1

1. **Source de données.** Il y a trois options : un reader `.tgm` (format propriétaire, cassable à chaque version de Treegram), attendre un export IFC SIA de Treegram, ou les deux. **Proposition : les deux.** On définit une interface `reader` qui produit le DataFrame normalisé, avec un backend `tgm` maintenant et un backend `ifc` quand l'export existera. Les règles ne voient que le DataFrame, comme le prévoit le brief.
2. **SUT (commerces).** Selon SIA 416 §2.1.1.1, un commerce est de la **SUP** dès lors que c'est la destination de l'immeuble. Faut-il l'additionner dans R1 et R2 (alias de SUP), ou l'ignorer comme le prévoit le brief, ce qui fait sortir 7 RDC en R1/R5 ?
3. **Quelle est l'anomalie « niveau avec SP sans SU » connue ?** Avec SUT ignoré, 7 niveaux sortent ; avec SUT compté, aucun. Il faut savoir quel niveau a été vu dans le viewer.
4. **SPT** : à exclure de SEP et à utiliser comme indice pour A2 ?
5. **Collision de code `ST`** : dans l'export IFC promoteur, `ST` désigne la surface taxable française, alors qu'en SIA 416 §1 c'est la surface de terrain. Lu avec la config SIA, cet IFC déclenche donc un contrôle R0 sur ST. Pas d'impact sur le `.tgm` (aucun ST), mais une config par nomenclature sera nécessaire si l'on contrôle aussi les exports promoteur.

## Annexe — reproduire

```bash
.venv/Scripts/python -I scripts/tgm_dump.py "…/L OREE/L OREE.tgm" surfaces.csv
.venv/Scripts/python -I scripts/inspect_ifc.py "…/Exports/L OREE - Export Surfaces.ifc" > docs/inventaire_loree.md
```
