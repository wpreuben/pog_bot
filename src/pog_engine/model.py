"""공개 엔진 값과 검증 오류."""

from dataclasses import dataclass
from typing import TypedDict


Action = dict[str, object]


class Decision(TypedDict):
    kind: str
    actor: str
    options: list[Action]


class FullGameState(TypedDict):
    schema_version: int
    phase: str
    decision: Decision | None


@dataclass(frozen=True)
class Transition:
    state: FullGameState
    record: dict[str, object]


class IllegalActionError(ValueError):
    """현재 창에서 선택할 수 없는 행동."""


class InvalidStateError(ValueError):
    """엔진 계약을 위반한 상태."""
