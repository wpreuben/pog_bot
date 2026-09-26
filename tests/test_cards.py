import copy

import pytest

from pog_engine import IllegalActionError, apply_action, create_game, generate_legal_actions
from pog_engine.rules.cards import discard_combat_cards, draw_to_hand, legal_card_actions
from pog_engine.rules.turn import complete_action
from pog_engine.data import load_data


def rolled(state, value):
    purpose = state["decision"]["purpose"]
    return apply_action(state, {"type": "RECORD_DIE_RESULT", "actor": "CHANCE", "purpose": purpose, "value": value}).state


def ap_action_state():
    state = rolled(rolled(create_game(seed=4), 1), 5)
    state = apply_action(
        state, {"type": "PLAY_CARD", "actor": "CP", "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"}
    ).state
    return apply_action(state, {"type": "END_COMBAT", "actor": "CP"}).state


def test_first_event_removes_guns_and_passes_action_to_ap():
    state = ap_action_state()
    assert "GUNS_OF_AUGUST" in state["players"]["CP"]["removed"]
    assert "GUNS_OF_AUGUST" not in state["players"]["CP"]["hand"]
    assert state["players"]["CP"]["war_status"] == 2
    assert state["active_side"] == "AP"
    assert state["action_round"] == 1


def test_card_modes_require_ownership_and_combat_card_event_is_unavailable():
    state = ap_action_state()
    actions = legal_card_actions(state, "AP")
    assert any(action["mode"] == "OPS" for action in actions)
    assert any(action["mode"] == "SR" for action in actions)
    assert any(action["mode"] == "RP" for action in actions)
    assert all(action["card_id"] in state["players"]["AP"]["hand"] for action in actions)
    assert all(not load_data().cards[action["card_id"]]["combat_card"]
               for action in actions if action["mode"] == "EVENT")

    before = copy.deepcopy(state)
    with pytest.raises(IllegalActionError):
        apply_action(state, {"type": "PLAY_CARD", "actor": "AP", "card_id": "GUNS_OF_AUGUST", "mode": "OPS"})
    assert state == before


def test_rp_card_adds_printed_points_and_cannot_repeat_next_action_round():
    state = ap_action_state()
    state["players"]["AP"]["hand"] = ["BLOCKADE"]
    state["players"]["AP"]["deck"] = []
    result = apply_action(state, {"type": "PLAY_CARD", "actor": "AP", "card_id": "BLOCKADE", "mode": "RP"}).state

    assert result["players"]["AP"]["replacement_points"]["BR"] == 2
    assert result["players"]["AP"]["replacement_points"]["RU"] == 3
    assert "BLOCKADE" in result["players"]["AP"]["discard"]
    assert result["active_side"] == "CP"
    assert result["action_round"] == 2

    result["players"]["AP"]["hand"] = ["PLEVE"]
    result = complete_action(result)
    assert all(action["mode"] != "RP" for action in legal_card_actions(result, "AP"))


def test_draw_respects_eight_card_limit_and_reshuffles_discard():
    state = ap_action_state()
    player = state["players"]["AP"]
    player["hand"] = []
    player["deck"] = ["PLEVE"]
    player["discard"] = ["PUTNIK"]

    result = draw_to_hand(state, "AP")

    assert set(result["players"]["AP"]["hand"]) == {"PLEVE", "PUTNIK"}
    assert result["players"]["AP"]["deck"] == []
    assert result["players"]["AP"]["discard"] == []


def test_only_selected_combat_cards_may_be_discarded():
    state = ap_action_state()
    state["players"]["AP"]["hand"] = ["PLEVE", "BLOCKADE"]

    result = discard_combat_cards(state, "AP", ["PLEVE"])
    assert result["players"]["AP"]["hand"] == ["BLOCKADE"]
    assert "PLEVE" in result["players"]["AP"]["discard"]
    with pytest.raises(IllegalActionError):
        discard_combat_cards(state, "AP", ["BLOCKADE"])
