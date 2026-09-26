from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.sr import legal_sr_actions
from pog_engine.rules.trenches import legal_entrench_actions


def choose(state, action_type, **fields):
    action = next(a for a in generate_legal_actions(state) if a["type"] == action_type and all(a.get(k) == v for k, v in fields.items()))
    return apply_action(state, action).state


def sr_state(points=4, side="CP"):
    state = create_game(seed=4)
    state["phase"] = "SR"
    state["active_side"] = side
    state["sr_remaining"] = points
    state["sr"] = {"unit": None, "done": [], "near_east_sea_used": False}
    state["decision"] = {"kind": "SR", "actor": side, "options": []}
    state["decision"]["options"] = legal_sr_actions(state)
    return state


def test_army_sr_cost_four_and_reachable_friendly_destination():
    state = sr_state()
    state = choose(state, "SELECT_SR_UNIT", unit_id="GE_1_ARMY_1")
    assert any(a.get("to") == "ESSEN" for a in generate_legal_actions(state))
    state = choose(state, "SR_TO", to="ESSEN")
    assert state["units"]["GE_1_ARMY_1"]["location"] == "ESSEN"
    assert state["sr_remaining"] == 0
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in generate_legal_actions(state))


def test_one_point_can_sr_corps_but_not_army_and_reserve_to_stack():
    state = sr_state(points=1)
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in generate_legal_actions(state))
    unit_id = next(uid for uid, u in state["units"].items() if u["location"] == "CP_RESERVE_BOX" and uid.startswith("GEC"))
    state = choose(state, "SELECT_SR_UNIT", unit_id=unit_id)
    assert any(a.get("to") == "AACHEN" for a in generate_legal_actions(state))
    state = choose(state, "SR_TO", to="AACHEN")
    assert state["units"][unit_id]["location"] == "AACHEN"


def test_sr_overland_cannot_enter_enemy_control():
    state = sr_state()
    state["spaces"]["KOBLENZ"]["control"] = "AP"
    state["decision"]["options"] = legal_sr_actions(state)
    state = choose(state, "SELECT_SR_UNIT", unit_id="GE_1_ARMY_1")
    assert not any(a.get("to") == "KOBLENZ" for a in generate_legal_actions(state))


def test_corps_can_sr_by_sea_between_friendly_ports():
    state = sr_state(points=1, side="AP")
    state["units"]["BR_BEFC_CORPS_1"]["location"] = "LONDON"
    state["decision"]["options"] = legal_sr_actions(state)
    state = choose(state, "SELECT_SR_UNIT", unit_id="BR_BEFC_CORPS_1")
    assert any(a.get("to") == "CALAIS" for a in generate_legal_actions(state))


def test_sr_rejects_isolated_army_at_nationality_restricted_connection():
    state = sr_state()
    state["units"]["GE_1_ARMY_1"]["location"] = "LONDON"
    state["spaces"]["LONDON"]["control"] = "CP"
    state["spaces"]["CALAIS"]["control"] = "CP"
    state["decision"]["options"] = legal_sr_actions(state)
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in generate_legal_actions(state))


def test_russian_army_cannot_cross_near_east_boundary_by_sr():
    state = sr_state(side="AP")
    state["units"]["RU_CAU_ARMY_1"]["location"] = "CAUCASUS"
    state["decision"]["options"] = legal_sr_actions(state)
    state = choose(state, "SELECT_SR_UNIT", unit_id="RU_CAU_ARMY_1")
    assert not any(a.get("to") in {"GROZNY", "POTI"} for a in generate_legal_actions(state))


def test_only_one_russian_corps_may_sr_across_near_east_boundary_per_turn():
    state = sr_state(points=2, side="AP")
    for unit_id in ("RUC_CORPS_1", "RUC_CORPS_2"):
        state["units"][unit_id]["location"] = "CAUCASUS"
    state["decision"]["options"] = legal_sr_actions(state)
    state = choose(choose(state, "SELECT_SR_UNIT", unit_id="RUC_CORPS_1"), "SR_TO", to="GROZNY")
    assert state["flags"]["near_east_sr"]["RU"] == 1
    state = choose(state, "SELECT_SR_UNIT", unit_id="RUC_CORPS_2")
    assert not any(a.get("to") in {"GROZNY", "POTI"} for a in generate_legal_actions(state))


def test_montenegrin_corps_only_sr_between_cetinje_and_reserve():
    state = sr_state(points=1, side="AP")
    state = choose(state, "SELECT_SR_UNIT", unit_id="MNC_CORPS_1")
    destinations = {a["to"] for a in generate_legal_actions(state) if a["type"] == "SR_TO"}
    assert destinations == {"AP_RESERVE_BOX"}


def trench_state():
    state = create_game(seed=4)
    state["turn"] = 2
    state["phase"] = "MOVEMENT"
    state["active_side"] = "CP"
    state["events"]["ENTRENCH"] = 1
    state["activated"]["MOVE"] = ["AACHEN"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP", "options": []}
    from pog_engine.rules.movement import legal_movement_actions
    state["decision"]["options"] = legal_movement_actions(state)
    return state


def test_trench_roll_failure_marker_and_next_round_minus_one():
    state = trench_state()
    assert {"type": "ENTRENCH", "actor": "CP", "unit_id": "GE_1_ARMY_1"} in legal_entrench_actions(state)
    state = choose(state, "ENTRENCH", unit_id="GE_1_ARMY_1")
    state = choose(state, "END_MOVEMENT")
    assert state["decision"]["actor"] == "CHANCE"
    state = choose(state, "RECORD_ENTRENCH_DIE", value=6)
    assert state["flags"]["failed_entrench"]["GE_1_ARMY_1"]


def test_trench_success_respects_level_two_limit():
    state = trench_state()
    state = choose(choose(state, "ENTRENCH", unit_id="GE_1_ARMY_1"), "END_MOVEMENT")
    state = choose(state, "RECORD_ENTRENCH_DIE", value=1)
    assert state["spaces"]["AACHEN"]["trenches"]["CP"] == 1
    state = trench_state()
    state["spaces"]["AACHEN"]["trenches"]["CP"] = 2
    assert not legal_entrench_actions(state)


def test_failed_trench_marker_modifies_only_next_own_action():
    state = trench_state()
    state["players"]["CP"]["actions_taken"] = 1
    state["flags"]["failed_entrench"] = {"GE_1_ARMY_1": 7}
    state = choose(choose(state, "ENTRENCH", unit_id="GE_1_ARMY_1"), "END_MOVEMENT")
    state = choose(state, "RECORD_ENTRENCH_DIE", value=4)
    assert state["spaces"]["AACHEN"]["trenches"]["CP"] == 1
    assert "GE_1_ARMY_1" not in state["flags"]["failed_entrench"]


def test_failed_trench_marker_expires_when_next_action_has_no_attempt():
    from pog_engine.rules.turn import complete_action

    state = trench_state()
    state["phase"] = "ACTION"
    state["players"]["CP"]["actions_taken"] = 1
    state["flags"]["failed_entrench"] = {"GE_1_ARMY_1": 7}
    state = complete_action(state)
    assert "GE_1_ARMY_1" not in state["flags"]["failed_entrench"]
