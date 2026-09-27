"""RTT 화면 행동을 현재 Python 합법 행동으로 번역."""

import json
from pathlib import Path
import subprocess

from rtt_test_support import rules_path

import pytest

from pog_engine import apply_action, generate_legal_actions
from pog_engine.rtt_replay.bootstrap import bootstrap_historical
from pog_engine.rtt_replay.ids import SourceIds
from pog_engine.rtt_replay.input import load_replay
from pog_engine.rtt_replay.normalize import Intent, normalize_steps
from pog_engine.rules.cards import legal_card_actions


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/replay-258629.json"
RULES = rules_path(__file__)


@pytest.fixture(scope="module")
def trace():
    replay = load_replay(FIXTURE)
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    return rows, {intent.end_index: intent for intent in normalize_steps(replay.actions, rows)}


def action_state(trace, side):
    rows, _ = trace
    state = bootstrap_historical(10762091171, rows[0]["after"], SourceIds.from_data())
    state["phase"] = "ACTION"
    state["active_side"] = side
    state["action_round"] = 2
    state["decision"] = {"kind": "ACTION_PHASE", "actor": side,
                         "options": legal_card_actions(state, side)}
    return state


def apply_all(state, actions):
    for action in actions:
        assert action in generate_legal_actions(state)
        state = apply_action(state, action).state
    return state


def test_setup_rolls_and_first_event_use_legal_actions(trace):
    from pog_engine.rtt_replay.translate import translate_intent

    rows, intents = trace
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    actions = translate_intent(state, intents[0], ids)
    assert [action["value"] for action in actions] == [4, 6]
    state = apply_all(state, actions)
    assert state["phase"] == "ACTION"
    assert translate_intent(state, intents[1], ids) == ()
    event = translate_intent(state, intents[2], ids)
    assert event == ({"type": "PLAY_CARD", "actor": "CP",
                      "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"},)


def test_ops_activation_and_single_unit_move(trace):
    from pog_engine.rtt_replay.translate import translate_intent

    _, intents = trace
    ids = SourceIds.from_data()
    state = action_state(trace, "AP")
    card = translate_intent(state, intents[26], ids)
    assert card[0]["card_id"] == "ENTRENCH_AP"
    assert card[0]["mode"] == "OPS"
    state = apply_all(state, card)
    for index in (27, 28, 29):
        translated = translate_intent(state, intents[index], ids)
        assert translated[0]["type"] == "ACTIVATE_SPACE"
        state = apply_all(state, translated)
    assert state["phase"] == "MOVEMENT"
    assert translate_intent(state, intents[30], ids) == ()
    move = translate_intent(state, intents[31], ids)
    assert move == ({"type": "MOVE", "actor": "AP", "unit_id": ids.lookup("units", 52),
                     "to": ids.lookup("spaces", 161)},)
    state = apply_all(state, move)
    stop = translate_intent(state, intents[37], ids)
    assert stop == (
        {"type": "STOP_MOVING_UNIT", "actor": "AP"},)
    state = apply_all(state, stop)
    assert translate_intent(state, intents[42], ids) == (
        {"type": "END_MOVEMENT", "actor": "AP"},)


def test_sr_unit_and_destination_and_rp_card(trace):
    from pog_engine.rtt_replay.translate import translate_intent

    _, intents = trace
    ids = SourceIds.from_data()
    state = action_state(trace, "CP")
    sr_card = translate_intent(state, intents[79], ids)
    assert sr_card == ({"type": "PLAY_CARD", "actor": "CP",
                        "card_id": "ENTRENCH_CP", "mode": "SR"},)
    state = apply_all(state, sr_card)
    select = translate_intent(state, intents[80], ids)
    assert select == ({"type": "SELECT_SR_UNIT", "actor": "CP",
                       "unit_id": ids.lookup("units", 89)},)
    state = apply_all(state, select)
    destination = ids.lookup("spaces", 99)
    if {"type": "SR_TO", "actor": "CP", "to": destination} in generate_legal_actions(state):
        assert translate_intent(state, intents[81], ids) == (
            {"type": "SR_TO", "actor": "CP", "to": destination},)

    state = action_state(trace, "CP")
    rp = translate_intent(state, intents[133], ids)
    assert rp == ({"type": "PLAY_CARD", "actor": "CP",
                   "card_id": "GERMAN_REINFORCEMENTS_GE_9", "mode": "RP"},)


