"""Historical 캠페인에서 발견한 전투·후퇴 규칙 회귀 사례."""

from pog_engine import apply_action, create_game, generate_legal_actions
def choose(state, action_type, **fields):
    action = next(action for action in generate_legal_actions(state)
                  if action["type"] == action_type
                  and all(action.get(key) == value for key, value in fields.items()))
    return apply_action(state, action).state


def test_guns_of_august_sedan_retreat_canceled_with_french_corps():
    state = create_game(seed=4)
    state = choose(state, "RECORD_DIE_RESULT", value=5)
    state = choose(state, "RECORD_DIE_RESULT", value=5)
    state = choose(state, "PLAY_CARD", card_id="GUNS_OF_AUGUST", mode="EVENT")
    attackers = ["GE_1_ARMY_1", "GE_2_ARMY_1", "GE_3_ARMY_1"]
    state = choose(state, "DECLARE_ATTACK", unit_ids=attackers, defender_space="SEDAN")
    state = choose(state, "ATTEMPT_FLANK", pinning_space="LIEGE")
    state = choose(state, "RECORD_FLANK_DIE", value=3)
    state = choose(state, "PASS_COMBAT_CARDS")
    state = choose(state, "PASS_COMBAT_CARDS")
    state = choose(state, "RECORD_COMBAT_DIE", side="CP", value=2)
    assert state["combat_context"]["results"]["CP"] == 5
    state = choose(state, "TAKE_LOSS", unit_id="FR_5_ARMY_1")
    state = choose(state, "END_LOSSES")
    state = choose(state, "RECORD_COMBAT_DIE", side="AP", value=1)
    assert state["combat_context"]["results"]["AP"] == 1
    state = choose(state, "END_LOSSES")

    choices = [action for action in generate_legal_actions(state)
               if action["type"] == "CANCEL_RETREAT"
               and action["unit_id"] == "FR_5_ARMY_1"]
    assert any(action.get("replacement_unit_id") for action in choices)
    state = apply_action(state, choices[0]).state
    replacement = choices[0]["replacement_unit_id"]
    assert state["units"]["FR_5_ARMY_1"]["location"] is None
    assert state["units"][replacement]["location"] == "SEDAN"


def test_russian_armies_can_follow_two_space_retreat_to_lemberg():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "AP"
    state["combat_context"] = {
        "attacker": "AP", "defender": "CP", "defender_space": "TARNOPOL",
        "attackers": ["RU_3_ARMY_1", "RU_8_ARMY_1"], "stage": "ADVANCE",
        "advanced": [], "retreat_total": 2, "retreat_path": ["LEMBERG", "PRZEMYSL"],
        "cards": {"AP": [], "CP": []}, "results": {"AP": 3, "CP": 1},
    }
    state["units"]["AH_3_ARMY_1"]["location"] = "PRZEMYSL"
    state["decision"] = {"kind": "COMBAT", "actor": "AP", "options": []}
    from pog_engine.rules.combat import legal_combat_actions

    state["decision"]["options"] = legal_combat_actions(state)
    for uid in ("RU_3_ARMY_1", "RU_8_ARMY_1"):
        state = choose(state, "ADVANCE_UNIT", unit_id=uid)
    for uid in ("RU_3_ARMY_1", "RU_8_ARMY_1"):
        state = choose(state, "ADVANCE_UNIT", unit_id=uid, to="LEMBERG")
    assert state["units"]["RU_3_ARMY_1"]["location"] == "LEMBERG"
    assert state["units"]["RU_8_ARMY_1"]["location"] == "LEMBERG"
    assert state["spaces"]["LEMBERG"]["control"] == "AP"


