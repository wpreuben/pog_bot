"""RTT 초기 카드 순서와 되돌리기 정제."""

import json
from copy import deepcopy
from pathlib import Path
import subprocess

from rtt_test_support import rules_path

import pytest

from pog_engine.rtt_replay.input import ReplayStep, load_replay
from pog_engine.rtt_replay.ids import SourceIds
from pog_engine.rtt_replay.projection import first_difference, project_engine, project_rtt


ROOT = Path(__file__).resolve().parents[1]
RULES = rules_path(__file__)
FIXTURE = ROOT / "tests/fixtures/replay-258629.json"


def rtt_setup():
    code = "const r=require(process.argv[1]);process.stdout.write(JSON.stringify(r.setup(10762091171,'Historical',{no_supply_warnings:true})))"
    return json.loads(subprocess.run(["node", "-e", code, str(RULES)],
                                     capture_output=True, text=True, check=True).stdout)


def test_bootstrap_keeps_rtt_cards_and_checks_equivalent_corps():
    from pog_engine.rtt_replay.bootstrap import bootstrap_historical

    ids = SourceIds.from_data()
    rtt = rtt_setup()
    state = bootstrap_historical(10762091171, rtt, ids)
    assert state["players"]["CP"]["hand"][0] == "GUNS_OF_AUGUST"
    assert state["players"]["AP"]["deck"] == project_rtt(rtt, ids)["players"]["AP"]["deck"]
    assert state["units"]["ITC_CORPS_1"]["location"] == "AP_RESERVE_BOX"
    assert first_difference(project_rtt(rtt, ids), project_engine(state)) is None


def test_bootstrap_rejects_real_initial_board_difference():
    from pog_engine.rtt_replay.bootstrap import BootstrapError, bootstrap_historical

    rtt = rtt_setup()
    rtt["location"][1] = 1  # GE 1군을 런던으로 옮기면 다른 유닛과 동형 교체로 설명할 수 없다.
    with pytest.raises(BootstrapError, match="GE_1_ARMY_1"):
        bootstrap_historical(10762091171, rtt, SourceIds.from_data())


def test_undo_removes_uncommitted_choice_and_preserves_source_index():
    from pog_engine.rtt_replay.normalize import normalize_steps

    steps = (ReplayStep(1, "Central Powers", "play_ops", 66),
             ReplayStep(2, "Central Powers", "undo", None),
             ReplayStep(3, "Central Powers", "play_event", 66))
    observations = [
        {"index": 1, "before": {"state": "card"}, "after": {"state": "ops"},
         "random": {"before": 4, "after": 4, "seeds": []}},
        {"index": 2, "before": {"state": "ops"}, "after": {"state": "card"},
         "random": {"before": 4, "after": 4, "seeds": []}},
        {"index": 3, "before": {"state": "card"}, "after": {"state": "event"},
         "random": {"before": 4, "after": 4, "seeds": []}},
    ]
    intents = normalize_steps(steps, observations)
    assert [(intent.start_index, intent.end_index, intent.kind) for intent in intents] == [
        (3, 3, "play_event")]


def test_accepted_rollback_removes_reverted_actions_and_ui_steps():
    from pog_engine.rtt_replay.normalize import normalize_steps

    trace = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                           capture_output=True, text=True, check=True)
    rows = [json.loads(line) for line in trace.stdout.splitlines()[:3]]
    action_phase = rows[1]["after"]
    event_state = rows[2]["after"]
    review = deepcopy(event_state)
    review["state"] = "review_rollback_proposal"
    confirm = deepcopy(event_state)
    confirm["state"] = "confirm_rollback"
    observations = [
        {"index": 1, "before": rows[1]["before"], "after": action_phase,
         "random": {"seeds": []}},
        {"index": 2, "before": action_phase, "after": event_state,
         "random": {"seeds": []}},
        {"index": 3, "before": event_state, "after": review,
         "random": {"seeds": []}},
        {"index": 4, "before": review, "after": confirm,
         "random": {"seeds": []}},
        {"index": 5, "before": confirm, "after": action_phase,
         "random": {"seeds": []}},
    ]
    steps = tuple(ReplayStep(index, "Central Powers", kind, None) for index, kind in
                  enumerate(("next", "play_event", "propose_rollback", "accept", "next"), 1))
    intents = normalize_steps(steps, observations)
    assert [(intent.end_index, intent.kind) for intent in intents] == [(1, "next")]


def test_missing_random_observation_is_error():
    from pog_engine.rtt_replay.normalize import NormalizeError, normalize_steps

    with pytest.raises(NormalizeError, match="index 4.*random"):
        normalize_steps((ReplayStep(4, "Allied Powers", "done", None),),
                        ({"index": 4, "before": {}, "after": {}},))


def test_actual_replay_discards_all_85_undos():
    from pog_engine.rtt_replay.normalize import normalize_steps

    replay = load_replay(FIXTURE)
    trace = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                           capture_output=True, text=True, check=True)
    observations = (json.loads(line) for line in trace.stdout.splitlines()[:-1])
    intents = normalize_steps(replay.actions, observations)
    assert sum(step.name == "undo" for step in replay.actions) == 85
    assert all(intent.kind != "undo" for intent in intents)
    assert intents[-1].end_index == 1446
