import pytest
from collections import Counter

from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.data import load_data
from pog_engine.rules.cards import EVENT_HANDLERS, legal_card_actions
from pog_engine.rules.events.reinforcements import ReinforcementHandler, placement_spaces, reinforcement_unit_ids


REINFORCEMENTS = [card_id for card_id, card in load_data().cards.items()
                  if card["reinforcement_nation"]]


def action_state(card_id):
    state = create_game(seed=3)
    state["turn"] = 2
    state["phase"] = "ACTION"
    state["active_side"] = load_data().cards[card_id]["side"]
    state["decision"] = {"kind": "ACTION_PHASE", "actor": state["active_side"], "options": []}
    state["players"][state["active_side"]]["hand"].append(card_id)
    state["decision"]["options"] = legal_card_actions(state, state["active_side"])
    return state


@pytest.mark.parametrize("card_id", REINFORCEMENTS)
def test_all_reinforcement_cards_have_handler_and_unique_unused_units(card_id):
    assert card_id in EVENT_HANDLERS
    units = reinforcement_unit_ids(create_game(seed=3), card_id)
    assert len(units) == len(load_data().cards[card_id]["reinforcement_units"])
    assert len(units) == len(set(units))
    assert Counter(load_data().units[unit_id]["name"] for unit_id in units) == Counter(
        load_data().cards[card_id]["reinforcement_units"]
    )
    assert all(load_data().units[unit_id]["side"] == load_data().cards[card_id]["side"]
               for unit_id in units)


@pytest.mark.parametrize("card_id", REINFORCEMENTS)
def test_no_reinforcement_event_on_first_turn(card_id):
    state = action_state(card_id)
    state["turn"] = 1
    assert not EVENT_HANDLERS[card_id].can_play(state, card_id)


def test_event_opens_placement_window_and_places_army_and_corps():
    state = action_state("BRITISH_REINFORCEMENTS_BR_2")
    action = {"type": "PLAY_CARD", "actor": "AP", "card_id": "BRITISH_REINFORCEMENTS_BR_2", "mode": "EVENT"}
    assert action in generate_legal_actions(state)
    state = apply_action(state, action).state
    assert state["phase"] == "REINFORCEMENTS"
    assert state["players"]["AP"]["war_status"] == 1
    assert state["events"]["BRITISH_REINFORCEMENTS_BR_2"] == 2
    first = next(a for a in generate_legal_actions(state) if a.get("to") == "LONDON")
    state = apply_action(state, first).state
    reserve = next(a for a in generate_legal_actions(state) if a.get("to") == "AP_RESERVE_BOX")
    state = apply_action(state, reserve).state
    assert state["phase"] == "ACTION"
    assert state["active_side"] == "CP"
    assert state["units"][first["unit_id"]]["location"] == "LONDON"
    assert state["units"][reserve["unit_id"]]["location"] == "AP_RESERVE_BOX"


def test_near_east_army_placed_in_europe_cannot_later_enter_near_east():
    state = action_state("YUDENITCH_RU_REINFORCEMENTS")
    state = apply_action(state, {"type": "PLAY_CARD", "actor": "AP",
                                 "card_id": "YUDENITCH_RU_REINFORCEMENTS", "mode": "EVENT"}).state
    placement = {"type": "PLACE_REINFORCEMENT", "actor": "AP",
                 "unit_id": "RU_CAU_ARMY_1", "to": "PETROGRAD"}
    assert placement in generate_legal_actions(state)
    state = apply_action(state, placement).state

    assert "RU_CAU_ARMY_1" in state["flags"].get("ne_armies_placed_outside_neareast", [])


@pytest.mark.parametrize("card_id,unit_id,place", [
    ("ARMY_OF_THE_ORIENT_FR_REINFORCEMENTS", "FR_ORIENT_ARMY_1", "SALONIKA"),
    ("MEF_BR_REINFORCEMENTS", "BR_MEF_ARMY_1", "MEF1"),
])
def test_near_east_army_special_start_does_not_mark_it_as_placed_outside(card_id, unit_id, place):
    state = action_state(card_id)
    state["war_nations"]["TU"] = True
    if place == "SALONIKA":
        state["events"]["SALONIKA"] = 1
    state["decision"]["options"] = legal_card_actions(state, "AP")
    state = apply_action(state, {"type": "PLAY_CARD", "actor": "AP",
                                 "card_id": card_id, "mode": "EVENT"}).state
    placement = {"type": "PLACE_REINFORCEMENT", "actor": "AP", "unit_id": unit_id,
                 "to": place}
    assert placement in generate_legal_actions(state)
    state = apply_action(state, placement).state

    assert unit_id not in state["flags"].get("ne_armies_placed_outside_neareast", [])


