from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.combat import legal_attack_declarations, legal_combat_actions
from pog_engine.rules.forts import fort_status, legal_siege_actions, resolve_fort_combat
from pog_engine.rules.movement import legal_movement_actions
from pog_engine.rules.turn import advance_automatic_phases


def choose(state, action_type, **fields):
    action = next(a for a in generate_legal_actions(state) if a["type"] == action_type and all(a.get(k) == v for k, v in fields.items()))
    return apply_action(state, action).state


def movement_state():
    state = create_game(seed=4)
    state["phase"] = "MOVEMENT"
    state["active_side"] = "CP"
    state["activated"]["MOVE"] = ["AACHEN"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP", "options": []}
    state["decision"]["options"] = legal_movement_actions(state)
    return state


def test_corps_may_enter_fort_temporarily_but_army_completes_siege():
    state = movement_state()
    state["units"]["GEC_CORPS_1"]["location"] = "AACHEN"
    state["decision"]["options"] = legal_movement_actions(state)
    assert any(a.get("unit_id") == "GEC_CORPS_1" and a.get("to") == "LIEGE" for a in generate_legal_actions(state))
    state = choose(state, "MOVE", unit_id="GEC_CORPS_1", to="LIEGE")
    assert not fort_status(state, "LIEGE").besieged
    assert not any(a["type"] == "END_MOVEMENT" for a in generate_legal_actions(state))
    state = choose(state, "MOVE", unit_id="GE_1_ARMY_1", to="LIEGE")
    status = fort_status(state, "LIEGE")
    assert status.besieged
    assert status.owner == "AP"
    assert status.strength == 3
    assert state["spaces"]["LIEGE"]["control"] == "AP"


def test_fort_combat_destroys_only_after_units_gone_and_lf_met():
    state = create_game(seed=4)
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    context = {"attacker": "CP", "defender": "AP", "defender_space": "LIEGE", "loss_remaining": 3}
    result = resolve_fort_combat(state, context)
    assert result["spaces"]["LIEGE"]["fort_destroyed"]
    assert result["spaces"]["LIEGE"]["control"] == "CP"
    assert not state["spaces"]["LIEGE"]["fort_destroyed"]
    state["units"]["BE_1_ARMY_1"]["location"] = "LIEGE"
    assert not resolve_fort_combat(state, context)["spaces"]["LIEGE"]["fort_destroyed"]


def test_first_turn_siege_roll_has_minus_two_modifier():
    state = create_game(seed=4)
    state["phase"] = "SIEGE"
    state["decision"] = None
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    state = advance_automatic_phases(state)
    assert state["decision"]["actor"] == "CHANCE"
    assert any(a["type"] == "RECORD_SIEGE_DIE" for a in legal_siege_actions(state))
    state = choose(state, "RECORD_SIEGE_DIE", value=5)
    assert not state["spaces"]["LIEGE"]["fort_destroyed"]
    assert state["phase"] == "WAR_STATUS"
    state["phase"] = "SIEGE"
    state = advance_automatic_phases(state)
    state = choose(state, "RECORD_SIEGE_DIE", value=6)
    assert state["spaces"]["LIEGE"]["fort_destroyed"]
    assert state["spaces"]["LIEGE"]["control"] == "CP"


def test_multiple_sieges_may_be_rolled_in_any_order():
    state = create_game(seed=4)
    state["phase"] = "SIEGE"
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["units"]["RU_1_ARMY_1"]["location"] = "PRZEMYSL"
    for place in ("LIEGE", "PRZEMYSL"):
        state["spaces"][place]["fort_besieged"] = True
    state["pending_sieges"] = ["LIEGE", "PRZEMYSL"]
    state["decision"] = {"kind": "SIEGE_ROLL", "actor": "CHANCE", "options": legal_siege_actions(state)}
    state = choose(state, "RECORD_SIEGE_DIE", space_id="PRZEMYSL", value=1)
    assert state["pending_sieges"] == ["LIEGE"]


def test_corps_cannot_advance_into_intact_enemy_fort_without_siege_force():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["GEC_CORPS_1"]["location"] = "AACHEN"
    state["units"]["GEC_CORPS_1"]["reduced"] = False
    state["combat_context"] = {
        "attacker": "CP", "defender": "AP", "attackers": ["GEC_CORPS_1"],
        "defending_units": [], "defender_space": "LIEGE", "stage": "ADVANCE", "advanced": [],
    }
    assert not any(a["type"] == "ADVANCE_UNIT" for a in legal_combat_actions(state))


def test_russian_fort_attack_restrictions():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["activated"]["ATTACK"] = ["INSTERBERG"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["units"]["GE_1_ARMY_1"]["location"] = "INSTERBERG"
    state["spaces"]["KOVNO"]["control"] = "AP"
    assert not any("GE_1_ARMY_1" in a["unit_ids"] and a["defender_space"] == "KOVNO"
                   for a in legal_attack_declarations(state))


def test_three_corps_can_enter_fort_as_one_siege_group():
    state = movement_state()
    state["units"]["GE_1_ARMY_1"]["location"] = "ESSEN"
    corps = ["GEC_CORPS_1", "GEC_CORPS_2", "GEC_CORPS_3"]
    for uid in corps:
        state["units"][uid]["location"] = "AACHEN"
    state["decision"]["options"] = legal_movement_actions(state)
    assert any(a["type"] == "MOVE_STACK" and a["to"] == "LIEGE" and set(a["unit_ids"]) == set(corps)
               for a in generate_legal_actions(state))
    state = choose(state, "MOVE_STACK", unit_ids=corps, to="LIEGE")
    assert state["spaces"]["LIEGE"]["fort_besieged"]
    assert all(state["units"][uid]["location"] == "LIEGE" for uid in corps)


def test_corps_siege_group_cannot_enter_enemy_occupied_fort():
    state = movement_state()
    state["units"]["GE_4_ARMY_1"]["location"] = "ESSEN"
    state["units"]["GE_5_ARMY_1"]["location"] = "ESSEN"
    for uid in ("GEC_CORPS_1", "GEC_CORPS_2"):
        state["units"][uid]["location"] = "METZ"
    state["units"]["FR_2_ARMY_1"]["location"] = "PARIS"
    state["activated"]["MOVE"] = ["METZ"]
    state["decision"]["options"] = legal_movement_actions(state)
    assert not any(a["type"] == "MOVE_STACK" and a.get("to") == "NANCY"
                   for a in generate_legal_actions(state))


def test_besieging_army_cannot_leave_understrength_corps_behind():
    state = movement_state()
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["units"]["GEC_CORPS_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    state["activated"]["MOVE"] = ["LIEGE"]
    state["decision"]["options"] = legal_movement_actions(state)
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" and a.get("to") == "AACHEN"
                   for a in generate_legal_actions(state))


def test_russian_army_cannot_enter_german_fort_in_august_1914():
    state = movement_state()
    state["active_side"] = "AP"
    state["units"]["RU_1_ARMY_1"]["location"] = "INSTERBERG"
    state["units"]["GE_8_ARMY_1"]["location"] = "ESSEN"
    state["units"]["GEC_CORPS_2"]["location"] = "ESSEN"
    state["spaces"]["INSTERBERG"]["control"] = "AP"
    state["activated"]["MOVE"] = ["INSTERBERG"]
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP", "options": legal_movement_actions(state)}
    assert not any(a.get("unit_id") == "RU_1_ARMY_1" and a.get("to") == "KONIGSBERG"
                   for a in generate_legal_actions(state))
    state["turn"] = 2
    state["decision"]["options"] = legal_movement_actions(state)
    assert any(a.get("unit_id") == "RU_1_ARMY_1" and a.get("to") == "KONIGSBERG"
               for a in generate_legal_actions(state))


def test_unoccupied_fort_combat_destroys_fort_before_advance():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["activated"]["ATTACK"] = ["AACHEN"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["decision"] = {"kind": "COMBAT", "actor": "CP", "options": legal_combat_actions(state)}
    state = choose(state, "DECLARE_ATTACK", unit_ids=["GE_1_ARMY_1"], defender_space="LIEGE")
    state = choose(state, "SKIP_FLANK")
    state = choose(choose(state, "PASS_COMBAT_CARDS"), "PASS_COMBAT_CARDS")
    state = choose(state, "RECORD_COMBAT_DIE", side="CP", value=5)
    state = choose(state, "RECORD_COMBAT_DIE", side="AP", value=1)
    assert not state["spaces"]["LIEGE"]["fort_destroyed"]
    state = choose(state, "END_LOSSES")
    assert state["spaces"]["LIEGE"]["fort_destroyed"]
    assert state["spaces"]["LIEGE"]["control"] == "AP"
    state = choose(state, "END_LOSSES")
    state = choose(state, "ADVANCE_UNIT", unit_id="GE_1_ARMY_1")
    assert state["spaces"]["LIEGE"]["control"] == "CP"


def test_besieged_fort_can_be_attacked_from_inside_but_siege_force_cannot_leave():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    state["activated"]["ATTACK"] = ["LIEGE"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    actions = legal_attack_declarations(state)
    assert any(a["defender_space"] == "LIEGE" and a["unit_ids"] == ["GE_1_ARMY_1"] for a in actions)
    assert not any(a["defender_space"] == "BRUSSELS" and a["unit_ids"] == ["GE_1_ARMY_1"] for a in actions)


def test_combat_loss_can_break_siege():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["units"]["GE_1_ARMY_1"]["reduced"] = True
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    state["combat_context"] = {
        "attacker": "CP", "defender": "AP", "attackers": ["GE_1_ARMY_1"],
        "defending_units": [], "defender_space": "LIEGE", "stage": "LOSSES",
        "loss_side": "CP", "loss_remaining": 3, "results": {"CP": 0, "AP": 3},
        "cards": {"CP": [], "AP": []}, "loss_queue": [], "fire_index": 1,
        "fire_order": ["CP", "AP"], "advanced": [],
    }
    state["decision"] = {"kind": "COMBAT", "actor": "CP", "options": legal_combat_actions(state)}
    action = next(a for a in generate_legal_actions(state) if a["type"] == "TAKE_LOSS")
    state = apply_action(state, action).state
    assert not state["spaces"]["LIEGE"]["fort_besieged"]


def test_retreating_army_breaks_siege_when_only_one_corps_remains():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["AH_4_ARMY_1"]["location"] = "STANISLAU"
    state["units"]["RU_3_ARMY_1"]["location"] = "PRZEMYSL"
    state["units"]["RUC_CORPS_9"]["location"] = "PRZEMYSL"
    state["spaces"]["PRZEMYSL"]["fort_besieged"] = True
    state["combat_context"] = {
        "attacker": "CP", "defender": "AP", "defender_space": "PRZEMYSL",
        "attackers": ["AH_4_ARMY_1"], "defending_units": ["RU_3_ARMY_1"],
        "stage": "RETREAT", "advanced": [], "retreat_total": 1,
        "retreat_remaining": 1, "retreat_location": "PRZEMYSL",
        "cards": {"AP": [], "CP": []}, "results": {"CP": 5, "AP": 3},
    }
    state["decision"] = {"kind": "COMBAT", "actor": "AP", "options": legal_combat_actions(state)}

    state = choose(state, "RETREAT_TO", to="LEMBERG")

    assert state["units"]["RUC_CORPS_9"]["location"] == "PRZEMYSL"
    assert state["units"]["RU_3_ARMY_1"]["location"] == "LEMBERG"
    assert not state["spaces"]["PRZEMYSL"]["fort_besieged"]


def test_corps_from_two_activated_spaces_can_enter_fort_together():
    state = movement_state()
    state["units"]["GEC_CORPS_1"]["location"] = "METZ"
    state["units"]["GEC_CORPS_2"]["location"] = "STRASBOURG"
    state["units"]["FR_1_ARMY_1"]["location"] = "PARIS"
    state["units"]["FR_2_ARMY_1"]["location"] = "PARIS"
    state["activated"]["MOVE"] = ["METZ", "STRASBOURG"]
    state["decision"]["options"] = legal_movement_actions(state)
    assert any(a["type"] == "MOVE_STACK" and a["to"] == "NANCY"
               and set(a["unit_ids"]) == {"GEC_CORPS_1", "GEC_CORPS_2"}
               for a in generate_legal_actions(state))
