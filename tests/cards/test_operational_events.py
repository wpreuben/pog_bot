from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.cards import EVENT_HANDLERS, legal_card_actions
from pog_engine.rules.ops import activation_cost
from pog_engine.rules.combat import legal_combat_actions
from pog_engine.rules.turn import complete_action


def action_state(card_id, turn=2):
    from pog_engine.data import load_data

    state = create_game(seed=4)
    side = load_data().cards[card_id]["side"]
    state["turn"] = turn
    state["phase"] = "ACTION"
    state["active_side"] = side
    state["players"][side]["hand"].append(card_id)
    state["decision"] = {"kind": "ACTION_PHASE", "actor": side, "options": []}
    state["decision"]["options"] = legal_card_actions(state, side)
    return state


def play_event(state, card_id):
    state["decision"]["options"] = legal_card_actions(state, state["active_side"])
    return apply_action(state, {"type": "PLAY_CARD", "actor": state["active_side"],
                                "card_id": card_id, "mode": "EVENT"}).state


def test_entrench_event_forbidden_on_first_turn_and_places_level_one():
    state = action_state("ENTRENCH_AP", 1)
    assert not EVENT_HANDLERS["ENTRENCH_AP"].can_play(state, "ENTRENCH_AP")
    state["turn"] = 2
    state = play_event(state, "ENTRENCH_AP")
    assert state["phase"] == "EVENT_ENTRENCH"
    place = next(a for a in generate_legal_actions(state) if a["type"] == "PLACE_EVENT_TRENCH")
    state = apply_action(state, place).state
    assert state["spaces"][place["to"]]["trenches"]["AP"] == 1


def test_moltke_and_falkenhayn_change_cp_activation_cost():
    state = action_state("MOLTKE", 2)
    state = play_event(state, "MOLTKE")
    state["active_side"] = "CP"
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["units"]["GE_2_ARMY_1"]["location"] = "LIEGE"
    assert activation_cost(state, "LIEGE", "ATTACK") == 2
    state["events"]["FALKENHAYN"] = 3
    assert activation_cost(state, "LIEGE", "ATTACK") == 1


def test_sud_army_eleventh_and_everyone_into_battle_modify_ops_cost():
    state = create_game(seed=4)
    state["active_side"] = "CP"
    state["turn"] = 5
    state["units"]["GEC_CORPS_1"]["location"] = "CRACOW"
    assert activation_cost(state, "CRACOW", "MOVE") == 2
    state["events"]["SUD_ARMY"] = 3
    assert activation_cost(state, "CRACOW", "MOVE") == 1
    state["active_side"] = "AP"
    state["units"]["FR_1_ARMY_1"]["location"] = "SEDAN"
    state["units"]["BR_1_ARMY_1"]["location"] = "SEDAN"
    state["events"]["EVERYONE_INTO_BATTLE"] = 5
    assert activation_cost(state, "SEDAN", "ATTACK") == 1


def test_sud_army_discount_is_reserved_for_eligible_stack():
    state = create_game(seed=4)
    state["active_side"] = "CP"
    state["turn"] = 5
    state["events"]["SUD_ARMY"] = 3
    state["units"]["GEC_CORPS_1"]["location"] = "CRACOW"
    state["flags"]["sud_army_used_round"] = {"turn": 5, "round": 1, "space": "OTHER"}
    assert activation_cost(state, "CRACOW", "MOVE") == 2


def test_event_ops_temporary_effects_end_with_action():
    state = action_state("YANKS_AND_TANKS", 8)
    state["temporary_effects"]["YANKS_AND_TANKS"] = 8
    state["temporary_effects"]["revealed_hand"] = {"viewer": "AP", "owner": "CP", "cards": []}
    state = complete_action(state)
    assert "YANKS_AND_TANKS" not in state["temporary_effects"]
    assert "revealed_hand" not in state["temporary_effects"]


def test_landwehr_flips_reduced_german_units_without_rp():
    state = action_state("LANDWEHR", 5)
    state["units"]["GE_1_ARMY_1"]["reduced"] = True
    state = play_event(state, "LANDWEHR")
    assert state["phase"] == "LANDWEHR"
    action = next(a for a in generate_legal_actions(state) if a.get("unit_id") == "GE_1_ARMY_1")
    state = apply_action(state, action).state
    assert not state["units"]["GE_1_ARMY_1"]["reduced"]
    assert state["players"]["CP"]["replacement_points"] == {}


def test_salonika_places_neutral_greeks_and_redeploys_corps():
    state = action_state("SALONIKA", 6)
    state = play_event(state, "SALONIKA")
    assert state["phase"] == "SALONIKA"
    assert not state["war_nations"]["GR"]
    assert sum(1 for uid, unit in state["units"].items() if uid.startswith("GRC_") and unit["location"]) == 3
    assert any(a["type"] == "SALONIKA_SR" for a in generate_legal_actions(state))