def test_unmatched_and_ambiguous_candidates_report_index(trace):
    from pog_engine.rtt_replay.translate import TranslationError, translate_intent

    _, intents = trace
    state = action_state(trace, "AP")
    with pytest.raises(TranslationError, match="index 26"):
        translate_intent(state, Intent(26, 26, "Allied Powers", "play_ops", 999,
                                       intents[26].before, intents[26].after, ()), SourceIds.from_data())
    state["decision"]["options"] = [
        {"type": "PLAY_CARD", "actor": "AP", "card_id": "ENTRENCH_AP", "mode": "OPS", "choice": 1},
        {"type": "PLAY_CARD", "actor": "AP", "card_id": "ENTRENCH_AP", "mode": "OPS", "choice": 2},
    ]
    with pytest.raises(TranslationError, match="index 26.*후보 2개"):
        translate_intent(state, intents[26], SourceIds.from_data())
    with pytest.raises(TranslationError, match="index 777.*bogus"):
        translate_intent(state, Intent(777, 777, "Allied Powers", "space", 31,
                                       {"state": "bogus"}, {"state": "bogus"}, ()),
                         SourceIds.from_data())


def test_accept_retreat_is_already_represented_by_combat_stage():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import TranslationError, translate_intent

    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["combat_context"] = {"stage": "RETREAT"}
    intent = Intent(15, 15, "Allied Powers", "retreat", None,
                    {"state": "cancel_retreat"}, {"state": "defender_retreat"}, ())
    assert translate_intent(state, intent, SourceIds.from_data()) == ()

    state["combat_context"]["stage"] = "LOSSES"
    with pytest.raises(TranslationError, match="index 15.*retreat"):
        translate_intent(state, intent, SourceIds.from_data())


def test_supply_warning_ui_actions_leave_engine_state_unchanged():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent

    state = create_game(seed=4)
    ids = SourceIds.from_data()
    for intent in (
        Intent(27, 27, "Allied Powers", "flag_supply_warnings", None,
               {"state": "end_operations"}, {"state": "flag_supply_warnings"}, ()),
        Intent(28, 28, "Allied Powers", "space", 12,
               {"state": "flag_supply_warnings"}, {"state": "flag_supply_warnings"}, ()),
        Intent(29, 29, "Allied Powers", "done", None,
               {"state": "flag_supply_warnings"}, {"state": "end_operations"}, ()),
        Intent(30, 30, "Allied Powers", "done", None,
               {"state": "review_supply_warnings"}, {"state": "action_phase"}, ()),
    ):
        assert translate_intent(state, intent, ids) == ()


def test_final_end_rp_draws_and_starts_next_turn_before_mo_confirmation():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.replacements import begin_replacement_phase

    state = create_game(seed=4)
    state["turn"] = 1
    state["action_round"] = 6
    for side in ("AP", "CP"):
        state["players"][side]["actions_taken"] = 6
        state["players"][side]["hand"] = []
    state["players"]["CP"]["replacement_points"] = {"GE": 1}
    state = begin_replacement_phase(state, "CP")
    intent = Intent(191, 191, "Central Powers", "end_rp", None,
                    {"state": "replacement_phase", "turn": 1},
                    {"state": "confirm_mo", "turn": 2}, (2, 1))

    actions = translate_intent(state, intent, SourceIds.from_data())
    assert [action["type"] for action in actions] == [
        "END_REPLACEMENT", "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE",
        "RECORD_DIE_RESULT", "RECORD_DIE_RESULT",
    ]
    assert [action["value"] for action in actions[-2:]] == [3, 2]
    state = apply_all(state, actions)
    assert (state["turn"], state["phase"]) == (2, "ACTION")
    assert (state["players"]["AP"]["actions_taken"],
            state["players"]["CP"]["actions_taken"]) == (0, 0)
    next_intent = Intent(192, 192, "Central Powers", "next", None,
                         {"state": "confirm_mo"}, {"state": "action_phase"}, ())
    assert translate_intent(state, next_intent, SourceIds.from_data()) == ()


