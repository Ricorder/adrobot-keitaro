"""Защита от случайных иероглифов в русском тексте.

Проверка не теоретическая: во время работы над проектом в русские комментарии и строки
реально подставлялись иероглифы и латинские слова. Такие опечатки не ловятся ни компилятором,
ни читателем, но выглядят как подмена текста, поэтому проверяем все исходники.
"""

from pathlib import Path

CJK_RANGES = (
    (0x3040, 0x30FF),  # хирагана, катакана
    (0x4E00, 0x9FFF),  # идеограммы
    (0xAC00, 0xD7A3),  # кореянский слог
    (0x3400, 0x4DBF),  # расширение идеограмм
)

SOURCE_DIRS = ("app", "tests")


def is_cjk(char: str) -> bool:
    return any(low <= ord(char) <= high for low, high in CJK_RANGES)


def test_no_cjk_in_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for folder in SOURCE_DIRS:
        for file in sorted((root / folder).rglob("*.py")):
            for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
                bad = [char for char in line if is_cjk(char)]
                if bad:
                    offenders.append(f"{file.relative_to(root)}:{line_no}: {''.join(bad)}")

    assert not offenders, "иероглифы в русском тексте:\n" + "\n".join(offenders)
