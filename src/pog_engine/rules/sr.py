"""전략 재배치의 선택, 경로, 비용."""

from collections import deque

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError


def _sr_cost(unit: dict) -> int:
    return 4 if unit["type"] == "ARMY" else 1


def _reserve_sources(nation: str) -> tuple[str, ...] | None:
    if nation in {"GE", "AH"}:
        return ("ESSEN", "BRESLAU")
    if nation == "TU":
        return ("CONSTANTINOPLE",)
    if nation == "BU":
        return ("SOFIA",)
    if nation in {"RU", "RO"}:
        return ("PETROGRAD", "MOSCOW", "KHARKOV", "CAUCASUS")
    return None


def _friendly(state: FullGameState, space_id: str, side: str) -> bool:
    data = load_data()
    space = state["spaces"][space_id]
    return (space["control"] == side or space["fort_besieged"]) and not any(
        unit["location"] == space_id and data.units[unit_id]["side"] != side
        for unit_id, unit in state["units"].items()
    )


def _allowed_destination(state: FullGameState, unit_id: str, destination: str, *, transit: bool = False) -> bool:
    data = load_data()
    unit = data.units[unit_id]
    if data.spaces[destination]["kind"] != "BOARD":
        return False
    if not _friendly(state, destination, unit["side"]):
        return False
    if not transit and sum(other["location"] == destination for other in state["units"].values()) >= 3:
        return False
    if unit["nation"] == "RU" and data.spaces[destination]["nation"] != "RU":
        return False
    if state["events"].get("TREATY_OF_BREST_LITOVSK") and unit["side"] == "AP":
        if any(other["location"] == destination and data.units[other_id]["side"] == "AP"
               and (data.units[other_id]["nation"] == "RU") != (unit["nation"] == "RU")
               for other_id, other in state["units"].items()):
            return False
    if unit["type"] == "ARMY" and data.spaces[destination]["map"] == "neareast" and not unit["near_east"]:
        return False
    if unit["type"] == "ARMY" and state["players"]["AP"]["commitment"] != "TOTAL":
        if data.spaces[destination]["nation"] == "IT" and unit["nation"] not in {"IT", "AH"}:
            return False
        if unit["nation"] == "GE" and destination in {"TRENT", "VILLACH", "TRIESTE"}:
            return False
    return True


def _capital_open(state: FullGameState, nation: str) -> bool:
    if nation in {"BE", "SB", "MN"}:
        return True
    data = load_data()
    capitals = [s for s in data.spaces.values() if s["nation"] == nation and s["capital"]]
    return not any(state["spaces"][s["id"]]["control"] != s["side"] or state["spaces"][s["id"]]["fort_besieged"] for s in capitals)


def _overland_reachable(state: FullGameState, unit_id: str, destination: str) -> bool:
    data = load_data()
    start = state["units"][unit_id]["location"]
    if data.spaces[start]["kind"] != "BOARD":
        return False
    nation = data.units[unit_id]["nation"]
    frontier = deque([start])
    visited = {start}
    while frontier:
        for next_space in data.neighbors(frontier.popleft(), nation):
            if next_space in visited or not _allowed_destination(state, unit_id, next_space, transit=True):
                continue
            if next_space == destination:
                return True
            visited.add(next_space)
            frontier.append(next_space)
    return False


