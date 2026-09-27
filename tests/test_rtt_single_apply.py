"""RTT 번역에서 확정된 전이를 runner가 다시 적용하지 않는다."""

from pathlib import Path

import pytest

from rtt_test_support import rules_path

from pog_engine import apply_action, create_game
from pog_engine.replay import replay
from pog_engine.rtt_replay import runner
from pog_engine.rtt_replay.bootstrap import bootstrap_historical
from pog_engine.rtt_replay.ids import SourceIds
from pog_engine.rtt_replay.input import load_replay
from pog_engine.rtt_replay.normalize import Intent, normalize_steps


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/replay-251187-resign.json"
RULES = rules_path(__file__)


def test_runner_uses_the_transitions_already_applied_by_translation(monkeypatch):
    def unexpected_reapplication(*_args, **_kwargs):
        raise AssertionError("runner가 번역 완료 행동을 재적용했습니다")

    monkeypatch.setattr(runner, "apply_action", unexpected_reapplication)
    report = runner.run_replay(FIXTURE, RULES)
    assert report.ok, report.first_difference
    assert replay(report.initial_state, list(report.records)) == report.final_state


def test_directly_appended_attack_keeps_its_record_and_final_state():
    from pog_engine.rtt_replay.translate import translate_intent, translate_intent_result

    ids = SourceIds.from_data()
    observations = runner._trace(FIXTURE, RULES)
    source = load_replay(FIXTURE)
    intents = normalize_steps(source.actions, observations[:-1])
    state = bootstrap_historical(source.seed, observations[0]["after"], ids)
    for intent in intents[:7]:
        for action in translate_intent(state, intent, ids):
            state = apply_action(state, action).state

    translated = translate_intent_result(state, intents[7], ids)
    assert any(action["type"] == "DECLARE_ATTACK" for action in translated.actions)
    assert translated.pending_actions == ()
    assert len(translated.records) == len(translated.actions)
    assert replay(state, list(translated.records)) == translated.state


@pytest.mark.parametrize("kind,action_type,destination", [
    ("space", "RETREAT_TO", "PARIS"),
    ("eliminate", "NO_RETREAT_ROUTE", "AP_ELIMINATED_BOX"),
])
def test_terminal_retreat_action_remains_pending_for_runner(kind, action_type, destination):
    from pog_engine.rtt_replay.translate import translate_intent_result

    ids = SourceIds.from_data()
    unit_id = ids.lookup("units", 1)
    destination_number = next(int(number) for number, place in ids.mappings["spaces"].items()
                              if place == destination)
    liege = next(int(number) for number, place in ids.mappings["spaces"].items()
                 if place == "LIEGE")
    before, after = [None, liege], [None, destination_number]
    intent = Intent(42, 42, "Allied Powers", kind, destination_number,
                    {"state": "defender_retreat", "location": before,
                     "attack": {"retreating_pieces": [1]}},
                    {"state": "defender_retreat", "location": after}, ())
    state = create_game(seed=4)
    action = {"type": action_type, "actor": "AP", "unit_id": unit_id}
    if kind == "space":
        action["to"] = destination
    state["decision"] = {"kind": "COMBAT", "actor": "AP", "options": [action]}

    translated = translate_intent_result(state, intent, ids)
    assert translated.actions == translated.pending_actions == (action,)
    assert translated.records == ()
    assert translated.state == state
