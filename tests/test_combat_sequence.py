from copy import deepcopy

from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.combat import legal_combat_actions
from pog_engine.rules.movement import legal_movement_actions


def choose(state, action_type, **fields):
    action = next(a for a in generate_legal_actions(state) if a["type"] == action_type and all(a.get(k) == v for k, v in fields.items()))
    return apply_action(state, action).state


def combat_state():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["BE_1_ARMY_1"]["location"] = "LIEGE"
    state["activated"]["ATTACK"] = ["AACHEN", "KOBLENZ"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["decision"] = {"kind": "COMBAT", "actor": "CP", "options": []}
    state["decision"]["options"] = legal_combat_actions(state)
    return state


def test_movement_with_attack_activation_enters_combat_window():
    state = combat_state()
    state["phase"] = "MOVEMENT"
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP", "options": []}
    state["decision"]["options"] = legal_movement_actions(state)
    state = choose(state, "END_MOVEMENT")
    assert state["phase"] == "COMBAT"
    assert any(a["type"] == "DECLARE_ATTACK" for a in generate_legal_actions(state))


def test_combat_cards_and_chance_rolls_switch_actor():
    state = combat_state()
    state = choose(state, "DECLARE_ATTACK", unit_ids=["GE_1_ARMY_1"], defender_space="LIEGE")
    state = choose(state, "SKIP_FLANK")
    assert state["decision"]["actor"] == "CP"
    assert any(a.get("card_id") == "WIRELESS_INTERCEPTS" for a in generate_legal_actions(state))
    state = choose(state, "PLAY_COMBAT_CARD", card_id="WIRELESS_INTERCEPTS")
    assert "WIRELESS_INTERCEPTS" not in state["players"]["CP"]["hand"]
    state = choose(state, "PASS_COMBAT_CARDS")
    assert state["decision"]["actor"] == "AP"
    state = choose(state, "PASS_COMBAT_CARDS")
    assert state["decision"]["actor"] == "CHANCE"
    assert all(a["actor"] == "CHANCE" for a in generate_legal_actions(state))


def test_losses_two_space_retreat_and_advance_are_replayable():
    state = combat_state()
    state = choose(state, "DECLARE_ATTACK", unit_ids=["GE_1_ARMY_1"], defender_space="LIEGE")
    state = choose(state, "SKIP_FLANK")
    state = choose(choose(state, "PASS_COMBAT_CARDS"), "PASS_COMBAT_CARDS")
    state = choose(state, "RECORD_COMBAT_DIE", side="CP", value=4)
    state = choose(state, "RECORD_COMBAT_DIE", side="AP", value=1)
    assert state["decision"]["actor"] == "AP"
    before = deepcopy(state)
    action = next(a for a in generate_legal_actions(state) if a["type"] == "TAKE_LOSS" and a["unit_id"] == "BE_1_ARMY_1")
    state = apply_action(state, action).state
    assert before["units"]["BE_1_ARMY_1"]["reduced"] is False
    assert state["units"]["BE_1_ARMY_1"]["reduced"] is True
    state = choose(state, "END_LOSSES")
    state = choose(state, "END_LOSSES")
    assert state["decision"]["actor"] == "AP"
    state = choose(state, "RETREAT_TO", to="BRUSSELS")
    state = choose(state, "RETREAT_TO", to="ANTWERP")
    state = choose(state, "ADVANCE_UNIT", unit_id="GE_1_ARMY_1")
    assert state["units"]["GE_1_ARMY_1"]["location"] == "LIEGE"
    assert state["units"]["BE_1_ARMY_1"]["location"] == "ANTWERP"
    assert state["spaces"]["LIEGE"]["control"] == "AP"


def test_reduced_army_loss_replaces_with_reserve_corps():
    state = combat_state()
    state["units"]["BE_1_ARMY_1"]["reduced"] = True
    state = choose(state, "DECLARE_ATTACK", unit_ids=["GE_1_ARMY_1", "GE_2_ARMY_1"], defender_space="LIEGE")
    state = choose(state, "SKIP_FLANK")
    state = choose(choose(state, "PASS_COMBAT_CARDS"), "PASS_COMBAT_CARDS")
    state = choose(state, "RECORD_COMBAT_DIE", side="CP", value=6)
    state = choose(state, "RECORD_COMBAT_DIE", side="AP", value=1)
    state = choose(state, "TAKE_LOSS", unit_id="BE_1_ARMY_1", replacement_unit_id="BEC_CORPS_1")
    assert state["units"]["BE_1_ARMY_1"]["eliminated"]
    assert state["units"]["BEC_CORPS_1"]["location"] == "LIEGE"


def test_loss_choices_preserve_maximum_payable_loss_number():
    state = combat_state()
    for uid in ("FR_1_ARMY_1", "FR_2_ARMY_1"):
        state["units"][uid]["location"] = "LIEGE"
    state["units"]["FR_2_ARMY_1"]["reduced"] = True
    state["units"]["FRC_CORPS_3"]["location"] = "AP_RESERVE_BOX"
    state["combat_context"] = {
        "attacker": "CP", "defender": "AP", "attackers": ["GE_1_ARMY_1"],
        "defender_space": "LIEGE", "defending_units": ["FR_1_ARMY_1", "FR_2_ARMY_1"],
        "stage": "LOSSES", "loss_side": "AP", "loss_remaining": 5,
    }
    actions = legal_combat_actions(state)
    assert any(a.get("unit_id") == "FR_2_ARMY_1" and a.get("replacement_unit_id") == "FRC_CORPS_3" for a in actions)
    assert not any(a.get("unit_id") == "FR_1_ARMY_1" for a in actions)
    assert not any(a["type"] == "END_LOSSES" for a in actions)


def test_combat_cards_are_discarded_on_tie():
    state = combat_state()
    state = choose(state, "DECLARE_ATTACK", unit_ids=["GE_1_ARMY_1"], defender_space="LIEGE")
    state = choose(state, "SKIP_FLANK")
    state = choose(state, "PLAY_COMBAT_CARD", card_id="WIRELESS_INTERCEPTS")
    state = choose(state, "PASS_COMBAT_CARDS")
    state = choose(state, "PLAY_COMBAT_CARD", card_id="PUTNIK")
    state = choose(state, "PASS_COMBAT_CARDS")
    state = choose(state, "RECORD_COMBAT_DIE", side="CP", value=1)
    state = choose(state, "RECORD_COMBAT_DIE", side="AP", value=1)
    state = choose(choose(state, "END_LOSSES"), "END_LOSSES")
    assert "WIRELESS_INTERCEPTS" in state["players"]["CP"]["discard"]
    assert "PUTNIK" in state["players"]["AP"]["discard"]


def test_eliminated_attacker_does_not_contribute_to_sequential_fire():
    from pog_engine.rules.combat import combat_snapshot, combat_strength

    state = combat_state()
    state["units"]["GE_1_ARMY_1"]["location"] = None
    state["units"]["GEC_CORPS_1"]["location"] = "AACHEN"
    state["units"]["GEC_CORPS_1"]["reduced"] = False
    context = {"attacker": "CP", "attackers": ["GE_1_ARMY_1", "GEC_CORPS_1"], "defender_space": "LIEGE"}
    assert combat_strength(state, context, "CP") == 2
    assert combat_snapshot(state, context)["tables"]["CP"] == "CORPS"


def test_successful_flank_applies_defender_losses_before_return_fire():
    state = combat_state()
    state = choose(state, "DECLARE_ATTACK", unit_ids=["GE_1_ARMY_1", "GE_2_ARMY_1"], defender_space="LIEGE")
    state = choose(state, "ATTEMPT_FLANK", pinning_space="KOBLENZ")
    assert state["decision"]["actor"] == "CHANCE"
    state = choose(state, "RECORD_FLANK_DIE", value=3)
    assert state["combat_context"]["flank_success"]
    state = choose(choose(state, "PASS_COMBAT_CARDS"), "PASS_COMBAT_CARDS")
    state = choose(state, "RECORD_COMBAT_DIE", side="CP", value=4)
    assert state["decision"]["actor"] == "AP"
    assert any(a["type"] == "TAKE_LOSS" for a in generate_legal_actions(state))


def test_defender_in_trench_can_cancel_retreat_with_extra_step():
    state = combat_state()
    state = choose(state, "DECLARE_ATTACK", unit_ids=["GE_1_ARMY_1"], defender_space="LIEGE")
    state["spaces"]["LIEGE"]["trenches"]["AP"] = 1
    context = state["combat_context"]
    context["stage"] = "RETREAT"
    context["results"] = {"CP": 4, "AP": 2}
    context["retreat_total"] = 2
    context["retreat_remaining"] = 2
    context["retreat_location"] = "LIEGE"
    state["decision"]["actor"] = "AP"
    state["decision"]["options"] = legal_combat_actions(state)
    state = choose(state, "CANCEL_RETREAT", unit_id="BE_1_ARMY_1")
    assert state["units"]["BE_1_ARMY_1"]["location"] == "LIEGE"
    assert state["units"]["BE_1_ARMY_1"]["reduced"]


def test_winning_combat_card_is_discarded_at_turn_end():
    from pog_engine.rules.turn import advance_automatic_phases

    state = combat_state()
    state["phase"] = "END_TURN"
    state["players"]["CP"]["in_play"] = ["WIRELESS_INTERCEPTS"]
    result = advance_automatic_phases(state)
    assert result["players"]["CP"]["in_play"] == []
    assert "WIRELESS_INTERCEPTS" in result["players"]["CP"]["discard"]