def test_hoffmann_requires_h_l_and_increases_cp_mo_die():
    from pog_engine.rules.war import mandatory_offensive

    state = action_state("HOFFMANN", 6)
    assert not EVENT_HANDLERS["HOFFMANN"].can_play(state, "HOFFMANN")
    state["events"]["H_L_TAKE_COMMAND"] = 5
    state = play_event(state, "HOFFMANN")
    state["war_nations"]["TU"] = True
    assert mandatory_offensive(state, "CP", 2) == "TU"


def test_landships_and_yanks_and_tanks_open_event_ops():
    state = play_event(action_state("LANDSHIPS", 6), "LANDSHIPS")
    assert state["phase"] == "OPS"
    assert state["events"]["LANDSHIPS"] == 6
    assert state["ops_remaining"] == 4
    state = play_event(action_state("YANKS_AND_TANKS", 8), "YANKS_AND_TANKS")
    assert state["phase"] == "OPS"
    assert state["temporary_effects"]["YANKS_AND_TANKS"] == 8


def combat_state_with_event(card_id, attackers, defender, defender_space="LIEGE"):
    state = action_state(card_id, 8)
    if card_id == "KERENSKY_OFFENSIVE":
        state["events"]["FALL_OF_THE_TSAR"] = 7
    state = play_event(state, card_id)
    state["phase"] = "COMBAT"
    state["active_side"] = "AP"
    if any(uid.startswith("US_") for uid in attackers):
        state["war_nations"]["US"] = True

    if any(uid.startswith("RU_") for uid in attackers):
        defender_space = "PRZEMYSL"
        source = "LUBLIN"
    else:
        source = "BRUSSELS"
    for uid in attackers:
        state["units"][uid]["location"] = source
    state["units"][defender]["location"] = defender_space
    state["activated"]["ATTACK"] = [source]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["decision"] = {"kind": "COMBAT", "actor": "AP", "options": []}
    state["decision"]["options"] = legal_combat_actions(state)
    return state


def test_yanks_and_tanks_adds_two_drm_to_us_attack():
    state = combat_state_with_event("YANKS_AND_TANKS", ("US_1_ARMY_1",), "GE_1_ARMY_1")
    action = next(a for a in generate_legal_actions(state) if a["type"] == "DECLARE_ATTACK"
                  and a["unit_ids"] == ["US_1_ARMY_1"])
    state = apply_action(state, action).state
    assert state["combat_context"]["drm"]["AP"] == 2


def test_kerensky_and_brusilov_offer_event_combat_choices():
    state = combat_state_with_event("KERENSKY_OFFENSIVE", ("RU_1_ARMY_1",), "AH_1_ARMY_1")
    action = next(a for a in generate_legal_actions(state) if a["type"] == "DECLARE_ATTACK"
                  and "RU_1_ARMY_1" in a["unit_ids"])
    state = apply_action(state, action).state
    state = apply_action(state, {"type": "SKIP_FLANK", "actor": "AP"}).state
    choice = next(a for a in generate_legal_actions(state) if a["type"] == "USE_KERENSKY_OFFENSIVE")
    state = apply_action(state, choice).state
    assert state["combat_context"]["drm"]["AP"] == 2

    state = combat_state_with_event("BRUSILOV_OFFENSIVE", ("RU_1_ARMY_1",), "AH_1_ARMY_1")
    state["spaces"]["PRZEMYSL"]["trenches"]["CP"] = 1
    state["decision"]["options"] = legal_combat_actions(state)
    action = next(a for a in generate_legal_actions(state) if a["type"] == "DECLARE_ATTACK"
                  and "RU_1_ARMY_1" in a["unit_ids"])
    state = apply_action(state, action).state
    assert state["combat_context"]["drm"]["AP"] == 1
    choice = next(a for a in generate_legal_actions(state) if a["type"] == "USE_BRUSILOV_TRENCH")
    state = apply_action(state, choice).state
    assert state["combat_context"]["trench_negated"]


def test_great_retreat_opens_russian_precombat_retreat():
    state = action_state("GREAT_RETREAT", 8)
    state = play_event(state, "GREAT_RETREAT")
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["RU_1_ARMY_1"]["location"] = "LIEGE"
    state["units"]["GE_1_ARMY_1"]["location"] = "AACHEN"
    state["activated"]["ATTACK"] = ["AACHEN"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["decision"] = {"kind": "COMBAT", "actor": "CP", "options": []}
    state["decision"]["options"] = legal_combat_actions(state)
    attack = next(a for a in generate_legal_actions(state) if a["type"] == "DECLARE_ATTACK"
                  and a["unit_ids"] == ["GE_1_ARMY_1"])
    state = apply_action(state, attack).state
    assert state["combat_context"]["stage"] == "GREAT_RETREAT"
    assert any(a["type"] == "RETREAT_RUSSIAN_UNIT" for a in generate_legal_actions(state))
