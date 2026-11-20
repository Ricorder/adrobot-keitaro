"""Валидация гео-кода.

У Keitaro нет эндпоинта со списком стран (в OpenAPI 87 путей такого нет), а фильтр страны
принимает ISO 3166-1 alpha-2. Если передать опечатку, трекер не ошибётся: созданётся поток,
который никогда ни с кем не совпадёт, и кампания начнёт лить не туда.

Список сгенерирован из набора ISO 3166-1 alpha-2 (249 кодов) и лежит в коде специально:
проверка не должна зависеть от сети. Если список стал неполным, это ловит тест
tests/test_geo.py по количеству и по контрольным странам.
"""

from __future__ import annotations

import re

_ISO_3166_CHUNKS = (
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA",
    "BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV",
    "BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU",
    "CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES",
    "ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM",
    "GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE",
    "IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM",
    "KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY",
    "MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT",
    "MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU",
    "NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA",
    "RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM",
    "SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL",
    "TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE",
    "VG VI VN VU WF WS YE YT ZA ZM ZW",
)

ISO_3166_ALPHA_2: list[str] = sorted(c for chunk in _ISO_3166_CHUNKS for c in chunk.split())
_ALLOWED = frozenset(ISO_3166_ALPHA_2)
_PATTERN = re.compile(r"^[A-Za-z]{2}$")


def normalize_geo(raw: str) -> str:
    """Возвращает ISO2 в верхнем регистре или объясняет, что не так."""
    value = raw.strip().upper()
    if not _PATTERN.match(value):
        raise ValueError(f"гео-код должен быть из двух букв (RU, AU, MX), получено: {raw!r}")
    if value not in _ALLOWED:
        raise ValueError(f"неизвестный код страны ISO 3166-1 alpha-2: {value}")
    return value