def test_dropping_only_piece_in_move_stack_stops_moving_unit():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.movement import legal_movement_actions

    state = create_game(seed=4)
    state["phase"] = "MOVEMENT"
    state["active_side"] = "AP"
    state["movement"] = {"unit": "SB_2_ARMY_1", "stack": None, "spent": 1, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP",
                         "options": legal_movement_actions(state)}
    ids = SourceIds.from_data()
    piece_id = next(int(key) for key, value in ids.mappings["units"].items()
                    if value == "SB_2_ARMY_1")
    intent = Intent(60, 60, "Allied Powers", "piece", piece_id,
                    {"state": "move_stack", "move": {"pieces": [piece_id]}},
                    {"state": "choose_move_space", "move": {"pieces": []}}, ())
    assert translate_intent(state, intent, ids) == (
        {"type": "STOP_MOVING_UNIT", "actor": "AP"},)


def test_dropping_one_piece_from_moving_stack_keeps_other_moving():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.movement import legal_movement_actions

    state = create_game(seed=4)
    state["phase"] = "MOVEMENT"
    state["active_side"] = "AP"
    for uid in ("RU_5_ARMY_1", "RU_11_ARMY_1"):
        state["units"][uid]["location"] = "KIEV"
    state["movement"] = {"unit": None, "stack": ["RU_11_ARMY_1", "RU_5_ARMY_1"],
                         "spent": 1, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP",
                         "options": legal_movement_actions(state)}
    ids = SourceIds.from_data()
    first = next(int(key) for key, value in ids.mappings["units"].items()
                 if value == "RU_5_ARMY_1")
    second = next(int(key) for key, value in ids.mappings["units"].items()
                  if value == "RU_11_ARMY_1")
    intent = Intent(10, 10, "Allied Powers", "piece", first,
                    {"state": "move_stack", "move": {"pieces": [first, second]}},
                    {"state": "move_stack", "move": {"pieces": [second]}}, ())
    assert translate_intent(state, intent, ids) == (
        {"type": "DROP_MOVING_UNIT", "actor": "AP", "unit_id": "RU_5_ARMY_1"},)


def test_landwehr_piece_and_finish_use_engine_actions():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.events.operations import _LANDWEHR

    state = create_game(seed=4)
    state["phase"] = "LANDWEHR"
    state["active_side"] = "CP"
    state["landwehr"] = {"spent": 0}
    state["units"]["GE_1_ARMY_1"]["reduced"] = True
    state["decision"] = {"kind": "LANDWEHR", "actor": "CP",
                         "options": _LANDWEHR.legal_choices(state)}
    ids = SourceIds.from_data()
    piece_id = next(int(key) for key, value in ids.mappings["units"].items()
                    if value == "GE_1_ARMY_1")
    flip = Intent(47, 47, "Central Powers", "piece", piece_id,
                  {"state": "landwehr"}, {"state": "landwehr"}, ())
    assert translate_intent(state, flip, ids) == (
        {"type": "LANDWEHR_FLIP", "actor": "CP", "unit_id": "GE_1_ARMY_1"},)
    finish = Intent(48, 48, "Central Powers", "end_action", None,
                    {"state": "landwehr"}, {"state": "action_phase"}, ())
    assert translate_intent(state, finish, ids) == ({"type": "END_LANDWEHR", "actor": "CP"},)


