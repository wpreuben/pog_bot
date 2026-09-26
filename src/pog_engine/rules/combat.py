"""공격 선언의 합법성, 전투력, 화력표와 측면 공격 계산."""

from functools import lru_cache
from importlib.resources import files
from itertools import combinations
import json

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError
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
    from .forts import siege_survives_departure

    target = data.spaces[destination]
    if (state["events"].get("LLOYD_GEORGE") == state["turn"]
            and not state["flags"].get("lloyd_george_canceled")
            and any(data.units[uid]["nation"] == "BR" for uid in unit_ids)
            and state["spaces"][destination]["trenches"]["CP"] == 2
            and any(unit["location"] == destination and data.units[uid]["nation"] == "GE"
                    for uid, unit in state["units"].items())):
        return False
    if state["events"].get("TREATY_OF_BREST_LITOVSK"):
        if any(data.units[uid]["nation"] == "RU" for uid in unit_ids):
            return False
        defending_russians = any(unit["location"] == destination and data.units[uid]["nation"] == "RU"
                                 for uid, unit in state["units"].items())
        if defending_russians and not (target["map"] == "neareast" and
                                       all(data.units[uid]["nation"] == "TU" for uid in unit_ids)):
            return False
    intact_fort = target["fort"] and not state["spaces"][destination]["fort_destroyed"]
    if intact_fort and target["nation"] == "RU" and state["players"]["CP"]["war_status"] < 4:
        if not state["events"].get("OBEROST") and any(data.units[uid]["nation"] == "GE" for uid in unit_ids):
            return False
    if intact_fort and target["nation"] == "GE" and state["turn"] == 1:
        if any(data.units[uid]["nation"] == "RU" for uid in unit_ids):
            return False
    places = {state["units"][uid]["location"] for uid in unit_ids}
    if any(not siege_survives_departure(state, place, tuple(uid for uid in unit_ids
                                                        if state["units"][uid]["location"] == place))
           for place in places if place != destination):
        return False
    for place in places - {destination}:
        if state["spaces"][place]["fort_besieged"]:
            remaining = [uid for uid, unit in state["units"].items()
                         if unit["location"] == place and data.units[uid]["side"] == state["active_side"]
                         and uid not in unit_ids]
            if not remaining:
                return False
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
        destinations = set(data.neighbors(start, definition["nation"]))
        if data.spaces[start]["fort"] and state["spaces"][start]["fort_besieged"]:
            destinations.add(start)
        for destination in destinations:
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
        units = [uid for uid in context["attackers"] if state["units"][uid]["location"] is not None]
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
            attacker: "ARMY" if any(data.units[uid]["type"] == "ARMY" and state["units"][uid]["location"] is not None
                                    for uid in context["attackers"]) else "CORPS",
            defender: "ARMY" if context.get("defender_army_table") or any(data.units[uid]["type"] == "ARMY" for uid in defenders) else "CORPS",
        },
        "shifts": {
            attacker: -(0 if unoccupied_fort or context.get("trench_shift_canceled") else trench) - (1 if terrain in {"MOUNTAIN", "SWAMP"} else 0),
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


def _context_units(state: FullGameState, side: str) -> list[str]:
    context = state["combat_context"]
    if side == context["attacker"]:
        return [uid for uid in context["attackers"] if state["units"][uid]["location"] is not None]
    place = context.get("retreat_location", context["defender_space"])
    return [uid for uid in context["defending_units"] if state["units"][uid]["location"] == place]


def _loss_options(state: FullGameState) -> list[Action]:
    context = state["combat_context"]
    side = context["loss_side"]
    remaining = context["loss_remaining"]
    data = load_data()
    actions: list[Action] = []
    for uid in _context_units(state, side):
        unit = state["units"][uid]
        definition = data.units[uid]
        lf = definition["reduced_lf"] if unit["reduced"] else definition["lf"]
        if lf > remaining:
            continue
        base = {"type": "TAKE_LOSS", "actor": side, "unit_id": uid}
        if unit["reduced"] and definition["type"] == "ARMY":
            reserve = f"{side}_RESERVE_BOX"
            corps = [cid for cid, candidate in data.units.items()
                     if candidate["side"] == side and candidate["nation"] == definition["nation"]
                     and candidate["type"] == "CORPS" and state["units"][cid]["location"] == reserve]
            if corps:
                actions.extend({**base, "replacement_unit_id": cid} for cid in sorted(corps))
            else:
                actions.append({**base, "replacement_unit_id": None})
        else:
            actions.append(base)
    active = tuple(sorted((uid, state["units"][uid]["reduced"]) for uid in _context_units(state, side)))
    reserve = tuple(sorted(
        cid for cid, candidate in data.units.items()
        if candidate["side"] == side and candidate["type"] == "CORPS"
        and state["units"][cid]["location"] == f"{side}_RESERVE_BOX"
    ))

    def after(active_units, reserve_units, uid, replacement):
        updated = list(active_units)
        index = next(i for i, (candidate, _) in enumerate(updated) if candidate == uid)
        was_reduced = updated[index][1]
        if was_reduced:
            updated.pop(index)
            if replacement:
                updated.append((replacement, False))
        else:
            updated[index] = (uid, True)
        updated_reserve = tuple(cid for cid in reserve_units if cid != replacement)
        return tuple(sorted(updated)), updated_reserve

    @lru_cache(maxsize=None)
    def payable(active_units, reserve_units, budget):
        best = 0
        for uid, reduced in active_units:
            definition = data.units[uid]
            lf = definition["reduced_lf"] if reduced else definition["lf"]
            if lf > budget:
                continue
            replacements = [None]
            if reduced and definition["type"] == "ARMY":
                replacements = [cid for cid in reserve_units
                                if data.units[cid]["nation"] == definition["nation"]] or [None]
            for replacement in replacements:
                following, remaining_reserve = after(active_units, reserve_units, uid, replacement)
                best = max(best, lf + payable(following, remaining_reserve, budget - lf))
        return best

    maximum = payable(active, reserve, remaining)
    if maximum == 0:
        return [{"type": "END_LOSSES", "actor": side}]
    optimal = []
    for action in actions:
        uid = action["unit_id"]
        reduced = state["units"][uid]["reduced"]
        definition = data.units[uid]
        lf = definition["reduced_lf"] if reduced else definition["lf"]
        following, remaining_reserve = after(active, reserve, uid, action.get("replacement_unit_id"))
        if lf + payable(following, remaining_reserve, remaining - lf) == maximum:
            optimal.append(action)
    return optimal


def _retreat_progress(state: FullGameState) -> dict[str, dict]:
    context = state["combat_context"]
    if "retreat_progress" in context:
        return context["retreat_progress"]
    return {
        uid: {"current": context["defender_space"], "remaining": context["retreat_total"], "path": []}
        for uid in context["defending_units"]
        if state["units"][uid]["location"] == context["defender_space"]
    }


def _retreat_destinations(state: FullGameState, uid: str, progress: dict) -> list[str]:
    context = state["combat_context"]
    current = progress["current"]
    data = load_data()
    neighbors = data.neighbors(current, data.units[uid]["nation"])
    enemy = context["attacker"]
    destinations = []
    for place in neighbors:
        if place == context["defender_space"] or data.spaces[place]["kind"] != "BOARD":
            continue
        if not state["war_nations"].get(data.spaces[place]["nation"], True):
            continue
        if any(unit["location"] == place and data.units[uid]["side"] == enemy for uid, unit in state["units"].items()):
            continue
        if data.spaces[place]["fort"] and state["spaces"][place]["control"] == enemy and not state["spaces"][place]["fort_destroyed"]:
            continue
        if progress["remaining"] == 1:
            occupied = sum(unit["location"] == place for unit in state["units"].values())
            if occupied >= 3:
                continue
        destinations.append(place)
    return sorted(destinations)


def _cancel_retreat_options(state: FullGameState) -> list[Action]:
    context = state["combat_context"]
    side = context["defender"]
    units = _context_units(state, side)
    data = load_data()
    actions = []
    for uid in units:
        unit = state["units"][uid]
        base = {"type": "CANCEL_RETREAT", "actor": side, "unit_id": uid}
        if not unit["reduced"]:
            actions.append(base)
            continue
        definition = data.units[uid]
        if definition["type"] == "ARMY":
            corps = sorted(cid for cid, candidate in data.units.items()
                           if candidate["side"] == side and candidate["nation"] == definition["nation"]
                           and candidate["type"] == "CORPS"
                           and state["units"][cid]["location"] == f"{side}_RESERVE_BOX")
            actions.extend({**base, "replacement_unit_id": cid} for cid in corps)
            if not corps and len(units) > 1:
                actions.append(base)
        elif len(units) > 1:
            actions.append(base)
    return actions


def _advance_options(state: FullGameState) -> list[Action]:
    context = state["combat_context"]
    side = context["attacker"]
    target = context["defender_space"]
    data = load_data()
    actions = [{"type": "END_ADVANCE", "actor": side}]
    target_open = not any(unit["location"] == target and data.units[uid]["side"] != side
                          for uid, unit in state["units"].items())
    target_room = sum(unit["location"] == target for unit in state["units"].values()) < 3
    for uid in context["attackers"]:
        unit = state["units"][uid]
        if unit["location"] is None or unit["reduced"]:
            continue
        if uid not in context["advanced"] and target_open and target_room and target in data.neighbors(
            unit["location"], data.units[uid]["nation"]
        ):
            target_data = data.spaces[target]
            if target_data["fort"] and not state["spaces"][target]["fort_destroyed"] and target_data["side"] != side:
                from .forts import can_besiege

                if not state["spaces"][target]["fort_besieged"] and not can_besiege(state, target, side, (uid,)):
                    continue
            actions.append({"type": "ADVANCE_UNIT", "actor": side, "unit_id": uid})
        elif (uid in context["advanced"] and unit["location"] == target
              and context.get("retreat_total") == 2
              and data.spaces[target]["terrain"] not in {"DESERT", "FOREST", "MOUNTAIN", "SWAMP"}
              and not state["spaces"][target]["fort_besieged"]):
            routes = context.get("retreat_progress", {}).values()
            next_places = {entry["path"][0] for entry in routes if len(entry["path"]) >= 2}
            if not next_places and len(context.get("retreat_path", [])) >= 2:
                next_places = {context["retreat_path"][0]}
            for next_place in sorted(next_places):
                next_data = data.spaces[next_place]
                if (next_data["fort"] and not state["spaces"][next_place]["fort_destroyed"]
                        and state["spaces"][next_place]["control"] != side):
                    from .forts import can_besiege

                    if not can_besiege(state, next_place, side, (uid,)):
                        continue
                if (next_place in data.neighbors(target, data.units[uid]["nation"])
                        and sum(other["location"] == next_place for other in state["units"].values()) < 3
                        and not any(other["location"] == next_place and data.units[other_id]["side"] != side
                                    for other_id, other in state["units"].items())):
                    actions.append({"type": "ADVANCE_UNIT", "actor": side, "unit_id": uid, "to": next_place})
    return actions


def _great_retreat_options(state: FullGameState) -> list[Action]:
    context = state["combat_context"]
    data = load_data()
    destination = context["defender_space"]
    actions = []
    for uid, unit in state["units"].items():
        if unit["location"] != destination or data.units[uid]["nation"] != "RU":
            continue
        for place in sorted(data.neighbors(destination, "RU")):
            if data.spaces[place]["kind"] != "BOARD" or not state["war_nations"].get(data.spaces[place]["nation"], True):
                continue
            if any(other["location"] == place and data.units[other_id]["side"] == "CP"
                   for other_id, other in state["units"].items()):
                continue
            if (data.spaces[place]["fort"] and state["spaces"][place]["control"] == "CP"
                    and not state["spaces"][place]["fort_destroyed"]):
                continue
            if sum(other["location"] == place for other in state["units"].values()) >= 3:
                continue
            actions.append({"type": "RETREAT_RUSSIAN_UNIT", "actor": "AP", "unit_id": uid, "to": place})
    return actions + [{"type": "PASS_GREAT_RETREAT", "actor": "AP"}]


def _after_precombat_retreat(state: FullGameState) -> None:
    context = state["combat_context"]
    data = load_data()
    destination = context["defender_space"]
    defenders = [uid for uid, unit in state["units"].items()
                 if unit["location"] == destination and data.units[uid]["side"] == context["defender"]]
    fort = (data.spaces[destination]["fort"] and not state["spaces"][destination]["fort_destroyed"]
            and state["spaces"][destination]["control"] == context["defender"])
    if not defenders and not fort:
        if any(state["units"][uid]["location"] is not None and not state["units"][uid]["reduced"]
               for uid in context["attackers"]):
            context["stage"] = "ADVANCE"
        else:
            _finish_combat(state)
        return
    from .events.combat import TRENCH_CARDS, combat_card_eligible

    attacker = context["attacker"]
    context["stage"] = "TRENCH_CARDS"
    if not any(combat_card_eligible(state, card_id, "TRENCH_CARDS") for card_id in
               state["players"][attacker]["hand"] + state["players"][attacker].get("in_play", [])
               if card_id in TRENCH_CARDS) and not _brusilov_trench_available(state):
        context["stage"] = "FLANK"


def _brusilov_trench_available(state: FullGameState) -> bool:
    context = state["combat_context"]
    data = load_data()
    return bool(
        context["attacker"] == "AP"
        and state["temporary_effects"].get("BRUSILOV_OFFENSIVE") == state["turn"]
        and not state["temporary_effects"].get("BRUSILOV_TRENCH_USED")
        and any(data.units[uid]["nation"] == "RU" for uid in context["attackers"])
        and not any(data.units[uid]["nation"] == "GE" for uid in context["defending_units"])
        and state["spaces"][context["defender_space"]]["trenches"]["CP"] > 0
    )


def legal_combat_actions(state: FullGameState) -> list[Action]:
    if state["phase"] != "COMBAT":
        return []
    context = state["combat_context"]
    if context is None:
        return legal_attack_declarations(state) + [{"type": "END_COMBAT", "actor": state["active_side"]}]
    stage = context["stage"]
    attacker, defender = context["attacker"], context["defender"]
    from .events.combat import combat_card_eligible

    def card_options(side: str) -> list[Action]:
        used = state["flags"].get("combat_card_used_round", {})
        round_key = [state["turn"], state["action_round"]]
        actions = [
            {"type": "PLAY_COMBAT_CARD", "actor": side, "card_id": cid}
            for cid in state["players"][side]["hand"]
            if load_data().cards[cid]["combat_card"] and combat_card_eligible(state, cid, stage)
        ]
        actions.extend(
            {"type": "USE_COMBAT_CARD", "actor": side, "card_id": cid}
            for cid in state["players"][side].get("in_play", [])
            if used.get(cid) != round_key and combat_card_eligible(state, cid, stage)
        )
        return actions

    if stage == "GREAT_RETREAT":
        return _great_retreat_options(state)
    if stage == "TRENCH_CARDS":
        actions = card_options(attacker)
        if _brusilov_trench_available(state):
            actions.append({"type": "USE_BRUSILOV_TRENCH", "actor": attacker})
        return actions + [{"type": "PASS_TRENCH_CARDS", "actor": attacker}]
    if stage == "FLANK":
        actions = card_options(attacker) + [{"type": "SKIP_FLANK", "actor": attacker}]
        for place in sorted({state["units"][uid]["location"] for uid in context["attackers"]}):
            if flank_modifier(state, {**context, "pinning_space": place}) is not None:
                actions.append({"type": "ATTEMPT_FLANK", "actor": attacker, "pinning_space": place})
        return actions
    if stage == "FLANK_ROLL":
        return [{"type": "RECORD_FLANK_DIE", "actor": "CHANCE", "value": die} for die in range(1, 7)]
    if stage in {"ATTACKER_CARDS", "DEFENDER_CARDS"}:
        side = attacker if stage == "ATTACKER_CARDS" else defender
        actions = card_options(side)
        if stage == "ATTACKER_CARDS" and attacker == "AP" and state["temporary_effects"].get("KERENSKY_OFFENSIVE") == state["turn"]:
            data = load_data()
            if (any(data.units[uid]["nation"] == "RU" for uid in context["attackers"])
                    and any(data.units[uid]["nation"] in {"AH", "BU", "TU"} for uid in context["defending_units"])):
                actions.append({"type": "USE_KERENSKY_OFFENSIVE", "actor": attacker})
        return actions + [{"type": "PASS_COMBAT_CARDS", "actor": side}]
    if stage == "FIRE":
        side = context["fire_order"][context["fire_index"]]
        return [{"type": "RECORD_COMBAT_DIE", "actor": "CHANCE", "side": side, "value": die} for die in range(1, 7)]
    if stage == "LOSSES":
        return _loss_options(state)
    if stage == "WITHDRAWAL_NEGATE":
        history = context.get("loss_history", [])
        corps = [entry for entry in history if load_data().units[entry["unit_id"]]["type"] == "CORPS"]
        choices = corps or history
        return [{"type": "NEGATE_WITHDRAWAL_LOSS", "actor": defender,
                 "unit_id": entry["unit_id"]} for entry in choices]
    if stage == "RETREAT":
        progress = _retreat_progress(state)
        active = [uid for uid, entry in progress.items() if entry["remaining"] > 0]
        actions = []
        for uid in active:
            fields = {"unit_id": uid} if len(progress) > 1 else {}
            destinations = _retreat_destinations(state, uid, progress[uid])
            actions.extend({"type": "RETREAT_TO", "actor": defender, **fields, "to": place}
                           for place in destinations)
            if not destinations:
                actions.append({"type": "NO_RETREAT_ROUTE", "actor": defender, **fields})
        if context["retreat_remaining"] == context["retreat_total"] and not context.get("withdrawal"):
            terrain = load_data().spaces[context["defender_space"]]["terrain"]
            trench = (state["spaces"][context["defender_space"]]["trenches"][defender]
                      and not context.get("trench_negated"))
            if trench or terrain in {"FOREST", "DESERT", "MOUNTAIN", "SWAMP"}:
                actions.extend(_cancel_retreat_options(state))
        return actions
    if stage == "ADVANCE":
        return _advance_options(state)
    raise ValueError(f"알 수 없는 전투 단계: {stage}")


def _refresh(state: FullGameState) -> None:
    options = legal_combat_actions(state)
    state["decision"] = {"kind": "COMBAT", "actor": options[0]["actor"] if options else state["active_side"], "options": options}


def enter_combat(state: FullGameState) -> FullGameState:
    state["phase"] = "COMBAT"
    state["combat_context"] = None
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    _refresh(state)
    return state


def _finish_combat(state: FullGameState) -> None:
    context = state["combat_context"]
    attacker, defender = context["attacker"], context["defender"]
    winner = attacker if context["results"].get(attacker, 0) > context["results"].get(defender, 0) else (
        defender if context["results"].get(defender, 0) > context["results"].get(attacker, 0) else None
    )
    for side in (attacker, defender):
        cards = context["cards"][side]
        from .events.combat import SINGLE_COMBAT_CARDS

        for card_id in cards:
            player = state["players"][side]
            if card_id in player.get("in_play", []):
                player["in_play"].remove(card_id)
            retain_tie = card_id == "THEY_SHALL_NOT_PASS" and winner is None
            zone = "removed" if load_data().cards[card_id]["remove"] else (
                "discard" if (side != winner and not retain_tie) or card_id in SINGLE_COMBAT_CARDS else "in_play"
            )
            player.setdefault(zone, []).append(card_id)
    state["attacked_units"].extend(context["attackers"])
    state["attacked_spaces"].append(context["defender_space"])
    state["combat_context"] = None


def _after_losses(state: FullGameState) -> None:
    context = state["combat_context"]
    if context["stage"] == "LOSSES" and context["loss_side"] == context["defender"]:
        from .forts import resolve_fort_combat

        result = resolve_fort_combat(state, context)
        state.clear()
        state.update(result)
        context = state["combat_context"]
    if context["loss_queue"]:
        context["loss_side"] = context["loss_queue"].pop(0)
        enemy = context["defender"] if context["loss_side"] == context["attacker"] else context["attacker"]
        context["loss_remaining"] = context["results"][enemy]
        context["stage"] = "LOSSES"
        return
    if context["fire_index"] + 1 < len(context["fire_order"]):
        context["fire_index"] += 1
        context["stage"] = "FIRE"
        return
    if context.get("withdrawal") and not context.get("withdrawal_negated") and context.get("loss_history"):
        context["stage"] = "WITHDRAWAL_NEGATE"
        return
    attacker, defender = context["attacker"], context["defender"]
    full_attackers = any(state["units"][uid]["location"] is not None and not state["units"][uid]["reduced"] for uid in context["attackers"])
    defenders = _context_units(state, defender)
    difference = context["results"].get(attacker, 0) - context["results"].get(defender, 0)
    if context.get("retreat_canceled") and difference > 0 and defenders:
        _finish_combat(state)
    elif (difference > 0 or context.get("withdrawal")) and defenders and full_attackers:
        context["stage"] = "RETREAT"
        context["retreat_total"] = 1 if context.get("withdrawal") or difference <= 1 else 2
        context["retreat_remaining"] = context["retreat_total"]
        context["retreat_location"] = context["defender_space"]
        context["retreat_path"] = []
        context["retreat_progress"] = _retreat_progress(state)
    elif difference > 0 and not defenders and full_attackers:
        context["stage"] = "ADVANCE"
    else:
        _finish_combat(state)


def _apply_step_loss(state: FullGameState, uid: str, replacement: str | None = None) -> int:
    unit = state["units"][uid]
    definition = load_data().units[uid]
    old_place = unit["location"]
    lf = definition["reduced_lf"] if unit["reduced"] else definition["lf"]
    if unit["reduced"]:
        old_place = unit["location"]
        unit["location"] = None
        unit["eliminated"] = True
        if replacement:
            state["units"][replacement]["location"] = old_place
    else:
        unit["reduced"] = True
    if old_place:
        from .forts import update_siege_status

        update_siege_status(state, old_place)
    return lf


def apply_combat_action(state: FullGameState, action: Action) -> FullGameState:
    if action not in legal_combat_actions(state):
        raise IllegalActionError("전투 창에서 합법적인 행동이 아닙니다")
    kind = action["type"]
    if kind == "END_COMBAT":
        from .turn import complete_action

        state["phase"] = "ACTION"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return state
    if kind == "DECLARE_ATTACK":
        attacker = state["active_side"]
        defender = "AP" if attacker == "CP" else "CP"
        defending_units = [uid for uid, unit in state["units"].items()
                           if unit["location"] == action["defender_space"] and load_data().units[uid]["side"] == defender]
        from .war import satisfies_mandatory_offensive

        french_mutiny_mo = (attacker == "AP" and state["events"].get("FRENCH_MUTINY")
                           and state["players"]["AP"]["mandatory_offensive"] == "FR")
        if french_mutiny_mo and load_data().spaces[action["defender_space"]]["nation"] in {"FR", "BE", "GE"}:
            sources = {state["units"][uid]["location"] for uid in action["unit_ids"]
                       if load_data().units[uid]["nation"] == "FR"}
            if any(not any(unit["location"] == source and load_data().units[uid]["nation"] == "US"
                           for uid, unit in state["units"].items()) for source in sources):
                from .war import apply_vp_change

                updated = apply_vp_change(state, 1, "FRENCH_MUTINY")
                state.clear()
                state.update(updated)
                state["players"]["AP"]["mandatory_offensive"] = None
        elif not french_mutiny_mo and satisfies_mandatory_offensive(
            state, attacker, action["unit_ids"], defending_units, action["defender_space"]
        ):
            state["players"][attacker]["mandatory_offensive"] = None
        state["combat_context"] = {
            "attacker": attacker, "defender": defender, "attackers": action["unit_ids"],
            "defender_space": action["defender_space"], "defending_units": defending_units, "stage": "FLANK",
            "cards": {"AP": [], "CP": []}, "results": {}, "rolls": {},
            "fire_order": [attacker, defender], "fire_index": 0,
            "loss_queue": [], "loss_side": None, "loss_remaining": 0, "advanced": [],
        }
        context = state["combat_context"]
        data = load_data()
        if attacker == "AP":
            nations = {data.units[uid]["nation"] for uid in action["unit_ids"]}
            drm = 0
            if "US" in nations and state["temporary_effects"].get("YANKS_AND_TANKS") == state["turn"]:
                drm += 2
            if "RU" in nations and state["temporary_effects"].get("BRUSILOV_OFFENSIVE") == state["turn"]:
                drm += 1
            if drm:
                context.setdefault("drm", {})["AP"] = drm
        if (attacker == "CP" and state["events"].get("GREAT_RETREAT") == state["turn"]
                and any(data.units[uid]["nation"] == "RU" for uid in defending_units)):
            context["stage"] = "GREAT_RETREAT"
        else:
            _after_precombat_retreat(state)
    else:
        context = state["combat_context"]
        if kind == "RETREAT_RUSSIAN_UNIT":
            state["units"][action["unit_id"]]["location"] = action["to"]
            if state["spaces"][action["to"]]["control"] != "AP":
                state["spaces"][action["to"]]["control"] = "AP"
            if not any(option["type"] == "RETREAT_RUSSIAN_UNIT" for option in _great_retreat_options(state)):
                _after_precombat_retreat(state)
        elif kind == "PASS_GREAT_RETREAT":
            _after_precombat_retreat(state)
        elif kind == "USE_BRUSILOV_TRENCH":
            context["trench_negated"] = True
            state["temporary_effects"]["BRUSILOV_TRENCH_USED"] = True
            context["stage"] = "FLANK"
        elif kind == "USE_KERENSKY_OFFENSIVE":
            context.setdefault("drm", {})["AP"] = context.get("drm", {}).get("AP", 0) + 2
            state["temporary_effects"].pop("KERENSKY_OFFENSIVE", None)
        elif kind == "PASS_TRENCH_CARDS":
            context["stage"] = "FLANK"
        elif kind == "SKIP_FLANK":
            context["stage"] = "ATTACKER_CARDS"
        elif kind == "ATTEMPT_FLANK":
            context["pinning_space"] = action["pinning_space"]
            context["flank_modifier"] = flank_modifier(state, context)
            context["stage"] = "FLANK_ROLL"
        elif kind == "RECORD_FLANK_DIE":
            success = action["value"] + context["flank_modifier"] >= 4
            context["flank_success"] = success
            context["fire_order"] = [context["attacker"], context["defender"]] if success else [context["defender"], context["attacker"]]
            context["stage"] = "ATTACKER_CARDS"
        elif kind in {"PLAY_COMBAT_CARD", "USE_COMBAT_CARD"}:
            side = action["actor"]
            card_id = action["card_id"]
            if kind == "PLAY_COMBAT_CARD":
                state["players"][side]["hand"].remove(card_id)
            context["cards"][side].append(card_id)
            state["flags"].setdefault("combat_card_used_round", {})[card_id] = [state["turn"], state["action_round"]]
            from .events.combat import COMBAT_HANDLERS

            COMBAT_HANDLERS[card_id].apply(state, action)
            if context["stage"] == "FLANK" and card_id == "WIRELESS_INTERCEPTS":
                context["stage"] = "ATTACKER_CARDS"
        elif kind == "PASS_COMBAT_CARDS":
            context["stage"] = "DEFENDER_CARDS" if context["stage"] == "ATTACKER_CARDS" else "FIRE"
        elif kind == "RECORD_COMBAT_DIE":
            side = action["side"]
            snapshot = combat_snapshot(state, context)
            column = fire_column(snapshot, side)
            drm = context.get("drm", {}).get(side, 0)
            if side == context["attacker"] and all(state["units"][uid]["location"] == "SINAI"
                                                    for uid in context["attackers"]):
                drm -= 3
            result = crt_result(snapshot["tables"][side], column, action["value"] + drm)
            context["rolls"][side] = action["value"]
            context["results"][side] = result
            if "flank_success" in context:
                opponent = context["defender"] if side == context["attacker"] else context["attacker"]
                context["loss_queue"] = [opponent]
                _after_losses(state)
            elif len(context["rolls"]) == 2:
                context["loss_queue"] = [context["defender"], context["attacker"]]
                _after_losses(state)
            else:
                context["fire_index"] += 1
        elif kind == "TAKE_LOSS":
            if context.get("withdrawal") and context["loss_side"] == context["defender"]:
                uid = action["unit_id"]
                context.setdefault("loss_history", []).append({
                    "unit_id": uid, "location": state["units"][uid]["location"],
                    "was_reduced": state["units"][uid]["reduced"],
                })
            context["loss_remaining"] -= _apply_step_loss(state, action["unit_id"], action.get("replacement_unit_id"))
            if action.get("replacement_unit_id"):
                context["defending_units" if context["loss_side"] == context["defender"] else "attackers"].append(action["replacement_unit_id"])
        elif kind == "END_LOSSES":
            _after_losses(state)
        elif kind == "NEGATE_WITHDRAWAL_LOSS":
            entry = next(item for item in context["loss_history"] if item["unit_id"] == action["unit_id"])
            unit = state["units"][entry["unit_id"]]
            unit["location"] = entry["location"]
            unit["reduced"] = entry["was_reduced"]
            unit["eliminated"] = False
            context["withdrawal_negated"] = True
            _after_losses(state)
        elif kind == "CANCEL_RETREAT":
            _apply_step_loss(state, action["unit_id"], action.get("replacement_unit_id"))
            _finish_combat(state)
        elif kind == "NO_RETREAT_ROUTE":
            progress = _retreat_progress(state)
            uid = action.get("unit_id") or next(iter(progress))
            state["units"][uid]["location"] = None
            state["units"][uid]["eliminated"] = True
            if load_data().units[uid]["type"] == "ARMY":
                state["units"][uid]["permanent"] = True
            progress[uid]["remaining"] = 0
            context["retreat_progress"] = progress
            if all(entry["remaining"] == 0 for entry in progress.values()):
                context["stage"] = "ADVANCE"
        elif kind == "RETREAT_TO":
            progress = _retreat_progress(state)
            uid = action.get("unit_id") or next(iter(progress))
            state["units"][uid]["location"] = action["to"]
            progress[uid]["current"] = action["to"]
            progress[uid]["path"].append(action["to"])
            progress[uid]["remaining"] -= 1
            context["retreat_progress"] = progress
            context["retreat_location"] = action["to"]
            context["retreat_path"] = progress[uid]["path"]
            context["retreat_remaining"] = min(entry["remaining"] for entry in progress.values())
            if all(entry["remaining"] == 0 for entry in progress.values()):
                context["stage"] = "ADVANCE"
        elif kind == "ADVANCE_UNIT":
            from .forts import update_siege_status

            uid = action["unit_id"]
            target = action.get("to", context["defender_space"])
            state["units"][uid]["location"] = target
            if uid not in context["advanced"]:
                context["advanced"].append(uid)
            space = state["spaces"][target]
            if not load_data().spaces[target]["fort"] or space["fort_destroyed"] or space["control"] == context["attacker"]:
                if space["control"] != context["attacker"] and space["vp"]:
                    state["vp"] += 1 if context["attacker"] == "CP" else -1
                space["control"] = context["attacker"]
            else:
                update_siege_status(state, target)
        elif kind == "END_ADVANCE":
            _finish_combat(state)
    _refresh(state)
    return state


def _apply_combat(state: FullGameState, action: Action, random_input: object | None) -> None:
    apply_combat_action(state, action)


register_decision_handler("COMBAT", _apply_combat)
