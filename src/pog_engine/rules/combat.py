"""공격 선언의 합법성, 전투력, 화력표와 측면 공격 계산."""

from functools import lru_cache
from importlib.resources import files
from itertools import combinations
import json

from pog_engine.data import load_data
from pog_engine.model import Action, FullGameState
from .supply import supply_status


@lru_cache(maxsize=1)
def _crt() -> dict:
    table = json.loads(files("pog_engine.data").joinpath("crt.json").read_text(encoding="utf-8"))
    assert tuple(map(int, table["CORPS"])) == tuple(range(9))
    assert tuple(map(int, table["ARMY"])) == (1, 2, 3, 4, 5, 6, 9, 12, 15, 16)
    assert all(len(row) == 6 for fire_table in table.values() for row in fire_table.values())
    return table


def _nation(unit: dict) -> str:
    nation = unit["nation"]
    if nation in {"ANA", "AUS", "CND", "PT"}:
        return "BR"
    if nation == "SN":
        return "TU"
    if nation == "MN":
        return "SB"
    return nation


def _can_target(state: FullGameState, destination: str, side: str) -> bool:
    data = load_data()
    enemy = "AP" if side == "CP" else "CP"
    if data.spaces[destination]["kind"] != "BOARD":
        return False
    if not state["war_nations"].get(data.spaces[destination]["nation"], True):
        return False
    enemy_units = any(
        unit["location"] == destination and data.units[uid]["side"] == enemy
        for uid, unit in state["units"].items()
    )
    enemy_fort = (
        data.spaces[destination]["fort"] > 0
        and state["spaces"][destination]["control"] == enemy
        and not state["spaces"][destination]["fort_destroyed"]
    )
    return (enemy_units or enemy_fort) and destination not in state.get("attacked_spaces", [])


def _valid_group(state: FullGameState, unit_ids: tuple[str, ...], destination: str) -> bool:
    data = load_data()
    places = {state["units"][uid]["location"] for uid in unit_ids}
    if "LONDON" in places and not any(data.spaces[place]["nation"] in {"FR", "BE"} for place in places):
        return False
    nations = {_nation(data.units[uid]) for uid in unit_ids}
    if len(places) > 1 and len(nations) > 1:
        if not any(
            {_nation(data.units[uid]) for uid in unit_ids if state["units"][uid]["location"] == place} == nations
            for place in places
        ):
            return False
    if any(data.units[uid]["nation"] == "RU" and data.units[uid]["type"] == "ARMY"
           and state["units"][uid]["location"] == "CAUCASUS"
           and data.spaces[destination]["map"] == "neareast" for uid in unit_ids):
        return False
    return True


def legal_attack_declarations(state: FullGameState) -> list[Action]:
    if state["phase"] != "COMBAT":
        return []
    data = load_data()
    side = state["active_side"]
    if side not in {"AP", "CP"}:
        return []
    targets: dict[str, list[str]] = {}
    for unit_id, unit in state["units"].items():
        start = unit["location"]
        definition = data.units[unit_id]
        if start not in state["activated"]["ATTACK"] or unit_id in state.get("attacked_units", []):
            continue
        if definition["side"] != side or not state["war_nations"].get(definition["nation"], True):
            continue
        if unit_id in state.get("activated_oos", []) or not supply_status(state, unit_id).supplied:
            continue
        for destination in data.neighbors(start, definition["nation"]):
            if _can_target(state, destination, side):
                targets.setdefault(destination, []).append(unit_id)
    actions = []
    for destination in sorted(targets):
        candidates = sorted(targets[destination])
        for size in range(1, len(candidates) + 1):
            for selected in combinations(candidates, size):
                if _valid_group(state, selected, destination):
                    actions.append({
                        "type": "DECLARE_ATTACK", "actor": side,
                        "unit_ids": list(selected), "defender_space": destination,
                    })
    return actions


