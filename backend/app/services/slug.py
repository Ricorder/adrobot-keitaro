"""Псевдоним кампании для URL: домен/АЛИАС в Keitaro должен быть ASCII.

Названия кампаний у маркетологов русские, поэтому транслитерируем, а не просим пользователя
придумывать латинское имя. Хвост из hex нужен, чтобы два одинаковых названия не столкнулись
в уникальный alias.
"""

from __future__ import annotations

import re
import secrets

TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_NON_LATIN = re.compile(r"[^a-z0-9]+")


def transliterate(text: str) -> str:
    out = []
    for char in text.lower():
        if char in TRANSLIT:
            out.append(TRANSLIT[char])
        else:
            out.append(char)
    return "".join(out)


def slugify(text: str, *, max_length: int = 40) -> str:
    slug = _NON_LATIN.sub("-", transliterate(text)).strip("-")
    return slug[:max_length].strip("-")


def make_alias(name: str, prefix: str) -> str:
    base = slugify(name) or "campaign"
    return f"{prefix}{base}-{secrets.token_hex(3)}"
