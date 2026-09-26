"""기본 전투 카드 27장의 사용 조건과 전투 중 효과."""

from pog_engine.data import load_data
from pog_engine.model import Action, FullGameState


TRENCH_CARDS = {"VON_BELOW", "VON_HUTIER", "MICHAEL", "BLUCHER", "PEACE_OFFENSIVE", "ROYAL_TANK_CORPS"}
SINGLE_COMBAT_CARDS = {"MINE_ATTACK", "KEMAL", "ROYAL_TANK_CORPS"}


def _nations(state: FullGameState, unit_ids: list[str]) -> set[str]:
    data = load_data()
    return {data.units[uid]["nation"] for uid in unit_ids if state["units"][uid]["location"] is not None}


def _season(state: FullGameState) -> str | None:
    if state["turn"] <= 2:
        return None
    return {0: "WINTER", 1: "SPRING", 2: "SUMMER", 3: "FALL"}[state["turn"] % 4]


def combat_card_eligible(state: FullGameState, card_id: str, stage: str) -> bool:
    context = state["combat_context"]
    if context is None or not load_data().cards[card_id]["combat_card"]:
        return False
    card_side = load_data().cards[card_id]["side"]
    attacker = context["attacker"]
    defender = context["defender"]
    if stage == "TRENCH_CARDS":
        if card_id not in TRENCH_CARDS or card_side != attacker:
            return False
    elif stage == "FLANK":
        if card_id != "WIRELESS_INTERCEPTS" or card_side != attacker:
            return False
    elif stage == "ATTACKER_CARDS":
        if card_side != attacker or card_id in TRENCH_CARDS | {"WIRELESS_INTERCEPTS"}:
            return False
    elif stage == "DEFENDER_CARDS":
        if card_side != defender or card_id in TRENCH_CARDS | {"WIRELESS_INTERCEPTS"}:
            return False
    else:
        return False
    if card_id in context["cards"][card_side]:
        return False
    data = load_data()
    attackers = _nations(state, context["attackers"])
    defenders = _nations(state, context["defending_units"])
    place = context["defender_space"]
    static = data.spaces[place]
    events = state["events"]
    if card_id == "WIRELESS_INTERCEPTS":
        from pog_engine.rules.combat import flank_modifier

        sources = {state["units"][uid]["location"] for uid in context["attackers"]}
        possible_flank = any(flank_modifier(state, {**context, "pinning_space": source}) is not None
                             for source in sources)
        return attacker == "CP" and "GE" in attackers and "RU" in defenders and possible_flank
    if card_id in {"PLEVE", "PUTNIK", "LIMAN_VON_SANDERS"}:
        if card_id == "PUTNIK" and state["turn"] > 7:
            return False
        nation = {"PLEVE": "RU", "PUTNIK": "SB", "LIMAN_VON_SANDERS": "TU"}[card_id]
        return nation in (attackers if card_side == attacker else defenders)
    if card_id == "WITHDRAWAL":
        return card_side == defender
    if card_id in {"SEVERE_WEATHER_AP", "SEVERE_WEATHER_CP"}:
        season = _season(state)
        return card_side == defender and (
            (static["terrain"] == "MOUNTAIN" and season in {"FALL", "WINTER"}) or
            (static["terrain"] == "SWAMP" and season in {"FALL", "SPRING"})
        )
    if card_id in {"HURRICANE_BARRAGE", "MINE_ATTACK"}:
        return attacker == "AP" and "BR" in attackers and (
            card_id != "MINE_ATTACK" or state["spaces"][place]["trenches"]["CP"] > 0)
    if card_id == "AIR_SUPERIORITY_AP":
        return attacker == "AP" and bool(attackers & {"BR", "FR"})
    if card_id == "PHOSGENE_GAS":
        return attacker == "AP" and "FR" in attackers
    if card_id == "THEY_SHALL_NOT_PASS":
        return (defender == "AP" and static["nation"] == "FR" and static["fort"] > 0
                and not state["spaces"][place]["fort_destroyed"] and "FR" in defenders)
    if card_id == "ROYAL_TANK_CORPS":
        return (attacker == "AP" and bool(events.get("LANDSHIPS")) and "BR" in attackers
                and static["nation"] in {"FR", "BE", "GE"} and not static["terrain"])
    if card_id == "VON_FRANCOIS":
        return attacker == "CP" and "GE" in attackers and "RU" in defenders
    if card_id in {"CHLORINE_GAS", "FLAMETHROWERS", "MUSTARD_GAS", "AIR_SUPERIORITY_CP"}:
        return attacker == "CP" and "GE" in attackers
    if card_id == "FORTIFIED_MACHINE_GUNS":
        return defender == "CP" and "GE" in defenders and state["spaces"][place]["trenches"]["CP"] > 0
    if card_id == "PLACE_OF_EXECUTION":
        return (attacker == "CP" and events.get("FALKENHAYN") and not events.get("H_L_TAKE_COMMAND")
                and static["nation"] == "FR" and static["fort"] > 0
                and not state["spaces"][place]["fort_destroyed"])
    if card_id == "ALPENKORPS":
        return attacker == "CP" and any(
            data.units[uid]["nation"] == "GE" and
            (static["terrain"] == "MOUNTAIN" or
             data.spaces[state["units"][uid]["location"]]["terrain"] == "MOUNTAIN")
            for uid in context["attackers"] if state["units"][uid]["location"] is not None)
    if card_id == "KEMAL":
        return defender == "CP" and "TU" in defenders and any(
            data.units[uid]["nation"] == "TU" and data.units[uid]["cf"] > 0
            for uid in context["defending_units"])
    if card_id == "VON_BELOW":
        return attacker == "CP" and "GE" in attackers and defenders == {"IT"} and not context.get("trench_negated")
    if card_id == "VON_HUTIER":
        return attacker == "CP" and "GE" in attackers and "RU" in defenders and not context.get("trench_negated")
    if card_id in {"MICHAEL", "BLUCHER", "PEACE_OFFENSIVE"}:
        return attacker == "CP" and "GE" in attackers and bool(events.get("H_L_TAKE_COMMAND")) and not context.get("trench_negated")
    return False