def _destinations(state: FullGameState, unit_id: str) -> list[str]:
    from .supply import supply_status

    data = load_data()
    unit = data.units[unit_id]
    start = state["units"][unit_id]["location"]
    side, nation = unit["side"], unit["nation"]
    reserve = f"{side}_RESERVE_BOX"
    reserve_sources = _reserve_sources(nation)
    reserve_purpose = "RESERVE_SR" if reserve_sources is not None else "NORMAL"
    if nation == "MN":
        return ["CETINJE"] if start == reserve and _allowed_destination(state, unit_id, "CETINJE") else (
            [reserve] if start == "CETINJE" else []
        )
    found: set[str] = set()
    overland: set[str] = set()
    if start == reserve:
        if not _capital_open(state, nation):
            return []
        for destination, space in data.spaces.items():
            if not _allowed_destination(state, unit_id, destination):
                continue
            same_nation_unit = any(
                other["location"] == destination and data.units[other_id]["nation"] == nation
                and other_id not in {"BR_ANA_CORPS_1", "TU_SN_CORPS_1"}
                for other_id, other in state["units"].items()
            )
            home_source = space["nation"] == nation and (space["capital"] or space["supply"])
            us_port = nation == "US" and space["nation"] == "FR" and space["ap_port"]
            if same_nation_unit or home_source or us_port:
                found.add(destination)
    else:
        frontier = deque([start])
        visited = {start}
        while frontier:
            current = frontier.popleft()
            for destination in data.neighbors(current, nation):
                if destination in visited or not _allowed_destination(state, unit_id, destination, transit=True):
                    continue
                visited.add(destination)
                if _allowed_destination(state, unit_id, destination):
                    found.add(destination)
                    overland.add(destination)
                frontier.append(destination)
        if unit["type"] == "CORPS" and _capital_open(state, nation):
            found.add(reserve)
        if unit["type"] == "CORPS" and nation != "RU":
            port_key = "ap_port" if side == "AP" else "cp_port"
            if data.spaces[start][port_key] and _friendly(state, start, side):
                for destination, space in data.spaces.items():
                    if not space[port_key] or not _allowed_destination(state, unit_id, destination):
                        continue
                    if side == "CP" and (space["nation"] not in {"GE", "RU"} or data.spaces[start]["nation"] not in {"GE", "RU"}):
                        continue
                    if side == "AP" and (space["nation"] in {"GE", "RU"} or data.spaces[start]["nation"] in {"GE", "RU"}):
                        continue
                    found.add(destination)
    restrictions = state["flags"].get("near_east_sr", {})
    start_ne = data.spaces[start]["map"] == "neareast"
    for destination in tuple(found):
        destination_ne = data.spaces[destination]["map"] == "neareast"
        if destination_ne == start_ne:
            continue
        if nation == "RU" and (unit["type"] == "ARMY" or restrictions.get("RU", 0) >= 1):
            found.discard(destination)
            continue
        if side == "CP" and nation != "TU" and restrictions.get("CP", 0) >= 1:
            found.discard(destination)
            continue
        if destination not in overland:
            if nation in {"FR", "IT", "GR", "RO", "SB", "US", "BE", "CND", "PT", "ANA"}:
                found.discard(destination)
            elif nation == "RU" and start != reserve:
                found.discard(destination)
            elif nation == "BR" and (unit["name"].startswith(("BR BEF", "CND", "PT")) or restrictions.get("BR", 0) >= 1):
                found.discard(destination)
    found.discard(start)
    if start == reserve:
        return sorted(
            place for place in found
            if supply_status(state, unit_id, location=place, purpose=reserve_purpose,
                             allowed_sources=reserve_sources).supplied
        )
    if reserve in found and not supply_status(
        state, unit_id, purpose=reserve_purpose, allowed_sources=reserve_sources
    ).supplied:
        found.remove(reserve)
    return sorted(place for place in found if place == reserve or supply_status(state, unit_id, location=place).supplied)


def legal_sr_actions(state: FullGameState) -> list[Action]:
    if state["phase"] != "SR":
        return []
    side = state["active_side"]
    chosen = state["sr"]["unit"]
    if chosen:
        actions = [{"type": "SR_TO", "actor": side, "to": destination} for destination in _destinations(state, chosen)]
        actions.append({"type": "SKIP_SR_UNIT", "actor": side})
        return actions
    data = load_data()
    from .supply import supply_status
    actions = []
    for unit_id, unit in state["units"].items():
        definition = data.units[unit_id]
        if unit["location"] is None or definition["side"] != side or unit_id in state["sr"]["done"]:
            continue
        if _sr_cost(definition) > state["sr_remaining"]:
            continue
        if definition["nation"] in state["war_nations"] and not state["war_nations"][definition["nation"]]:
            continue
        if not supply_status(state, unit_id).supplied:
            continue
        actions.append({"type": "SELECT_SR_UNIT", "actor": side, "unit_id": unit_id})
    actions.append({"type": "END_SR", "actor": side})
    return actions


def apply_sr_action(state: FullGameState, action: Action) -> FullGameState:
    if action not in legal_sr_actions(state):
        raise IllegalActionError("전략 재배치 행동이 합법적이지 않습니다")
    kind = action["type"]
    if kind == "SELECT_SR_UNIT":
        state["sr"]["unit"] = action["unit_id"]
    elif kind == "SR_TO":
        unit_id = state["sr"]["unit"]
        data = load_data()
        source = state["units"][unit_id]["location"]
        source_ne = data.spaces[source]["map"] == "neareast"
        destination_ne = data.spaces[action["to"]]["map"] == "neareast"
        if source_ne != destination_ne:
            nation = data.units[unit_id]["nation"]
            key = "RU" if nation == "RU" else ("CP" if state["active_side"] == "CP" and nation != "TU" else None)
            if nation == "BR" and not _overland_reachable(state, unit_id, action["to"]):
                key = "BR"
            if key:
                counters = state["flags"].setdefault("near_east_sr", {})
                counters[key] = counters.get(key, 0) + 1
        state["units"][unit_id]["location"] = action["to"]
        state["sr_remaining"] -= _sr_cost(load_data().units[unit_id])
        state["sr"]["done"].append(unit_id)
        state["sr"]["unit"] = None
    elif kind == "SKIP_SR_UNIT":
        state["sr"]["done"].append(state["sr"]["unit"])
        state["sr"]["unit"] = None
    elif kind == "END_SR":
        from .turn import complete_action

        state["phase"] = "ACTION"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return state
    state["decision"]["options"] = legal_sr_actions(state)
    return state


def _apply_sr(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_sr_action(state, action)


register_decision_handler("SR", _apply_sr)
