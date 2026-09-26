"""Historical 턴과 행동 라운드의 순서."""

from copy import deepcopy

from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError, InvalidStateError
from .war import mandatory_offensive


def _roll_decision(side: str) -> dict:
    purpose = f"{side}_MANDATORY_OFFENSIVE"
    return {
        "kind": "MANDATORY_OFFENSIVE_ROLL",
        "actor": "CHANCE",
        "purpose": purpose,
        "options": [
            {"type": "RECORD_DIE_RESULT", "actor": "CHANCE", "purpose": purpose, "value": die}
            for die in range(1, 7)
        ],
    }


def _action_decision(state: dict) -> dict:
    side = state["active_side"]
    from .cards import legal_card_actions

    options = legal_card_actions(state, side)
    return {"kind": "ACTION_PHASE", "actor": side, "options": options}


def legal_turn_actions(state: FullGameState) -> list[Action]:
    if state["phase"] not in ("MANDATORY_OFFENSIVE", "ACTION"):
        return []
    return deepcopy(state["decision"]["options"])


def apply_turn_action(state: FullGameState, action: Action) -> FullGameState:
    if state["phase"] != "MANDATORY_OFFENSIVE":
        raise IllegalActionError("의무 공세 굴림 단계가 아닙니다")
    if action.get("type") != "RECORD_DIE_RESULT" or action.get("actor") != "CHANCE":
        raise IllegalActionError("주사위 결과 행동이 필요합니다")
    purpose = state["decision"]["purpose"]
    if action.get("purpose") != purpose:
        raise IllegalActionError("다른 주사위 목적입니다")
    side = purpose.split("_", 1)[0]
    state["players"][side]["mandatory_offensive"] = mandatory_offensive(state, side, action["value"])
    if side == "AP":
        state["decision"] = _roll_decision("CP")
    else:
        state["phase"] = "ACTION"
        state["active_side"] = "CP"
        state["decision"] = _action_decision(state)
    return state


def _apply_mandatory_roll(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_turn_action(state, action)


def complete_action(state: FullGameState) -> FullGameState:
    if state["phase"] != "ACTION":
        raise InvalidStateError("행동 단계가 아닙니다")
    next_state = deepcopy(state)
    side = next_state["active_side"]
    for effect in ("YANKS_AND_TANKS", "KERENSKY_OFFENSIVE", "BRUSILOV_OFFENSIVE",
                   "BRUSILOV_TRENCH_USED", "revealed_hand"):
        next_state["temporary_effects"].pop(effect, None)
    if side == "AP" and next_state["events"].get("HIGH_SEAS_FLEET"):
        from .war import apply_vp_change

        next_state = apply_vp_change(next_state, 1, "HIGH_SEAS_FLEET")
        del next_state["events"]["HIGH_SEAS_FLEET"]
    ordinal = (next_state["turn"] - 1) * 6 + next_state["players"][side]["actions_taken"]
    failed = next_state["flags"].get("failed_entrench", {})
    for unit_id, next_ordinal in list(failed.items()):
        from pog_engine.data import load_data

        if load_data().units[unit_id]["side"] == side and next_ordinal <= ordinal:
            del failed[unit_id]
    next_state["players"][side]["actions_taken"] += 1
    if side == "CP":
        next_state["active_side"] = "AP"
    elif next_state["action_round"] < 6:
        next_state["action_round"] += 1
        next_state["active_side"] = "CP"
    else:
        next_state["phase"] = "ATTRITION"
        next_state["active_side"] = "CHANCE"
        next_state["decision"] = None
        return next_state
    next_state["decision"] = _action_decision(next_state)
    return next_state


_AFTER_ACTIONS = {
    "ATTRITION": "SIEGE",
    "SIEGE": "WAR_STATUS",
    "WAR_STATUS": "REPLACEMENT_AP",
    "REPLACEMENT_AP": "REPLACEMENT_CP",
    "REPLACEMENT_CP": "DRAW",
    "DRAW": "END_TURN",
}


def advance_automatic_phases(state: FullGameState) -> FullGameState:
    if state["decision"] is not None:
        raise InvalidStateError("선택 창이 열려 있는 단계는 자동으로 넘길 수 없습니다")
    next_state = deepcopy(state)
    phase = next_state["phase"]
    if phase == "ATTRITION":
        from .supply import resolve_attrition

        next_state = resolve_attrition(next_state)
    if phase == "SIEGE":
        from .forts import begin_siege_phase

        return begin_siege_phase(next_state)
    if phase == "WAR_STATUS":
        from .war import resolve_war_status
        from .events.economy import apply_replacement_phase_events

        next_state = resolve_war_status(next_state)
        if next_state["phase"] == "GAME_OVER":
            return next_state
        if next_state["turn"] >= 20:
            from .victory import finish_game, game_result

            next_state["phase"] = "END_TURN"
            victory = game_result(next_state)
            assert victory is not None
            return finish_game(next_state, victory)
        apply_replacement_phase_events(next_state)
    if phase == "DRAW":
        from .cards import draw_to_hand

        for side in ("AP", "CP"):
            player = next_state["players"][side]
            player["discard"].extend(player.get("in_play", []))
            player["in_play"] = []
        next_state = draw_to_hand(next_state, "AP")
        next_state = draw_to_hand(next_state, "CP")
    if phase in _AFTER_ACTIONS:
        next_state["phase"] = _AFTER_ACTIONS[phase]
        if next_state["phase"] in {"REPLACEMENT_AP", "REPLACEMENT_CP"}:
            from .replacements import begin_replacement_phase

            return begin_replacement_phase(next_state, "AP" if next_state["phase"] == "REPLACEMENT_AP" else "CP")
        next_state["active_side"] = "AP" if next_state["phase"] == "REPLACEMENT_AP" else (
            "CP" if next_state["phase"] == "REPLACEMENT_CP" else "CHANCE"
        )
        next_state["decision"] = None
        return next_state
    if phase == "END_TURN":
        from .victory import finish_game, game_result
        from .events.economy import expire_effects

        victory = game_result(next_state)
        if victory is not None:
            return finish_game(next_state, victory)
        expire_effects(next_state, phase)
        for side in ("AP", "CP"):
            player = next_state["players"][side]
            player["discard"].extend(player.get("in_play", []))
            player["in_play"] = []
        next_state["turn"] += 1
        next_state["action_round"] = 1
        next_state["phase"] = "MANDATORY_OFFENSIVE"
        next_state["active_side"] = "CHANCE"
        next_state["players"]["AP"]["actions_taken"] = 0
        next_state["players"]["CP"]["actions_taken"] = 0
        next_state["players"]["AP"]["last_action_mode"] = None
        next_state["players"]["CP"]["last_action_mode"] = None
        next_state["flags"].pop("near_east_sr", None)
        next_state["decision"] = _roll_decision("AP")
        return next_state
    raise InvalidStateError(f"자동으로 넘길 수 없는 단계: {phase}")


register_decision_handler("MANDATORY_OFFENSIVE_ROLL", _apply_mandatory_roll)
