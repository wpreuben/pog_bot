"""RTT 관측과 Python 합법 행동을 같은 의미 상태에서 대조."""

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

from pog_engine.engine import apply_action, generate_legal_actions
from pog_engine.model import FullGameState

from .bootstrap import bootstrap_historical
from .ids import SourceIds
from .input import load_replay
from .normalize import normalize_steps
from .projection import first_difference, project_engine, project_rtt
from .translate import TranslationError, translate_intent


@dataclass(frozen=True)
class ReplayDifference:
    index: int
    action: str
    path: str
    expected: object
    actual: object
    phase: str
    legal_candidates: tuple[dict, ...]


class ReplayTraceError(ValueError):
    """RTT 관측기 입력·규칙 실행 오류."""


@dataclass(frozen=True)
class AdjudicatedDifference:
    index: int
    path: str
    expected: object
    actual: object
    rule: str


@dataclass(frozen=True)
class ReplayReport:
    ok: bool
    processed_steps: int
    records: tuple[dict, ...]
    initial_state: FullGameState
    final_state: FullGameState
    first_difference: ReplayDifference | None
    adjudicated_differences: tuple[AdjudicatedDifference, ...] = ()
    checked_steps: int = 0


def compare_checkpoint(rtt_state: dict, engine_state: FullGameState,
                       index: int, action: str, ids: SourceIds,
                       adjudications: list[AdjudicatedDifference] | None = None,
                       before_rtt_state: dict | None = None,
                       before_engine_state: FullGameState | None = None) -> ReplayDifference | None:
    expected = project_rtt(rtt_state, ids)
    actual = project_engine(engine_state)
    if (adjudications is not None
            and ((before_rtt_state is not None
                  and before_rtt_state.get("state") == "attrition_phase")
                 or any(item.path == "$.spaces.ARABIA.control" for item in adjudications))
            and expected["spaces"]["ARABIA"]["control"] == "AP"
            and actual["spaces"]["ARABIA"]["control"] == "CP"):
        if not any(item.path == "$.spaces.ARABIA.control" for item in adjudications):
            adjudications.append(AdjudicatedDifference(index, "$.spaces.ARABIA.control",
                                                       "AP", "CP", "14.3.6"))
        expected["spaces"]["ARABIA"]["control"] = "CP"
    if (adjudications is not None and expected["result"] == "CP" and actual["result"] == "AP"
            and rtt_state.get("victory") == "Central Powers resigned."):
        adjudications.append(AdjudicatedDifference(index, "$.result", "CP", "AP",
                                                   "RTT_RESIGN_ROLE"))
        expected["result"] = "AP"
    if (adjudications is not None and action == ".resign"
            and engine_state.get("result", {}).get("reason") == "RESIGN"
            and rtt_state.get("state") == "game_over"
            and before_rtt_state is not None and before_engine_state is not None
            and before_engine_state["phase"] in {"OPS", "MOVEMENT", "COMBAT"}
            and before_rtt_state.get("state") not in {"action_phase", "game_over"}
            and (expected["turn"], expected["vp"]) == (actual["turn"], actual["vp"])):
        unfinished = [side for side in ("AP", "CP")
                      if (expected["round"][side] == actual["round"][side] + 1
                          and len(before_rtt_state[side.lower()]["actions"]) == expected["round"][side]
                          and before_engine_state["players"][side]["actions_taken"] == actual["round"][side])]
        if (len(unfinished) == 1 and before_engine_state["active_side"] == unfinished[0] and all(
                expected["round"][side] == actual["round"][side]
                == len(before_rtt_state[side.lower()]["actions"])
                == before_engine_state["players"][side]["actions_taken"]
                for side in ("AP", "CP") if side not in unfinished)):
            side = unfinished[0]
            path = f"$.round.{side}"
            adjudications.append(AdjudicatedDifference(
                index, path, expected["round"][side], actual["round"][side],
                "RTT_RESIGN_IN_PROGRESS_ACTION"))
            expected["round"][side] = actual["round"][side]
    difference = first_difference(expected, actual)
    if difference is None:
        return None
    return ReplayDifference(index, action, difference.path, difference.expected,
                            difference.actual, engine_state["phase"],
                            tuple(generate_legal_actions(engine_state)[:20]))


