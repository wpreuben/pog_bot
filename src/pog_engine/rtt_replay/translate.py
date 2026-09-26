"""RTT 미세 입력을 현재 엔진의 합법 행동으로 연결."""

from copy import deepcopy

from pog_engine.engine import apply_action, generate_legal_actions
from pog_engine.model import Action, FullGameState

from .ids import SourceIdError, SourceIds
from .normalize import Intent


class TranslationError(ValueError):
    """의미 행동의 합법 후보가 없거나 모호한 경우."""


def _select(state: FullGameState, intent: Intent, action_type: str, **fields) -> Action:
    options = generate_legal_actions(state)
    candidates = [action for action in options if action["type"] == action_type
                  and all(action.get(key) == value for key, value in fields.items())]
    if len(candidates) != 1:
        raise TranslationError(
            f"index {intent.start_index}: {action_type} 후보 {len(candidates)}개; "
            f"단계={state['phase']}, 필드={fields}, 합법 행동={options[:12]}"
        )
    return candidates[0]


def _lookup(ids: SourceIds, kind: str, source_id: object, intent: Intent) -> str:
    try:
        return ids.lookup(kind, source_id, index=intent.start_index)
    except SourceIdError as exc:
        raise TranslationError(str(exc)) from exc


def _moved_units(intent: Intent, ids: SourceIds) -> list[tuple[str, str]]:
    before = intent.before["location"]
    after = intent.after["location"]
    if len(before) != len(after):
        raise TranslationError(f"index {intent.start_index}: 유닛 배열 길이가 다릅니다")
    return [(_lookup(ids, "units", index, intent), _lookup(ids, "spaces", place, intent))
            for index, (old, place) in enumerate(zip(before, after))
            if index and old != place and place]


def translate_intent(state: FullGameState, intent: Intent, ids: SourceIds) -> tuple[Action, ...]:
    name = intent.kind
    before_state = intent.before.get("state") if intent.before else None
    after_state = intent.after.get("state")
    current = deepcopy(state)
    actions: list[Action] = []

    def add(action_type: str, **fields) -> None:
        nonlocal current
        action = _select(current, intent, action_type, **fields)
        actions.append(action)
        current = apply_action(current, action).state

    if name == ".setup":
        if len(intent.random_seeds) < 2:
            raise TranslationError(f"index {intent.start_index}: 의무 공세 굴림 두 개가 없습니다")
        ap_die, cp_die = (seed % 6 + 1 for seed in intent.random_seeds[-2:])
        add("RECORD_DIE_RESULT", value=ap_die)
        add("RECORD_DIE_RESULT", value=cp_die)
    elif name in ("play_event", "play_ops", "play_sr", "play_rps"):
        mode = {"play_event": "EVENT", "play_ops": "OPS", "play_sr": "SR", "play_rps": "RP"}[name]
        add("PLAY_CARD", card_id=_lookup(ids, "cards", intent.argument, intent), mode=mode)
    elif name in ("activate_move", "activate_attack"):
        kind = "MOVE" if name == "activate_move" else "ATTACK"
        add("ACTIVATE_SPACE", space_id=_lookup(ids, "spaces", intent.argument, intent), kind=kind)
        if after_state != "activate_spaces":
            add("FINISH_ACTIVATION")
    elif name == "piece" and before_state == "choose_sr_unit":
        add("SELECT_SR_UNIT", unit_id=_lookup(ids, "units", intent.argument, intent))
    elif name == "space" and before_state == "choose_sr_destination":
        add("SR_TO", to=_lookup(ids, "spaces", intent.argument, intent))
    elif name == "space" and before_state in ("choose_pieces_to_move", "move_stack"):
        moved = _moved_units(intent, ids)
        if len(moved) > 1:
            destination = moved[0][1]
            if all(to == destination for _, to in moved):
                groups = [action for action in generate_legal_actions(current)
                          if action["type"] == "MOVE_STACK" and action["to"] == destination
                          and set(action["unit_ids"]) == {uid for uid, _ in moved}]
                if len(groups) == 1:
                    add("MOVE_STACK", to=destination, unit_ids=groups[0]["unit_ids"])
                    return tuple(actions)
        for uid, destination in moved:
            add("MOVE", unit_id=uid, to=destination)
    elif name == "stop" and state["phase"] == "MOVEMENT":
        if any(action["type"] == "STOP_MOVING_UNIT" for action in generate_legal_actions(state)):
            add("STOP_MOVING_UNIT")
    elif name in ("done", "end_action") and state["phase"] == "MOVEMENT":
        if after_state in ("end_operations", "action_phase"):
            add("END_MOVEMENT")
    elif name == "end_action" and state["phase"] == "SR":
        add("END_SR")
    elif name == "end_rp" and state["phase"].startswith("REPLACEMENT_"):
        add("END_REPLACEMENT")
    elif name == "next" and state["decision"] is None:
        add("ADVANCE_AUTOMATIC_PHASE")
    elif (name == "piece" and before_state in ("choose_move_space", "choose_pieces_to_move")):
        pass
    elif name == "space" and before_state == "choose_move_space":
        pass
    elif name == "done" and before_state == "choose_pieces_to_move":
        pass
    elif name == "end_action" and state["phase"] == "ACTION":
        pass
    elif name == "next" and before_state == "confirm_mo" and state["phase"] == "ACTION":
        pass
    else:
        raise TranslationError(
            f"index {intent.start_index}: 번역하지 않은 RTT 행동 {name!r}, 상태 {before_state!r}"
        )
    return tuple(actions)
