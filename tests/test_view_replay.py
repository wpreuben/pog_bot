import json

import pytest

from pog_engine import apply_action, create_game, generate_legal_actions, get_player_view
from pog_engine.replay import replay
from pog_engine.model import InvalidStateError
from pog_engine.rules.turn import advance_automatic_phases


def test_player_view_hides_opponent_hand_deck_and_rng():
    state = create_game(seed=11)
    view = get_player_view(state, "AP")
    assert view["players"]["AP"]["hand"] == state["players"]["AP"]["hand"]
    assert "hand" not in view["players"]["CP"]
    assert "deck" not in view["players"]["CP"]
    assert "rng_state" not in view
    assert "rng_state" not in json.dumps(view)
    assert "deck" not in view["players"]["AP"]
    assert view["players"]["CP"]["hand_count"] == 8
    assert "decision" not in view or view["decision"] is None
    assert all(card not in view["players"]["CP"].get("hand", [])
               for card in state["players"]["CP"]["hand"])


def test_reveal_event_only_exposes_hand_to_its_viewer():
    state = create_game(seed=11)
    state["temporary_effects"]["revealed_hand"] = {
        "viewer": "AP", "owner": "CP", "cards": list(state["players"]["CP"]["hand"]),
    }
    assert get_player_view(state, "AP")["revealed_hand"] == state["players"]["CP"]["hand"]
    assert "revealed_hand" not in get_player_view(state, "CP")


def test_opponent_action_choices_are_hidden():
    state = create_game(seed=11)
    state["phase"] = "ACTION"
    state["active_side"] = "CP"
    state["decision"] = {"kind": "ACTION_PHASE", "actor": "CP", "options": [
        {"type": "PLAY_CARD", "actor": "CP", "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"}
    ]}
    assert get_player_view(state, "AP")["decision"] is None
    assert get_player_view(state, "CP")["decision"] == state["decision"]


def test_recorded_die_and_automatic_phase_replay_exact_state():
    initial = create_game(seed=13)
    action = next(a for a in generate_legal_actions(initial) if a["value"] == 4)
    transition = apply_action(initial, action)
    records = [json.loads(json.dumps(transition.record))]
    assert replay(initial, records) == transition.state
    assert records[0]["random_input"] == 4
    forged = json.loads(json.dumps(records))
    forged[0]["random_input"] = 1
    with pytest.raises(InvalidStateError):
        replay(initial, forged)
    del forged[0]["random_input"]
    with pytest.raises(InvalidStateError):
        replay(initial, forged)
    with pytest.raises(InvalidStateError):
        replay(initial, [{"action": {"type": "FORGED", "actor": "CHANCE"}, "random_input": None}])


def test_player_view_is_detached_and_rejects_invalid_side():
    state = create_game(seed=11)
    view = get_player_view(state, "AP")
    view["units"]["GE_1_ARMY_1"]["location"] = "NOWHERE"
    assert state["units"]["GE_1_ARMY_1"]["location"] != "NOWHERE"
    with pytest.raises(ValueError):
        get_player_view(state, "CHANCE")


def test_draw_phase_allows_optional_combat_card_discard_before_refill():
    state = create_game(seed=5)
    state["phase"] = "DRAW"
    state["decision"] = None
    state["players"]["AP"]["hand"] = ["PLEVE"]
    state = advance_automatic_phases(state)
    assert state["decision"]["kind"] == "DRAW_DISCARD"
    choice = next(action for action in generate_legal_actions(state)
                  if action["type"] == "DISCARD_DRAW_CARD")
    state = apply_action(state, choice).state
    assert "PLEVE" in state["players"]["AP"]["discard"]
    state = apply_action(state, {"type": "END_DRAW_DISCARD", "actor": "AP"}).state
    assert state["players"]["AP"]["hand"]
    assert len(state["players"]["AP"]["hand"]) <= state["hand_size"]
