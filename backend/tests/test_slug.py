from app.services.slug import make_alias, slugify, transliterate


def test_transliterates_russian_names_in_lowercase() -> None:
    # alias участвует в URL, поэтому регистр снижаем сразу на транслитерации;
    # по нашей таблице щ = sch, ж = zh, ч = ch (бытовая транслитерация, не ГОСТ)
    assert transliterate("Осень в Москве") == "osen v moskve"
    assert transliterate("Жук щук чашка") == "zhuk schuk chashka"


def test_slug_drops_punctuation_and_limits_length() -> None:
    assert slugify("  Кампания #2026: старт!  ") == "kampaniya-2026-start"
    assert len(slugify("а" * 200, max_length=40)) == 40


def test_alias_is_ascii_and_prefixed() -> None:
    alias = make_alias("Осень PE", "kolesnikov-")
    assert alias.startswith("kolesnikov-osen-pe-")
    assert alias.isascii()


def test_prefix_is_not_doubled_when_name_already_starts_with_it() -> None:
    """Живой случай: кандидат пишет название с префиксом, alias не должен сдвоить его."""
    alias = make_alias("kolesnikov-live", "kolesnikov-")
    assert not alias.startswith("kolesnikov-kolesnikov")
    assert alias.startswith("kolesnikov-live-")