def test_rtt_combat_selection_controls_do_not_change_engine_state():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent

    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["combat_context"] = None
    no_attack = Intent(100, 100, "Central Powers", "no_attack", None,
                       {"state": "choose_attackers"}, {"state": "choose_attackers"}, ())
    assert translate_intent(state, no_attack, SourceIds.from_data()) == ()

    state["combat_context"] = {"stage": "ADVANCE"}
    stop = Intent(101, 101, "Central Powers", "stop", None,
                  {"state": "attacker_advance"}, {"state": "attacker_advance"}, ())
    assert translate_intent(state, stop, SourceIds.from_data()) == ()


def test_single_operation_translates_to_cardless_engine_action(trace):
    from pog_engine.rtt_replay.translate import translate_intent

    state = action_state(trace, "AP")
    state["decision"]["options"] = legal_card_actions(state, "AP")
    intent = Intent(204, 204, "Allied Powers", "single_op", None,
                    {"state": "action_phase"}, {"state": "activate_spaces"}, ())
    assert translate_intent(state, intent, SourceIds.from_data()) == (
        {"type": "SINGLE_OP", "actor": "AP"},)


def test_skipping_remaining_ops_finishes_empty_action_round():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.ops import legal_ops_actions

    state = create_game(seed=4)
    state["phase"] = "OPS"
    state["active_side"] = "CP"
    state["ops_remaining"] = 1
    state["decision"] = {"kind": "OPS", "actor": "CP", "options": legal_ops_actions(state)}
    intent = Intent(227, 227, "Central Powers", "skip", None,
                    {"state": "activate_spaces", "ops": 1, "activated": {"move": [], "attack": []}},
                    {"state": "end_operations", "ops": 0, "activated": {"move": [], "attack": []}}, ())

    actions = translate_intent(state, intent, SourceIds.from_data())
    assert actions == ({"type": "FINISH_ACTIVATION", "actor": "CP"},
                       {"type": "END_MOVEMENT", "actor": "CP"})
    assert apply_all(state, actions)["phase"] == "ACTION"


def test_replacement_choice_advances_pending_automatic_phases():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent

    state = create_game(seed=4)
    state["phase"] = "SIEGE"
    state["decision"] = None
    state["players"]["AP"]["replacement_points"]["FR"] = 1
    state["units"]["FR_5_ARMY_1"]["reduced"] = True
    ids = SourceIds.from_data()
    piece_id = next(int(key) for key, value in ids.mappings["units"].items()
                    if value == "FR_5_ARMY_1")
    intent = Intent(217, 217, "Allied Powers", "piece", piece_id,
                    {"state": "replacement_phase", "reduced": [piece_id], "location": []},
                    {"state": "replacement_phase", "reduced": [], "location": []}, ())
    assert [action["type"] for action in translate_intent(state, intent, ids)] == [
        "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE", "FLIP_UNIT"]


def test_sr_end_action_advances_through_war_status_when_rtt_reaches_replacements():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.sr import legal_sr_actions

    state = create_game(seed=4)
    state["turn"] = 2
    state["action_round"] = 6
    state["phase"] = "SR"
    state["active_side"] = "AP"
    state["players"]["CP"]["actions_taken"] = 6
    state["players"]["AP"]["actions_taken"] = 5
    state["players"]["AP"]["war_status"] = 4
    state["sr"] = {"unit": None, "done": []}
    state["sr_remaining"] = 4
    state["decision"] = {"kind": "SR", "actor": "AP", "options": legal_sr_actions(state)}
    intent = Intent(464, 464, "Allied Powers", "end_action", None,
                    {"state": "choose_sr_unit"}, {"state": "replacement_phase"}, ())

    actions = translate_intent(state, intent, SourceIds.from_data())
    assert [action["type"] for action in actions] == [
        "END_SR", "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE",
        "ADVANCE_AUTOMATIC_PHASE",
    ]
    result = apply_all(state, actions)
    assert result["phase"] == "REPLACEMENT_AP"
    assert result["players"]["AP"]["commitment"] == "LIMITED"


