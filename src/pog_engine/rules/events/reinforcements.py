"""9.5.3: 기본 증원 카드와 유닛 배치 창."""

from collections import Counter
import re

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError


def reinforcement_unit_ids(state: FullGameState, card_id: str) -> list[str]:
    card = load_data().cards[card_id]
    available: dict[str, list[str]] = {}
    for unit_id, unit in load_data().units.items():
        dynamic = state["units"][unit_id]
        if dynamic["location"] is None and not dynamic["eliminated"] and not dynamic["permanent"]:
            available.setdefault(unit["name"], []).append(unit_id)
    selected: list[str] = []
    for name, count in Counter(card["reinforcement_units"]).items():
        candidates = sorted(available.get(name, []),
                            key=lambda uid: (re.sub(r"_\d+$", "", uid),
                                             int(uid.rsplit("_", 1)[-1])))
        if len(candidates) < count:
            return []
        selected.extend(candidates[:count])
    return selected


def _stack_count(state: FullGameState, place: str) -> int:
    return sum(unit["location"] == place for unit in state["units"].values())


def _army_spaces(state: FullGameState, unit_id: str) -> list[str]:
    from pog_engine.rules.supply import supply_status

    data = load_data()
    unit = data.units[unit_id]
    nation = unit["nation"]
    side = unit["side"]
    name = unit["name"]
    special: list[str] = []
    if name == "BR MEF" and not state["events"].get("SALONIKA"):
        special = [f"MEF{i}" for i in range(1, 5)]
    elif name == "FR Orient" and state["events"].get("SALONIKA"):
        special = ["SALONIKA"]
    elif name == "BR NE" and state["events"].get("SINAI_PIPELINE"):
        special = ["ALEXANDRIA"]
    elif name == "RU CAU":
        special = [space_id for space_id, static in data.spaces.items()
                   if static["nation"] == "RU" and static["map"] == "neareast"]
    candidates = set(special)
    if nation == "US":
        candidates.update(space_id for space_id, static in data.spaces.items()
                          if static["nation"] == "FR" and static["ap_port"])
    else:
        candidates.update(space_id for space_id, static in data.spaces.items()
                          if static["nation"] == nation and (static["capital"] or static["supply"]))
        if nation == "FR" and _stack_count(state, "PARIS") >= 3 and state["spaces"]["PARIS"]["control"] == "AP":
            candidates.add("ORLEANS")
    result = []
    for place in sorted(candidates):
        static, dynamic = data.spaces[place], state["spaces"][place]
        if dynamic["control"] != side or dynamic["fort_besieged"] or _stack_count(state, place) >= 3:
            continue
        if static["kind"] != "BOARD":
            continue
        if place == "ORLEANS" and (state["spaces"]["PARIS"]["fort_besieged"] or
                                   state["spaces"]["PARIS"]["control"] != "AP"):
            continue
        if (place not in special or name == "RU CAU") and not supply_status(state, unit_id, location=place).supplied:
            continue
        result.append(place)
    return result


def placement_spaces(state: FullGameState, unit_id: str) -> list[str]:
    unit = load_data().units[unit_id]
    if unit["type"] == "CORPS":
        if unit["name"] == "TU SNc":
            return ["LIBYA"] if not any(
                dynamic["location"] == "LIBYA" and load_data().units[other]["side"] == "AP"
                for other, dynamic in state["units"].items()
            ) else []
        if unit["name"] == "BR ANAc":
            return ["ARABIA"]
        return [f"{unit['side']}_RESERVE_BOX"]
    return _army_spaces(state, unit_id)


def _can_place_all(state: FullGameState, remaining: list[str]) -> bool:
    if not remaining:
        return True
    unit_id = remaining[0]
    for place in placement_spaces(state, unit_id):
        state["units"][unit_id]["location"] = place
        valid = _can_place_all(state, remaining[1:])
        state["units"][unit_id]["location"] = None
        if valid:
            return True
    return False


class ReinforcementHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        card = load_data().cards[card_id]
        nation = card["reinforcement_nation"]
        if state["turn"] == 1 or state["flags"].get("reinforced_this_turn", {}).get(nation) == state["turn"]:
            return False
        if nation in state["war_nations"] and not state["war_nations"][nation]:
            return False
        if nation == "US" and state["us_entry"] < 3:
            return False
        if nation == "US" and state["events"].get("U_BOATS_UNLEASHED") and not state["events"].get("CONVOY"):
            return False
        if card_id == "MEF_BR_REINFORCEMENTS" and not state["war_nations"]["TU"]:
            return False
        unit_ids = reinforcement_unit_ids(state, card_id)
        return bool(unit_ids) and _can_place_all(state, unit_ids)

    def legal_choices(self, state: FullGameState) -> list[Action]:
        pending = state["reinforcements"]["pending"]
        if not pending:
            return []
        unit_id = pending[0]
        actions = []
        for place in placement_spaces(state, unit_id):
            state["units"][unit_id]["location"] = place
            valid = _can_place_all(state, pending[1:])
            state["units"][unit_id]["location"] = None
            if valid:
                actions.append({"type": "PLACE_REINFORCEMENT", "actor": state["active_side"],
                                "unit_id": unit_id, "to": place})
        return actions

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        if choice is None:
            card_id = state["players"][state["active_side"]]["removed"][-1]
            card = load_data().cards[card_id]
            state["flags"].setdefault("reinforced_this_turn", {})[card["reinforcement_nation"]] = state["turn"]
            state["events"][card_id] = state["turn"]
            state["reinforcements"] = {"card_id": card_id, "pending": reinforcement_unit_ids(state, card_id)}
            state["phase"] = "REINFORCEMENTS"
        else:
            if choice not in self.legal_choices(state):
                raise IllegalActionError("증원 배치 장소가 잘못되었습니다")
            unit_id, place = choice["unit_id"], choice["to"]
            state["units"][unit_id]["location"] = place
            state["units"][unit_id]["reduced"] = False
            state["reinforcements"]["pending"].pop(0)
            if place.startswith("MEF"):
                state["flags"]["mef_beachhead"] = place
                state["flags"]["mef_beachhead_captured"] = False
            if not state["reinforcements"]["pending"]:
                from pog_engine.rules.turn import complete_action

                state["phase"] = "ACTION"
                del state["reinforcements"]
                next_state = complete_action(state)
                state.clear()
                state.update(next_state)
                return state
        state["decision"] = {"kind": "REINFORCEMENTS", "actor": state["active_side"],
                             "options": self.legal_choices(state)}
        return state


_HANDLER = ReinforcementHandler()


def _apply_reinforcement(state: FullGameState, action: Action, random_input: object | None) -> None:
    _HANDLER.apply(state, action)


register_decision_handler("REINFORCEMENTS", _apply_reinforcement)


def register_reinforcements(registry: dict[str, object]) -> None:
    for card_id, card in load_data().cards.items():
        if card["reinforcement_nation"]:
            registry[card_id] = _HANDLER
