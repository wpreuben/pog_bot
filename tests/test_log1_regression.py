"""사용자가 제공한 LOG1 첫 전투의 규칙 재현."""

from pathlib import Path
import re

from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.combat import crt_result


LOG1 = Path(__file__).parent / "fixtures" / "LOG1.txt"


def test_log1_all_recorded_fire_results_are_possible_on_crt():
    """기록에 주사위 눈이 없으므로 각 결과를 낼 수 있는 눈의 존재를 확인한다."""
    lines = LOG1.read_text(encoding="utf-8").splitlines()
    checked = 0
    for index, line in enumerate(lines):
        match = re.search(r"×\s*(\d+)\s*\((Army|Corps)\)\s*=\s*(\d+)", line)
        if match is None:
            continue
        column, table, result = int(match[1]), match[2].upper(), int(match[3])
        modifier = 0
        for earlier in lines[max(0, index - 3):index]:
            drm = re.match(r"\s*([+-]\d+)\s+(?!VP)", earlier)
            if drm:
                modifier += int(drm[1])
        assert any(crt_result(table, column, die + modifier) == result for die in range(1, 7)), (
            index + 1, line
        )
        checked += 1
    assert checked == 60


def choose(state, action_type, **fields):
    action = next(action for action in generate_legal_actions(state)
                  if action["type"] == action_type
                  and all(action.get(key) == value for key, value in fields.items()))
    return apply_action(state, action).state


def test_log1_guns_of_august_sedan_retreat_canceled_with_french_corps():
    log = LOG1.read_text(encoding="utf-8")
    assert "(FR 5) in Sedan broke to FRc(6,0)" in log

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


def test_log1_russian_armies_can_follow_two_space_retreat_to_lemberg():
    log = LOG1.read_text(encoding="utf-8")
    assert "(AH 3) → Lemberg, Przemysl" in log
    assert "RU 3, RU 8 → Lemberg" in log

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


def test_log1_withdrawal_allows_russian_units_to_split_retreat():
    log = LOG1.read_text(encoding="utf-8")
    assert "RU 1 → Grodno" in log
    assert "RUc → Vilna" in log

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
