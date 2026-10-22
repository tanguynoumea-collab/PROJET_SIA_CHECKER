"""Décodeur des sacs de propriétés d'un projet Treegram `.tgm` (format binaire non documenté).

Structure observée (rétro-ingénierie sur L'Orée, Treegram juin 2026 — docs/ifc-schema.md §2.2) :

    int32 nprops
    nprops × ( int32 len, nom UTF-8, tag 4 octets [x 00 00 T], valeur, 00 00 00 00 )
        T = 02 : chaîne  -> int32 len + UTF-8
        T = 04 : double  -> 8 octets little-endian
        T = 08 : int32   -> 4 octets little-endian
        x vaut T ou 0 ; seul T fait foi.
    int64 len, nom de l'élément UTF-8

Chaque sac est précédé (à moins de 200 octets) d'un en-tête d'enregistrement contenant
l'identifiant du conteneur et l'identifiant interne de l'élément :
`<int32 conteneur> 04 <int32 id> 04 01 00×7`. L'identifiant est celui que référencent les géométries
du cache VWR (geom.py) ; le couple donne l'« ID TGM » des exports Excel Treegram,
`H<conteneur>::H<id>` (ex. `H170::H2527` sur L'Orée, dont les surfaces SIA sont toutes dans le
conteneur 170).

Chaque sac est repéré en balayant le fichier à la recherche d'un compteur plausible
suivi d'une propriété décodable. Le format pouvant changer avec Treegram, toute
incohérence fait rejeter le sac plutôt que d'interpréter des octets au hasard.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Iterator

STR, DBL, INT = 0x02, 0x04, 0x08
NAME_RE = re.compile(rb"[\x20-\x7e\xc2-\xf4][\x20-\x7e\x80-\xbf\xc2-\xf4]{0,80}")
BAG_START_RE = re.compile(rb"[\x01-\x3c]\x00\x00\x00[\x01-\x50]\x00\x00\x00")
# Les 7 octets nuls qui suivent distinguent l'en-tête des références `<int32> 04 <int32> 04 01 00 00 00 01`
# qui le suivent dans l'enregistrement.
RECORD_ID_RE = re.compile(rb"(....)\x04(....)\x04\x01\x00\x00\x00\x00\x00\x00\x00", re.S)
MAX_PROPS, MAX_PROP_NAME, MAX_STR, MAX_ELEMENT_NAME = 60, 80, 4096, 200
RECORD_HEADER_WINDOW = 200


@dataclass(frozen=True)
class Bag:
    offset: int
    name: str
    props: dict[str, object]
    element_id: int | None = None  # identifiant interne Treegram (lien vers la géométrie)
    container_id: int | None = None

    @property
    def tgm_id(self) -> str | None:
        """Identifiant des exports Excel Treegram (colonne « ID TGM »)."""
        if self.element_id is None or self.container_id is None:
            return None
        return f"H{self.container_id}::H{self.element_id}"


def _record_ids(b: bytes, start: int) -> tuple[int | None, int | None]:
    """(conteneur, élément) du dernier en-tête d'enregistrement avant le sac."""
    window = b[max(0, start - RECORD_HEADER_WINDOW) : start]
    last = None
    for last in RECORD_ID_RE.finditer(window):
        pass
    if last is None:
        return None, None
    return struct.unpack("<i", last.group(1))[0], struct.unpack("<i", last.group(2))[0]


def _prop(b: bytes, i: int) -> tuple[str, object, int] | None:
    if i + 8 > len(b):
        return None
    (ln,) = struct.unpack_from("<i", b, i)
    if not 1 <= ln <= MAX_PROP_NAME:
        return None
    name = b[i + 4 : i + 4 + ln]
    if not NAME_RE.fullmatch(name):
        return None
    j = i + 4 + ln
    tag = b[j : j + 4]
    if len(tag) < 4 or tag[1:3] != b"\x00\x00" or tag[0] not in (0, tag[3]):
        return None
    j += 4
    kind = tag[3]
    if kind == STR:
        (sl,) = struct.unpack_from("<i", b, j)
        if not 0 <= sl <= MAX_STR:
            return None
        val: object = b[j + 4 : j + 4 + sl].decode("utf-8", "replace")
        j += 4 + sl
    elif kind == DBL:
        (val,) = struct.unpack_from("<d", b, j)
        j += 8
    elif kind == INT:
        (val,) = struct.unpack_from("<i", b, j)
        j += 4
    else:
        return None
    if b[j : j + 4] != b"\x00\x00\x00\x00":
        return None
    return name.decode("utf-8", "replace"), val, j + 4


def read_bag(b: bytes, start: int) -> tuple[Bag, int] | None:
    """Lit un sac commençant au compteur `start` ; renvoie (sac, offset de fin) ou None."""
    if start + 4 > len(b):
        return None
    (n,) = struct.unpack_from("<i", b, start)
    if not 1 <= n <= MAX_PROPS:
        return None
    i, props = start + 4, {}
    for _ in range(n):
        p = _prop(b, i)
        if p is None:
            return None
        props[p[0]], i = p[1], p[2]
    if i + 8 > len(b):
        return None
    (nl,) = struct.unpack_from("<q", b, i)
    if not 0 < nl <= MAX_ELEMENT_NAME:
        return None
    name = b[i + 8 : i + 8 + nl]
    if not NAME_RE.fullmatch(name):
        return None
    container, element = _record_ids(b, start)
    return Bag(start, name.decode("utf-8", "replace"), props, element, container), i + 8 + nl


def scan(b: bytes) -> Iterator[Bag]:
    """Tous les sacs du fichier, dans l'ordre du fichier."""
    end = 0
    for m in BAG_START_RE.finditer(b):
        if m.start() < end:
            continue
        r = read_bag(b, m.start())
        if r:
            yield r[0]
            end = r[1]