class CombatEventHandler:
    def __init__(self, card_id: str):
        self.card_id = card_id

    def can_play(self, state: FullGameState, card_id: str) -> bool:
        context = state.get("combat_context")
        return bool(context) and combat_card_eligible(state, card_id, context["stage"])

    def legal_choices(self, state: FullGameState) -> list[Action]:
        return []

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        context = state["combat_context"]
        card_id = self.card_id
        side = load_data().cards[card_id]["side"]
        context.setdefault("drm", {"AP": 0, "CP": 0})
        drm = 0
        if card_id in {"SEVERE_WEATHER_AP", "SEVERE_WEATHER_CP", "PLACE_OF_EXECUTION"}:
            drm = 2
        elif card_id in {
            "PLEVE", "PUTNIK", "HURRICANE_BARRAGE", "AIR_SUPERIORITY_AP", "PHOSGENE_GAS",
            "MINE_ATTACK", "VON_FRANCOIS", "CHLORINE_GAS", "LIMAN_VON_SANDERS",
            "FORTIFIED_MACHINE_GUNS", "FLAMETHROWERS", "ALPENKORPS", "MUSTARD_GAS",
            "AIR_SUPERIORITY_CP", "MICHAEL",
        }:
            drm = 1
        context["drm"][side] += drm
        if card_id in {"VON_BELOW", "VON_HUTIER", "MICHAEL", "BLUCHER", "PEACE_OFFENSIVE"}:
            context["trench_negated"] = True
        if card_id == "ROYAL_TANK_CORPS":
            context["trench_shift_canceled"] = True
        if card_id == "WIRELESS_INTERCEPTS":
            context["flank_success"] = True
            context["fire_order"] = [context["attacker"], context["defender"]]
        if card_id == "WITHDRAWAL":
            context["withdrawal"] = True
        if card_id == "THEY_SHALL_NOT_PASS":
            context["retreat_canceled"] = True
        if card_id == "KEMAL":
            context["defender_army_table"] = True
        if card_id in {"MICHAEL", "BLUCHER", "PEACE_OFFENSIVE"}:
            state["events"][card_id] = state["turn"]
            state["flags"]["lloyd_george_canceled"] = True
        return state


COMBAT_HANDLERS = {
    card_id: CombatEventHandler(card_id)
    for card_id, card in load_data().cards.items() if card["combat_card"]
}


def register_combat_events(registry: dict[str, object]) -> None:
    registry.update(COMBAT_HANDLERS)
