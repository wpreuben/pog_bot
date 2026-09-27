"""RTT 미세 입력을 현재 엔진의 합법 행동으로 연결."""

from copy import deepcopy
from dataclasses import dataclass
import re

from pog_engine.engine import apply_action, generate_legal_actions
from pog_engine.model import Action, FullGameState

from .ids import SourceIdError, SourceIds
from .normalize import Intent


class TranslationError(ValueError):
    """의미 행동의 합법 후보가 없거나 모호한 경우."""


@dataclass(frozen=True)
class TranslationResult:
    actions: tuple[Action, ...]
    records: tuple[dict, ...]
    state: FullGameState
    pending_actions: tuple[Action, ...]


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


def translate_intent_result(state: FullGameState, intent: Intent, ids: SourceIds) -> TranslationResult:
    name = intent.kind
    before_state = intent.before.get("state") if intent.before else None
    after_state = intent.after.get("state")
    current = deepcopy(state)
    actions: list[Action] = []
    records: list[dict] = []

    def emit(action: Action) -> None:
        nonlocal current
        if len(actions) != len(records):
            raise TranslationError(
                f"index {intent.start_index}: 적용하지 않은 행동 뒤에 다른 행동을 적용할 수 없습니다")
        actions.append(action)
        transition = apply_action(current, action)
        current = transition.state
        records.append(transition.record)

    def finish() -> TranslationResult:
        return TranslationResult(tuple(actions), tuple(records), current,
                                 tuple(actions[len(records):]))

    def add(action_type: str, **fields) -> None:
        action = _select(current, intent, action_type, **fields)
        emit(action)

    def add_combat_card() -> None:
        card_id = _lookup(ids, "cards", intent.argument, intent)
        choices = [action for action in generate_legal_actions(current)
                   if action["type"] in {"PLAY_COMBAT_CARD", "USE_COMBAT_CARD"}
                   and action["card_id"] == card_id]
        if len(choices) != 1:
            raise TranslationError(f"index {intent.start_index}: 전투 카드 {card_id} 후보 {len(choices)}개")
        emit(choices[0])

    def die() -> int:
        if len(intent.random_seeds) != 1:
            raise TranslationError(f"index {intent.start_index}: 주사위 관측이 모호하거나 없습니다")
        return intent.random_seeds[0] % 6 + 1

    def advance_after_action() -> None:
        target = {"replacement_phase": "REPLACEMENT_AP",
                  "confirm_mo": "MANDATORY_OFFENSIVE"}.get(after_state)
        if target is None:
            return
        if (after_state == "confirm_mo" and current["phase"] == "ACTION"
                and intent.before and intent.before.get("turn") == intent.after.get("turn")):
            return
        for _ in range(8):
            if current["phase"] == target:
                break
            if current["phase"] not in {
                    "ATTRITION", "SIEGE", "WAR_STATUS", "REPLACEMENT_AP",
                    "REPLACEMENT_CP", "DRAW", "END_TURN"} or current["decision"] is not None:
                raise TranslationError(
                    f"index {intent.start_index}: {after_state}까지 자동 진행할 수 없습니다; "
                    f"단계={current['phase']}")
            add("ADVANCE_AUTOMATIC_PHASE")
        else:
            raise TranslationError(f"index {intent.start_index}: 자동 단계 진행 한도를 넘었습니다")
        if after_state == "confirm_mo":
            if len(intent.random_seeds) < 2:
                raise TranslationError(f"index {intent.start_index}: 새 턴 의무 공세 굴림이 없습니다")
            add("RECORD_DIE_RESULT", value=intent.random_seeds[-2] % 6 + 1)
            add("RECORD_DIE_RESULT", value=intent.random_seeds[-1] % 6 + 1)

    if name == ".setup":
        if len(intent.random_seeds) < 2:
            raise TranslationError(f"index {intent.start_index}: 의무 공세 굴림 두 개가 없습니다")
        ap_die, cp_die = (seed % 6 + 1 for seed in intent.random_seeds[-2:])
        add("RECORD_DIE_RESULT", value=ap_die)
        add("RECORD_DIE_RESULT", value=cp_die)
    elif name == ".resign":
        side = {"Allied Powers": "AP", "Central Powers": "CP"}.get(intent.role)
        if side is None:
            raise TranslationError(f"index {intent.start_index}: 항복 진영을 알 수 없습니다")
        add("RESIGN", actor=side)
    elif name == "done" and before_state == "war_in_africa_confirm":
        pass
    elif name == "piece" and before_state == "war_in_africa":
        add("REMOVE_BRITISH_CORPS", unit_id=_lookup(ids, "units", intent.argument, intent))
    elif name == "piece" and before_state == "landwehr":
        add("LANDWEHR_FLIP", unit_id=_lookup(ids, "units", intent.argument, intent))
    elif name == "piece" and before_state == "salonika":
        moved = _moved_units(intent, ids)
        uid = _lookup(ids, "units", intent.argument, intent)
        if moved != [(uid, "SALONIKA")]:
            raise TranslationError(f"index {intent.start_index}: Salonika 재배치 유닛이 모호합니다")
        add("SALONIKA_SR", unit_id=uid)
    elif name == "done" and before_state == "salonika":
        add("END_SALONIKA")
    elif name == "piece" and before_state in {"great_retreat_option", "great_retreat"}:
        pass
    elif name == "space" and before_state == "great_retreat":
        moved = _moved_units(intent, ids)
        if len(moved) != 1:
            raise TranslationError(f"index {intent.start_index}: Great Retreat 후퇴 유닛이 모호합니다")
        unit_id, destination = moved[0]
        add("RETREAT_RUSSIAN_UNIT", unit_id=unit_id, to=destination)
    elif name == "pass" and before_state == "great_retreat_option":
        add("PASS_GREAT_RETREAT")
    elif name == "done" and before_state == "great_retreat":
        if current["combat_context"] and current["combat_context"]["stage"] == "GREAT_RETREAT":
            add("PASS_GREAT_RETREAT")
    elif name == "end_action" and before_state == "landwehr":
        add("END_LANDWEHR")
    elif name == "done" and before_state == "war_in_africa" and state["phase"] == "ACTION":
        pass
    elif name in ("play_event", "play_ops", "play_sr", "play_rps"):
        mode = {"play_event": "EVENT", "play_ops": "OPS", "play_sr": "SR", "play_rps": "RP"}[name]
        add("PLAY_CARD", card_id=_lookup(ids, "cards", intent.argument, intent), mode=mode)
    elif name == "single_op" and before_state == "action_phase":
        add("SINGLE_OP")
    elif name in ("activate_move", "activate_attack"):
        kind = "MOVE" if name == "activate_move" else "ATTACK"
        add("ACTIVATE_SPACE", space_id=_lookup(ids, "spaces", intent.argument, intent), kind=kind)
        if after_state != "activate_spaces":
            add("FINISH_ACTIVATION")
            if after_state in ("choose_attackers", "choose_attack_space") and current["phase"] == "MOVEMENT":
                add("END_MOVEMENT")
    elif name == "skip" and before_state == "activate_spaces":
        add("FINISH_ACTIVATION")
        if (after_state in ("end_operations", "choose_attackers", "choose_attack_space")
                and current["phase"] == "MOVEMENT"):
            add("END_MOVEMENT")
    elif name == "piece" and before_state == "choose_sr_unit":
        add("SELECT_SR_UNIT", unit_id=_lookup(ids, "units", intent.argument, intent))
    elif name == "space" and before_state == "choose_sr_destination":
        add("SR_TO", to=_lookup(ids, "spaces", intent.argument, intent))
    elif name == "entrench" and before_state == "choose_pieces_to_move":
        pieces = intent.before.get("move", {}).get("pieces", [])
        if len(pieces) != 1:
            raise TranslationError(f"index {intent.start_index}: 참호 유닛이 모호합니다")
        add("ENTRENCH", unit_id=_lookup(ids, "units", pieces[0], intent))
    elif name == "space" and before_state == "trench_rolls":
        if current["phase"] == "MOVEMENT":
            add("END_MOVEMENT")
        space_id = _lookup(ids, "spaces", intent.argument, intent)
        pending = [uid for uid in current.get("entrench_pending", [])
                   if current["units"][uid]["location"] == space_id]
        if len(pending) != 1:
            raise TranslationError(f"index {intent.start_index}: 참호 굴림 대상이 모호합니다")
        add("RECORD_ENTRENCH_DIE", unit_id=pending[0], value=die())
    elif name == "space" and before_state == "attrition_phase":
        if current["phase"] == "ATTRITION":
            add("ADVANCE_AUTOMATIC_PHASE")
        if after_state == "replacement_phase":
            while current["decision"] is None and current["phase"] in {"SIEGE", "WAR_STATUS"}:
                add("ADVANCE_AUTOMATIC_PHASE")
    elif name == "piece" and before_state == "attrition_phase":
        if current["phase"] == "ATTRITION":
            add("ADVANCE_AUTOMATIC_PHASE")
        if after_state == "replacement_phase":
            while current["decision"] is None and current["phase"] in {"SIEGE", "WAR_STATUS"}:
                add("ADVANCE_AUTOMATIC_PHASE")
    elif name == "space" and before_state == "siege_phase":
        while current["phase"] in {"ATTRITION", "SIEGE"} and current["decision"] is None:
            add("ADVANCE_AUTOMATIC_PHASE")
        add("RECORD_SIEGE_DIE", space_id=_lookup(ids, "spaces", intent.argument, intent), value=die())
        if after_state == "replacement_phase" and current["phase"] == "WAR_STATUS":
            add("ADVANCE_AUTOMATIC_PHASE")
    elif name == "piece" and before_state == "replacement_phase":
        while current["decision"] is None and current["phase"] in {"ATTRITION", "SIEGE", "WAR_STATUS"}:
            add("ADVANCE_AUTOMATIC_PHASE")
        if current["phase"] in {"REPLACEMENT_AP", "REPLACEMENT_CP"} and all(
                option["type"] in {"ADVANCE_AUTOMATIC_PHASE", "RESIGN"}
                for option in generate_legal_actions(current)):
            add("ADVANCE_AUTOMATIC_PHASE")
        source_id = intent.argument
        uid = _lookup(ids, "units", source_id, intent)
        before_reduced = source_id in intent.before["reduced"]
        after_reduced = source_id in intent.after["reduced"]
        if before_reduced and not after_reduced:
            add("FLIP_UNIT", unit_id=uid)
        elif intent.before["location"][source_id] != intent.after["location"][source_id]:
            add("REBUILD_CORPS", unit_id=uid)
    elif name == "space" and before_state == "replacement_phase":
        while current["decision"] is None and current["phase"] in {"ATTRITION", "SIEGE", "WAR_STATUS"}:
            add("ADVANCE_AUTOMATIC_PHASE")
        moved = _moved_units(intent, ids)
        if len(moved) != 1:
            raise TranslationError(f"index {intent.start_index}: 보충 재건 유닛이 모호합니다")
        uid, destination = moved[0]
        add("REBUILD_ARMY", unit_id=uid, space_id=destination)
    elif name == "space" and before_state == "place_reinforcements":
        moved = _moved_units(intent, ids)
        if len(moved) != 1:
            raise TranslationError(f"index {intent.start_index}: 증원 배치 유닛이 모호합니다")
        uid, destination = moved[0]
        add("PLACE_REINFORCEMENT", unit_id=uid, to=destination)
    elif name == "space" and before_state == "place_new_neutral_units":
        moved = _moved_units(intent, ids)
        if len(moved) != 1:
            raise TranslationError(f"index {intent.start_index}: 중립국 배치 유닛이 모호합니다")
        uid, destination = moved[0]
        add("PLACE_NEUTRAL", unit_id=uid, to=destination)
    elif name == "space" and before_state == "place_event_trench":
        add("PLACE_EVENT_TRENCH", to=_lookup(ids, "spaces", intent.argument, intent))
    elif name == "done" and before_state == "place_reinforcements":
        if state["phase"] == "ATTRITION" and after_state == "attrition_phase":
            pass
        elif state["phase"] == "ATTRITION" and after_state == "siege_phase":
            add("ADVANCE_AUTOMATIC_PHASE")
        elif after_state == "replacement_phase":
            while current["decision"] is None and current["phase"] in {"ATTRITION", "SIEGE", "WAR_STATUS"}:
                add("ADVANCE_AUTOMATIC_PHASE")
        elif after_state == "draw_cards_phase":
            while current["decision"] is None and current["phase"] in {
                    "ATTRITION", "SIEGE", "WAR_STATUS", "REPLACEMENT_AP", "REPLACEMENT_CP"}:
                add("ADVANCE_AUTOMATIC_PHASE")
        elif state["phase"] not in {"ACTION", "SIEGE"}:
            raise TranslationError(f"index {intent.start_index}: 증원 배치 완료 단계가 맞지 않습니다")
    elif name == "done" and before_state == "place_new_neutral_units" and state["phase"] == "ACTION":
        pass
    elif name == "attack" and before_state == "confirm_attack":
        if current["phase"] == "MOVEMENT":
            add("END_MOVEMENT")
        attack = intent.before["attack"]
        unit_ids = [_lookup(ids, "units", unit, intent) for unit in attack["pieces"]]
        defender_space = _lookup(ids, "spaces", attack["space"], intent)
        declarations = [action for action in generate_legal_actions(current)
                        if action["type"] == "DECLARE_ATTACK"
                        and action["defender_space"] == defender_space
                        and set(action["unit_ids"]) == set(unit_ids)
                        and len(action["unit_ids"]) == len(unit_ids)]
        if len(declarations) != 1:
            raise TranslationError(f"index {intent.start_index}: DECLARE_ATTACK 후보 {len(declarations)}개")
        emit(declarations[0])
        if after_state in ("attacker_combat_cards", "defender_combat_cards"):
            if current["combat_context"]["stage"] == "TRENCH_CARDS":
                add("PASS_TRENCH_CARDS")
            if current["combat_context"]["stage"] == "FLANK":
                add("SKIP_FLANK")
            if after_state == "defender_combat_cards" and current["combat_context"]["stage"] == "ATTACKER_CARDS":
                add("PASS_COMBAT_CARDS")
        if intent.random_seeds:
            if len(intent.random_seeds) != 2:
                raise TranslationError(f"index {intent.start_index}: 전투 주사위 두 개가 필요합니다")
            while current["combat_context"]["stage"] in (
                    "TRENCH_CARDS", "FLANK", "ATTACKER_CARDS", "DEFENDER_CARDS"):
                stage = current["combat_context"]["stage"]
                add({"TRENCH_CARDS": "PASS_TRENCH_CARDS", "FLANK": "SKIP_FLANK",
                     "ATTACKER_CARDS": "PASS_COMBAT_CARDS", "DEFENDER_CARDS": "PASS_COMBAT_CARDS"}[stage])
            for seed in intent.random_seeds:
                context = current["combat_context"]
                add("RECORD_COMBAT_DIE", side=context["fire_order"][context["fire_index"]],
                    value=seed % 6 + 1)
    elif name == "flank" and before_state == "choose_flank_attack":
        flanking = [int(match.group(1)) for line in intent.log_delta
                   if (match := re.fullmatch(r">\+\d+ s(\d+)", line))]
        if flanking:
            flanking_spaces = {_lookup(ids, "spaces", source, intent) for source in flanking}
            attacker_spaces = {current["units"][uid]["location"] for uid in current["combat_context"]["attackers"]}
            pinning_spaces = attacker_spaces - flanking_spaces
            if len(pinning_spaces) != 1:
                raise TranslationError(f"index {intent.start_index}: 고정 공격 공간이 모호합니다")
            pinning_space = next(iter(pinning_spaces))
        else:
            from pog_engine.rules.combat import flank_modifier

            choices = [option for option in generate_legal_actions(current)
                       if option["type"] == "ATTEMPT_FLANK"]
            if not choices or any(flank_modifier(current, {**current["combat_context"],
                                                "pinning_space": option["pinning_space"]}) != 0
                                  for option in choices):
                raise TranslationError(f"index {intent.start_index}: 측면 공격 공간이 모호합니다")
            pinning_space = min(option["pinning_space"] for option in choices)
        if len(intent.random_seeds) not in (1, 2):
            raise TranslationError(f"index {intent.start_index}: 측면 공격 주사위 관측 수가 잘못되었습니다")
        add("ATTEMPT_FLANK", pinning_space=pinning_space)
        add("RECORD_FLANK_DIE", value=intent.random_seeds[0] % 6 + 1)
        if after_state == "defender_combat_cards" and current["combat_context"]["stage"] == "ATTACKER_CARDS":
            add("PASS_COMBAT_CARDS")
        if len(intent.random_seeds) == 2:
            add("PASS_COMBAT_CARDS")
            add("PASS_COMBAT_CARDS")
            add("RECORD_COMBAT_DIE", side=current["combat_context"]["fire_order"][0],
                value=intent.random_seeds[1] % 6 + 1)
    elif name == "card" and before_state == "choose_flank_attack":
        add_combat_card()
    elif name == "done" and before_state == "choose_flank_attack":
        if current["combat_context"]["stage"] != "ATTACKER_CARDS":
            raise TranslationError(f"index {intent.start_index}: 측면 공격 완료 단계가 맞지 않습니다")
        if after_state != "attacker_combat_cards":
            add("PASS_COMBAT_CARDS")
        if after_state not in ("attacker_combat_cards", "defender_combat_cards"):
            add("PASS_COMBAT_CARDS")
        if intent.random_seeds:
            add("RECORD_COMBAT_DIE", side=current["combat_context"]["fire_order"][0], value=die())
    elif name == "pass" and before_state == "choose_flank_attack":
        add("SKIP_FLANK")
        if after_state in ("defender_combat_cards", "apply_defender_losses", "apply_attacker_losses") or intent.random_seeds:
            add("PASS_COMBAT_CARDS")
        if intent.random_seeds:
            add("PASS_COMBAT_CARDS")
        if len(intent.random_seeds) > 2:
            raise TranslationError(f"index {intent.start_index}: 전투 주사위 관측 수가 잘못되었습니다")
        for seed in intent.random_seeds:
            context = current["combat_context"]
            add("RECORD_COMBAT_DIE", side=context["fire_order"][context["fire_index"]],
                value=seed % 6 + 1)
    elif name == "confirm_pass_attack" and before_state == "choose_attackers":
        if state["phase"] == "COMBAT" and state["combat_context"] is None:
            add("END_COMBAT")
        elif state["phase"] != "ACTION":
            raise TranslationError(f"index {intent.start_index}: 전투 종료 단계가 맞지 않습니다")
    elif name == "next" and state["phase"] == "COMBAT":
        if (before_state == "negate_trench" and state["combat_context"]
                and state["combat_context"]["stage"] == "TRENCH_CARDS"):
            add("PASS_TRENCH_CARDS")
        elif (before_state == "confirm_mo" and state["combat_context"]
                and state["combat_context"]["stage"] in {"TRENCH_CARDS", "FLANK"}):
            if current["combat_context"]["stage"] == "TRENCH_CARDS":
                add("PASS_TRENCH_CARDS")
            if current["combat_context"]["stage"] == "FLANK":
                add("SKIP_FLANK")
            if after_state == "defender_combat_cards":
                add("PASS_COMBAT_CARDS")
        elif state["combat_context"] and state["combat_context"]["stage"] == "ATTACKER_CARDS":
            add("PASS_COMBAT_CARDS")
        elif (before_state == "confirm_mo" and after_state == "defender_combat_cards"
              and state["combat_context"] and state["combat_context"]["stage"] == "DEFENDER_CARDS"):
            pass
        elif before_state == "confirm_mo" and state["combat_context"]["stage"] == "LOSSES":
            pass
        else:
            raise TranslationError(f"index {intent.start_index}: 전투 next 단계가 맞지 않습니다")
    elif name == "card" and before_state in ("negate_trench", "attacker_combat_cards", "defender_combat_cards"):
        add_combat_card()
    elif name == "card" and before_state == "draw_cards_phase":
        if current["phase"] == "MOVEMENT" and any(
                option["type"] == "END_MOVEMENT" for option in generate_legal_actions(current)):
            add("END_MOVEMENT")
        while current["decision"] is None and current["phase"] in {
                "ATTRITION", "SIEGE", "WAR_STATUS", "REPLACEMENT_AP", "REPLACEMENT_CP"}:
            add("ADVANCE_AUTOMATIC_PHASE")
        if current["phase"] == "DRAW" and current["decision"] is None:
            add("ADVANCE_AUTOMATIC_PHASE")
        add("DISCARD_DRAW_CARD", card_id=_lookup(ids, "cards", intent.argument, intent))
    elif name == "done" and before_state == "draw_cards_phase":
        while current["decision"] is None and current["phase"] in {
                "ATTRITION", "SIEGE", "WAR_STATUS", "REPLACEMENT_AP", "REPLACEMENT_CP"}:
            add("ADVANCE_AUTOMATIC_PHASE")
        if current["phase"] == "DRAW" and current["decision"] is None:
            add("ADVANCE_AUTOMATIC_PHASE")
        add("END_DRAW_DISCARD")
        if after_state == "confirm_mo":
            if current["phase"] == "END_TURN":
                add("ADVANCE_AUTOMATIC_PHASE")
            if len(intent.random_seeds) < 2:
                raise TranslationError(f"index {intent.start_index}: 새 턴 의무 공세 굴림이 없습니다")
            add("RECORD_DIE_RESULT", value=intent.random_seeds[-2] % 6 + 1)
            add("RECORD_DIE_RESULT", value=intent.random_seeds[-1] % 6 + 1)
    elif name == "done" and before_state in ("attacker_combat_cards", "defender_combat_cards"):
        add("PASS_COMBAT_CARDS")
        if before_state == "attacker_combat_cards" and intent.random_seeds:
            if current["combat_context"]["stage"] == "DEFENDER_CARDS":
                add("PASS_COMBAT_CARDS")
            if len(intent.random_seeds) not in (1, 2):
                raise TranslationError(f"index {intent.start_index}: 전투 주사위 관측 수가 잘못되었습니다")
            for seed in intent.random_seeds:
                context = current["combat_context"]
                side = context["fire_order"][context["fire_index"]]
                add("RECORD_COMBAT_DIE", side=side, value=seed % 6 + 1)
        if intent.random_seeds:
            if before_state == "defender_combat_cards":
                for seed in intent.random_seeds:
                    context = current["combat_context"]
                    add("RECORD_COMBAT_DIE", side=context["fire_order"][context["fire_index"]],
                        value=seed % 6 + 1)
    elif name == "space" and before_state == "apply_defender_losses" and "Fort destroyed" in " ".join(intent.log_delta):
        pass
    elif name == "done" and before_state in ("apply_attacker_losses", "apply_defender_losses"):
        if (current["combat_context"]["stage"] == "LOSSES"
                and (before_state == "apply_attacker_losses"
                     or current["combat_context"]["loss_side"] == current["combat_context"]["defender"])):
            add("END_LOSSES")
        if intent.random_seeds:
            add("RECORD_COMBAT_DIE", side=current["combat_context"]["fire_order"][current["combat_context"]["fire_index"]], value=die())
        if (after_state in ("choose_attackers", "end_operations")
                and current["phase"] == "COMBAT" and current["combat_context"]
                and current["combat_context"]["stage"] == "ADVANCE"):
            add("END_ADVANCE")
    elif name == "piece" and before_state in ("apply_attacker_losses", "apply_defender_losses"):
        replacements = [int(match.group(1)) for line in intent.log_delta
                        if (match := re.search(r"broke to P(\d+)", line))]
        fields = {"unit_id": _lookup(ids, "units", intent.argument, intent)}
        if len(replacements) == 1:
            fields["replacement_unit_id"] = _lookup(ids, "units", replacements[0], intent)
        add("TAKE_LOSS", **fields)
    elif name == "piece" and before_state == "withdrawal_negate_step_loss":
        add("NEGATE_WITHDRAWAL_LOSS", unit_id=_lookup(ids, "units", intent.argument, intent))
    elif name == "piece" and before_state == "cancel_retreat":
        fields = {"unit_id": _lookup(ids, "units", intent.argument, intent)}
        replacements = [int(match.group(1)) for line in intent.log_delta
                        if (match := re.search(r"broke to P(\d+)", line))]
        if len(replacements) == 1:
            fields["replacement_unit_id"] = _lookup(ids, "units", replacements[0], intent)
        add("CANCEL_RETREAT", **fields)
    elif (name == "retreat" and before_state == "cancel_retreat"
          and after_state == "defender_retreat" and state["phase"] == "COMBAT"
          and state["combat_context"] and state["combat_context"]["stage"] == "RETREAT"):
        pass
    elif name == "done" and before_state == "cancel_retreat_confirm":
        pass
    elif name == "done" and before_state == "withdrawal_negate_step_loss_confirm":
        pass
    elif name == "piece" and before_state == "defender_retreat":
        pass
    elif name == "space" and before_state == "defender_retreat":
        moved = _moved_units(intent, ids)
        if len(moved) != 1:
            raise TranslationError(f"index {intent.start_index}: 후퇴 유닛이 모호합니다")
        uid, destination = moved[0]
        choices = [action for action in generate_legal_actions(current)
                   if action["type"] == "RETREAT_TO" and action.get("to") == destination
                   and action.get("unit_id", uid) == uid]
        if len(choices) != 1:
            raise TranslationError(f"index {intent.start_index}: 후퇴 후보 {len(choices)}개")
        actions.append(choices[0])
    elif name == "eliminate" and before_state == "defender_retreat":
        selected = (intent.before.get("attack") or {}).get("retreating_pieces", [])
        before_locations = intent.before["location"]
        after_locations = intent.after["location"]
        changed = [index for index, (old, new) in enumerate(zip(before_locations, after_locations))
                   if index and old != new]
        if len(selected) != 1 or len(before_locations) != len(after_locations):
            raise TranslationError(f"index {intent.start_index}: 제거할 후퇴 유닛이 모호합니다")
        source_id = selected[0]
        if source_id not in changed:
            raise TranslationError(f"index {intent.start_index}: 후퇴 유닛 제거가 관측되지 않았습니다")
        uid = _lookup(ids, "units", source_id, intent)
        replacements = (current.get("combat_context") or {}).get("defender_replacements", {})
        for extra_id in changed:
            if extra_id == source_id:
                continue
            replaced_uid = _lookup(ids, "units", extra_id, intent)
            old_box = _lookup(ids, "spaces", before_locations[extra_id], intent)
            new_box = _lookup(ids, "spaces", after_locations[extra_id], intent)
            if (replacements.get(replaced_uid) != uid
                    or not old_box.endswith("_ELIMINATED_BOX")
                    or not new_box.endswith("_PERMANENTLY_ELIMINATED_BOX")):
                raise TranslationError(f"index {intent.start_index}: 추가 제거 유닛이 모호합니다")
        destination = _lookup(ids, "spaces", after_locations[source_id], intent)
        if not destination.endswith("_ELIMINATED_BOX"):
            raise TranslationError(f"index {intent.start_index}: 후퇴 실패 제거 칸이 아닙니다")
        choices = [action for action in generate_legal_actions(current)
                   if action["type"] == "NO_RETREAT_ROUTE" and action.get("unit_id", uid) == uid]
        if len(choices) != 1:
            raise TranslationError(f"index {intent.start_index}: 후퇴 실패 후보 {len(choices)}개")
        actions.append(choices[0])
    elif name == "done" and before_state == "defender_retreat":
        pass
    elif name == "piece" and before_state == "attacker_advance":
        pass
    elif name == "space" and before_state == "attacker_advance":
        for uid, destination in _moved_units(intent, ids):
            candidates = [action for action in generate_legal_actions(current)
                          if action["type"] == "ADVANCE_UNIT" and action["unit_id"] == uid
                          and action.get("to", destination) == destination]
            if len(candidates) != 1:
                raise TranslationError(f"index {intent.start_index}: 진격 후보 {len(candidates)}개 {uid}")
            emit(candidates[0])
    elif name == "done" and before_state == "attacker_advance":
        if current["phase"] == "COMBAT" and current["combat_context"] is not None:
            add("END_ADVANCE")
    elif (name == "stop" and before_state == "attacker_advance"
          and after_state == "attacker_advance" and state["phase"] == "COMBAT"
          and state["combat_context"] and state["combat_context"]["stage"] == "ADVANCE"):
        pass
    elif (name == "end_action" and before_state == "confirm_event"
          and (after_state, state["phase"]) in {
              ("action_phase", "ACTION"), ("attrition_phase", "ATTRITION"),
              ("siege_phase", "SIEGE"), ("replacement_phase", "REPLACEMENT_AP"),
          }):
        pass
    elif (name == "end_action" and before_state == "confirm_event"
          and after_state == "siege_phase" and state["phase"] == "ATTRITION"):
        add("ADVANCE_AUTOMATIC_PHASE")
    elif (name == "end_action" and before_state == "confirm_event"
          and after_state == "replacement_phase"
          and state["phase"] in {"ATTRITION", "SIEGE", "WAR_STATUS"}):
        while current["decision"] is None and current["phase"] in {"ATTRITION", "SIEGE", "WAR_STATUS"}:
            add("ADVANCE_AUTOMATIC_PHASE")
    elif name == "end_action" and state["phase"] == "COMBAT":
        if current["combat_context"] and current["combat_context"]["stage"] == "ADVANCE":
            add("END_ADVANCE")
        add("END_COMBAT")
        advance_after_action()
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
                    return finish()
        for uid, destination in moved:
            add("MOVE", unit_id=uid, to=destination)
    elif name == "stop" and state["phase"] == "MOVEMENT":
        if any(action["type"] == "STOP_MOVING_UNIT" for action in generate_legal_actions(state)):
            add("STOP_MOVING_UNIT")
    elif name in ("done", "end_action") and state["phase"] == "MOVEMENT":
        if after_state in ("end_operations", "action_phase", "confirm_mo", "trench_rolls",
                           "choose_attackers", "choose_attack_space", "attrition_phase",
                           "siege_phase", "replacement_phase"):
            add("END_MOVEMENT")
            advance_after_action()
    elif name == "end_action" and state["phase"] == "SR":
        add("END_SR")
        advance_after_action()
    elif name == "end_action" and before_state == "rps":
        if after_state == "siege_phase":
            if current["phase"] == "ATTRITION" and current["decision"] is None:
                add("ADVANCE_AUTOMATIC_PHASE")
        elif after_state != "attrition_phase":
            while current["decision"] is None and current["phase"] in {"ATTRITION", "SIEGE", "WAR_STATUS"}:
                add("ADVANCE_AUTOMATIC_PHASE")
    elif (name == "end_action" and before_state == "end_operations"
          and after_state == "siege_phase" and current["phase"] == "ATTRITION"
          and current["decision"] is None):
        add("ADVANCE_AUTOMATIC_PHASE")
    elif name == "end_action" and before_state == "end_operations" and after_state == "replacement_phase":
        advance_after_action()
    elif name == "end_action" and before_state == "end_operations" and after_state == "confirm_mo":
        advance_after_action()
    elif name == "end_action" and before_state == "end_operations" and after_state == "attrition_phase":
        pass
    elif name in {"end_rp", "confirm_end_rp"} and state["phase"].startswith("REPLACEMENT_"):
        add("END_REPLACEMENT")
        if after_state == "confirm_mo":
            if len(intent.random_seeds) < 2:
                raise TranslationError(f"index {intent.start_index}: 새 턴 의무 공세 굴림이 없습니다")
            add("ADVANCE_AUTOMATIC_PHASE")
            add("ADVANCE_AUTOMATIC_PHASE")
            add("RECORD_DIE_RESULT", value=intent.random_seeds[-2] % 6 + 1)
            add("RECORD_DIE_RESULT", value=intent.random_seeds[-1] % 6 + 1)
    elif name == "flag_supply_warnings" and after_state == "flag_supply_warnings":
        pass
    elif before_state == "flag_supply_warnings" and name in ("space", "done"):
        pass
    elif name == "done" and before_state == "review_supply_warnings" and after_state == "action_phase":
        pass
    elif (name == "next" and before_state == "confirm_mo"
          and after_state == "war_in_africa" and state["phase"] == "WAR_IN_AFRICA"):
        pass
    elif name == "next" and state["decision"] is None:
        add("ADVANCE_AUTOMATIC_PHASE")
    elif (name == "piece" and before_state in ("choose_move_space", "choose_pieces_to_move")):
        pass
    elif name == "piece" and before_state == "move_stack" and state["phase"] == "MOVEMENT":
        uid = _lookup(ids, "units", intent.argument, intent)
        if (intent.argument not in (intent.before.get("move") or {}).get("pieces", [])
                or intent.argument in (intent.after.get("move") or {}).get("pieces", [])):
            raise TranslationError(f"index {intent.start_index}: 이동 중 중지할 유닛을 확인할 수 없습니다")
        if uid in (current["movement"].get("stack") or []):
            add("DROP_MOVING_UNIT", unit_id=uid)
        elif current["movement"].get("unit") == uid:
            add("STOP_MOVING_UNIT")
        else:
            raise TranslationError(f"index {intent.start_index}: 이동 중인 유닛이 다릅니다")
    elif name == "piece" and before_state == "choose_attackers":
        pass
    elif (name == "no_attack" and before_state == "choose_attackers"
          and state["phase"] in {"MOVEMENT", "COMBAT"}
          and state["combat_context"] is None):
        pass
    elif name == "space" and before_state == "choose_move_space":
        pass
    elif name == "space" and before_state in ("guns_of_august", "choose_attackers"):
        pass
    elif name == "select_all" and before_state == "choose_attackers":
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
    return finish()


def translate_intent(state: FullGameState, intent: Intent, ids: SourceIds) -> tuple[Action, ...]:
    """기존의 행동 목록 API를 유지한다."""
    return translate_intent_result(state, intent, ids).actions
