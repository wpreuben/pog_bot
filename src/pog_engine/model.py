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
    scenario: str
    data_version: str
    seed: int
    rng_state: int
    turn: int
    action_round: int
    phase: str
    active_side: str
    decision: Decision | None
    vp: int
    players: dict
    units: dict
    spaces: dict
    war_nations: dict
    us_entry: int
    russian_capitulation: int
    events: dict
    temporary_effects: dict
    flags: dict
    combat_context: dict | None
    activated: dict
    ops_remaining: int
    result: dict | None


@dataclass(frozen=True)
class Transition:
    state: FullGameState
    record: dict[str, object]


class IllegalActionError(ValueError):
    """현재 창에서 선택할 수 없는 행동."""


class InvalidStateError(ValueError):
    """엔진 계약을 위반한 상태."""
