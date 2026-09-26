"""기록된 행동과 자동 단계를 결정적으로 재생."""

from copy import deepcopy

from .engine import apply_action, generate_legal_actions
from .model import FullGameState, InvalidStateError
from .rules.turn import advance_automatic_phases


def replay(initial_state: FullGameState, records: list[dict]) -> FullGameState:
    state = deepcopy(initial_state)
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("action"), dict):
            raise InvalidStateError(f"재생 기록 {index}에 행동이 없습니다")
        action = record["action"]
        if action == {"type": "ADVANCE_AUTOMATIC_PHASE", "actor": "SYSTEM"}:
            if generate_legal_actions(state):
                raise InvalidStateError(f"재생 기록 {index}: 선택 창을 자동으로 넘길 수 없습니다")
            state = advance_automatic_phases(state)
            continue
        try:
            state = apply_action(state, action, record.get("random_input")).state
        except (ValueError, TypeError, KeyError) as exc:
            raise InvalidStateError(f"재생 기록 {index}의 행동이 현재 상태와 맞지 않습니다") from exc
    return state
