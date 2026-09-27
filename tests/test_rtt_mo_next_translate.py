"""RTT 관측기가 남긴 지연 AP MO 확인 행만 무동작으로 번역한다."""

from copy import deepcopy
from pathlib import Path

import pytest

from rtt_test_support import rules_path

from pog_engine.rtt_replay.ids import SourceIds
from pog_engine.rtt_replay.normalize import Intent
from pog_engine.rtt_replay.runner import run_replay
from pog_engine.rtt_replay.translate import TranslationError, translate_intent


ROOT = Path(__file__).resolve().parents[1]
RULES = rules_path(__file__)


def _intent(*, role="Allied Powers", after_change=None, random_seeds=(), log_delta=()):
    before = {"state": "action_phase", "turn": 1, "active": "Allied Powers",
              "ap": {"actions": [1]}, "cp": {"actions": [1]}}
    after = deepcopy(before)
    if after_change:
        after.update(after_change)
    return Intent(25, 25, role, "next", None, before, after, random_seeds, log_delta)


def test_identical_ap_action_phase_next_is_noop():
    state = {"phase": "ACTION", "active_side": "AP", "decision": {"kind": "ACTION_PHASE"}}
    assert translate_intent(state, _intent(), SourceIds.from_data()) == ()


@pytest.mark.parametrize("changes", [
    {"role": "Central Powers"},
    {"after_change": {"turn": 2}},
    {"random_seeds": (1,)},
    {"log_delta": ("changed",)},
])
def test_other_next_is_not_silently_ignored(changes):
    state = {"phase": "ACTION", "active_side": "AP", "decision": {"kind": "ACTION_PHASE"}}
    with pytest.raises(TranslationError):
        translate_intent(state, _intent(**changes), SourceIds.from_data())


@pytest.mark.parametrize("game_id", [166206, 166209, 166239, 166243, 166569])
def test_legacy_mo_replay_passes_delayed_next(game_id):
    report = run_replay(ROOT / f"tests/fixtures/rtt-mo-{game_id}.json", RULES)
    assert report.ok, report.first_difference