def test_second_reinforcement_for_same_nation_is_disallowed_this_turn():
    state = action_state("BRITISH_REINFORCEMENTS_BR_1")
    state["flags"]["reinforced_this_turn"] = {"BR": 2}
    assert not EVENT_HANDLERS["BRITISH_REINFORCEMENTS_BR_1"].can_play(
        state, "BRITISH_REINFORCEMENTS_BR_1"
    )


def test_us_army_requires_over_there_and_french_port():
    state = action_state("USA_REINFORCEMENTS_US_1")
    assert not EVENT_HANDLERS["USA_REINFORCEMENTS_US_1"].can_play(state, "USA_REINFORCEMENTS_US_1")
    state["us_entry"] = 3
    state["war_nations"]["US"] = True
    assert EVENT_HANDLERS["USA_REINFORCEMENTS_US_1"].can_play(state, "USA_REINFORCEMENTS_US_1")


def test_unavailable_army_destination_blocks_event():
    state = action_state("FRENCH_REINFORCEMENTS_FR_10")
    state["spaces"]["PARIS"]["control"] = "CP"
    assert not EVENT_HANDLERS["FRENCH_REINFORCEMENTS_FR_10"].can_play(
        state, "FRENCH_REINFORCEMENTS_FR_10"
    )


def test_special_reinforcement_destinations():
    state = create_game(seed=3)
    assert {f"MEF{i}" for i in range(1, 5)} <= set(placement_spaces(state, "BR_MEF_ARMY_1"))
    assert placement_spaces(state, "BR_ANAC_CORPS_1") == ["ARABIA"]
    assert placement_spaces(state, "TU_SNC_CORPS_1") == ["LIBYA"]
    assert "SALONIKA" not in placement_spaces(state, "FR_ORIENT_ARMY_1")
    state["events"]["SALONIKA"] = 2
    assert "SALONIKA" in placement_spaces(state, "FR_ORIENT_ARMY_1")
    assert "ALEXANDRIA" not in placement_spaces(state, "BR_NE_ARMY_1")
    state["events"]["SINAI_PIPELINE"] = 2
    assert "ALEXANDRIA" in placement_spaces(state, "BR_NE_ARMY_1")


def test_mef_requires_turkey_and_us_reinforcements_obey_uboats():
    state = action_state("MEF_BR_REINFORCEMENTS")
    assert not EVENT_HANDLERS["MEF_BR_REINFORCEMENTS"].can_play(state, "MEF_BR_REINFORCEMENTS")
    state["war_nations"]["TU"] = True
    assert EVENT_HANDLERS["MEF_BR_REINFORCEMENTS"].can_play(state, "MEF_BR_REINFORCEMENTS")
    state = action_state("USA_REINFORCEMENTS_US_1")
    state["us_entry"] = 3
    state["war_nations"]["US"] = True
    state["events"]["U_BOATS_UNLEASHED"] = 6
    assert not EVENT_HANDLERS["USA_REINFORCEMENTS_US_1"].can_play(state, "USA_REINFORCEMENTS_US_1")
    state["events"]["CONVOY"] = 7
    assert EVENT_HANDLERS["USA_REINFORCEMENTS_US_1"].can_play(state, "USA_REINFORCEMENTS_US_1")


def test_new_mef_placement_reopens_captured_beachhead():
    state = create_game(seed=4)
    state["active_side"] = "AP"
    state["phase"] = "REINFORCEMENTS"
    state["war_nations"]["TU"] = True
    state["flags"]["mef_beachhead_captured"] = True
    state["reinforcements"] = {"card_id": "MEF_BR_REINFORCEMENTS",
                               "pending": ["BR_MEF_ARMY_1", "AUSC_CORPS_1"]}
    handler = ReinforcementHandler()
    choice = {"type": "PLACE_REINFORCEMENT", "actor": "AP",
              "unit_id": "BR_MEF_ARMY_1", "to": "MEF4"}

    handler.apply(state, choice)

    assert state["flags"]["mef_beachhead"] == "MEF4"
    assert state["flags"]["mef_beachhead_captured"] is False
