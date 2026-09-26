import copy

import pytest

from pog_engine.data import load_data, validate_data


def test_base_card_and_unit_ids_are_complete_and_unique():
    data = load_data()
    assert len(data.cards) == 110
    assert len(data.units) == 193
    assert "GUNS_OF_AUGUST" in data.cards
    assert "GE_1_ARMY_1" in data.units
    assert all(card_id == card["id"] for card_id, card in data.cards.items())
    assert all(unit_id == unit["id"] for unit_id, unit in data.units.items())


def test_map_spaces_and_restricted_connections():
    data = load_data()
    assert sum(space["kind"] == "BOARD" for space in data.spaces.values()) == 281
    assert sum(space["kind"] == "BOX" for space in data.spaces.values()) == 80
    assert "CALAIS" in data.neighbors("LONDON", "BR")
    assert "CALAIS" not in data.neighbors("LONDON", "GE")
    assert "LONDON" in data.neighbors("CALAIS", "BR")
    assert "LONDON" not in data.neighbors("CALAIS", "GE")


def test_historical_setup_references_resolve():
    data = load_data()
    assert data.historical["vp"] == 10
    assert len(data.historical["placements"]) == 80
    for placement in data.historical["placements"]:
        assert placement["unit_id"] in data.units
        assert placement["space_id"] in data.spaces
    validate_data(data)


def test_invalid_data_reference_is_rejected():
    data = copy.deepcopy(load_data())
    data.historical["placements"][0]["space_id"] = "MISSING_SPACE"
    with pytest.raises(ValueError, match="MISSING_SPACE"):
        validate_data(data)