def combat_strength(state: FullGameState, context: dict, side: str) -> int:
    data = load_data()
    attacker = context["attacker"]
    if side == attacker:
        units = context["attackers"]
    else:
        destination = context["defender_space"]
        units = [uid for uid, unit in state["units"].items()
                 if unit["location"] == destination and data.units[uid]["side"] == side]
    strength = sum(
        data.units[uid]["reduced_cf"] if state["units"][uid]["reduced"] else data.units[uid]["cf"]
        for uid in units
    )
    if side != attacker:
        destination = context["defender_space"]
        if data.spaces[destination]["fort"] and not state["spaces"][destination]["fort_destroyed"]:
            strength += data.spaces[destination]["fort"]
    return strength


def combat_snapshot(state: FullGameState, context: dict) -> dict:
    data = load_data()
    attacker = context["attacker"]
    defender = "AP" if attacker == "CP" else "CP"
    destination = context["defender_space"]
    defenders = [uid for uid, unit in state["units"].items()
                 if unit["location"] == destination and data.units[uid]["side"] == defender]
    trench = state["spaces"][destination]["trenches"][defender]
    if context.get("trench_negated"):
        trench = 0
    unoccupied_fort = not defenders and data.spaces[destination]["fort"] > 0
    terrain = data.spaces[destination]["terrain"]
    return {
        "attacker": attacker,
        "defender": defender,
        "strengths": {
            attacker: combat_strength(state, context, attacker),
            defender: combat_strength(state, context, defender),
        },
        "tables": {
            attacker: "ARMY" if any(data.units[uid]["type"] == "ARMY" for uid in context["attackers"]) else "CORPS",
            defender: "ARMY" if any(data.units[uid]["type"] == "ARMY" for uid in defenders) else "CORPS",
        },
        "shifts": {
            attacker: -(0 if unoccupied_fort else trench) - (1 if terrain in {"MOUNTAIN", "SWAMP"} else 0),
            defender: 1 if trench else 0,
        },
    }


def fire_column(context: dict, side: str) -> int:
    table = context["tables"][side]
    columns = sorted(int(key) for key in _crt()[table])
    strength = context["strengths"][side]
    base = max((index for index, column in enumerate(columns) if column <= strength), default=0)
    index = min(max(base + context["shifts"].get(side, 0), 0), len(columns) - 1)
    return columns[index]


def crt_result(table: str, column: int, die: int) -> int:
    if table not in {"ARMY", "CORPS"} or not isinstance(column, int) or not isinstance(die, int):
        raise ValueError("CRT의 표, 열, 주사위 값이 잘못되었습니다")
    columns = sorted(int(key) for key in _crt()[table])
    selected = max((value for value in columns if value <= column), default=columns[0])
    return _crt()[table][str(selected)][min(max(die, 1), 6) - 1]


def flank_modifier(state: FullGameState, context: dict) -> int | None:
    data = load_data()
    destination = context["defender_space"]
    attackers = context["attackers"]
    places = {state["units"][uid]["location"] for uid in attackers}
    pinning = context.get("pinning_space")
    if len(places) < 2 or pinning not in places:
        return None
    if not any(data.units[uid]["type"] == "ARMY" for uid in attackers):
        return None
    if data.spaces[destination]["terrain"] in {"MOUNTAIN", "SWAMP"}:
        return None
    defender = "AP" if context["attacker"] == "CP" else "CP"
    if state["spaces"][destination]["trenches"][defender] and not context.get("trench_negated"):
        return None
    defending_units = any(unit["location"] == destination and data.units[uid]["side"] == defender
                          for uid, unit in state["units"].items())
    if not defending_units and data.spaces[destination]["fort"] and not state["spaces"][destination]["fort_destroyed"]:
        return None
    modifier = 0
    for place in places - {pinning}:
        adjacent_enemy = any(
            edge["allowed_nations"] is None and place in {edge["a"], edge["b"]}
            and (edge["b"] if edge["a"] == place else edge["a"]) != destination
            and any(unit["location"] == (edge["b"] if edge["a"] == place else edge["a"])
                    and data.units[uid]["side"] == defender for uid, unit in state["units"].items())
            for edge in data.edges
        )
        if not adjacent_enemy:
            modifier += 1
    return modifier
