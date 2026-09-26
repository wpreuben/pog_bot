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
