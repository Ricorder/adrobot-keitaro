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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = ("backend/app", "backend/tests", "frontend/src")
SOURCE_FILES = ("README.md",)
SOURCE_PATTERNS = ("*.py", "*.ts", "*.tsx", "*.css", "*.html", "*.md")


def is_cjk(char: str) -> bool:
    return any(low <= ord(char) <= high for low, high in CJK_RANGES)


def _collect_files() -> list[Path]:
    files = [PROJECT_ROOT / name for name in SOURCE_FILES if (PROJECT_ROOT / name).exists()]
    for folder in SOURCE_DIRS:
        base = PROJECT_ROOT / folder
        if not base.is_dir():
            continue
        for pattern in SOURCE_PATTERNS:
            files.extend(sorted(base.rglob(pattern)))
    return files


def test_no_cjk_in_sources() -> None:
    offenders: list[str] = []

    for file in _collect_files():
        for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
            bad = [char for char in line if is_cjk(char)]
            if bad:
                rel = file.relative_to(PROJECT_ROOT)
                offenders.append(f"{rel}:{line_no}: {''.join(bad)}")

    assert offenders == [], "иероглифы в русском тексте:\n" + "\n".join(offenders)


def test_hygiene_actually_scans_something() -> None:
    """Без этой проверки тест мог бы тихо перестать видеть файлы после переезда каталогов."""
    found = _collect_files()
    assert len(found) > 30, f"гигиена текста сканирует только {len(found)} файлов"
    assert any(f.name == "README.md" for f in found), "README не попадает в проверку"
