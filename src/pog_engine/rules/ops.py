"""OPS 비용과 공간 활성화."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError


_BRITISH = {"BR", "AUS", "CND", "PT", "ANA"}


def _sud_army_eligible(state: FullGameState, space_id: str, pieces: list[str]) -> bool:
    definitions = [load_data().units[uid] for uid in pieces]
    ah = [item for item in definitions if item["nation"] == "AH"]
    ge_corps = [item for item in definitions if item["nation"] == "GE" and item["type"] == "CORPS"]
    return bool(ah and sum(item["type"] == "ARMY" for item in ah) <= 1 and ge_corps
                and all(item["type"] == "CORPS" for item in definitions if item["nation"] != "AH"))


def activation_cost(state: FullGameState, space_id: str, kind: str) -> int:
    if kind not in {"MOVE", "ATTACK"}:
        raise ValueError("알 수 없는 활성화 종류")
    data = load_data()
    if space_id not in data.spaces or data.spaces[space_id]["kind"] != "BOARD":
        raise ValueError("활성화할 수 없는 공간")
    side = state["active_side"]
    nations = set()
    russian_attackers = 0
    pieces = []
    for unit_id, unit in state["units"].items():
        if unit["location"] != space_id or data.units[unit_id]["side"] != side:
            continue
        pieces.append(unit_id)
        nation = data.units[unit_id]["nation"]
        if not state["war_nations"].get(nation, True):
            continue
        if kind == "ATTACK" and nation == "RU" and state["events"].get("TREATY_OF_BREST_LITOVSK"):
            continue
        if kind == "ATTACK" and nation == "RU" and state["events"].get("FALL_OF_THE_TSAR"):
            russian_attackers += 1
            continue
        if nation in _BRITISH or (nation == "BE" and space_id in {"ANTWERP", "OSTEND", "CALAIS", "AMIENS"}):
            nation = "BR"
        elif nation == "US" and data.spaces[space_id]["nation"] in {"FR", "GE"}:
            nation = "FR"
        nations.add(nation)
    cost = len(nations)
    if side == "AP" and state["events"].get("EVERYONE_INTO_BATTLE") == state["turn"]:
        if data.spaces[space_id]["nation"] in {"IT", "FR", "BE"} and cost:
            cost = 1
    if side == "CP" and state["events"].get("SUD_ARMY"):
        used = state["flags"].get("sud_army_used_round", {})
        if used.get("turn") != state["turn"] or used.get("round") != state["action_round"] or used.get("space") == space_id:
            if _sud_army_eligible(state, space_id, pieces):
                ah_count = sum(data.units[uid]["nation"] == "AH" for uid in pieces)
                cost = 1 if ah_count == 1 and len(pieces) == 2 else 2
    if side == "CP" and state["events"].get("11TH_ARMY") and "GE_11_ARMY_1" in pieces:
        armies = [data.units[uid] for uid in pieces if data.units[uid]["type"] == "ARMY"]
        if len(armies) < 2:
            cost = len({item["nation"] for item in armies})
    if side == "CP" and state["events"].get("MOLTKE") and not state["events"].get("FALKENHAYN"):
        if data.spaces[space_id]["nation"] in {"FR", "BE"}:
            cost = len(pieces)
    if russian_attackers:
        cost = russian_attackers + len(nations)
    return cost


def legal_ops_actions(state: FullGameState) -> list[Action]:
    if state["phase"] != "OPS":
        return []
    side = state["active_side"]
    actions: list[Action] = []
    activated = set(state["activated"]["MOVE"] + state["activated"]["ATTACK"])
    data = load_data()
    spaces = sorted({unit["location"] for unit in state["units"].values() if unit["location"]})
    for space_id in spaces:
        if space_id in activated or state["ops_remaining"] <= 0 or data.spaces[space_id]["kind"] != "BOARD":
            continue
        for kind in ("MOVE", "ATTACK"):
            cost = activation_cost(state, space_id, kind)
            if 0 < cost <= state["ops_remaining"]:
                actions.append({"type": "ACTIVATE_SPACE", "actor": side, "space_id": space_id, "kind": kind})
    actions.append({"type": "FINISH_ACTIVATION", "actor": side})
    return actions


def _apply_ops(state: FullGameState, action: Action, random_input: object | None) -> None:
    if action["type"] == "ACTIVATE_SPACE":
        from .supply import supply_status

        space_id, kind = action["space_id"], action["kind"]
        cost = activation_cost(state, space_id, kind)
        if cost == 0 or cost > state["ops_remaining"]:
            raise IllegalActionError("활성화 비용이 부족합니다")
        state["ops_remaining"] -= cost
        state["activated"][kind].append(space_id)
        if state["active_side"] == "CP" and state["events"].get("SUD_ARMY"):
            pieces = [uid for uid, unit in state["units"].items()
                      if unit["location"] == space_id and load_data().units[uid]["side"] == "CP"]
            used = state["flags"].get("sud_army_used_round", {})
            if _sud_army_eligible(state, space_id, pieces) and (
                used.get("turn") != state["turn"] or used.get("round") != state["action_round"]
            ):
                state["flags"]["sud_army_used_round"] = {
                    "turn": state["turn"], "round": state["action_round"], "space": space_id,
                }
        state.setdefault("activated_oos", []).extend(
            uid for uid, unit in state["units"].items()
            if unit["location"] == space_id and not supply_status(state, uid).supplied
            and uid not in state.get("activated_oos", [])
        )
        state["decision"]["options"] = legal_ops_actions(state)
        return
    if action["type"] == "FINISH_ACTIVATION":
        from .movement import legal_movement_actions

        state["phase"] = "MOVEMENT"
        state["movement"] = {"unit": None, "spent": 0, "done": []}
        state["decision"] = {"kind": "MOVEMENT", "actor": state["active_side"], "options": []}
        state["decision"]["options"] = legal_movement_actions(state)
        return
    raise IllegalActionError("알 수 없는 OPS 행동")


register_decision_handler("OPS", _apply_ops)
