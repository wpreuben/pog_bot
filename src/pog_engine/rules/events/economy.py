"""RP 수정, 해상 위협과 턴 만료 이벤트."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError
from pog_engine.rules.war import apply_vp_change, update_entry_markers


class EconomyEventHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        events = state["events"]
        if card_id == "U_BOATS_UNLEASHED":
            return bool(events.get("H_L_TAKE_COMMAND"))
        if card_id == "CONVOY":
            return bool(events.get("U_BOATS_UNLEASHED"))
        if card_id == "GRAND_FLEET":
            return bool(events.get("HIGH_SEAS_FLEET"))
        if card_id == "LLOYD_GEORGE":
            return not any(events.get(name) for name in ("MICHAEL", "BLUCHER", "PEACE_OFFENSIVE"))
        return True

    def legal_choices(self, state: FullGameState) -> list[Action]:
        return []

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        card_id = state["players"][state["active_side"]]["removed"][-1]
        state["events"][card_id] = state["turn"]
        if card_id == "CONVOY":
            updated = apply_vp_change(state, -1, card_id)
            state.clear()
            state.update(updated)
        if card_id == "GRAND_FLEET":
            state["events"].pop("HIGH_SEAS_FLEET", None)
        update_entry_markers(state)
        from pog_engine.rules.turn import complete_action

        state["phase"] = "ACTION"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return state


def apply_replacement_phase_events(state: FullGameState) -> None:
    """16절 이벤트의 RP 수치를 AP→CP 지출 전에 한 번 반영한다."""
    events = state["events"]
    ap = state["players"]["AP"]["replacement_points"]
    cp = state["players"]["CP"]["replacement_points"]
    if events.get("ZEPPELIN_RAIDS") == state["turn"]:
        ap["BR"] = max(0, ap.get("BR", 0) - 4)
        del events["ZEPPELIN_RAIDS"]
    if events.get("WALTER_RATHENAU") and not events.get("INDEPENDENT_AIR_FORCE"):
        cp["GE"] = cp.get("GE", 0) + 1
    if events.get("U_BOATS_UNLEASHED") and not events.get("CONVOY"):
        ap["BR"] = max(0, ap.get("BR", 0) - 1)


def expire_effects(state: FullGameState, phase: str) -> None:
    if phase == "END_TURN":
        state["events"].pop("LLOYD_GEORGE", None)
        state["flags"].pop("lloyd_george_canceled", None)


class WarInAfricaHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        return True

    def legal_choices(self, state: FullGameState) -> list[Action]:
        data = load_data()
        eligible = [unit_id for unit_id, dynamic in state["units"].items()
                    if data.units[unit_id]["nation"] == "BR" and data.units[unit_id]["type"] == "CORPS"
                    and data.units[unit_id]["name"] != "BR BEFc" and dynamic["location"] is not None
                    and not dynamic["permanent"]]
        if any(not state["units"][unit_id]["reduced"] for unit_id in eligible):
            eligible = [unit_id for unit_id in eligible if not state["units"][unit_id]["reduced"]]
        return ([{"type": "REMOVE_BRITISH_CORPS", "actor": "AP", "unit_id": unit_id}
                 for unit_id in sorted(eligible)] + [{"type": "PASS_WAR_IN_AFRICA", "actor": "AP"}])

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        if choice is None:
            state["events"]["WAR_IN_AFRICA"] = state["turn"]
            state["phase"] = "WAR_IN_AFRICA"
            state["active_side"] = "AP"
            state["decision"] = {"kind": "WAR_IN_AFRICA", "actor": "AP", "options": self.legal_choices(state)}
            return state
        if choice not in self.legal_choices(state):
            raise IllegalActionError("아프리카 전쟁 선택이 잘못되었습니다")
        if choice["type"] == "REMOVE_BRITISH_CORPS":
            unit = state["units"][choice["unit_id"]]
            unit.update({"location": None, "eliminated": True, "permanent": True})
        else:
            updated = apply_vp_change(state, 1, "WAR_IN_AFRICA")
            state.clear()
            state.update(updated)
        from pog_engine.rules.turn import complete_action

        state["phase"] = "ACTION"
        state["active_side"] = "CP"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return state


_AFRICA = WarInAfricaHandler()


def _apply_africa(state: FullGameState, action: Action, random_input: object | None) -> None:
    _AFRICA.apply(state, action)


register_decision_handler("WAR_IN_AFRICA", _apply_africa)


_HANDLER = EconomyEventHandler()


def register_economy_events(registry: dict[str, object]) -> None:
    for card_id in (
        "HIGH_SEAS_FLEET", "GRAND_FLEET", "ZEPPELIN_RAIDS", "WALTER_RATHENAU",
        "U_BOATS_UNLEASHED", "CONVOY", "INDEPENDENT_AIR_FORCE", "LLOYD_GEORGE",
    ):
        registry[card_id] = _HANDLER
    registry["WAR_IN_AFRICA"] = _AFRICA