def test_tarnopol_battle_records_retreat_path_for_advance():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "AP"
    state["activated"]["ATTACK"] = ["DUBNO", "KAMENETS_PODOLSKI"]
    state["decision"] = {"kind": "COMBAT", "actor": "AP", "options": []}
    from pog_engine.rules.combat import legal_combat_actions

    state["decision"]["options"] = legal_combat_actions(state)
    steps = [
        ("DECLARE_ATTACK", {"unit_ids": ["RU_3_ARMY_1", "RU_8_ARMY_1"], "defender_space": "TARNOPOL"}),
        ("ATTEMPT_FLANK", {"pinning_space": "KAMENETS_PODOLSKI"}),
        ("RECORD_FLANK_DIE", {"value": 3}),
        ("PASS_COMBAT_CARDS", {}), ("PASS_COMBAT_CARDS", {}),
        ("RECORD_COMBAT_DIE", {"side": "AP", "value": 1}),
        ("TAKE_LOSS", {"unit_id": "AH_3_ARMY_1"}),
        ("END_LOSSES", {}),
        ("RECORD_COMBAT_DIE", {"side": "CP", "value": 2}),
        ("END_LOSSES", {}),
        ("RETREAT_TO", {"to": "LEMBERG"}),
        ("RETREAT_TO", {"to": "PRZEMYSL"}),
    ]
    for kind, fields in steps:
        state = choose(state, kind, **fields)
    assert state["combat_context"]["retreat_progress"]["AH_3_ARMY_1"]["path"] == [
        "LEMBERG", "PRZEMYSL"
    ]
    for uid in ("RU_3_ARMY_1", "RU_8_ARMY_1"):
        state = choose(state, "ADVANCE_UNIT", unit_id=uid)
        state = choose(state, "ADVANCE_UNIT", unit_id=uid, to="LEMBERG")
    assert all(state["units"][uid]["location"] == "LEMBERG"
               for uid in ("RU_3_ARMY_1", "RU_8_ARMY_1"))


def test_withdrawal_allows_russian_units_to_split_retreat():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["RUC_CORPS_1"]["location"] = "KOVNO"
    state["units"]["GE_8_ARMY_1"]["location"] = "INSTERBERG"
    state["combat_context"] = {
        "attacker": "CP", "defender": "AP", "defender_space": "KOVNO",
        "attackers": ["GE_8_ARMY_1"], "defending_units": ["RU_1_ARMY_1", "RUC_CORPS_1"],
        "stage": "RETREAT", "advanced": [],
        "retreat_total": 1, "retreat_remaining": 1, "retreat_location": "KOVNO",
        "cards": {"AP": [], "CP": []}, "results": {"CP": 5, "AP": 3},
    }
    state["decision"] = {"kind": "COMBAT", "actor": "AP", "options": []}
    from pog_engine.rules.combat import legal_combat_actions

    state["decision"]["options"] = legal_combat_actions(state)
    state = choose(state, "RETREAT_TO", unit_id="RU_1_ARMY_1", to="GRODNO")
    assert state["combat_context"]["stage"] == "RETREAT"
    state = choose(state, "RETREAT_TO", unit_id="RUC_CORPS_1", to="VILNA")
    assert state["units"]["RU_1_ARMY_1"]["location"] == "GRODNO"
    assert state["units"]["RUC_CORPS_1"]["location"] == "VILNA"


def test_second_advance_cannot_enter_fort_without_siege_force():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["units"]["GEC_CORPS_1"]["location"] = "LODZ"
    state["units"]["GEC_CORPS_1"]["reduced"] = False
    state["combat_context"] = {
        "attacker": "CP", "defender": "AP", "defender_space": "LODZ",
        "attackers": ["GEC_CORPS_1"], "stage": "ADVANCE", "advanced": ["GEC_CORPS_1"],
        "retreat_total": 2, "retreat_path": ["WARSAW", "IVANGOROD"],
        "cards": {"AP": [], "CP": []}, "results": {"CP": 3, "AP": 1},
    }
    state["decision"] = {"kind": "COMBAT", "actor": "CP", "options": []}
    from pog_engine.rules.combat import legal_combat_actions

    options = legal_combat_actions(state)
    assert not any(action["type"] == "ADVANCE_UNIT" and action.get("to") == "WARSAW"
                   for action in options)
