"""요새의 통제, 공성 조건과 항복 주사위."""

from copy import deepcopy
from dataclasses import dataclass

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError


@dataclass(frozen=True)
class FortStatus:
    owner: str
    strength: int
    intact: bool
    besieged: bool
    besieging_side: str | None


def can_besiege(state: FullGameState, space_id: str, side: str, entrants: tuple[str, ...] = ()) -> bool:
    data = load_data()
    if data.spaces[space_id]["fort"] == 0 or state["spaces"][space_id]["fort_destroyed"]:
        return False
    units = [uid for uid, unit in state["units"].items()
             if unit["location"] == space_id and data.units[uid]["side"] == side]
    units.extend(entrants)
    return any(data.units[uid]["type"] == "ARMY" for uid in units) or len(units) >= data.spaces[space_id]["fort"]


def fort_status(state: FullGameState, space_id: str) -> FortStatus:
    data = load_data()
    if space_id not in data.spaces or data.spaces[space_id]["fort"] == 0:
        raise ValueError("요새가 아닌 공간입니다")
    owner = data.spaces[space_id]["side"]
    enemy = "AP" if owner == "CP" else "CP"
    intact = not state["spaces"][space_id]["fort_destroyed"]
    besieged = intact and state["spaces"][space_id]["fort_besieged"] and can_besiege(state, space_id, enemy)
    return FortStatus(owner, data.spaces[space_id]["fort"], intact, besieged, enemy if besieged else None)


def update_siege_status(state: FullGameState, space_id: str) -> None:
    data = load_data()
    if not space_id or data.spaces[space_id]["fort"] == 0:
        return
    owner = data.spaces[space_id]["side"]
    enemy = "AP" if owner == "CP" else "CP"
    state["spaces"][space_id]["fort_besieged"] = bool(
        not state["spaces"][space_id]["fort_destroyed"] and can_besiege(state, space_id, enemy)
    )


def siege_survives_departure(state: FullGameState, space_id: str, departing: tuple[str, ...]) -> bool:
    data = load_data()
    if not space_id or data.spaces[space_id]["fort"] == 0 or not state["spaces"][space_id]["fort_besieged"]:
        return True
    owner = data.spaces[space_id]["side"]
    enemy = "AP" if owner == "CP" else "CP"
    remaining = [uid for uid, unit in state["units"].items()
                 if unit["location"] == space_id and data.units[uid]["side"] == enemy and uid not in departing]
    return not remaining or any(data.units[uid]["type"] == "ARMY" for uid in remaining) or len(remaining) >= data.spaces[space_id]["fort"]


def resolve_fort_combat(state: FullGameState, context: dict) -> FullGameState:
    result = deepcopy(state)
    data = load_data()
    place = context["defender_space"]
    attacker = context["attacker"]
    defender = "AP" if attacker == "CP" else "CP"
    fort = data.spaces[place]["fort"]
    if fort == 0 or result["spaces"][place]["fort_destroyed"] or fort > context["loss_remaining"]:
        return result
    if data.spaces[place]["side"] != defender:
        return result
    if any(unit["location"] == place and data.units[uid]["side"] == defender for uid, unit in result["units"].items()):
        return result
    result["spaces"][place]["fort_destroyed"] = True
    result["spaces"][place]["fort_besieged"] = False
    if any(unit["location"] == place and data.units[uid]["side"] == attacker for uid, unit in result["units"].items()):
        if result["spaces"][place]["control"] != attacker and result["spaces"][place]["vp"]:
            result["vp"] += 1 if attacker == "CP" else -1
        result["spaces"][place]["control"] = attacker
    return result


def _pending_forts(state: FullGameState) -> list[str]:
    data = load_data()
    return sorted(place for place, space in state["spaces"].items()
                  if data.spaces[place]["fort"] and space["fort_besieged"] and fort_status(state, place).besieged)


def legal_siege_actions(state: FullGameState) -> list[Action]:
    if state["phase"] != "SIEGE" or not state.get("pending_sieges"):
        return []
    return [{"type": "RECORD_SIEGE_DIE", "actor": "CHANCE", "space_id": place, "value": value}
            for place in state["pending_sieges"] for value in range(1, 7)]


def begin_siege_phase(state: FullGameState) -> FullGameState:
    state["pending_sieges"] = _pending_forts(state)
    if not state["pending_sieges"]:
        state["phase"] = "WAR_STATUS"
        state["active_side"] = "CHANCE"
        state["decision"] = None
    else:
        state["active_side"] = "CHANCE"
        state["decision"] = {"kind": "SIEGE_ROLL", "actor": "CHANCE", "options": legal_siege_actions(state)}
    return state


def apply_siege_result(state: FullGameState, action: Action) -> FullGameState:
    if action not in legal_siege_actions(state):
        raise IllegalActionError("공성 주사위 행동이 합법적이지 않습니다")
    place = action["space_id"]
    state["pending_sieges"].remove(place)
    status = fort_status(state, place)
    modifier = -2 if state["turn"] <= 2 else 0
    if action["value"] + modifier > status.strength:
        side = status.besieging_side
        dynamic = state["spaces"][place]
        dynamic["fort_destroyed"] = True
        dynamic["fort_besieged"] = False
        if dynamic["control"] != side and dynamic["vp"]:
            state["vp"] += 1 if side == "CP" else -1
        dynamic["control"] = side
        other = status.owner
        enemy_trench = dynamic["trenches"][other]
        dynamic["trenches"][other] = 0
        if enemy_trench == 2:
            dynamic["trenches"][side] = 1
    if state["pending_sieges"]:
        state["decision"]["options"] = legal_siege_actions(state)
    else:
        state["phase"] = "WAR_STATUS"
        state["active_side"] = "CHANCE"
        state["decision"] = None
    return state


def _apply_siege(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_siege_result(state, action)


register_decision_handler("SIEGE_ROLL", _apply_siege)
