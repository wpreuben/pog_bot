"""국가별 RP 지출, 군·군단 재건과 배치."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError
from .supply import supply_status


def _capital_open(state: FullGameState, nation: str) -> bool:
    if nation in {"BE", "SB"}:
        return True
    capitals = [place for place, space in load_data().spaces.items()
                if space["nation"] == nation and space["capital"]]
    return all(state["spaces"][place]["control"] == load_data().spaces[place]["side"]
               and not state["spaces"][place]["fort_besieged"] for place in capitals)


def _rp_sources(nation: str) -> tuple[str, ...] | None:
    if nation in {"GE", "AH"}:
        return ("ESSEN", "BRESLAU")
    if nation == "TU":
        return ("CONSTANTINOPLE",)
    if nation == "BU":
        return ("SOFIA",)
    if nation in {"RU", "RO"}:
        return ("PETROGRAD", "MOSCOW", "KHARKOV", "CAUCASUS")
    return None


def _can_receive_rp(state: FullGameState, unit_id: str, place: str | None = None) -> bool:
    definition = load_data().units[unit_id]
    location = place if place is not None else state["units"][unit_id]["location"]
    if location in {"AP_RESERVE_BOX", "CP_RESERVE_BOX"}:
        return True
    return supply_status(state, unit_id, location=location, purpose="RP",
                         allowed_sources=_rp_sources(definition["nation"])).supplied


def _can_place(state: FullGameState, unit_id: str, place: str) -> bool:
    data = load_data()
    definition = data.units[unit_id]
    side = definition["side"]
    if state["spaces"][place]["control"] != side or not _can_receive_rp(state, unit_id, place):
        return False
    if sum(unit["location"] == place for unit in state["units"].values()) >= 3:
        return False
    if state["spaces"][place]["fort_besieged"]:
        return False
    return True


def _army_spaces(state: FullGameState, unit_id: str) -> list[str]:
    data = load_data()
    definition = data.units[unit_id]
    nation = definition["nation"]
    if nation == "BE":
        preferred = [place for place in ("BRUSSELS", "ANTWERP", "OSTEND") if _can_place(state, unit_id, place)]
        return preferred or (["CALAIS"] if _can_place(state, unit_id, "CALAIS") else [])
    if nation == "US":
        return [place for place, space in data.spaces.items()
                if space["nation"] == "FR" and space["ap_port"] and _can_place(state, unit_id, place)]
    possible = [place for place, space in data.spaces.items()
                if space["nation"] == nation and (space["capital"] or space["supply"])
                and _can_place(state, unit_id, place)]
    if nation == "FR" and "PARIS" not in possible:
        if state["spaces"]["PARIS"]["control"] == "AP" and not state["spaces"]["PARIS"]["fort_besieged"]:
            if sum(unit["location"] == "PARIS" for unit in state["units"].values()) >= 3 and _can_place(state, unit_id, "ORLEANS"):
                possible.append("ORLEANS")
    if nation == "SB":
        if state["spaces"]["NIS"]["control"] == "CP":
            possible = [place for place in possible if place != "BELGRADE"]
        if state["events"].get("SALONIKA") or state["events"].get("GREECE_NEUTRAL_ENTRY"):
            if _can_place(state, unit_id, "SALONIKA"):
                possible.append("SALONIKA")
    return sorted(set(possible))


def legal_replacement_actions(state: FullGameState, side: str) -> list[Action]:
    if state["phase"] != f"REPLACEMENT_{side}" or state["active_side"] != side:
        return []
    data = load_data()
    points = state["players"][side]["replacement_points"]
    actions = []
    for uid, unit in state["units"].items():
        definition = data.units[uid]
        nation = definition["nation"]
        if definition["side"] != side or definition["not_replaceable"] or unit["permanent"]:
            continue
        if not state["war_nations"].get(nation, True) or not _capital_open(state, nation):
            continue
        pool = definition["rp_type"]
        cost = 1 if definition["type"] == "ARMY" else 0.5
        if nation == "RU" and state["events"].get("BOLSHEVIK_REVOLUTION"):
            spent = state["flags"].get("ru_rp_spent", {})
            if spent.get("turn") == state["turn"] and spent.get("amount", 0) + cost > 1:
                continue
        if pool is None or points.get(pool, 0) < cost:
            continue
        if unit["eliminated"] and unit["location"] is None:
            if definition["type"] == "CORPS":
                actions.append({"type": "REBUILD_CORPS", "actor": side, "unit_id": uid})
            else:
                actions.extend({"type": "REBUILD_ARMY", "actor": side, "unit_id": uid, "space_id": place}
                               for place in _army_spaces(state, uid))
        elif unit["reduced"] and unit["location"] is not None and _can_receive_rp(state, uid):
            actions.append({"type": "FLIP_UNIT", "actor": side, "unit_id": uid})
    actions.append({"type": "END_REPLACEMENT", "actor": side})
    return actions


def _award_sedan_bonus(state: FullGameState) -> None:
    if state["flags"].get("sedan_bonus_awarded_turn") == state["turn"]:
        return
    if state["players"]["CP"]["commitment"] != "TOTAL" or state["flags"].get("cp_first_total_war_turn") == state["turn"]:
        return
    if state["spaces"]["SEDAN"]["control"] != "CP":
        return
    data = load_data()
    count = sum(space["nation"] in {"FR", "BE"} and state["spaces"][place]["control"] == "CP"
                for place, space in data.spaces.items() if space["kind"] == "BOARD")
    if count >= 3:
        points = state["players"]["CP"]["replacement_points"]
        points["GE"] = points.get("GE", 0) + 1
        state["flags"]["sedan_bonus_awarded_turn"] = state["turn"]


def begin_replacement_phase(state: FullGameState, side: str) -> FullGameState:
    state["phase"] = f"REPLACEMENT_{side}"
    state["active_side"] = side
    if side == "CP":
        _award_sedan_bonus(state)
    points = state["players"][side]["replacement_points"]
    if any(value > 0 for value in points.values()):
        state["decision"] = {"kind": "REPLACEMENT", "actor": side, "options": legal_replacement_actions(state, side)}
    else:
        state["decision"] = None
    return state


def close_replacement_phase(state: FullGameState, side: str) -> FullGameState:
    if state["phase"] != f"REPLACEMENT_{side}" or state["active_side"] != side:
        raise IllegalActionError("지금은 해당 진영의 보충 단계가 아닙니다")
    state["players"][side]["replacement_points"] = {}
    if side == "AP":
        return begin_replacement_phase(state, "CP")
    state["phase"] = "DRAW"
    state["active_side"] = "CHANCE"
    state["decision"] = None
    return state


def apply_replacement_action(state: FullGameState, action: Action) -> FullGameState:
    side = state["active_side"]
    if action not in legal_replacement_actions(state, side):
        raise IllegalActionError("보충 행동이 합법적이지 않습니다")
    if action["type"] == "END_REPLACEMENT":
        return close_replacement_phase(state, side)
    uid = action["unit_id"]
    definition = load_data().units[uid]
    unit = state["units"][uid]
    if action["type"] == "FLIP_UNIT":
        unit["reduced"] = False
    elif action["type"] == "REBUILD_CORPS":
        unit["location"] = "ARABIA" if definition["nation"] == "ANA" else f"{side}_RESERVE_BOX"
        unit["reduced"] = True
        unit["eliminated"] = False
    elif action["type"] == "REBUILD_ARMY":
        unit["location"] = action["space_id"]
        unit["reduced"] = True
        unit["eliminated"] = False
    pool = definition["rp_type"]
    cost = 1 if definition["type"] == "ARMY" else 0.5
    state["players"][side]["replacement_points"][pool] -= cost
    if definition["nation"] == "RU" and state["events"].get("BOLSHEVIK_REVOLUTION"):
        spent = state["flags"].setdefault("ru_rp_spent", {"turn": state["turn"], "amount": 0})
        if spent["turn"] != state["turn"]:
            spent.update({"turn": state["turn"], "amount": 0})
        spent["amount"] += cost
    state["decision"]["options"] = legal_replacement_actions(state, side)
    return state


def _apply_replacement(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_replacement_action(state, action)


register_decision_handler("REPLACEMENT", _apply_replacement)
