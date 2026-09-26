"""동형 유닛을 검증한 뒤 RTT 초기 카드 순서로 재현 상태를 만든다."""

from collections import Counter, defaultdict
from copy import deepcopy

from pog_engine.data import load_data
from pog_engine.model import FullGameState
from pog_engine.rules.setup import create_game

from .ids import SourceIds
from .projection import first_difference, project_engine, project_rtt


class BootstrapError(ValueError):
    """RTT 초기 상태와 Historical 설정의 규칙상 차이."""


def _unit_signature(unit: dict) -> tuple:
    return tuple(sorted((key, str(value)) for key, value in unit.items() if key != "id"))


def _status(unit: dict) -> tuple:
    return (unit["location"], unit["reduced"], unit["eliminated"], unit["permanent"])


def bootstrap_historical(seed: int, rtt_setup_state: dict, ids: SourceIds) -> FullGameState:
    state = create_game(seed=seed)
    expected = project_rtt(rtt_setup_state, ids)
    actual = project_engine(state)
    for field in ("turn", "vp", "spaces", "war_nations", "result"):
        difference = first_difference(expected[field], actual[field], f"$.{field}")
        if difference is not None:
            raise BootstrapError(f"초기 상태 {difference.path}: {difference.expected!r} != {difference.actual!r}")

    grouped: dict[tuple, list[str]] = defaultdict(list)
    for uid, definition in load_data().units.items():
        grouped[_unit_signature(definition)].append(uid)
    for unit_ids in grouped.values():
        rtt_positions = Counter(_status(expected["units"][uid]) for uid in unit_ids)
        engine_positions = Counter(_status(actual["units"][uid]) for uid in unit_ids)
        if rtt_positions != engine_positions:
            raise BootstrapError(f"초기 유닛 배치가 다릅니다: {unit_ids[0]}")

    state = deepcopy(state)
    for uid, status in expected["units"].items():
        state["units"][uid].update(status)
    for side in ("AP", "CP"):
        for zone in ("hand", "deck", "discard", "removed"):
            state["players"][side][zone] = list(expected["players"][side][zone])
    return state
