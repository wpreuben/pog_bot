"""RTT JSON 기보의 최소 입력 형식."""

from dataclasses import dataclass
import json
from pathlib import Path


class ReplayInputError(ValueError):
    """원본 인덱스를 포함한 기보 형식 오류."""


@dataclass(frozen=True)
class ReplayStep:
    index: int
    role: str | None
    name: str
    argument: object | None


@dataclass(frozen=True)
class ReplayInput:
    game_id: int
    seed: int
    scenario: str
    options: dict
    actions: tuple[ReplayStep, ...]


_ROLES = {"Central Powers", "Allied Powers"}


def load_replay(path: Path) -> ReplayInput:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayInputError(f"기보 JSON을 읽을 수 없습니다: {path}") from exc
    if not isinstance(document, dict):
        raise ReplayInputError("기보 최상위 값은 객체여야 합니다")
    setup = document.get("setup")
    raw = document.get("replay")
    if not isinstance(setup, dict) or not isinstance(raw, list) or not raw:
        raise ReplayInputError("setup 객체와 비어 있지 않은 replay 배열이 필요합니다")
    game_id = setup.get("game_id")
    scenario = setup.get("scenario")
    options = setup.get("options", {})
    if not isinstance(game_id, int) or isinstance(game_id, bool) or game_id <= 0:
        raise ReplayInputError("setup.game_id는 양의 정수여야 합니다")
    if scenario != "Historical" or not isinstance(options, dict):
        raise ReplayInputError("Historical 시나리오와 options 객체만 지원합니다")

    steps: list[ReplayStep] = []
    for index, item in enumerate(raw):
        if not isinstance(item, list) or len(item) not in (2, 3):
            raise ReplayInputError(f"행동 {index}: [역할, 행동, 선택적 인수] 배열이 필요합니다")
        role, name = item[:2]
        if index == 0:
            if role is not None or name != ".setup" or len(item) != 3:
                raise ReplayInputError("행동 0: .setup 인수가 필요합니다")
        elif role not in _ROLES:
            raise ReplayInputError(f"행동 {index}: 알 수 없는 역할 {role!r}")
        if not isinstance(name, str) or not name:
            raise ReplayInputError(f"행동 {index}: 행동 이름은 문자열이어야 합니다")
        steps.append(ReplayStep(index, role, name, item[2] if len(item) == 3 else None))

    first = steps[0].argument
    if (not isinstance(first, list) or len(first) != 3
            or not isinstance(first[0], int) or isinstance(first[0], bool)
            or first[0] < 0 or first[1] != scenario or not isinstance(first[2], dict)
            or first[2] != options):
        raise ReplayInputError("행동 0: 시드·시나리오·옵션이 setup과 맞지 않습니다")
    return ReplayInput(game_id, first[0], scenario, options, tuple(steps))
