"""참호 시도와 Historical 11.2.10 굴림 수정."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError


def legal_entrench_actions(state: FullGameState) -> list[Action]:
    if state["phase"] != "MOVEMENT" or not state["events"].get("ENTRENCH"):
        return []
    side = state["active_side"]
    if state["movement"]["unit"]:
        return []
    data = load_data()
    from .supply import supply_status
    actions = []
    chosen_spaces = {state["units"][uid]["location"] for uid in state.get("entrench_pending", [])}
    for unit_id, unit in state["units"].items():
        place = unit["location"]
        if place not in state["activated"]["MOVE"] or unit_id in state["movement"]["done"]:
            continue
        if data.units[unit_id]["side"] != side or data.units[unit_id]["type"] != "ARMY":
            continue
        if not state["war_nations"].get(data.units[unit_id]["nation"], True):
            continue
        if unit_id in state.get("activated_oos", []) or not supply_status(state, unit_id).supplied:
            continue
        if place in chosen_spaces or state["spaces"][place]["trenches"][side] >= 2:
            continue
        if state["spaces"][place]["control"] != side and not state["spaces"][place]["fort_besieged"]:
            continue
        actions.append({"type": "ENTRENCH", "actor": side, "unit_id": unit_id})
    return actions


def entrench_decision(state: FullGameState) -> None:
    pending = state.get("entrench_pending", [])
    if not pending:
        if state["activated"]["ATTACK"]:
            from .combat import enter_combat

            enter_combat(state)
            return
        from .turn import complete_action

        state["phase"] = "ACTION"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return
    unit_id = pending[0]
    state["phase"] = "TRENCH_ROLL"
    state["decision"] = {
        "kind": "TRENCH_ROLL", "actor": "CHANCE", "unit_id": unit_id,
        "options": [{"type": "RECORD_ENTRENCH_DIE", "actor": "CHANCE", "unit_id": unit_id, "value": value} for value in range(1, 7)],
    }


def apply_entrench_result(state: FullGameState, action: Action) -> FullGameState:
    if state["phase"] != "TRENCH_ROLL" or action not in state["decision"]["options"]:
        raise IllegalActionError("참호 굴림 결과가 합법적이지 않습니다")
    unit_id = state["entrench_pending"].pop(0)
    unit = state["units"][unit_id]
    definition = load_data().units[unit_id]
    loss_factor = definition["reduced_lf"] if unit["reduced"] else definition["lf"]
    failed = state["flags"].setdefault("failed_entrench", {})
    ordinal = (state["turn"] - 1) * 6 + state["players"][definition["side"]]["actions_taken"]
    modifier = -1 if failed.get(unit_id) == ordinal else 0
    if action["value"] + modifier <= loss_factor:
        space = state["spaces"][unit["location"]]
        space["trenches"][definition["side"]] = min(2, space["trenches"][definition["side"]] + 1)
        failed.pop(unit_id, None)
    elif definition["nation"] in {"GE", "BR", "FR", "IT"}:
        failed[unit_id] = ordinal + 1
    entrench_decision(state)
    return state


def _apply_trench_roll(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_entrench_result(state, action)


register_decision_handler("TRENCH_ROLL", _apply_trench_roll)
