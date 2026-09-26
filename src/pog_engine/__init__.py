"""Paths of Glory 엔진 공개 진입점."""

from .engine import apply_action, generate_legal_actions
from .model import Action, FullGameState, IllegalActionError, InvalidStateError, Transition
from .rules.setup import create_game
from .rules import turn as _turn  # 선택 창 처리기 등록
from .rules import cards as _cards  # 카드 처리기 등록
from .rules import ops as _ops  # OPS 처리기 등록
from .rules import movement as _movement  # 이동 처리기 등록
from .rules import trenches as _trenches  # 참호 처리기 등록
from .rules import sr as _sr  # 전략 재배치 처리기 등록
from .rules import combat as _combat  # 전투 처리기 등록
from .rules import forts as _forts  # 공성 처리기 등록

__all__ = [
    "Action",
    "FullGameState",
    "IllegalActionError",
    "InvalidStateError",
    "Transition",
    "apply_action",
    "create_game",
    "generate_legal_actions",
]