def _trace(path: Path, rules_path: Path) -> list[dict]:
    script = Path(__file__).resolve().parents[3] / "tools/rtt_trace.cjs"
    result = subprocess.run(["node", str(script), str(path), str(rules_path)],
                            capture_output=True, text=True)
    if result.returncode:
        raise ReplayTraceError(result.stderr.strip() or f"RTT 관측기 종료 코드 {result.returncode}")
    return [json.loads(line) for line in result.stdout.splitlines()]


def build_draw_schedule(observations: list[dict], ids: SourceIds) -> dict[str, list[dict]]:
    schedule: dict[str, list[dict]] = {"AP": [], "CP": []}
    for observation in observations:
        before, after = observation["before"], observation["after"]
        if before is None:
            continue
        if before["state"] not in ("replacement_phase", "draw_cards_phase"):
            continue
        for side, key in (("AP", "ap"), ("CP", "cp")):
            if len(after[key]["hand"]) <= len(before[key]["hand"]):
                continue
            entry = {"turn": before["turn"]}
            for zone in ("hand", "deck", "discard"):
                entry[zone] = [ids.lookup("cards", card, index=observation["index"])
                               for card in after[key][zone]]
            schedule[side].append(entry)
    return schedule


def run_replay(path: Path, rules_path: Path) -> ReplayReport:
    source = load_replay(path)
    observations = _trace(path, rules_path)
    if len(observations) != len(source.actions) + 1:
        raise ValueError("RTT 관측 행동 수가 입력과 다릅니다")
    ids = SourceIds.from_data()
    state = bootstrap_historical(source.seed, observations[0]["after"], ids)
    intents = normalize_steps(source.actions, observations[:-1])
    committed_indices = {intent.end_index for intent in intents}
    state["flags"]["rtt_replay_draws"] = build_draw_schedule(
        [observation for observation in observations[:-1]
         if observation["index"] in committed_indices], ids)
    initial = state
    records: list[dict] = []
    adjudications: list[AdjudicatedDifference] = []
    checked_steps = 0
    for intent in intents:
        before_engine_state = state
        try:
            actions = translate_intent(state, intent, ids)
            for action in actions:
                transition = apply_action(state, action)
                state = transition.state
                records.append(transition.record)
        except (TranslationError, ValueError, KeyError, TypeError) as exc:
            difference = ReplayDifference(intent.end_index, intent.kind, "$action", intent.argument,
                                          str(exc), state["phase"],
                                          tuple(generate_legal_actions(state)[:20]))
            return ReplayReport(False, intent.end_index + 1, tuple(records), initial, state,
                                difference, tuple(adjudications), checked_steps)
        after_phase = intent.after["state"]
        boundary = (intent.end_index == 0 or after_phase in {
            "action_phase", "game_over", "replacement_phase", "siege_phase"}
            or (after_phase == "draw_cards_phase" and intent.before["state"] == "draw_cards_phase"))
        if boundary:
            checked_steps += 1
            difference = compare_checkpoint(intent.after, state, intent.end_index, intent.kind,
                                            ids, adjudications, intent.before, before_engine_state)
            if difference is not None:
                return ReplayReport(False, intent.end_index + 1, tuple(records), initial, state,
                                    difference, tuple(adjudications), checked_steps)
    final = observations[-1]
    if final["state"] != "game_over":
        difference = ReplayDifference(len(source.actions) - 1, ".final", "$.final.state",
                                      "game_over", final["state"], state["phase"],
                                      tuple(generate_legal_actions(state)[:20]))
        return ReplayReport(False, len(source.actions), tuple(records), initial, state,
                            difference, tuple(adjudications), checked_steps)
    if (state["turn"], state["vp"]) != (final["turn"], final["vp"]):
        difference = ReplayDifference(len(source.actions) - 1, ".final", "$.final",
                                      (final["turn"], final["vp"]), (state["turn"], state["vp"]),
                                      state["phase"], tuple(generate_legal_actions(state)[:20]))
        return ReplayReport(False, len(source.actions), tuple(records), initial, state,
                            difference, tuple(adjudications), checked_steps)
    return ReplayReport(True, len(source.actions), tuple(records), initial, state,
                        None, tuple(adjudications), checked_steps)
