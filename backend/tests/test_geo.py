import pytest

from app.services.geo import ISO_3166_ALPHA_2, normalize_geo


def test_list_is_complete_iso_3166_alpha_2() -> None:
    """249 кодов в официальном списке ISO 3166-1; проверка на число, а не «на глаз».

    Частичное молчание здесь опаснее падения: пропущенная страна означала бы, что легитимное
    гео отклоняется как опечатка.
    """
    assert len(ISO_3166_ALPHA_2) == 249
    assert len(set(ISO_3166_ALPHA_2)) == 249
    for code in ("RU", "AU", "PE", "RO", "MX", "US", "ZW"):
        assert code in ISO_3166_ALPHA_2


def test_normalize_accepts_lowercase_and_spaces() -> None:
    assert normalize_geo(" ru ") == "RU"
    assert normalize_geo("au") == "AU"


@pytest.mark.parametrize(
    ("raw", "expect"),
    [("Россия", "из двух букв"), ("RUS", "из двух букв"), ("XX", "ISO 3166"), ("", "из двух букв")],
)
def test_normalize_rejects_bad_input(raw: str, expect: str) -> None:
    with pytest.raises(ValueError, match=expect):
        normalize_geo(raw)
