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


def test_sud_army_one_ah_and_multiple_german_corps_cost_one_op():
    state = ops_state(1)
    state["events"]["SUD_ARMY"] = 1
    for uid in ("AH_1_ARMY_1", "GEC_CORPS_2", "GEC_CORPS_4"):
        state["units"][uid]["location"] = "TARNOW"
    assert activation_cost(state, "TARNOW", "ATTACK") == 1


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


def test_two_armies_can_move_as_a_stack_for_multiple_edges():
    state = ops_state()
    state["active_side"] = "AP"
    state["units"]["RU_5_ARMY_1"]["location"] = "KHARKOV"
    state["units"]["RU_11_ARMY_1"]["location"] = "KHARKOV"
    state["activated"]["MOVE"] = ["KHARKOV"]
    state["phase"] = "MOVEMENT"
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP", "options": legal_movement_actions(state)}
    group = ["RU_11_ARMY_1", "RU_5_ARMY_1"]
    state = choose(state, "MOVE_STACK", unit_ids=group, to="KIEV")
    assert state["movement"]["stack"] == group
    assert {"type": "MOVE_STACK", "actor": "AP", "unit_ids": group, "to": "ZHITOMIR"} in generate_legal_actions(state)


def test_stack_can_drop_one_unit_and_continue_with_the_other():
    state = ops_state()
    state["active_side"] = "AP"
    for uid in ("RU_5_ARMY_1", "RU_11_ARMY_1"):
        state["units"][uid]["location"] = "KHARKOV"
    state["activated"]["MOVE"] = ["KHARKOV"]
    state["phase"] = "MOVEMENT"
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP",
                         "options": legal_movement_actions(state)}
    state = choose(state, "MOVE_STACK", unit_ids=["RU_11_ARMY_1", "RU_5_ARMY_1"], to="KIEV")
    state = choose(state, "DROP_MOVING_UNIT", unit_id="RU_5_ARMY_1")
    assert state["movement"]["unit"] == "RU_11_ARMY_1"
    assert "RU_5_ARMY_1" in state["movement"]["done"]
    assert any(a["type"] == "MOVE" and a.get("unit_id") == "RU_11_ARMY_1"
               and a.get("to") == "ZHITOMIR" for a in generate_legal_actions(state))


def test_movement_may_temporarily_overstack_but_cannot_end_overstacked():
    state = ops_state()
    state["active_side"] = "AP"
    state["phase"] = "MOVEMENT"
    state["activated"]["MOVE"] = ["LONDON"]
    for uid in ("BR_1_ARMY_1", "BR_2_ARMY_1", "BR_4_ARMY_1"):
        state["units"][uid]["location"] = "LONDON"
    state["units"]["FRC_CORPS_3"]["location"] = "CALAIS"
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP", "options": legal_movement_actions(state)}
    group = ["BR_1_ARMY_1", "BR_2_ARMY_1", "BR_4_ARMY_1"]
    state = choose(state, "MOVE_STACK", unit_ids=group, to="CALAIS")
    assert not any(a["type"] == "END_MOVEMENT" for a in generate_legal_actions(state))
    assert {"type": "MOVE_STACK", "actor": "AP", "unit_ids": group, "to": "CAMBRAI"} in generate_legal_actions(state)


def test_unit_cannot_exhaust_movement_in_attack_activated_space():
    state = ops_state()
    state["phase"] = "MOVEMENT"
    state["active_side"] = "CP"
    state["activated"]["MOVE"] = ["AACHEN"]
    state["activated"]["ATTACK"] = ["LIEGE"]
    state["movement"] = {"unit": "GE_1_ARMY_1", "spent": 2, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP", "options": legal_movement_actions(state)}
    assert not any(action["type"] == "MOVE" and action.get("to") == "LIEGE"
                   for action in generate_legal_actions(state))


def test_german_army_may_pass_through_amiens_before_early_war_limit():
    state = ops_state()
    state["phase"] = "MOVEMENT"
    state["players"]["CP"]["war_status"] = 3
    state["units"]["GE_3_ARMY_1"]["location"] = "CAMBRAI"
    for unit in state["units"].values():
        if unit["location"] == "AMIENS":
            unit["location"] = None
    state["activated"]["MOVE"] = ["CAMBRAI"]
    state["movement"] = {"unit": "GE_3_ARMY_1", "spent": 1, "done": [], "stack": None}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP",
                         "options": legal_movement_actions(state)}

    assert {"type": "MOVE", "actor": "CP", "unit_id": "GE_3_ARMY_1",
            "to": "AMIENS"} in generate_legal_actions(state)
    last_step = deepcopy(state)
    last_step["movement"]["spent"] = 2
    last_step["decision"]["options"] = legal_movement_actions(last_step)
    assert not any(a["type"] == "MOVE" and a.get("to") == "AMIENS"
                   for a in generate_legal_actions(last_step))
    state = choose(state, "MOVE", unit_id="GE_3_ARMY_1", to="AMIENS")
    assert not any(a["type"] == "STOP_MOVING_UNIT" for a in generate_legal_actions(state))
    assert any(a["type"] == "MOVE" and a.get("to") == "CAMBRAI"
               for a in generate_legal_actions(state))


