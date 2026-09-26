"""전략 카드 이벤트 처리기의 공통 계약."""

from typing import Protocol

from pog_engine.model import Action, FullGameState


class EventHandler(Protocol):
    def can_play(self, state: FullGameState, card_id: str) -> bool: ...

    def legal_choices(self, state: FullGameState) -> list[Action]: ...

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState: ...
