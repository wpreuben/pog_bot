"""국가별 보급 경로와 동시 소모 판정."""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass

from pog_engine.data import load_data
from pog_engine.model import FullGameState


@dataclass(frozen=True)
class SupplyStatus:
    supplied: bool
    source: str | None = None
    path: tuple[str, ...] = ()
    special: str | None = None


_RU_SOURCES = ("PETROGRAD", "MOSCOW", "KHARKOV", "CAUCASUS")
_CP_SOURCES = ("ESSEN", "BRESLAU", "SOFIA", "CONSTANTINOPLE")


def _sources(state: FullGameState, side: str, nation: str | None) -> tuple[str, ...]:
    if side == "CP":
        return tuple(s for s in _CP_SOURCES if s in {"ESSEN", "BRESLAU"} or state["war_nations"].get(load_data().spaces[s]["nation"], True))
    if nation in {"RU", "RO", "SB"}:
        return _RU_SOURCES + ("BELGRADE",) + (("SALONIKA",) if nation == "SB" else ())
    if nation is None:
        return ("LONDON",) + _RU_SOURCES + ("BELGRADE", "SALONIKA")
    return ("LONDON",)


def _port_allowed(state: FullGameState, space_id: str, side: str) -> bool:
    data = load_data()
    space = data.spaces[space_id]
    if side == "CP":
        return bool(space["cp_port"] and space["nation"] in {"GE", "RU"} and not state["spaces"][space_id]["fort_besieged"])
    if not space["ap_port"] or space["nation"] in {"GE", "RU"} or state["spaces"][space_id]["fort_besieged"]:
        return False
    return space_id != "CONSTANTINOPLE" or state["spaces"]["GALLIPOLI"]["control"] == "AP"


def _trace(state: FullGameState, origin: str, side: str, nation: str | None,
           sources_override: tuple[str, ...] | None = None) -> SupplyStatus:
    data = load_data()
    sources = set(sources_override if sources_override is not None else _sources(state, side, nation))
    if data.spaces[origin]["kind"] != "BOARD":
        return SupplyStatus(False)
    enemy = "AP" if side == "CP" else "CP"
    enemy_spaces = {
        unit["location"] for uid, unit in state["units"].items()
        if data.units[uid]["side"] == enemy and unit["location"] is not None
    }
    friendly_spaces = {
        unit["location"] for uid, unit in state["units"].items()
        if data.units[uid]["side"] == side and unit["location"] is not None
    }

    def traversable(place: str) -> bool:
        static = data.spaces[place]
        if static["kind"] != "BOARD" or place in enemy_spaces:
            return False
        if static["nation"] in state["war_nations"] and not state["war_nations"][static["nation"]]:
            return False
        dynamic = state["spaces"][place]
        return dynamic["control"] == side or (dynamic["fort_besieged"] and place in friendly_spaces)

    if not traversable(origin):
        return SupplyStatus(False)
    ports = [place for place in data.spaces if traversable(place) and _port_allowed(state, place, side)]
    use_sea = side == "CP" or nation not in {"RU", "RO", "SB"}
    queue = deque([origin])
    parent: dict[str, str | None] = {origin: None}
    edge_nation = "RU" if nation in {"RU", "RO", "SB"} else nation
    while queue:
        current = queue.popleft()
        if current in sources and state["spaces"][current]["control"] == side:
            path = [current]
            while parent[path[-1]] is not None:
                path.append(parent[path[-1]])
            path.reverse()
            return SupplyStatus(True, current, tuple(path))
        neighbors = data.neighbors(current, edge_nation)
        if use_sea and current in ports:
            neighbors = neighbors | set(ports)
        for next_space in neighbors:
            if next_space in parent or not traversable(next_space):
                continue
            parent[next_space] = current
            queue.append(next_space)
    return SupplyStatus(False)


def supply_status(state: FullGameState, unit_id: str, *, location: str | None = None,
                  purpose: str = "NORMAL", allowed_sources: tuple[str, ...] | None = None) -> SupplyStatus:
    data = load_data()
    if unit_id not in data.units:
        raise ValueError(f"알 수 없는 유닛: {unit_id}")
    definition = data.units[unit_id]
    place = location if location is not None else state["units"][unit_id]["location"]
    if place is None or data.spaces[place]["kind"] != "BOARD":
        return SupplyStatus(True, special="OFF_MAP")
    nation, side = definition["nation"], definition["side"]
    if nation == "MN" and place == "CETINJE":
        return SupplyStatus(True, special="MONTENEGRO")
    if nation == "SB" and data.spaces[place]["nation"] == "SB" and purpose != "RESERVE_SR":
        return SupplyStatus(True, special="SERBIA")
    if nation in {"ANA", "SN"} and data.spaces[place]["map"] == "neareast":
        return SupplyStatus(True, special="NEAR_EAST")
    if nation == "TU" and place == "MEDINA" and purpose == "ATTRITION":
        return SupplyStatus(True, special="MEDINA_ATTRITION")
    if nation != "TU" and side == "CP" and place == "MEDINA":
        return SupplyStatus(False)
    return _trace(state, place, side, nation, allowed_sources)


def supplied_spaces(state: FullGameState, side: str) -> frozenset[str]:
    if side not in {"AP", "CP"}:
        raise ValueError("진영은 AP 또는 CP여야 합니다")
    data = load_data()
    nations = (None, "RU", "IT") if side == "AP" else (None, "TU")
    return frozenset(
        place for place, definition in data.spaces.items()
        if definition["kind"] == "BOARD" and state["spaces"][place]["control"] == side
        and any(_trace(state, place, side, nation).supplied for nation in nations)
    )


def resolve_attrition(state: FullGameState) -> FullGameState:
    next_state = deepcopy(state)
    data = load_data()
    lost_units = [
        uid for uid, unit in state["units"].items()
        if unit["location"] is not None and data.spaces[unit["location"]]["kind"] == "BOARD"
        and state["war_nations"].get(data.units[uid]["nation"], True)
        and not supply_status(state, uid, purpose="ATTRITION").supplied
    ]
    unsupplied_spaces = {
        side: set(data.spaces) - supplied_spaces(state, side)
        for side in ("AP", "CP")
    }
    for unit_id in lost_units:
        unit = next_state["units"][unit_id]
        unit["location"] = None
        unit["eliminated"] = True
        if data.units[unit_id]["type"] == "ARMY":
            unit["permanent"] = True
    for place, definition in data.spaces.items():
        if definition["kind"] != "BOARD":
            continue
        if definition["nation"] == "NONE" or not state["war_nations"].get(definition["nation"], True):
            continue
        side = state["spaces"][place]["control"]
        if side not in {"AP", "CP"} or place not in unsupplied_spaces[side]:
            continue
        if side == "AP" and definition["nation"] == "SB":
            continue
        if definition["fort"] and not state["spaces"][place]["fort_destroyed"] and definition["side"] == side:
            continue
        enemy = "AP" if side == "CP" else "CP"
        next_state["spaces"][place]["control"] = enemy
        if state["spaces"][place]["vp"]:
            next_state["vp"] += 1 if enemy == "CP" else -1
    return next_state
