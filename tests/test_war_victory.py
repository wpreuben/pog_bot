from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.data import load_data
from pog_engine.rules.combat import legal_combat_actions
from pog_engine.rules.turn import advance_automatic_phases
from pog_engine.rules.victory import game_result
from pog_engine.rules.war import apply_vp_change, resolve_war_status


def at_war_status(turn=2):
    state = create_game(seed=7)
    state["turn"] = turn
    state["phase"] = "WAR_STATUS"
    state["decision"] = None
    return state


def test_commitment_adds_cards_and_turkey_on_turn_two():
    state = at_war_status()
    state["players"]["CP"]["war_status"] = 4
    before = set(state["players"]["CP"]["set_aside"])
    result = resolve_war_status(state)
    cp = result["players"]["CP"]
    assert cp["commitment"] == "LIMITED"
    assert result["war_nations"]["TU"]
    assert cp["shuffle_pending"]
    assert before - set(cp["set_aside"]) == set(cp["deck"]) - set(state["players"]["CP"]["deck"])
    assert state["players"]["CP"]["commitment"] == "MOBILIZATION"


def test_first_turn_does_not_change_commitment_and_total_war_sets_flag():
    state = at_war_status(1)
    state["players"]["CP"]["war_status"] = 11
    state = resolve_war_status(state)
    assert state["players"]["CP"]["commitment"] == "MOBILIZATION"
    state["turn"] = 2
    state = resolve_war_status(state)
    assert state["players"]["CP"]["commitment"] == "TOTAL"
    assert state["flags"]["cp_first_total_war_turn"] == 2


def test_mandatory_offensive_penalties_and_blockade():
    state = at_war_status(4)
    state["players"]["AP"]["mandatory_offensive"] = "FR"
    state["players"]["CP"]["mandatory_offensive"] = "GE"
    state["events"]["BLOCKADE"] = 2
    result = resolve_war_status(state)
    assert result["vp"] == 9  # AP +1, CP -1, 봉쇄 -1
    assert result["players"]["AP"]["mandatory_offensive"] is None
    assert result["players"]["CP"]["mandatory_offensive"] is None


def test_vp_bounds_only_win_in_war_status_phase():
    state = at_war_status()
    state["vp"] = 19
    state["phase"] = "ACTION"
    changed = apply_vp_change(state, 1, "TEST")
    assert changed["vp"] == 20 and game_result(changed) is None
    changed["phase"] = "WAR_STATUS"
    resolved = resolve_war_status(changed)
    assert resolved["result"]["winner"] == "CP"
    assert resolved["result"]["reason"] == "AUTOMATIC_VICTORY"
    assert generate_legal_actions(resolved) == []


def test_armistice_applies_historical_vp_adjustments():
    state = at_war_status()
    state["vp"] = 11
    state["players"]["AP"]["war_status"] = 20
    state["players"]["CP"]["war_status"] = 20
    result = resolve_war_status(state)
    assert result["result"] == {"winner": "AP", "reason": "ARMISTICE", "vp": 11}
    assert result["vp"] == 11  # 미사용 미군 군 2장 +2, 차르 몰락 미사용 -2


def test_turn_twenty_and_brest_litovsk_thresholds():
    state = at_war_status(20)
    state["phase"] = "END_TURN"
    state["vp"] = 12
    state["events"]["FALL_OF_THE_TSAR"] = 15
    state["events"]["USA_REINFORCEMENTS_US_1"] = 18
    state["events"]["USA_REINFORCEMENTS_US_2"] = 19
    result = advance_automatic_phases(state)
    assert result["result"] == {"winner": "AP", "reason": "TURN_LIMIT", "vp": 12}
    state["events"]["TREATY_OF_BREST_LITOVSK"] = 19
    result = advance_automatic_phases(state)
    assert result["result"] == {"winner": "CP", "reason": "TURN_LIMIT", "vp": 12}


def test_war_status_phase_advances_or_finishes():
    state = at_war_status(2)
    assert advance_automatic_phases(state)["phase"] == "REPLACEMENT_AP"
    state["vp"] = 0
    result = advance_automatic_phases(state)
    assert result["phase"] == "GAME_OVER"
    assert result["result"]["winner"] == "AP"


def test_us_and_russian_prerequisite_markers_track_changes():
    state = at_war_status()
    state["players"]["AP"]["war_status"] = 15
    state["players"]["CP"]["war_status"] = 15
    state = resolve_war_status(state)
    assert state["us_entry"] == 1
    russian = [key for key, space in state["spaces"].items()
               if space["vp"] and load_data().spaces[key]["nation"] == "RU"]
    for key in russian[:3]:
        state["spaces"][key]["control"] = "CP"
    state = resolve_war_status(state)
    assert state["russian_capitulation"] == 1
    state["events"]["TSAR_TAKES_COMMAND"] = 3
    state = resolve_war_status(state)
    assert state["russian_capitulation"] == 3


def test_qualifying_attack_fulfills_mandatory_offensive():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["players"]["CP"]["mandatory_offensive"] = "GE"
    state["units"]["BE_1_ARMY_1"]["location"] = "LIEGE"
    state["activated"]["ATTACK"] = ["AACHEN"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["decision"] = {"kind": "COMBAT", "actor": "CP", "options": []}
    state["decision"]["options"] = legal_combat_actions(state)
    action = next(a for a in generate_legal_actions(state) if a["type"] == "DECLARE_ATTACK"
                  and a["unit_ids"] == ["GE_1_ARMY_1"] and a["defender_space"] == "LIEGE")
    result = apply_action(state, action).state
    assert result["players"]["CP"]["mandatory_offensive"] is None
