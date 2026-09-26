"""RTT 되돌리기를 제거하고 원본 인덱스가 있는 선택을 보존."""

from dataclasses import dataclass
from typing import Iterable

from .input import ReplayStep


class NormalizeError(ValueError):
    """관측이 누락되거나 되돌리기 상태가 모호한 경우."""


@dataclass(frozen=True)
class Intent:
    start_index: int
    end_index: int
    role: str | None
    kind: str
    argument: object | None
    before: dict | None
    after: dict
    random_seeds: tuple[int, ...]


def normalize_steps(steps: tuple[ReplayStep, ...],
                    observations: Iterable[dict]) -> tuple[Intent, ...]:
    rows = list(observations)
    if len(rows) != len(steps):
        raise NormalizeError(f"행동 {len(steps)}개와 관측 {len(rows)}개가 일치하지 않습니다")
    committed: list[Intent] = []
    for step, observation in zip(steps, rows, strict=True):
        index = step.index
        if observation.get("index") != index:
            raise NormalizeError(f"index {index}: 관측 인덱스가 다릅니다")
        random = observation.get("random")
        if not isinstance(random, dict) or not isinstance(random.get("seeds"), list):
            raise NormalizeError(f"index {index}: random 관측이 없습니다")
        before, after = observation.get("before"), observation.get("after")
        if not isinstance(after, dict):
            raise NormalizeError(f"index {index}: after 상태가 없습니다")
        if step.name == "undo":
            match = next((position for position in range(len(committed) - 1, -1, -1)
                          if committed[position].before == after), None)
            if match is None:
                raise NormalizeError(f"index {index}: undo 대상 상태를 찾지 못했습니다")
            del committed[match:]
            continue
        committed.append(Intent(index, index, step.role, step.name, step.argument,
                                before, after, tuple(random["seeds"])))
    return tuple(committed)
