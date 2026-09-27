"""전략 카드의 사용 방식과 덱 영역."""

from copy import deepcopy
from collections import Counter

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError, InvalidStateError
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
        late_entry_only = (side == "AP" and card_id in {"ITALY", "ROMANIA"}
                           and state["players"]["CP"]["commitment"] == "TOTAL"
                           and state["players"]["AP"]["commitment"] != "TOTAL")
        if card["ops"] and not late_entry_only:
            modes.append("OPS")
        if card["sr"] and not late_entry_only:
            modes.append("SR")
        if card["rp"] and player.get("last_action_mode") != "RP" and not late_entry_only:
            modes.append("RP")
        handler = EVENT_HANDLERS.get(card_id)
        if handler is not None and not card["combat_card"] and handler.can_play(state, card_id):
            modes.append("EVENT")
        actions.extend({"type": "PLAY_CARD", "actor": side, "card_id": card_id, "mode": mode} for mode in modes)
    return actions + [{"type": "SINGLE_OP", "actor": side}]


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
        handler = EVENT_HANDLERS[card_id]
        handler.apply(state, None)
        return state
    player["discard"].append(card_id)
    if mode == "RP":
        for nation, points in card["rp"].items():
            if nation in state["war_nations"] and not state["war_nations"][nation]:
                continue
            pool = "ALLIED" if nation == "A" else nation
            player["replacement_points"][pool] = player["replacement_points"].get(pool, 0) + points
        if side == "AP" and state["events"].get("OVER_THERE"):
            player["replacement_points"]["US"] = player["replacement_points"].get("US", 0) + 1
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
    elif mode == "OPS":
        begin_ops(state, card["ops"])
    elif mode == "SR":
        from .sr import legal_sr_actions

        state["sr_remaining"] = card["sr"]
        state["sr"] = {"unit": None, "done": [], "near_east_sea_used": False}
        state["phase"] = "SR"
        state["decision"] = {"kind": "SR", "actor": side, "options": []}
        state["decision"]["options"] = legal_sr_actions(state)
    return state


def begin_ops(state: FullGameState, points: int) -> FullGameState:
    """카드 OPS 또는 5.7.4.7의 이벤트 이후 OPS를 연다."""
    from .ops import legal_ops_actions

    state["ops_remaining"] = points
    state["activated"] = {"MOVE": [], "ATTACK": []}
    state["activated_oos"] = []
    state["phase"] = "OPS"
    state["decision"] = {"kind": "OPS", "actor": state["active_side"], "options": []}
    state["decision"]["options"] = legal_ops_actions(state)
    return state


def _apply_card(state: FullGameState, action: Action, random_input: object | None) -> None:
    if action["type"] == "SINGLE_OP":
        state["players"][state["active_side"]]["last_action_mode"] = "OPS"
        begin_ops(state, 1)
    else:
        play_card(state, action["card_id"], action["mode"])


def draw_to_hand(state: FullGameState, side: str) -> FullGameState:
    next_state = deepcopy(state)
    player = next_state["players"][side]
    schedule = next_state.get("flags", {}).get("rtt_replay_draws", {}).get(side, [])
    if schedule and schedule[0]["turn"] == next_state["turn"]:
        observed = schedule.pop(0)
        zones = ("hand", "deck", "discard")
        before_cards = Counter(card for zone in zones for card in player[zone])
        after_cards = Counter(card for zone in zones for card in observed[zone])
        if before_cards != after_cards:
            raise InvalidStateError("RTT 카드 보충 관측에 카드가 누락되거나 추가되었습니다")
        for zone in zones:
            player[zone] = list(observed[zone])
        player["shuffle_pending"] = False
        return next_state
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

from .events.reinforcements import register_reinforcements
from .events.entry import register_entry_events
from .events.politics import register_political_events
from .events.war_status import register_war_status_events
from .events.economy import register_economy_events
from .events.combat import register_combat_events
from .events.operations import register_operational_events
from .events.misc import register_misc_events

register_reinforcements(EVENT_HANDLERS)
register_entry_events(EVENT_HANDLERS)
register_political_events(EVENT_HANDLERS)
register_war_status_events(EVENT_HANDLERS)
register_economy_events(EVENT_HANDLERS)
register_combat_events(EVENT_HANDLERS)
register_operational_events(EVENT_HANDLERS)
register_misc_events(EVENT_HANDLERS)
