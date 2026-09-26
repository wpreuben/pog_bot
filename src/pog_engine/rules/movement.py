"""공간 단위 이동과 행군 종료."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError
from itertools import combinations


def _can_enter(state: FullGameState, unit_id: str, destination: str) -> bool:
    data = load_data()
    unit = data.units[unit_id]
    space = data.spaces[destination]
    side, nation = unit["side"], unit["nation"]
    if space["kind"] != "BOARD":
        return False
    if state["events"].get("TREATY_OF_BREST_LITOVSK") and side == "AP":
        if nation == "RU" and space["nation"] not in {"RU", "GE", "TU", "AH", "RO"}:
            return False
        if any(other["location"] == destination and data.units[other_id]["side"] == "AP"
               and (data.units[other_id]["nation"] == "RU") != (nation == "RU")
               for other_id, other in state["units"].items()):
            return False
    if space["nation"] in state["war_nations"] and not state["war_nations"][space["nation"]]:
        return False
    if any(other["location"] == destination and data.units[other_id]["side"] != side
           for other_id, other in state["units"].items()):
        return False
    if destination in state["activated"]["ATTACK"]:
        movement = state["movement"]
        mf = unit["reduced_mf"] if state["units"][unit_id]["reduced"] else unit["mf"]
        if movement["spent"] + 1 >= mf:
            return False
    from .forts import siege_survives_departure

    if not siege_survives_departure(state, state["units"][unit_id]["location"], (unit_id,)):
        return False
    if space["fort"] and not state["spaces"][destination]["fort_destroyed"] and space["side"] != side:
        from .forts import can_besiege, fort_status

        if not fort_status(state, destination).besieged and not can_besiege(state, destination, side, (unit_id,)):
            return False
        if state["turn"] == 1 and nation == "RU" and space["nation"] == "GE":
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
    moving_stack = context.get("stack")
    moving = context["unit"] or moving_stack
    candidates = ([context["unit"]] if context["unit"] else list(moving_stack)) if moving else [
        unit_id for unit_id, unit in state["units"].items()
        if unit_id not in context["done"] and unit["location"] in state["activated"]["MOVE"]
        and data.units[unit_id]["side"] == side
    ]
    actions: list[Action] = []
    for unit_id in ([] if moving_stack else candidates):
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
    stack_groups = ([tuple(moving_stack)] if moving_stack else
                    [group for size in (2, 3) for group in combinations(sorted(candidates), size)
                     if len({state["units"][uid]["location"] for uid in group}) == 1])
    for group in stack_groups:
        if any(uid in state.get("activated_oos", []) for uid in group):
            continue
        if not moving and any(not supply_status(state, uid).supplied for uid in group):
            continue
        source = state["units"][group[0]]["location"]
        if not source:
            continue
        destinations = set(data.neighbors(source, data.units[group[0]]["nation"]))
        for uid in group[1:]:
            destinations.intersection_update(data.neighbors(source, data.units[uid]["nation"]))
        for destination in sorted(destinations):
            if all(context["spent"] < (data.units[uid]["reduced_mf"] if state["units"][uid]["reduced"] else data.units[uid]["mf"])
                   and _can_enter(state, uid, destination) for uid in group):
                actions.append({"type": "MOVE_STACK", "actor": side, "unit_ids": list(group), "to": destination})
    if not moving:
        from .forts import siege_survives_departure

        corps = sorted(uid for uid in candidates if data.units[uid]["type"] == "CORPS"
                       and uid not in state.get("activated_oos", []) and supply_status(state, uid).supplied)
        for destination, target in sorted(data.spaces.items()):
            if target["fort"] < 2 or target["side"] == side or target["fort"] > 3:
                continue
            if state["spaces"][destination]["fort_destroyed"] or state["spaces"][destination]["fort_besieged"]:
                continue
            if not state["war_nations"].get(target["nation"], True) or destination in state["activated"]["ATTACK"]:
                continue
            if any(unit["location"] == destination and data.units[uid]["side"] != side
                   for uid, unit in state["units"].items()):
                continue
            if sum(unit["location"] == destination for unit in state["units"].values()) + target["fort"] > 3:
                continue
            eligible = [uid for uid in corps if destination in data.neighbors(
                state["units"][uid]["location"], data.units[uid]["nation"])]
            for group in combinations(eligible, target["fort"]):
                sources = {state["units"][uid]["location"] for uid in group}
                if all(siege_survives_departure(state, source, tuple(uid for uid in group
                                                                     if state["units"][uid]["location"] == source))
                       for source in sources):
                    actions.append({"type": "MOVE_STACK", "actor": side, "unit_ids": list(group), "to": destination})
    if moving:
        current_places = ([state["units"][uid]["location"] for uid in moving_stack]
                          if moving_stack else [state["units"][context["unit"]]["location"]])
        if all(place not in state["activated"]["ATTACK"] for place in current_places):
            actions.append({"type": "STOP_MOVING_UNIT", "actor": side})
    else:
        from .trenches import legal_entrench_actions

        actions.extend(legal_entrench_actions(state))
        if all(sum(unit["location"] == place for unit in state["units"].values()) <= 3
               for place, static in data.spaces.items() if static["kind"] == "BOARD"):
            actions.append({"type": "END_MOVEMENT", "actor": side})
    return actions


def apply_movement_action(state: FullGameState, action: Action) -> FullGameState:
    if action not in legal_movement_actions(state):
        raise IllegalActionError("이동할 수 없는 경로입니다")
    context = state["movement"]
    kind = action["type"]
    if kind == "MOVE_STACK":
        from .forts import update_siege_status

        destination = action["to"]
        sources = {state["units"][uid]["location"] for uid in action["unit_ids"]}
        general = not (load_data().spaces[destination]["fort"]
                       and load_data().spaces[destination]["side"] != state["active_side"]
                       and not state["spaces"][destination]["fort_destroyed"])
        for uid in action["unit_ids"]:
            state["units"][uid]["location"] = destination
            state["flags"].get("failed_entrench", {}).pop(uid, None)
            if not general:
                context["done"].append(uid)
        if not general:
            context["stack"] = None
            context["spent"] = 0
        for source in sources:
            update_siege_status(state, source)
        update_siege_status(state, destination)
        if general:
            space = state["spaces"][destination]
            enemy = "AP" if state["active_side"] == "CP" else "CP"
            if space["control"] != state["active_side"] and space["vp"]:
                state["vp"] += 1 if state["active_side"] == "CP" else -1
            space["control"] = state["active_side"]
            opposing_trench = space["trenches"][enemy]
            if opposing_trench:
                space["trenches"][enemy] = 0
                space["trenches"][state["active_side"]] = 1 if opposing_trench == 2 else 0
            context["stack"] = list(action["unit_ids"])
            context["spent"] += 1
            if any(context["spent"] >= (load_data().units[uid]["reduced_mf"] if state["units"][uid]["reduced"]
                                         else load_data().units[uid]["mf"]) for uid in action["unit_ids"]):
                context["done"].extend(action["unit_ids"])
                context["stack"] = None
                context["spent"] = 0
    elif kind == "MOVE":
        from .forts import update_siege_status

        unit_id, destination = action["unit_id"], action["to"]
        source = state["units"][unit_id]["location"]
        state["units"][unit_id]["location"] = destination
        update_siege_status(state, source)
        update_siege_status(state, destination)
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
        context["done"].extend(context.get("stack") or [context["unit"]])
        context["unit"] = None
        context["stack"] = None
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
