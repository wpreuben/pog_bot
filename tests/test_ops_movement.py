from copy import deepcopy

import pytest

from pog_engine import IllegalActionError, apply_action, create_game, generate_legal_actions
from pog_engine.rules.movement import legal_movement_actions
from pog_engine.rules.ops import activation_cost, legal_ops_actions


def ops_state(points=3):
    state = create_game(seed=4)
    state["phase"] = "OPS"
    state["active_side"] = "CP"
    state["ops_remaining"] = points
    state["decision"] = {"kind": "OPS", "actor": "CP", "options": []}
    state["decision"]["options"] = legal_ops_actions(state)
    return state


def choose(state, action_type, **fields):
    action = next(a for a in generate_legal_actions(state) if a["type"] == action_type and all(a.get(k) == v for k, v in fields.items()))
    return apply_action(state, action).state


def test_activation_cost_counts_nations_and_refuses_insufficient_ops():
    state = ops_state(1)
    state["units"]["AH_1_ARMY_1"]["location"] = "AACHEN"
    assert activation_cost(state, "AACHEN", "MOVE") == 2
    assert not any(a["space_id"] == "AACHEN" for a in legal_ops_actions(state) if a["type"] == "ACTIVATE_SPACE")


def test_activated_unit_moves_one_edge_and_changes_control():
    state = ops_state()
    state["spaces"]["LIEGE"]["fort_destroyed"] = True
    state = choose(state, "ACTIVATE_SPACE", space_id="AACHEN", kind="MOVE")
    state = choose(state, "FINISH_ACTIVATION")
    assert state["phase"] == "MOVEMENT"
    assert {"type": "MOVE", "actor": "CP", "unit_id": "GE_1_ARMY_1", "to": "LIEGE"} in legal_movement_actions(state)
    state = choose(state, "MOVE", unit_id="GE_1_ARMY_1", to="LIEGE")
    assert state["units"]["GE_1_ARMY_1"]["location"] == "LIEGE"
    assert state["spaces"]["LIEGE"]["control"] == "CP"


def test_undestroyed_enemy_fort_keeps_control_when_entered():
    state = ops_state()
    state = choose(choose(state, "ACTIVATE_SPACE", space_id="AACHEN", kind="MOVE"), "FINISH_ACTIVATION")
    state = choose(state, "MOVE", unit_id="GE_1_ARMY_1", to="LIEGE")
    assert state["spaces"]["LIEGE"]["control"] == "AP"
    assert not any(a["type"] == "MOVE" and a["unit_id"] == "GE_1_ARMY_1" for a in generate_legal_actions(state))


def test_stack_limit_enemy_occupation_and_repeat_move():
    state = ops_state()
    state["spaces"]["LIEGE"]["fort_destroyed"] = True
    state = choose(choose(state, "ACTIVATE_SPACE", space_id="AACHEN", kind="MOVE"), "FINISH_ACTIVATION")
    state["units"]["FRC_CORPS_3"]["location"] = "LIEGE"
    state["decision"]["options"] = legal_movement_actions(state)
    assert not any(a.get("to") == "LIEGE" for a in generate_legal_actions(state))
    state["units"]["FRC_CORPS_3"]["location"] = "GRENOBLE"
    for unit_id in ["GEC_CORPS_1", "GEC_CORPS_2", "GEC_CORPS_3"]:
        state["units"][unit_id]["location"] = "ESSEN"
    state["decision"]["options"] = legal_movement_actions(state)
    assert not any(a.get("to") == "ESSEN" for a in generate_legal_actions(state))
    state = choose(state, "MOVE", unit_id="GE_1_ARMY_1", to="LIEGE")
    state = choose(state, "STOP_MOVING_UNIT")
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in generate_legal_actions(state))


def test_reduced_movement_factor_and_nationality_restricted_edge():
    state = ops_state()
    state["spaces"]["LIEGE"]["fort_destroyed"] = True
    state["units"]["TU_YLD_ARMY_1"]["location"] = "AACHEN"
    state["units"]["TU_YLD_ARMY_1"]["reduced"] = True
    state["units"]["GE_1_ARMY_1"]["location"] = "LONDON"
    state["decision"]["options"] = legal_ops_actions(state)
    state = choose(choose(state, "ACTIVATE_SPACE", space_id="AACHEN", kind="MOVE"), "FINISH_ACTIVATION")
    state = choose(state, "MOVE", unit_id="TU_YLD_ARMY_1", to="LIEGE")
    state = choose(state, "MOVE", unit_id="TU_YLD_ARMY_1", to="KOBLENZ")
    assert not any(a["type"] == "MOVE" for a in generate_legal_actions(state))
    assert "CALAIS" not in __import__("pog_engine.data", fromlist=["load_data"]).load_data().neighbors("LONDON", "GE")


def test_italian_border_restriction_until_ap_total_war():
    state = ops_state()
    state["units"]["GE_1_ARMY_1"]["location"] = "INNSBRUCK"
    state["decision"]["options"] = legal_ops_actions(state)
    state = choose(choose(state, "ACTIVATE_SPACE", space_id="INNSBRUCK", kind="MOVE"), "FINISH_ACTIVATION")
    assert not any(a.get("to") == "TRENT" for a in generate_legal_actions(state))
    state["players"]["AP"]["commitment"] = "TOTAL"
    state["decision"]["options"] = legal_movement_actions(state)
    assert any(a.get("to") == "TRENT" for a in generate_legal_actions(state))


def test_illegal_move_does_not_mutate_input():
    state = ops_state()
    before = deepcopy(state)
    with pytest.raises(IllegalActionError):
        apply_action(state, {"type": "MOVE", "actor": "CP", "unit_id": "GE_1_ARMY_1", "to": "LIEGE"})
    assert state == before


def test_ops_card_opens_activation_decision():
    state = create_game(seed=4)
    for value in (1, 5):
        purpose = state["decision"]["purpose"]
        state = apply_action(state, {"type": "RECORD_DIE_RESULT", "actor": "CHANCE", "purpose": purpose, "value": value}).state
    state = apply_action(state, {"type": "PLAY_CARD", "actor": "CP", "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"}).state
    card_id = next(a["card_id"] for a in generate_legal_actions(state) if a["mode"] == "OPS")
    state = apply_action(state, {"type": "PLAY_CARD", "actor": "AP", "card_id": card_id, "mode": "OPS"}).state
    assert state["phase"] == "OPS"
    assert any(a["type"] == "ACTIVATE_SPACE" for a in generate_legal_actions(state))
    state = choose(choose(state, "FINISH_ACTIVATION"), "END_MOVEMENT")
    assert state["active_side"] == "CP"
    assert state["action_round"] == 2
