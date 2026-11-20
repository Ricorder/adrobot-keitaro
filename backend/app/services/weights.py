"""Пересчёт долей офферов в потоке.

Правила взяты из демонстрации редактора:
 - при добавлении оффера веса пересчитываются так, чтобы в сумме было 100 % (4 оффера = по 25 %);
 - закреплённый (pinned) вес не меняется ни при каких операциях, остаток делится между
   остальными поровну;
 - оффер, помеченный на удаление, получает 0 % и в делении не участвует, но строка живёт
   в базе до Push KT.

Целые проценты: остаток от деления раздаётся по единице первым по стабильному порядку
(сначала закреплённые идут как есть, затем остальные по id), поэтому сумма всегда ровно 100.
"""

from __future__ import annotations

from dataclasses import dataclass


class WeightConflict(ValueError):
    """Закреплённые веса уже больше 100 % — пересчёт невозможен."""


@dataclass(frozen=True)
class OfferWeight:
    offer_id: int
    pinned: int | None = None
    removed: bool = False


def total_pinned(offers: list[OfferWeight]) -> int:
    return sum(o.pinned or 0 for o in offers if not o.removed and o.pinned is not None)


def recalculate(offers: list[OfferWeight]) -> dict[int, int]:
    """Возвращает долю для каждого оффера: offer_id -> share в процентах."""
    if total_pinned(offers) > 100:
        raise WeightConflict(f"сумма закреплённых весов {total_pinned(offers)} % больше 100 %")

    shares: dict[int, int] = {}
    active = [o for o in offers if not o.removed]
    removed = [o for o in offers if o.removed]

    for offer in removed:
        shares[offer.offer_id] = 0

    flexible = [o for o in active if o.pinned is None]
    for offer in active:
        if offer.pinned is not None:
            shares[offer.offer_id] = offer.pinned

    remaining = 100 - total_pinned(offers)
    if not flexible:
        return shares

    base, remainder = divmod(remaining, len(flexible))
    for index, offer in enumerate(sorted(flexible, key=lambda o: o.offer_id)):
        extra = 1 if index < remainder else 0
        shares[offer.offer_id] = base + extra
    return shares


def unassigned_percent(shares: dict[int, int]) -> int:
    """Сколько процентов потока никому не досталось.

    Возникает, когда закреплённый вес остался один (например, 25 %), а все свободные офферы
    удалены: менять закрепление мы не вправе, поэтому интерфейс обязан показать дырку, а не
    молча долить её до ста.
    """
    return max(0, 100 - sum(shares.values()))
