import json

import pytest

from pog_engine import create_game


def test_historical_opening_has_units_vp_trenches_and_hands():
    state = create_game(seed=7)

    assert state["scenario"] == "HISTORICAL"
    assert state["turn"] == 1
    assert state["action_round"] == 1
    assert state["vp"] == 10
    assert state["units"]["GE_1_ARMY_1"]["location"] == "AACHEN"
    assert state["spaces"]["STRASBOURG"]["trenches"]["CP"] == 1
    assert state["spaces"]["BRUSSELS"]["trenches"]["AP"] == 0
    assert len(state["players"]["AP"]["hand"]) == 8
    assert len(state["players"]["CP"]["hand"]) == 8
    assert "GUNS_OF_AUGUST" in state["players"]["CP"]["hand"]
    assert sum(unit["location"] is not None for unit in state["units"].values()) == 112


def test_historical_opening_has_uncaptured_mef1_beachhead():
    state = create_game(seed=7)

    assert state["flags"]["mef_beachhead"] == "MEF1"
    assert state["flags"]["mef_beachhead_captured"] is False


def test_decks_contain_each_base_card_once_and_exclude_later_commitments():
    state = create_game(seed=7)
    zones = [
        card
        for side in ("AP", "CP")
        for zone in ("hand", "deck", "set_aside")
        for card in state["players"][side][zone]
    ]
    assert len(zones) == len(set(zones)) == 110
    assert "GUNS_OF_AUGUST" not in state["players"]["CP"]["deck"]
    assert state["players"]["CP"]["commitment"] == "MOBILIZATION"


def test_seeded_setup_repeats_and_can_be_serialized():
    first = create_game(seed=7)
    again = create_game(seed=7)
    other = create_game(seed=8)

    assert first == again
    assert first["players"]["AP"]["deck"] != other["players"]["AP"]["deck"]
    assert json.loads(json.dumps(first)) == first
    assert first["decision"]["actor"] == "CHANCE"
    assert first["decision"]["kind"] == "MANDATORY_OFFENSIVE_ROLL"


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="시나리오"):
        create_game(scenario="THE_GREAT_WAR")
