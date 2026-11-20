import pytest

from app.services.weights import (
    OfferWeight,
    WeightConflict,
    recalculate,
    total_pinned,
    unassigned_percent,
)


def shares(*ids: int) -> list[OfferWeight]:
    return [OfferWeight(offer_id=i) for i in ids]


def test_four_offers_get_quarter_each() -> None:
    """Ровно тот случай, который показан в демонстрации: 4 оффера = по 25 %."""
    result = recalculate(shares(1, 2, 3, 4))
    assert result == {1: 25, 2: 25, 3: 25, 4: 25}
    assert sum(result.values()) == 100


def test_adding_offer_rebalances_everyone() -> None:
    result = recalculate(shares(1, 2, 3, 4, 5))
    assert list(result.values()) == [20, 20, 20, 20, 20]


def test_removing_offer_redistributes_without_leftovers() -> None:
    """3 свободных оффера: 100 не делится нацело, остаток раздается по единице первым."""
    result = recalculate(shares(1, 2, 3))
    assert sorted(result.values(), reverse=True) == [34, 33, 33]
    assert sum(result.values()) == 100


def test_removed_offer_is_zero_and_out_of_division() -> None:
    offers = [OfferWeight(1), OfferWeight(2), OfferWeight(3, removed=True)]
    result = recalculate(offers)
    assert result == {1: 50, 2: 50, 3: 0}


def test_pinned_weight_survives_add_and_remove() -> None:
    """Из демонстрации: закрепленные 25 % остаются 25 %, остальные делят остаток поровну."""
    offers = [OfferWeight(1, pinned=25), OfferWeight(2), OfferWeight(3), OfferWeight(4)]
    result = recalculate(offers)
    assert result[1] == 25
    assert sum(result[o.offer_id] for o in offers if o.pinned is None) == 75

    offers.append(OfferWeight(5))
    result = recalculate(offers)
    assert result[1] == 25
    assert sum(result.values()) == 100


def test_pinned_one_and_no_flexible_leaves_a_gap() -> None:
    offers = [OfferWeight(1, pinned=25), OfferWeight(2, removed=True)]
    result = recalculate(offers)
    assert result == {1: 25, 2: 0}
    assert unassigned_percent(result) == 75


def test_all_pinned_to_hundred_is_valid() -> None:
    offers = [OfferWeight(1, pinned=70), OfferWeight(2, pinned=30)]
    assert recalculate(offers) == {1: 70, 2: 30}


def test_conflicting_pins_are_rejected() -> None:
    offers = [OfferWeight(1, pinned=70), OfferWeight(2, pinned=60)]
    assert total_pinned(offers) == 130
    with pytest.raises(WeightConflict, match="130"):
        recalculate(offers)


def test_empty_flow_has_no_shares() -> None:
    assert recalculate([]) == {}
