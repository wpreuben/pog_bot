import pytest

from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.cards import EVENT_HANDLERS, legal_card_actions
from pog_engine.rules.turn import advance_automatic_phases, complete_action
from pog_engine.rules.events.economy import expire_effects
from pog_engine.rules.combat import legal_combat_actions


def action_state(card_id, turn=4):
    state = create_game(seed=4)
    from pog_engine.data import load_data

    side = load_data().cards[card_id]["side"]
    state["turn"] = turn
    state["phase"] = "ACTION"
    state["active_side"] = side
    state["players"][side]["hand"].append(card_id)
    state["decision"] = {"kind": "ACTION_PHASE", "actor": side, "options": []}
    state["decision"]["options"] = legal_card_actions(state, side)
    return state


def play_event(state, card_id):
    side = state["active_side"]
    state["decision"]["options"] = legal_card_actions(state, side)
    return apply_action(state, {"type": "PLAY_CARD", "actor": side,
                                "card_id": card_id, "mode": "EVENT"}).state


@pytest.mark.parametrize("card_id", [
    "BLOCKADE", "RAPE_OF_BELGIUM", "LUSITANIA", "REICHSTAG_TRUCE",
    "HIGH_SEAS_FLEET", "GRAND_FLEET", "ZEPPELIN_RAIDS", "WALTER_RATHENAU",
    "U_BOATS_UNLEASHED", "CONVOY", "INDEPENDENT_AIR_FORCE", "14_POINTS",
    "FRENCH_MUTINY", "H_L_TAKE_COMMAND", "FALKENHAYN", "LLOYD_GEORGE",
])
def test_persistent_card_has_handler(card_id):
    assert card_id in EVENT_HANDLERS


def test_blockade_lusitania_and_winter_vp():
    state = play_event(action_state("BLOCKADE", 4), "BLOCKADE")
    assert state["players"]["AP"]["war_status"] == 2
    assert state["events"]["BLOCKADE"] == 4
    state["phase"] = "WAR_STATUS"
    state["decision"] = None
    state = advance_automatic_phases(state)
    assert state["vp"] == 9
    state["phase"] = "ACTION"
    state["active_side"] = "AP"
    state["turn"] = 5
    state["players"]["AP"]["hand"].append("LUSITANIA")
    state["decision"] = {"kind": "ACTION_PHASE", "actor": "AP", "options": []}
    state = play_event(state, "LUSITANIA")
    assert state["vp"] == 8


def test_uboats_convoy_and_walter_rp_effects():
    state = action_state("U_BOATS_UNLEASHED", 8)
    assert not EVENT_HANDLERS["U_BOATS_UNLEASHED"].can_play(state, "U_BOATS_UNLEASHED")
    state["events"]["H_L_TAKE_COMMAND"] = 7
    state = play_event(state, "U_BOATS_UNLEASHED")
    assert state["events"]["U_BOATS_UNLEASHED"] == 8
    state["events"]["WALTER_RATHENAU"] = 6
    state["players"]["AP"]["replacement_points"] = {"BR": 2}
    state["phase"] = "WAR_STATUS"
    state["decision"] = None
    state = advance_automatic_phases(state)
    assert state["players"]["AP"]["replacement_points"]["BR"] == 1
    assert state["players"]["CP"]["replacement_points"]["GE"] == 1

    state = action_state("CONVOY", 9)
    state["events"]["U_BOATS_UNLEASHED"] = 8
    state = play_event(state, "CONVOY")
    assert state["vp"] == 9


def test_zeppelin_subtracts_four_british_rp_once_and_expires():
    state = play_event(action_state("ZEPPELIN_RAIDS", 8), "ZEPPELIN_RAIDS")
    state["players"]["AP"]["replacement_points"] = {"BR": 5}
    state["phase"] = "WAR_STATUS"
    state["decision"] = None
    state = advance_automatic_phases(state)
    assert state["players"]["AP"]["replacement_points"]["BR"] == 1
    assert "ZEPPELIN_RAIDS" not in state["events"]


def test_high_seas_fleet_challenge_and_grand_fleet_counter():
    state = play_event(action_state("HIGH_SEAS_FLEET", 6), "HIGH_SEAS_FLEET")
    assert state["active_side"] == "AP"
    assert state["events"]["HIGH_SEAS_FLEET"] == 6
    state = complete_action(state)
    assert state["vp"] == 11
    assert "HIGH_SEAS_FLEET" not in state["events"]

    state = action_state("GRAND_FLEET", 6)
    assert not EVENT_HANDLERS["GRAND_FLEET"].can_play(state, "GRAND_FLEET")
    state["events"]["HIGH_SEAS_FLEET"] = 6
    state = play_event(state, "GRAND_FLEET")
    assert state["vp"] == 10
    assert "HIGH_SEAS_FLEET" not in state["events"]


