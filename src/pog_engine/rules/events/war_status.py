"""전쟁 상태, 외교 및 승점에 영향을 주는 지속 이벤트."""

from pog_engine.model import Action, FullGameState
from pog_engine.rules.war import apply_vp_change, update_entry_markers


VP_CHANGES = {
    "RAPE_OF_BELGIUM": -1,
    "LUSITANIA": -1,
    "14_POINTS": -1,
    "REICHSTAG_TRUCE": 1,
}


class WarStatusEventHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        events = state["events"]
        if card_id == "RAPE_OF_BELGIUM":
            return bool(events.get("GUNS_OF_AUGUST")) and state["players"]["AP"]["commitment"] == "MOBILIZATION"
        if card_id == "LUSITANIA":
            return bool(events.get("BLOCKADE")) and not events.get("ZIMMERMANN_TELEGRAM")
        if card_id == "14_POINTS":
            return bool(events.get("ZIMMERMANN_TELEGRAM"))
        if card_id == "REICHSTAG_TRUCE":
            return state["players"]["CP"]["commitment"] != "TOTAL"
        if card_id == "FALKENHAYN":
            return state["turn"] >= 3 or bool(events.get("MOLTKE"))
        if card_id == "H_L_TAKE_COMMAND":
            return True
        if card_id == "FRENCH_MUTINY":
            return True
        return card_id == "BLOCKADE"

    def legal_choices(self, state: FullGameState) -> list[Action]:
        return []

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        card_id = state["players"][state["active_side"]]["removed"][-1]
        state["events"][card_id] = state["turn"]
        if card_id in VP_CHANGES:
            updated = apply_vp_change(state, VP_CHANGES[card_id], card_id)
            state.clear()
            state.update(updated)
        if card_id == "H_L_TAKE_COMMAND" and state["players"]["CP"]["mandatory_offensive"] == "GE":
            state["players"]["CP"]["mandatory_offensive"] = None
        update_entry_markers(state)
        from pog_engine.rules.turn import complete_action

        state["phase"] = "ACTION"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return state


_HANDLER = WarStatusEventHandler()


def register_war_status_events(registry: dict[str, object]) -> None:
    for card_id in (
        "BLOCKADE", "RAPE_OF_BELGIUM", "LUSITANIA", "14_POINTS",
        "REICHSTAG_TRUCE", "FALKENHAYN", "H_L_TAKE_COMMAND", "FRENCH_MUTINY",
    ):
        registry[card_id] = _HANDLER
