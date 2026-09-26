"""공간 단위 이동과 행군 종료."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError


def _can_enter(state: FullGameState, unit_id: str, destination: str) -> bool:
    data = load_data()
    unit = data.units[unit_id]
    space = data.spaces[destination]
    side, nation = unit["side"], unit["nation"]
    if space["kind"] != "BOARD":
        return False
    if space["nation"] in state["war_nations"] and not state["war_nations"][space["nation"]]:
        return False
    if any(other["location"] == destination and data.units[other_id]["side"] != side
           for other_id, other in state["units"].items()):
        return False
    if sum(other["location"] == destination for other in state["units"].values()) >= 3:
        return False
    if destination in state["activated"]["ATTACK"]:
        return False
    if side == "CP" and destination in {"AMIENS", "CALAIS", "OSTEND"}:
        if not state["events"].get("RACE_TO_THE_SEA") and state["players"]["CP"]["war_status"] < 4:
            return False
    if state["players"]["AP"]["commitment"] != "TOTAL" and unit["type"] == "ARMY":
        if space["nation"] == "IT" and nation not in {"IT", "AH"}:
            return False
        if nation == "GE" and destination in {"TRENT", "VILLACH", "TRIESTE"}:
            return False
    return True


def legal_movement_actions(state: FullGameState) -> list[Action]:
    if state["phase"] != "MOVEMENT":
        return []
    data = load_data()
    from .supply import supply_status

    side = state["active_side"]
    context = state["movement"]
    moving = context["unit"]
    candidates = [moving] if moving else [
        unit_id for unit_id, unit in state["units"].items()
        if unit_id not in context["done"] and unit["location"] in state["activated"]["MOVE"]
        and data.units[unit_id]["side"] == side
    ]
    actions: list[Action] = []
    for unit_id in candidates:
        unit = state["units"][unit_id]
        if unit["location"] is None:
            continue
        if unit_id in state.get("activated_oos", []):
            continue
        if not state["war_nations"].get(data.units[unit_id]["nation"], True):
            continue
        if not moving and not supply_status(state, unit_id).supplied:
            continue
        definition = data.units[unit_id]
        mf = definition["reduced_mf"] if unit["reduced"] else definition["mf"]
        if context["spent"] >= mf:
            continue
        for destination in sorted(data.neighbors(unit["location"], definition["nation"])):
            if _can_enter(state, unit_id, destination):
                actions.append({"type": "MOVE", "actor": side, "unit_id": unit_id, "to": destination})
    if moving:
        actions.append({"type": "STOP_MOVING_UNIT", "actor": side})
    else:
        from .trenches import legal_entrench_actions

        actions.extend(legal_entrench_actions(state))
        actions.append({"type": "END_MOVEMENT", "actor": side})
    return actions


def apply_movement_action(state: FullGameState, action: Action) -> FullGameState:
    if action not in legal_movement_actions(state):
        raise IllegalActionError("이동할 수 없는 경로입니다")
    context = state["movement"]
    kind = action["type"]
    if kind == "MOVE":
        unit_id, destination = action["unit_id"], action["to"]
        state["units"][unit_id]["location"] = destination
        state["flags"].get("failed_entrench", {}).pop(unit_id, None)
        space = state["spaces"][destination]
        enemy = "AP" if state["active_side"] == "CP" else "CP"
        enemy_fort = (
            load_data().spaces[destination]["fort"] > 0
            and not space["fort_destroyed"]
            and space["control"] == enemy
        )
        if enemy_fort:
            space["fort_besieged"] = True
        else:
            if space["control"] != state["active_side"] and space["vp"]:
                state["vp"] += 1 if state["active_side"] == "CP" else -1
            space["control"] = state["active_side"]
        opposing_trench = space["trenches"][enemy]
        if opposing_trench:
            space["trenches"][enemy] = 0
            space["trenches"][state["active_side"]] = 1 if opposing_trench == 2 else 0
        context["unit"] = unit_id
        context["spent"] += 1
        definition = load_data().units[unit_id]
        mf = definition["reduced_mf"] if state["units"][unit_id]["reduced"] else definition["mf"]
        if context["spent"] >= mf or enemy_fort:
            context["done"].append(unit_id)
            context["unit"] = None
            context["spent"] = 0
    elif kind == "STOP_MOVING_UNIT":
        context["done"].append(context["unit"])
        context["unit"] = None
        context["spent"] = 0
    elif kind == "ENTRENCH":
        unit_id = action["unit_id"]
        state.setdefault("entrench_pending", []).append(unit_id)
        context["done"].append(unit_id)
    elif kind == "END_MOVEMENT":
        from .trenches import entrench_decision

        entrench_decision(state)
        return state
    state["decision"]["options"] = legal_movement_actions(state)
    return state


def _apply_movement(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_movement_action(state, action)


register_decision_handler("MOVEMENT", _apply_movement)
