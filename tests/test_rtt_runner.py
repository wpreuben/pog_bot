"""258629번 JSON 기보의 두 엔진 교차 재현."""

from copy import deepcopy
from pathlib import Path
import subprocess

from rtt_test_support import rules_path
import json

from pog_engine.replay import replay
from pog_engine.rtt_replay.bootstrap import bootstrap_historical
from pog_engine.rtt_replay.ids import SourceIds
from pog_engine import apply_action
from pog_engine.rtt_replay.input import load_replay
from pog_engine.rtt_replay.normalize import normalize_steps
from pog_engine.rtt_replay.translate import translate_intent
from pog_engine.rules.cards import draw_to_hand
from pog_engine import create_game
from pog_engine.rtt_replay.runner import build_draw_schedule
from pog_engine.rtt_replay.projection import project_engine, project_rtt


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/replay-258629.json"
RULES = rules_path(__file__)


def test_changed_vp_reports_first_path_and_source_index():
    from pog_engine.rtt_replay.runner import compare_checkpoint

    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    setup = json.loads(output.splitlines()[0])["after"]
    ids = SourceIds.from_data()
    engine = bootstrap_historical(10762091171, setup, ids)
    changed = deepcopy(setup)
    changed["vp"] += 1
    difference = compare_checkpoint(changed, engine, 0, ".setup", ids)
    assert difference.index == 0
    assert difference.action == ".setup"
    assert difference.path == "$.vp"
    assert difference.expected == 11
    assert difference.actual == 10


def test_official_arabia_attrition_difference_is_reported_not_hidden():
    from pog_engine.rtt_replay.runner import compare_checkpoint

    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    setup = json.loads(output.splitlines()[0])["after"]
    ids = SourceIds.from_data()
    engine = bootstrap_historical(10762091171, setup, ids)
    engine["spaces"]["ARABIA"]["control"] = "CP"
    adjudications = []
    assert compare_checkpoint(setup, engine, 188, "next", ids, adjudications) is None
    assert len(adjudications) == 1
    assert adjudications[0].path == "$.spaces.ARABIA.control"
    assert adjudications[0].rule == "14.3.6"


def test_entire_historical_replay_matches_and_records_are_replayable():
    from pog_engine.rtt_replay.runner import run_replay

    report = run_replay(FIXTURE, RULES)
    assert report.ok, report.first_difference
    assert report.processed_steps == 1447
    assert report.first_difference is None
    assert report.final_state["turn"] == 8
    assert report.final_state["vp"] == 7
    assert report.final_state["result"] == {"winner": "AP", "reason": "RESIGN", "vp": 7}
    assert {(item.path, item.rule) for item in report.adjudicated_differences} == {
        ("$.spaces.ARABIA.control", "14.3.6"), ("$.result", "RTT_RESIGN_ROLE")}
    assert replay(report.initial_state, list(report.records)) == report.final_state


def test_first_attrition_and_siege_reach_replacement_phase():
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    intents = {intent.end_index: intent for intent in normalize_steps(load_replay(FIXTURE).actions, rows)}
    for index in range(170):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert state["phase"] == "REPLACEMENT_AP"


def test_first_replacement_spending_reaches_draw_phase():
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    intents = {intent.end_index: intent for intent in normalize_steps(load_replay(FIXTURE).actions, rows)}
    for index in range(186):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert state["phase"] == "DRAW"


def test_replay_draw_schedule_keeps_recorded_card_order():
    state = create_game(seed=4)
    cards = state["players"]["AP"]["deck"][:2]
    state["players"]["AP"]["hand"] = []
    state["players"]["AP"]["deck"] = cards[:]
    state["players"]["AP"]["discard"] = []
    state["flags"]["rtt_replay_draws"] = {"AP": [{"turn": 1, "hand": cards[:],
                                                   "deck": [], "discard": []}], "CP": []}
    drawn = draw_to_hand(state, "AP")
    assert drawn["players"]["AP"]["hand"] == cards
    assert drawn["players"]["AP"]["deck"] == []
    assert drawn["flags"]["rtt_replay_draws"]["AP"] == []


def test_trace_extracts_both_first_turn_draws():
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    schedule = build_draw_schedule(rows, SourceIds.from_data())
    assert schedule["AP"][0]["turn"] == 1
    assert len(schedule["AP"][0]["hand"]) == 8
    assert schedule["CP"][0]["turn"] == 1
    assert len(schedule["CP"][0]["hand"]) == 8


def test_first_draw_reaches_turn_two_with_recorded_hands():
    output = subprocess.run(["node", str(ROOT / "tools/rtt_trace.cjs"), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in output.splitlines()[:-1]]
    ids = SourceIds.from_data()
    state = bootstrap_historical(10762091171, rows[0]["after"], ids)
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(rows, ids)
    intents = {intent.end_index: intent for intent in normalize_steps(load_replay(FIXTURE).actions, rows)}
    for index in range(188):
        if index not in intents:
            continue
        for action in translate_intent(state, intents[index], ids):
            state = apply_action(state, action).state
    assert state["turn"] == 2
    assert state["phase"] == "ACTION"
    assert project_engine(state)["players"] == project_rtt(rows[187]["after"], ids)["players"]
