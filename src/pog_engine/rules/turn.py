"""Historical 턴과 행동 라운드의 순서."""

from copy import deepcopy

from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError, InvalidStateError
from .war import mandatory_offensive


def _roll_decision(side: str) -> dict:
    purpose = f"{side}_MANDATORY_OFFENSIVE"
    return {
        "kind": "MANDATORY_OFFENSIVE_ROLL",
        "actor": "CHANCE",
        "purpose": purpose,
        "options": [
            {"type": "RECORD_DIE_RESULT", "actor": "CHANCE", "purpose": purpose, "value": die}
            for die in range(1, 7)
        ],
    }


def _action_decision(state: dict) -> dict:
    side = state["active_side"]
    options = []
    if state["turn"] == 1 and state["action_round"] == 1 and side == "CP":
        options.append({"type": "PLAY_CARD", "actor": "CP", "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"})
    return {"kind": "ACTION_PHASE", "actor": side, "options": options}


def legal_turn_actions(state: FullGameState) -> list[Action]:
    if state["phase"] not in ("MANDATORY_OFFENSIVE", "ACTION"):
        return []
    return deepcopy(state["decision"]["options"])


def apply_turn_action(state: FullGameState, action: Action) -> FullGameState:
    if state["phase"] != "MANDATORY_OFFENSIVE":
        raise IllegalActionError("의무 공세 굴림 단계가 아닙니다")
    if action.get("type") != "RECORD_DIE_RESULT" or action.get("actor") != "CHANCE":
        raise IllegalActionError("주사위 결과 행동이 필요합니다")
    purpose = state["decision"]["purpose"]
    if action.get("purpose") != purpose:
        raise IllegalActionError("다른 주사위 목적입니다")
    side = purpose.split("_", 1)[0]
    state["players"][side]["mandatory_offensive"] = mandatory_offensive(state, side, action["value"])
    if side == "AP":
        state["decision"] = _roll_decision("CP")
    else:
        state["phase"] = "ACTION"
        state["active_side"] = "CP"
        state["decision"] = _action_decision(state)
    return state


def _apply_mandatory_roll(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_turn_action(state, action)


def complete_action(state: FullGameState) -> FullGameState:
    if state["phase"] != "ACTION":
        raise InvalidStateError("행동 단계가 아닙니다")
    next_state = deepcopy(state)
    side = next_state["active_side"]
    next_state["players"][side]["actions_taken"] += 1
    if side == "CP":
        next_state["active_side"] = "AP"
    elif next_state["action_round"] < 6:
        next_state["action_round"] += 1
        next_state["active_side"] = "CP"
    else:
        next_state["phase"] = "ATTRITION"
        next_state["active_side"] = "CHANCE"
        next_state["decision"] = None
        return next_state
    next_state["decision"] = _action_decision(next_state)
    return next_state


_AFTER_ACTIONS = {
    "ATTRITION": "SIEGE",
    "SIEGE": "WAR_STATUS",
    "WAR_STATUS": "REPLACEMENT_AP",
    "REPLACEMENT_AP": "REPLACEMENT_CP",
    "REPLACEMENT_CP": "DRAW",
    "DRAW": "END_TURN",
}


def advance_automatic_phases(state: FullGameState) -> FullGameState:
    next_state = deepcopy(state)
    phase = next_state["phase"]
    if phase in _AFTER_ACTIONS:
        next_state["phase"] = _AFTER_ACTIONS[phase]
        next_state["active_side"] = "AP" if next_state["phase"] == "REPLACEMENT_AP" else (
            "CP" if next_state["phase"] == "REPLACEMENT_CP" else "CHANCE"
        )
        next_state["decision"] = None
        return next_state
    if phase == "END_TURN":
        next_state["turn"] += 1
        next_state["action_round"] = 1
        next_state["phase"] = "MANDATORY_OFFENSIVE"
        next_state["active_side"] = "CHANCE"
        next_state["players"]["AP"]["actions_taken"] = 0
        next_state["players"]["CP"]["actions_taken"] = 0
        next_state["decision"] = _roll_decision("AP")
        return next_state
    raise InvalidStateError(f"자동으로 넘길 수 없는 단계: {phase}")


register_decision_handler("MANDATORY_OFFENSIVE_ROLL", _apply_mandatory_roll)
