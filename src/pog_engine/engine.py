"""엔진의 상태 불변 행동 경계."""

from collections.abc import Callable, Mapping
from copy import deepcopy
import json

from .model import Action, FullGameState, IllegalActionError, InvalidStateError, Transition


Handler = Callable[[FullGameState, Action, object | None], None]
_HANDLERS: dict[str, Handler] = {}
_AUTOMATIC_PHASES = {"ATTRITION", "SIEGE", "WAR_STATUS", "REPLACEMENT_AP",
                     "REPLACEMENT_CP", "DRAW", "END_TURN"}
_ADVANCE_ACTION: Action = {"type": "ADVANCE_AUTOMATIC_PHASE", "actor": "CHANCE"}


def register_decision_handler(kind: str, handler: Handler) -> None:
    if kind in _HANDLERS:
        raise InvalidStateError(f"이미 등록된 선택 창: {kind}")
    _HANDLERS[kind] = handler


def _canonical_action(action: object) -> str:
    if not isinstance(action, dict):
        raise IllegalActionError("행동은 객체여야 합니다")
    if not isinstance(action.get("type"), str) or not isinstance(action.get("actor"), str):
        raise IllegalActionError("행동의 type과 actor가 필요합니다")
    try:
        return json.dumps(action, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise IllegalActionError("행동은 JSON으로 직렬화할 수 있어야 합니다") from exc


def _decision(state: FullGameState) -> Mapping[str, object] | None:
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise InvalidStateError("지원하지 않는 상태 버전입니다")
    if not isinstance(state.get("phase"), str):
        raise InvalidStateError("상태에 phase가 필요합니다")
    decision = state.get("decision")
    if decision is None:
        return None
    if not isinstance(decision, dict) or not isinstance(decision.get("kind"), str):
        raise InvalidStateError("잘못된 선택 창입니다")
    if not isinstance(decision.get("actor"), str) or not isinstance(decision.get("options"), list):
        raise InvalidStateError("선택 창에 actor와 options가 필요합니다")
    return decision


def generate_legal_actions(state: FullGameState) -> list[Action]:
    decision = _decision(state)
    if decision is None:
        return [deepcopy(_ADVANCE_ACTION)] if state["phase"] in _AUTOMATIC_PHASES else []
    actions: list[Action] = []
    seen: set[str] = set()
    for option in decision["options"]:
        key = _canonical_action(option)
        if option["actor"] != decision["actor"]:
            raise InvalidStateError("선택 창과 행동의 행위자가 다릅니다")
        if key not in seen:
            actions.append(deepcopy(option))
            seen.add(key)
    return actions


def apply_action(state: FullGameState, action: Action, random_input: object | None = None) -> Transition:
    wanted = _canonical_action(action)
    if wanted not in {_canonical_action(legal) for legal in generate_legal_actions(state)}:
        raise IllegalActionError("현재 선택 창에서 합법적인 행동이 아닙니다")
    if random_input is not None and (action.get("actor") != "CHANCE" or action.get("value") != random_input):
        raise IllegalActionError("무작위 입력과 선택한 주사위 결과가 다릅니다")
    consumed = deepcopy(action.get("value")) if action.get("actor") == "CHANCE" else None
    next_state = deepcopy(state)
    decision = _decision(next_state)
    if decision is None:
        from .rules.turn import advance_automatic_phases

        next_state = advance_automatic_phases(next_state)
        return Transition(next_state, {"action": deepcopy(action), "random_input": None})
    handler = _HANDLERS.get(decision["kind"])
    if handler is None:
        raise InvalidStateError(f"처리기가 없는 선택 창: {decision['kind']}")
    handler(next_state, deepcopy(action), random_input)
    return Transition(next_state, {"action": deepcopy(action), "random_input": consumed})


def _confirm(state: FullGameState, action: Action, random_input: object | None) -> None:
    state["decision"] = None
    state["phase"] = "IDLE"


register_decision_handler("CONFIRM", _confirm)