def test_lusitania_requires_blockade_before_zimmermann():
    state = action_state("LUSITANIA")
    assert not EVENT_HANDLERS["LUSITANIA"].can_play(state, "LUSITANIA")
    state["events"]["BLOCKADE"] = 2
    assert EVENT_HANDLERS["LUSITANIA"].can_play(state, "LUSITANIA")
    state["events"]["ZIMMERMANN_TELEGRAM"] = 3
    assert not EVENT_HANDLERS["LUSITANIA"].can_play(state, "LUSITANIA")


def test_temporary_events_expire_at_correct_phase():
    state = create_game(seed=4)
    state["turn"] = 9
    state["events"]["LLOYD_GEORGE"] = 8
    state["events"]["FRENCH_MUTINY"] = 7
    expire_effects(state, "END_TURN")
    assert "LLOYD_GEORGE" not in state["events"]
    assert state["events"]["FRENCH_MUTINY"] == 7


def test_walter_bonus_is_cancelled_by_independent_air_force():
    state = action_state("INDEPENDENT_AIR_FORCE", 9)
    state["events"]["WALTER_RATHENAU"] = 7
    state = play_event(state, "INDEPENDENT_AIR_FORCE")
    state["phase"] = "WAR_STATUS"
    state["decision"] = None
    state = advance_automatic_phases(state)
    assert state["players"]["CP"]["replacement_points"].get("GE", 0) == 0


def test_reichstag_rape_fourteen_points_and_prerequisites():
    state = action_state("REICHSTAG_TRUCE", 3)
    state = play_event(state, "REICHSTAG_TRUCE")
    assert state["vp"] == 11
    state = action_state("RAPE_OF_BELGIUM", 2)
    assert not EVENT_HANDLERS["RAPE_OF_BELGIUM"].can_play(state, "RAPE_OF_BELGIUM")
    state["events"]["GUNS_OF_AUGUST"] = 1
    state = play_event(state, "RAPE_OF_BELGIUM")
    assert state["vp"] == 9
    state = action_state("14_POINTS", 8)
    assert not EVENT_HANDLERS["14_POINTS"].can_play(state, "14_POINTS")
    state["events"]["ZIMMERMANN_TELEGRAM"] = 7
    state = play_event(state, "14_POINTS")
    assert state["vp"] == 9


def test_war_in_africa_lets_ap_remove_corps_or_concede_vp():
    state = play_event(action_state("WAR_IN_AFRICA", 6), "WAR_IN_AFRICA")
    assert state["phase"] == "WAR_IN_AFRICA"
    assert state["active_side"] == "AP"
    removal = next(a for a in generate_legal_actions(state) if a["type"] == "REMOVE_BRITISH_CORPS")
    state = apply_action(state, removal).state
    assert state["units"][removal["unit_id"]]["permanent"]
    assert state["active_side"] == "AP"
    assert state["vp"] == 10
    state = play_event(action_state("WAR_IN_AFRICA", 6), "WAR_IN_AFRICA")
    state = apply_action(state, {"type": "PASS_WAR_IN_AFRICA", "actor": "AP"}).state
    assert state["vp"] == 11


def test_draw_step_refills_hands_before_next_turn():
    state = create_game(seed=4)
    state["turn"] = 2
    state["phase"] = "DRAW"
    state["decision"] = None
    state["players"]["AP"]["hand"] = []
    state["players"]["AP"]["deck"] = ["BLOCKADE", "LUSITANIA"]
    state = advance_automatic_phases(state)
    assert state["phase"] == "END_TURN"
    assert state["players"]["AP"]["hand"] == ["LUSITANIA", "BLOCKADE"]


def test_french_mutiny_penalty_applies_on_qualifying_attack():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "AP"
    state["events"]["FRENCH_MUTINY"] = 3
    state["players"]["AP"]["mandatory_offensive"] = "FR"
    state["units"]["FR_1_ARMY_1"]["location"] = "BRUSSELS"
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["activated"]["ATTACK"] = ["BRUSSELS"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["decision"] = {"kind": "COMBAT", "actor": "AP", "options": []}
    state["decision"]["options"] = legal_combat_actions(state)
    attack = next(a for a in generate_legal_actions(state) if a["type"] == "DECLARE_ATTACK"
                  and a["unit_ids"] == ["FR_1_ARMY_1"] and a["defender_space"] == "LIEGE")
    state = apply_action(state, attack).state
    assert state["vp"] == 11
    assert state["players"]["AP"]["mandatory_offensive"] is None


def test_turn_twenty_ends_after_war_status_without_rp_or_draw():
    state = create_game(seed=4)
    state["turn"] = 20
    state["phase"] = "WAR_STATUS"
    state["decision"] = None
    state["players"]["AP"]["replacement_points"] = {"FR": 2}
    result = advance_automatic_phases(state)
    assert result["phase"] == "GAME_OVER"
    assert result["result"]["reason"] == "TURN_LIMIT"
