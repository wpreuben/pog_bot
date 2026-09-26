"""전략 카드의 사용 방식과 덱 영역."""

from copy import deepcopy

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError
from pog_engine.randomness import shuffle_with_state
from .turn import complete_action


EVENT_HANDLERS: dict[str, object] = {}


def legal_card_actions(state: FullGameState, side: str) -> list[Action]:
    if state["phase"] != "ACTION" or state["active_side"] != side:
        return []
    if state["turn"] == 1 and state["action_round"] == 1 and side == "CP":
        return [{"type": "PLAY_CARD", "actor": side, "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"}]
    data = load_data()
    player = state["players"][side]
    actions: list[Action] = []
    for card_id in player["hand"]:
        card = data.cards[card_id]
        modes = []
        if card["ops"]:
            modes.append("OPS")
        if card["sr"]:
            modes.append("SR")
        if card["rp"] and player.get("last_action_mode") != "RP":
            modes.append("RP")
        handler = EVENT_HANDLERS.get(card_id)
        if handler is not None and not card["combat_card"] and handler.can_play(state, card_id):
            modes.append("EVENT")
        actions.extend({"type": "PLAY_CARD", "actor": side, "card_id": card_id, "mode": mode} for mode in modes)
    return actions


def play_card(state: FullGameState, card_id: str, mode: str) -> FullGameState:
    side = state["active_side"]
    action = {"type": "PLAY_CARD", "actor": side, "card_id": card_id, "mode": mode}
    if action not in legal_card_actions(state, side):
        raise IllegalActionError("이 카드를 현재 방식으로 사용할 수 없습니다")
    card = load_data().cards[card_id]
    player = state["players"][side]
    player["hand"].remove(card_id)
    player["last_action_mode"] = mode
    if mode == "EVENT":
        if card["remove"]:
            player["removed"].append(card_id)
        else:
            player["discard"].append(card_id)
        player["war_status"] += card["war_status"]
        if card_id == "GUNS_OF_AUGUST":
            state["events"]["GUNS_OF_AUGUST"] = state["turn"]
            next_state = complete_action(state)
            state.clear()
            state.update(next_state)
            return state
        handler = EVENT_HANDLERS[card_id]
        handler.apply(state, None)
        return state
    player["discard"].append(card_id)
    if mode == "RP":
        for nation, points in card["rp"].items():
            if nation in state["war_nations"] and not state["war_nations"][nation]:
                continue
            player["replacement_points"][nation] = player["replacement_points"].get(nation, 0) + points
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
    elif mode == "OPS":
        from .ops import legal_ops_actions

        state["ops_remaining"] = card["ops"]
        state["activated"] = {"MOVE": [], "ATTACK": []}
        state["phase"] = "OPS"
        state["decision"] = {"kind": "OPS", "actor": side, "options": []}
        state["decision"]["options"] = legal_ops_actions(state)
    elif mode == "SR":
        state["sr_remaining"] = card["sr"]
        state["phase"] = "SR"
        state["decision"] = {"kind": "SR", "actor": side, "options": []}
    return state


def _apply_card(state: FullGameState, action: Action, random_input: object | None) -> None:
    play_card(state, action["card_id"], action["mode"])


def draw_to_hand(state: FullGameState, side: str) -> FullGameState:
    next_state = deepcopy(state)
    player = next_state["players"][side]
    if player.get("shuffle_pending"):
        player["deck"].extend(player["discard"])
        player["discard"] = []
        player["deck"], next_state["rng_state"] = shuffle_with_state(player["deck"], next_state["rng_state"])
        player["shuffle_pending"] = False
    while len(player["hand"]) < next_state["hand_size"]:
        if not player["deck"]:
            if not player["discard"]:
                break
            player["deck"], next_state["rng_state"] = shuffle_with_state(player["discard"], next_state["rng_state"])
            player["discard"] = []
        player["hand"].append(player["deck"].pop())
    return next_state


def discard_combat_cards(state: FullGameState, side: str, card_ids: list[str]) -> FullGameState:
    player = state["players"][side]
    cards = load_data().cards
    if len(card_ids) != len(set(card_ids)) or any(
        card_id not in player["hand"] or not cards[card_id]["combat_card"] for card_id in card_ids
    ):
        raise IllegalActionError("버릴 수 없는 전투 카드가 포함되었습니다")
    next_state = deepcopy(state)
    for card_id in card_ids:
        next_state["players"][side]["hand"].remove(card_id)
        next_state["players"][side]["discard"].append(card_id)
    return next_state


register_decision_handler("ACTION_PHASE", _apply_card)
