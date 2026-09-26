"""선택 창이 필요한 참호·Landwehr·Salonika 이벤트."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError
from pog_engine.rules.supply import supply_status


def _finish(state: FullGameState) -> FullGameState:
    from pog_engine.rules.turn import complete_action

    state["phase"] = "ACTION"
    next_state = complete_action(state)
    state.clear()
    state.update(next_state)
    return state


class EntrenchEventHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        return state["turn"] > 1 and not state["events"].get("ENTRENCH")

    def legal_choices(self, state: FullGameState) -> list[Action]:
        side = state["active_side"]
        spaces = sorted({dynamic["location"] for unit_id, dynamic in state["units"].items()
                         if load_data().units[unit_id]["side"] == side
                         and load_data().units[unit_id]["type"] == "ARMY"
                         and dynamic["location"] is not None
                         and load_data().spaces[dynamic["location"]]["kind"] == "BOARD"
                         and state["spaces"][dynamic["location"]]["trenches"][side] == 0
                         and (state["spaces"][dynamic["location"]]["control"] == side or
                              state["spaces"][dynamic["location"]]["fort_besieged"])
                         and supply_status(state, unit_id).supplied})
        return ([{"type": "PLACE_EVENT_TRENCH", "actor": side, "to": place} for place in spaces]
                or [{"type": "SKIP_EVENT_TRENCH", "actor": side}])

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        if choice is None:
            state["events"]["ENTRENCH"] = state["turn"]
            state["phase"] = "EVENT_ENTRENCH"
            state["decision"] = {"kind": "EVENT_ENTRENCH", "actor": state["active_side"],
                                 "options": self.legal_choices(state)}
            return state
        if choice not in self.legal_choices(state):
            raise IllegalActionError("참호 이벤트 공간이 잘못되었습니다")
        if choice["type"] == "PLACE_EVENT_TRENCH":
            state["spaces"][choice["to"]]["trenches"][state["active_side"]] = 1
        return _finish(state)


class LandwehrHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        return state["spaces"]["BERLIN"]["control"] == "CP" and supply_status(
            state, "GE_1_ARMY_1", location="BERLIN"
        ).supplied

    def legal_choices(self, state: FullGameState) -> list[Action]:
        spent = state["landwehr"]["spent"]
        actions = []
        for unit_id, static in load_data().units.items():
            dynamic = state["units"][unit_id]
            if static["nation"] != "GE" or not dynamic["reduced"] or dynamic["location"] is None:
                continue
            cost = 1 if static["type"] == "ARMY" else 0.5
            if spent + cost > 2:
                continue
            if dynamic["location"] != "CP_RESERVE_BOX" and not supply_status(state, unit_id).supplied:
                continue
            actions.append({"type": "LANDWEHR_FLIP", "actor": "CP", "unit_id": unit_id})
        actions.append({"type": "END_LANDWEHR", "actor": "CP"})
        return actions

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        if choice is None:
            state["events"]["LANDWEHR"] = state["turn"]
            state["landwehr"] = {"spent": 0}
            state["phase"] = "LANDWEHR"
            state["decision"] = {"kind": "LANDWEHR", "actor": "CP", "options": self.legal_choices(state)}
            return state
        if choice not in self.legal_choices(state):
            raise IllegalActionError("Landwehr 보충 선택이 잘못되었습니다")
        if choice["type"] == "END_LANDWEHR":
            del state["landwehr"]
            return _finish(state)
        unit_id = choice["unit_id"]
        state["units"][unit_id]["reduced"] = False
        state["landwehr"]["spent"] += 1 if load_data().units[unit_id]["type"] == "ARMY" else 0.5
        state["decision"]["options"] = self.legal_choices(state)
        return state


class SalonikaHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        if not state["war_nations"]["GR"]:
            return True
        return state["spaces"]["SALONIKA"]["control"] == "AP" and sum(
            unit["location"] == "SALONIKA" for unit in state["units"].values()) < 3

    def legal_choices(self, state: FullGameState) -> list[Action]:
        choices = []
        if state["salonika"]["remaining"] > 0 and sum(
            unit["location"] == "SALONIKA" for unit in state["units"].values()
        ) < 3:
            data = load_data()
            for unit_id, dynamic in state["units"].items():
                static = data.units[unit_id]
                place = dynamic["location"]
                if static["nation"] not in {"FR", "BR"} or static["type"] != "CORPS" or place in {None, "SALONIKA"}:
                    continue
                if static["name"] == "BR BEFc":
                    continue
                if place == "AP_RESERVE_BOX" or data.spaces[place]["ap_port"]:
                    choices.append({"type": "SALONIKA_SR", "actor": "AP", "unit_id": unit_id})
        return choices + [{"type": "END_SALONIKA", "actor": "AP"}]

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        if choice is None:
            state["events"]["SALONIKA"] = state["turn"]
            if not state["war_nations"]["GR"]:
                greeks = sorted(uid for uid, static in load_data().units.items() if static["nation"] == "GR")
                for unit_id, place in zip(greeks, ("ATHENS", "FLORINA", "LARISA")):
                    state["units"][unit_id]["location"] = place
            state["salonika"] = {"remaining": 3}
            state["phase"] = "SALONIKA"
            state["decision"] = {"kind": "SALONIKA", "actor": "AP", "options": self.legal_choices(state)}
            return state
        if choice not in self.legal_choices(state):
            raise IllegalActionError("Salonika 재배치 선택이 잘못되었습니다")
        if choice["type"] == "END_SALONIKA":
            del state["salonika"]
            return _finish(state)
        state["units"][choice["unit_id"]]["location"] = "SALONIKA"
        state["spaces"]["SALONIKA"]["control"] = "AP"
        state["salonika"]["remaining"] -= 1
        state["decision"]["options"] = self.legal_choices(state)
        return state


_ENTRENCH = EntrenchEventHandler()
_LANDWEHR = LandwehrHandler()
_SALONIKA = SalonikaHandler()


def _apply_entrench(state: FullGameState, action: Action, random_input: object | None) -> None:
    _ENTRENCH.apply(state, action)


def _apply_landwehr(state: FullGameState, action: Action, random_input: object | None) -> None:
    _LANDWEHR.apply(state, action)


def _apply_salonika(state: FullGameState, action: Action, random_input: object | None) -> None:
    _SALONIKA.apply(state, action)


register_decision_handler("EVENT_ENTRENCH", _apply_entrench)
register_decision_handler("LANDWEHR", _apply_landwehr)
register_decision_handler("SALONIKA", _apply_salonika)


def register_operational_events(registry: dict[str, object]) -> None:
    for card_id in ("ENTRENCH_AP", "ENTRENCH_CP"):
        registry[card_id] = _ENTRENCH
    registry["LANDWEHR"] = _LANDWEHR
    registry["SALONIKA"] = _SALONIKA