def test_sr_end_action_confirmation_in_same_turn_needs_no_new_roll():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.sr import legal_sr_actions

    state = create_game(seed=4)
    state["turn"] = 2
    state["phase"] = "SR"
    state["active_side"] = "CP"
    state["sr"] = {"unit": None, "done": []}
    state["sr_remaining"] = 4
    state["decision"] = {"kind": "SR", "actor": "CP", "options": legal_sr_actions(state)}
    intent = Intent(174, 174, "Central Powers", "end_action", None,
                    {"state": "choose_sr_unit", "turn": 2},
                    {"state": "confirm_mo", "turn": 2}, ())

    assert [action["type"] for action in translate_intent(
        state, intent, SourceIds.from_data())] == ["END_SR"]


def test_end_operations_advances_through_new_turn_before_rtt_confirmation():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent

    state = create_game(seed=4)
    state["turn"] = 2
    state["phase"] = "ATTRITION"
    state["active_side"] = "CHANCE"
    state["decision"] = None
    state["players"]["AP"]["war_status"] = 4
    for side in ("AP", "CP"):
        state["players"][side]["actions_taken"] = 6
        state["players"][side]["hand"] = []
    intent = Intent(319, 319, "Allied Powers", "end_action", None,
                    {"state": "end_operations"}, {"state": "confirm_mo"}, (2, 1))

    actions = translate_intent(state, intent, SourceIds.from_data())
    assert [action["type"] for action in actions] == [
        "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE",
        "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE", "ADVANCE_AUTOMATIC_PHASE",
        "ADVANCE_AUTOMATIC_PHASE", "RECORD_DIE_RESULT", "RECORD_DIE_RESULT",
    ]
    result = apply_all(state, actions)
    assert (result["turn"], result["phase"]) == (3, "ACTION")
    assert result["players"]["AP"]["commitment"] == "LIMITED"


def test_movement_end_action_advances_through_new_turn_before_rtt_confirmation():
    from pog_engine import create_game
    from pog_engine.rtt_replay.translate import translate_intent
    from pog_engine.rules.movement import legal_movement_actions

    state = create_game(seed=4)
    state["turn"] = 2
    state["action_round"] = 6
    state["phase"] = "MOVEMENT"
    state["active_side"] = "AP"
    state["players"]["AP"]["actions_taken"] = 5
    state["players"]["AP"]["war_status"] = 4
    state["players"]["CP"]["actions_taken"] = 6
    for side in ("AP", "CP"):
        state["players"][side]["hand"] = []
    state["activated"] = {"MOVE": [], "ATTACK": []}
    state["movement"] = {"unit": None, "stack": None, "spent": 0, "done": []}
    state["decision"] = {"kind": "MOVEMENT", "actor": "AP",
                         "options": legal_movement_actions(state)}
    intent = Intent(319, 319, "Allied Powers", "end_action", None,
                    {"state": "end_operations", "turn": 2},
                    {"state": "confirm_mo", "turn": 3}, (2, 1))

    actions = translate_intent(state, intent, SourceIds.from_data())
    assert actions[0]["type"] == "END_MOVEMENT"
    result = apply_all(state, actions)
    assert (result["turn"], result["phase"]) == (3, "ACTION")
    assert result["players"]["AP"]["commitment"] == "LIMITED"


def test_combat_end_action_reaches_war_status_before_next_rtt_confirmation():
    from pog_engine.rtt_replay.runner import run_replay

    replay = ROOT.parents[1] / "replays/176981.json"
    report = run_replay(replay, RULES)
    assert report.final_state["players"]["AP"]["commitment"] == "LIMITED"
    assert report.first_difference is None or report.first_difference.path != "$.players.AP.commitment"


def test_resignation_uses_replay_role_even_out_of_turn(trace):
    from pog_engine.rtt_replay.translate import translate_intent

    state = action_state(trace, "CP")
    intent = Intent(9, 9, "Allied Powers", ".resign", "Central Powers",
                    {"state": "action_phase"}, {"state": "game_over"}, ())
    action, = translate_intent(state, intent, SourceIds.from_data())
    assert action == {"type": "RESIGN", "actor": "AP"}
    assert apply_action(state, action).state["result"]["winner"] == "CP"
