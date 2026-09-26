"""미국 참전과 러시아 항복의 정치 이벤트."""

from pog_engine.data import load_data
from pog_engine.model import Action, FullGameState
from pog_engine.rules.war import apply_vp_change, update_entry_markers


RUSSIAN_VP_SPACES = ("RIGA", "KOVNO", "VILNA", "WARSAW", "LODZ", "KIEV", "ODESSA")
OPS_AFTER_EVENT = {
    "TSAR_TAKES_COMMAND", "FALL_OF_THE_TSAR", "BOLSHEVIK_REVOLUTION",
    "ZIMMERMANN_TELEGRAM", "OVER_THERE",
}


def russian_vp_count(state: FullGameState) -> int:
    data = load_data()
    return sum(dynamic["vp"] and data.spaces[space_id]["nation"] == "RU" and
               dynamic["control"] == "CP" for space_id, dynamic in state["spaces"].items())


class PoliticalHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        events = state["events"]
        combined = sum(state["players"][side]["war_status"] for side in ("AP", "CP"))
        russian_vp = russian_vp_count(state)
        if card_id == "TSAR_TAKES_COMMAND":
            return russian_vp >= 3
        if card_id == "FALL_OF_THE_TSAR":
            return bool(events.get("TSAR_TAKES_COMMAND")) and combined + russian_vp >= 33
        if card_id == "BOLSHEVIK_REVOLUTION":
            return bool(events.get("FALL_OF_THE_TSAR")) and state["turn"] > events["FALL_OF_THE_TSAR"] and (
                russian_vp > state["flags"].get("tsar_fell_russian_vp", 99) or
                all(state["spaces"][space_id]["control"] == "CP" for space_id in RUSSIAN_VP_SPACES)
            )
        if card_id == "TREATY_OF_BREST_LITOVSK":
            return bool(events.get("BOLSHEVIK_REVOLUTION"))
        if card_id == "ZIMMERMANN_TELEGRAM":
            return combined >= 30
        if card_id == "OVER_THERE":
            return bool(events.get("ZIMMERMANN_TELEGRAM")) and state["turn"] > events["ZIMMERMANN_TELEGRAM"]
        return False

    def legal_choices(self, state: FullGameState) -> list[Action]:
        return []

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        card_id = state["players"][state["active_side"]]["removed"][-1]
        state["events"][card_id] = state["turn"]
        if card_id == "FALL_OF_THE_TSAR":
            state["flags"]["tsar_fell_russian_vp"] = russian_vp_count(state)
            delta = 1 if state["war_nations"]["RO"] else 3
            updated = apply_vp_change(state, delta, card_id)
            state.clear()
            state.update(updated)
        elif card_id == "BOLSHEVIK_REVOLUTION":
            if state["players"]["AP"]["mandatory_offensive"] == "RU":
                state["players"]["AP"]["mandatory_offensive"] = None
        elif card_id == "ZIMMERMANN_TELEGRAM":
            updated = apply_vp_change(state, -1, card_id)
            state.clear()
            state.update(updated)
        elif card_id == "TREATY_OF_BREST_LITOVSK":
            self._apply_treaty(state)
        update_entry_markers(state)
        if card_id in OPS_AFTER_EVENT:
            from pog_engine.rules.cards import begin_ops

            return begin_ops(state, load_data().cards[card_id]["ops"])
        from pog_engine.rules.turn import complete_action

        state["phase"] = "ACTION"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return state

    @staticmethod
    def _apply_treaty(state: FullGameState) -> None:
        data = load_data()
        allowed = {"RU", "GE", "TU", "AH", "RO"}
        for unit_id, dynamic in state["units"].items():
            if data.units[unit_id]["nation"] != "RU" or dynamic["location"] is None:
                continue
            place = dynamic["location"]
            if data.spaces[place]["kind"] != "BOARD":
                continue
            other_allied = any(other_id != unit_id and other["location"] == place and
                               data.units[other_id]["side"] == "AP" and
                               data.units[other_id]["nation"] != "RU"
                               for other_id, other in state["units"].items())
            if data.spaces[place]["nation"] not in allowed or other_allied:
                dynamic["location"] = None
                dynamic["eliminated"] = True


_HANDLER = PoliticalHandler()


def register_political_events(registry: dict[str, object]) -> None:
    for card_id in (
        "TSAR_TAKES_COMMAND", "FALL_OF_THE_TSAR", "BOLSHEVIK_REVOLUTION",
        "TREATY_OF_BREST_LITOVSK", "ZIMMERMANN_TELEGRAM", "OVER_THERE",
    ):
        registry[card_id] = _HANDLER