def test_moving_corps_stack_can_besiege_two_strength_fort_together():
    state = ops_state()
    state["phase"] = "MOVEMENT"
    state["active_side"] = "AP"
    state["war_nations"]["TU"] = True
    for uid in ("BRC_CORPS_3", "BRC_CORPS_5"):
        state["units"][uid]["location"] = "SINAI"
    state["movement"] = {"unit": None, "spent": 1, "done": [],
                         "stack": ["BRC_CORPS_3", "BRC_CORPS_5"]}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP",
                         "options": legal_movement_actions(state)}

    assert {"type": "MOVE_STACK", "actor": "AP",
            "unit_ids": ["BRC_CORPS_3", "BRC_CORPS_5"], "to": "BEERSHEBA"} in generate_legal_actions(state)


def test_undestroyed_enemy_fort_keeps_control_when_entered():
    state = ops_state()
    state = choose(choose(state, "ACTIVATE_SPACE", space_id="AACHEN", kind="MOVE"), "FINISH_ACTIVATION")
    state = choose(state, "MOVE", unit_id="GE_1_ARMY_1", to="LIEGE")
    assert state["spaces"]["LIEGE"]["control"] == "AP"
    assert not any(a["type"] == "MOVE" and a["unit_id"] == "GE_1_ARMY_1" for a in generate_legal_actions(state))


def test_army_can_move_through_already_besieged_enemy_fort():
    state = ops_state()
    state["phase"] = "MOVEMENT"
    state["units"]["AH_3_ARMY_1"]["location"] = "LUBLIN"
    state["units"]["AH_4_ARMY_1"]["location"] = "BREST_LITOVSK"
    state["units"]["RU_5_ARMY_1"]["location"] = "KIEV"
    state["spaces"]["LUBLIN"]["control"] = "CP"
    state["spaces"]["BREST_LITOVSK"]["fort_besieged"] = True
    state["activated"]["MOVE"] = ["LUBLIN"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP",
                         "options": legal_movement_actions(state)}
    state = choose(state, "MOVE", unit_id="AH_3_ARMY_1", to="BREST_LITOVSK")
    assert state["movement"]["unit"] == "AH_3_ARMY_1"
    assert any(a["type"] == "MOVE" and a.get("unit_id") == "AH_3_ARMY_1"
               and a.get("to") == "BIALYSTOK" for a in generate_legal_actions(state))


def test_stack_can_move_through_already_besieged_enemy_fort():
    state = ops_state()
    state["phase"] = "MOVEMENT"
    for uid in ("AH_2_ARMY_1", "AH_3_ARMY_1"):
        state["units"][uid]["location"] = "LUBLIN"
    state["units"]["AH_4_ARMY_1"]["location"] = "BREST_LITOVSK"
    state["units"]["RU_5_ARMY_1"]["location"] = "KIEV"
    state["spaces"]["LUBLIN"]["control"] = "CP"
    state["spaces"]["BREST_LITOVSK"]["fort_besieged"] = True
    state["activated"]["MOVE"] = ["LUBLIN"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP",
                         "options": legal_movement_actions(state)}
    group = ["AH_2_ARMY_1", "AH_3_ARMY_1"]
    state = choose(state, "MOVE_STACK", unit_ids=group, to="BREST_LITOVSK")
    assert state["movement"]["stack"] == group
    assert state["spaces"]["BREST_LITOVSK"]["control"] == "AP"


def test_stack_captures_enemy_trench_when_newly_besieging_fort():
    state = ops_state()
    state["phase"] = "MOVEMENT"
    for uid in ("GEC_CORPS_1", "GEC_CORPS_2", "GEC_CORPS_3"):
        state["units"][uid]["location"] = "AACHEN"
    state["units"]["BE_1_ARMY_1"]["location"] = "ANTWERP"
    state["spaces"]["LIEGE"]["trenches"]["AP"] = 1
    state["activated"]["MOVE"] = ["AACHEN"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP",
                         "options": legal_movement_actions(state)}
    state = choose(state, "MOVE_STACK", unit_ids=["GEC_CORPS_1", "GEC_CORPS_2", "GEC_CORPS_3"], to="LIEGE")
    assert state["spaces"]["LIEGE"]["fort_besieged"]
    assert state["spaces"]["LIEGE"]["trenches"]["AP"] == 0


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
    assert any(a.get("to") == "ESSEN" for a in generate_legal_actions(state))
    state = choose(state, "MOVE", unit_id="GE_1_ARMY_1", to="LIEGE")
    state = choose(state, "STOP_MOVING_UNIT")
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in generate_legal_actions(state))


def test_reduced_movement_factor_and_nationality_restricted_edge():
    state = ops_state()
    state["spaces"]["LIEGE"]["fort_destroyed"] = True
    state["war_nations"]["TU"] = True
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
    state = apply_action(state, {"type": "END_COMBAT", "actor": "CP"}).state
    card_id = next(a["card_id"] for a in generate_legal_actions(state) if a["mode"] == "OPS")
    state = apply_action(state, {"type": "PLAY_CARD", "actor": "AP", "card_id": card_id, "mode": "OPS"}).state
    assert state["phase"] == "OPS"
    assert any(a["type"] == "ACTIVATE_SPACE" for a in generate_legal_actions(state))
    state = choose(choose(state, "FINISH_ACTIVATION"), "END_MOVEMENT")
    assert state["active_side"] == "CP"
    assert state["action_round"] == 2
