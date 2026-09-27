"""RTT 첫 Guns of August 전투의 합법 행동 번역."""

import json
from dataclasses import replace
from pathlib import Path
import subprocess

from rtt_test_support import rules_path

import pytest

from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rtt_replay.bootstrap import bootstrap_historical
from pog_engine.rtt_replay.ids import SourceIds
from pog_engine.rtt_replay.input import load_replay
from pog_engine.rtt_replay.normalize import Intent, normalize_steps
from pog_engine.rtt_replay.translate import TranslationError, translate_intent


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/replay-258629.json"
RULES = rules_path(__file__)


@pytest.fixture(scope="module")
def opening():
    replay = load_replay(FIXTURE)
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    return rows, {intent.end_index: intent for intent in normalize_steps(replay.actions, rows)}


def test_sedan_battle_replays_through_ap_card_action(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    record_types = []
    for index in range(26):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            assert action in generate_legal_actions(state), index
            record_types.append(action["type"])
            state = apply_action(state, action).state
    assert "DECLARE_ATTACK" in record_types
    assert "RECORD_FLANK_DIE" in record_types
    assert record_types.count("RECORD_COMBAT_DIE") == 2
    assert state["phase"] == "ACTION"
    assert state["active_side"] == "AP"


def test_flank_roll_refuses_missing_random_observation(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(8):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    flank = intents[8]
    with pytest.raises(TranslationError, match="index 8.*주사위"):
        translate_intent(state, Intent(flank.start_index, flank.end_index, flank.role,
                                       flank.kind, flank.argument, flank.before, flank.after, (),
                                       flank.log_delta), ids)


def test_attack_only_ops_enters_combat_without_movement(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(108):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert state["phase"] == "COMBAT"


def test_two_roll_combat_inputs_replay_through_next_card(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(133):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            assert action in generate_legal_actions(state), index
            state = apply_action(state, action).state
    assert state["phase"] == "ACTION"
    assert state["active_side"] == "CP"


def test_recorded_entrench_and_siege_dice_use_chance_actions(opening):
    _, intents = opening
    ids = SourceIds.from_data()
    from pog_engine.rules.movement import legal_movement_actions
    from pog_engine.rules.forts import legal_siege_actions

    state = create_game(seed=4)
    state["phase"] = "MOVEMENT"
    state["active_side"] = "CP"
    state["events"]["ENTRENCH"] = True
    state["activated"]["MOVE"] = ["KOBLENZ"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP",
                         "options": legal_movement_actions(state)}
    entrench = translate_intent(state, intents[787], ids)
    assert entrench == ({"type": "ENTRENCH", "actor": "CP", "unit_id": "GE_3_ARMY_1"},)
    state = apply_action(state, entrench[0]).state
    state = apply_action(state, translate_intent(state, intents[788], ids)[0]).state
    koblenz = next(int(number) for number, space in ids.mappings["spaces"].items()
                   if space == "KOBLENZ")
    assert translate_intent(state, replace(intents[789], argument=koblenz), ids) == (
        {"type": "RECORD_ENTRENCH_DIE", "actor": "CHANCE", "unit_id": "GE_3_ARMY_1", "value": 6},)

    state = create_game(seed=4)
    state["phase"] = "SIEGE"
    state["active_side"] = "CHANCE"
    state["pending_sieges"] = ["PRZEMYSL"]
    state["spaces"]["PRZEMYSL"]["fort_besieged"] = True
    state["decision"] = {"kind": "SIEGE_ROLL", "actor": "CHANCE",
                         "options": legal_siege_actions(state)}
    assert translate_intent(state, intents[169], ids)[0] == (
        {"type": "RECORD_SIEGE_DIE", "actor": "CHANCE", "space_id": "PRZEMYSL", "value": 2})


def test_pass_flank_and_confirm_end_attack(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(8):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    passed = translate_intent(state, intents[963], ids)
    assert [action["type"] for action in passed] == [
        "SKIP_FLANK", "PASS_COMBAT_CARDS", "PASS_COMBAT_CARDS",
        "RECORD_COMBAT_DIE", "RECORD_COMBAT_DIE"]
    assert [action["value"] for action in passed[-2:]] == [4, 6]
    without_rolls = translate_intent(
        state, replace(intents[963], after={**intents[963].after,
                                             "state": "defender_combat_cards"},
                       random_seeds=()), ids)
    assert [action["type"] for action in without_rolls] == [
        "SKIP_FLANK", "PASS_COMBAT_CARDS"]

    from pog_engine.rules.combat import legal_combat_actions
    state["combat_context"] = None
    state["decision"] = {"kind": "COMBAT", "actor": "CP",
                         "options": legal_combat_actions(state)}
    assert translate_intent(state, intents[1071], ids) == (
        {"type": "END_COMBAT", "actor": "CP"},)
    state["phase"] = "ACTION"
    assert translate_intent(state, intents[1071], ids) == ()


def test_end_action_finishes_pending_advance_before_combat(opening):
    from pog_engine.rules.combat import legal_combat_actions

    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["combat_context"] = {
        "stage": "ADVANCE", "attacker": "CP", "defender": "AP",
        "defender_space": "LIEGE", "attackers": ["GE_1_ARMY_1"],
        "advanced": [], "results": {"CP": 3, "AP": 1},
        "cards": {"CP": [], "AP": []},
    }
    state["decision"] = {"kind": "COMBAT", "actor": "CP",
                         "options": legal_combat_actions(state)}
    intent = replace(intents[1071], kind="end_action",
                     before={**intents[1071].before, "state": "end_operations"},
                     after={**intents[1071].after, "state": "action_phase"})
    assert [action["type"] for action in translate_intent(state, intent, SourceIds.from_data())] == [
        "END_ADVANCE", "END_COMBAT"]


def test_done_advance_ui_can_follow_automatic_combat_finish(opening):
    from pog_engine.rules.combat import legal_combat_actions

    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["combat_context"] = None
    state["decision"] = {"kind": "COMBAT", "actor": "CP",
                         "options": legal_combat_actions(state)}
    intent = replace(intents[1071], kind="done",
                     before={**intents[1071].before, "state": "attacker_advance"},
                     after={**intents[1071].after, "state": "choose_attackers"})
    assert translate_intent(state, intent, SourceIds.from_data()) == ()


def test_losses_done_can_finish_unshown_advance(opening):
    from pog_engine.rules.combat import legal_combat_actions

    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["combat_context"] = {
        "stage": "LOSSES", "attacker": "CP", "defender": "AP",
        "defender_space": "LIEGE", "attackers": ["GE_1_ARMY_1"],
        "defending_units": [], "loss_side": "CP", "loss_remaining": 0,
        "loss_queue": [], "fire_index": 1, "fire_order": ["CP", "AP"],
        "advanced": [], "results": {"CP": 3, "AP": 1},
        "cards": {"CP": [], "AP": []},
    }
    state["decision"] = {"kind": "COMBAT", "actor": "CP",
                         "options": legal_combat_actions(state)}
    intent = replace(intents[1071], kind="done",
                     before={**intents[1071].before, "state": "apply_attacker_losses"},
                     after={**intents[1071].after, "state": "choose_attackers"},
                     random_seeds=())
    assert [action["type"] for action in translate_intent(state, intent, SourceIds.from_data())] == [
        "END_LOSSES", "END_ADVANCE"]


def test_movement_done_enters_attack_selection(opening):
    from pog_engine.rules.movement import legal_movement_actions

    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "MOVEMENT"
    state["active_side"] = "CP"
    state["activated"]["ATTACK"] = ["AACHEN"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP",
                         "options": legal_movement_actions(state)}
    intent = replace(intents[1071], kind="done",
                     before={**intents[1071].before, "state": "choose_pieces_to_move"},
                     after={**intents[1071].after, "state": "choose_attackers"})
    assert [a["type"] for a in translate_intent(state, intent, SourceIds.from_data())] == [
        "END_MOVEMENT"]


def test_flank_done_keeps_attacker_card_window_open(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(8):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    state = apply_action(state, next(a for a in generate_legal_actions(state)
                                     if a["type"] == "SKIP_FLANK")).state
    intent = replace(intents[963], kind="done",
                     after={**intents[963].after, "state": "attacker_combat_cards"},
                     random_seeds=())
    assert translate_intent(state, intent, ids) == ()


def test_mandatory_offensive_confirm_resumes_combat_cards(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(8):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    intent = replace(intents[963], kind="next",
                     before={**intents[963].before, "state": "confirm_mo"},
                     after={**intents[963].after, "state": "defender_combat_cards"},
                     random_seeds=())
    assert [a["type"] for a in translate_intent(state, intent, ids)] == [
        "SKIP_FLANK", "PASS_COMBAT_CARDS"]
    for action_type in ("SKIP_FLANK", "PASS_COMBAT_CARDS"):
        state = apply_action(state, next(a for a in generate_legal_actions(state)
                                         if a["type"] == action_type)).state
    assert state["combat_context"]["stage"] == "DEFENDER_CARDS"
    assert translate_intent(state, intent, ids) == ()


def test_flank_roll_can_advance_to_defender_card_window(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(8):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    intent = replace(intents[8],
                     after={**intents[8].after, "state": "defender_combat_cards"})
    assert [a["type"] for a in translate_intent(state, intent, ids)] == [
        "ATTEMPT_FLANK", "RECORD_FLANK_DIE", "PASS_COMBAT_CARDS"]


def test_flank_can_use_multiple_bonus_spaces(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(8):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    state["units"]["GE_2_ARMY_1"]["location"] = "METZ"
    from pog_engine.rules.combat import legal_combat_actions
    state["decision"]["options"] = legal_combat_actions(state)
    liege = next(source for source, name in ids.mappings["spaces"].items() if name == "LIEGE")
    koblenz = next(source for source, name in ids.mappings["spaces"].items() if name == "KOBLENZ")
    intent = replace(intents[8], log_delta=(f">+1 s{liege}", f">+1 s{koblenz}"))
    assert translate_intent(state, intent, ids)[0]["pinning_space"] == "METZ"


def test_flank_with_no_bonus_space_uses_equivalent_pinning_choice(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(8):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    state["units"]["FR_1_ARMY_1"]["location"] = "AACHEN"
    from pog_engine.rules.combat import flank_modifier, legal_combat_actions
    state["decision"]["options"] = legal_combat_actions(state)
    choices = [a for a in generate_legal_actions(state) if a["type"] == "ATTEMPT_FLANK"]
    assert len(choices) == 2
    assert all(flank_modifier(state, {**state["combat_context"],
                                      "pinning_space": a["pinning_space"]}) == 0 for a in choices)
    intent = replace(intents[8], log_delta=("Flank attempt:", ">B6 Success"))

    assert translate_intent(state, intent, ids)[0] == min(choices, key=lambda a: a["pinning_space"])


def test_draw_done_can_cross_finished_replacement_phase(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "REPLACEMENT_CP"
    state["active_side"] = "CP"
    state["decision"] = None
    intent = replace(intents[187],
                     after={**intents[187].after, "state": "draw_cards_phase"},
                     random_seeds=())
    assert [a["type"] for a in translate_intent(state, intent, SourceIds.from_data())] == [
        "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE", "END_DRAW_DISCARD"]


def test_event_confirmation_can_follow_engine_action_completion(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "ATTRITION"
    state["decision"] = None
    intent = replace(intents[1071], kind="end_action",
                     before={**intents[1071].before, "state": "confirm_event"},
                     after={**intents[1071].after, "state": "attrition_phase"})
    assert translate_intent(state, intent, SourceIds.from_data()) == ()


def test_reinforcement_confirmation_advances_attrition_to_siege(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "ATTRITION"
    state["decision"] = None
    intent = replace(intents[1071], kind="done",
                     before={**intents[1071].before, "state": "place_reinforcements"},
                     after={**intents[1071].after, "state": "siege_phase"})
    assert [a["type"] for a in translate_intent(state, intent, SourceIds.from_data())] == [
        "ADVANCE_AUTOMATIC_PHASE"]
    replacement = replace(intent, after={**intent.after, "state": "replacement_phase"})
    assert [a["type"] for a in translate_intent(state, replacement, SourceIds.from_data())] == [
        "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE"]


def test_event_confirmation_advances_empty_attrition_before_siege(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "ATTRITION"
    state["decision"] = None
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    intent = replace(intents[1071], kind="end_action",
                     before={**intents[1071].before, "state": "confirm_event"},
                     after={**intents[1071].after, "state": "siege_phase"})

    assert [a["type"] for a in translate_intent(state, intent, SourceIds.from_data())] == [
        "ADVANCE_AUTOMATIC_PHASE"]


def test_cancel_retreat_confirmation_keeps_combat_open(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["decision"] = None
    intent = replace(intents[1071], kind="done",
                     before={**intents[1071].before, "state": "cancel_retreat_confirm"},
                     after={**intents[1071].after, "state": "choose_attackers"})

    assert translate_intent(state, intent, SourceIds.from_data()) == ()


def test_replacement_points_end_does_not_resolve_pending_attrition(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "ATTRITION"
    state["decision"] = None
    intent = replace(intents[1071], kind="end_action",
                     before={**intents[1071].before, "state": "rps"},
                     after={**intents[1071].after, "state": "attrition_phase"})
    assert translate_intent(state, intent, SourceIds.from_data()) == ()


def test_end_operations_closes_movement_before_mandatory_offensive_notice(opening):
    from pog_engine.rules.movement import legal_movement_actions

    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "MOVEMENT"
    state["active_side"] = "CP"
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "CP",
                         "options": legal_movement_actions(state)}
    intent = replace(intents[1071], kind="end_action",
                     before={**intents[1071].before, "state": "end_operations"},
                     after={**intents[1071].after, "state": "confirm_mo"})
    assert [a["type"] for a in translate_intent(state, intent, SourceIds.from_data())] == [
        "END_MOVEMENT"]
    attrition = replace(intent, after={**intent.after, "state": "attrition_phase"})
    assert [a["type"] for a in translate_intent(state, attrition, SourceIds.from_data())] == [
        "END_MOVEMENT"]


def test_last_movement_action_resolves_turn_to_replacement(opening):
    from pog_engine.rules.movement import legal_movement_actions

    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "MOVEMENT"
    state["active_side"] = "AP"
    state["action_round"] = 6
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP",
                         "options": legal_movement_actions(state)}
    intent = replace(intents[1071], kind="end_action",
                     before={**intents[1071].before, "state": "end_operations"},
                     after={**intents[1071].after, "state": "replacement_phase"})

    assert [a["type"] for a in translate_intent(state, intent, SourceIds.from_data())] == [
        "END_MOVEMENT", "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE",
        "ADVANCE_AUTOMATIC_PHASE"]


def test_siege_roll_can_follow_automatic_attrition(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "ATTRITION"
    state["decision"] = None
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    ids = SourceIds.from_data()
    liege = next(int(source) for source, name in ids.mappings["spaces"].items()
                 if name == "LIEGE")
    intent = replace(intents[169], argument=liege)
    assert [a["type"] for a in translate_intent(state, intent, ids)] == [
        "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE", "RECORD_SIEGE_DIE",
        "ADVANCE_AUTOMATIC_PHASE"]


def test_last_attrition_choice_reaches_replacement_phase(opening):
    _, intents = opening
    state = create_game(seed=4)
    state["phase"] = "SIEGE"
    state["decision"] = None
    assert [a["type"] for a in translate_intent(state, intents[668], SourceIds.from_data())] == [
        "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE"]


def test_attack_that_rolls_immediately_enters_losses(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(146):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert state["combat_context"]["stage"] == "LOSSES"


def test_attack_unit_order_uses_engine_canonical_legal_action(opening):
    rows, intents = opening
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    for index in range(3):
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    from copy import deepcopy
    before = deepcopy(intents[7].before)
    before["attack"]["pieces"] = [3, 1, 2]
    intent = Intent(7, 7, "Central Powers", "attack", None, before, intents[7].after, ())
    result = translate_intent(state, intent, ids)
    assert result[0]["type"] == "DECLARE_ATTACK"
    assert result[0]["unit_ids"] == ["GE_1_ARMY_1", "GE_2_ARMY_1", "GE_3_ARMY_1"]


def test_cancel_retreat_selects_observed_replacement_corps():
    from pog_engine.rtt_replay.runner import build_draw_schedule

    fixture = ROOT / "tests/fixtures/replay-173637-retreat-prefix.json"
    replay = load_replay(fixture)
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(fixture), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    intents = normalize_steps(replay.actions, rows)
    ids = SourceIds.from_data()
    state = bootstrap_historical(replay.seed, rows[0]["after"], ids)
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(rows, ids)
    for intent in intents[:14]:
        for action in translate_intent(state, intent, ids):
            state = apply_action(state, action).state
    assert translate_intent(state, intents[14], ids) == (
        {"type": "CANCEL_RETREAT", "actor": "AP", "unit_id": "FR_5_ARMY_1",
         "replacement_unit_id": ids.lookup("units", 149)},)


def test_combat_card_from_in_play_uses_existing_card():
    from pog_engine.rtt_replay.runner import build_draw_schedule

    fixture = ROOT / "tests/fixtures/replay-176760-combat-card-prefix.json"
    replay = load_replay(fixture)
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(fixture), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    intents = normalize_steps(replay.actions, rows)
    ids = SourceIds.from_data()
    state = bootstrap_historical(replay.seed, rows[0]["after"], ids)
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(rows, ids)
    for intent in (item for item in intents if item.start_index < 165):
        for action in translate_intent(state, intent, ids):
            state = apply_action(state, action).state
    card_intent = next(item for item in intents if item.start_index == 165)
    assert translate_intent(state, card_intent, ids) == (
        {"type": "USE_COMBAT_CARD", "actor": "AP", "card_id": "PUTNIK"},)


def test_wireless_intercepts_during_flank_is_translated(opening):
    rows, intents = opening
    from pog_engine.rtt_replay.runner import build_draw_schedule

    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(rows, ids)
    for index in range(195):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert translate_intent(state, intents[195], ids) == (
        {"type": "PLAY_COMBAT_CARD", "actor": "CP", "card_id": "WIRELESS_INTERCEPTS"},)


def test_besieging_enemy_does_not_get_forts_combat_factor(opening):
    rows, intents = opening
    from pog_engine.rtt_replay.runner import build_draw_schedule
    from pog_engine.rules.combat import combat_snapshot

    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(rows, ids)
    for index in range(200):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    snapshot = combat_snapshot(state, state["combat_context"])
    assert snapshot["strengths"]["AP"] == 1


def test_reinforcement_placement_uses_observed_unit_and_space(opening):
    rows, intents = opening
    from pog_engine.rtt_replay.runner import build_draw_schedule

    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(rows, ids)
    for index in range(209):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert translate_intent(state, intents[209], ids) == (
        {"type": "PLACE_REINFORCEMENT", "actor": "AP", "unit_id": "BR_2_ARMY_1", "to": "LONDON"},)


def test_fort_destruction_uses_defender_loss_completion(opening):
    rows, intents = opening
    from pog_engine.rtt_replay.runner import build_draw_schedule

    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(rows, ids)
    for index in range(235):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert translate_intent(state, intents[235], ids) == ({"type": "END_LOSSES", "actor": "AP"},)
