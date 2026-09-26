"""첫 행동과 중립국 참전 카드."""

from pog_engine.data import load_data
from pog_engine.engine import register_decision_handler
from pog_engine.model import Action, FullGameState, IllegalActionError


ENTRY_NATIONS = {"ITALY": "IT", "ROMANIA": "RO", "BULGARIA": "BU", "GREECE": "GR"}


def _end_event(state: FullGameState) -> FullGameState:
    from pog_engine.rules.turn import complete_action

    state["phase"] = "ACTION"
    next_state = complete_action(state)
    state.clear()
    state.update(next_state)
    return state


class GunsOfAugustHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        return state["turn"] == 1 and state["action_round"] == 1 and state["active_side"] == "CP"

    def legal_choices(self, state: FullGameState) -> list[Action]:
        return []

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        state["events"]["GUNS_OF_AUGUST"] = state["turn"]
        state["spaces"]["LIEGE"]["fort_destroyed"] = True
        state["spaces"]["LIEGE"]["control"] = "CP"
        for unit_id in ("GE_1_ARMY_1", "GE_2_ARMY_1"):
            state["units"][unit_id]["location"] = "LIEGE"
        state["activated"] = {"MOVE": [], "ATTACK": ["LIEGE", "KOBLENZ"]}
        state["activated_oos"] = []
        state["attacked_units"] = []
        state["attacked_spaces"] = []
        state["phase"] = "COMBAT"
        from pog_engine.rules.combat import legal_combat_actions

        state["decision"] = {"kind": "COMBAT", "actor": "CP", "options": []}
        state["decision"]["options"] = legal_combat_actions(state)
        return state


class NeutralEntryHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        nation = ENTRY_NATIONS[card_id]
        if state["war_nations"][nation] or state["flags"].get("neutral_entry_turn") == state["turn"]:
            return False
        if nation == "RO" and state["events"].get("FALL_OF_THE_TSAR"):
            return False
        if nation in {"RO", "BU"}:
            occupied = {unit["location"] for unit in state["units"].values() if unit["location"]}
            open_spaces = sum(static["nation"] == nation and static["kind"] == "BOARD"
                              and place not in occupied for place, static in load_data().spaces.items())
            if open_spaces < 4:
                return False
        return True

    def legal_choices(self, state: FullGameState) -> list[Action]:
        pending = state["neutral_entry"]["pending"]
        if not pending:
            return []
        nation = state["neutral_entry"]["nation"]
        occupied = {unit["location"] for unit in state["units"].values() if unit["location"]}
        options = [place for place, static in load_data().spaces.items()
                   if static["nation"] == nation and static["kind"] == "BOARD" and place not in occupied]
        return [{"type": "PLACE_NEUTRAL", "actor": state["active_side"],
                 "unit_id": pending[0], "to": place} for place in sorted(options)]

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        if choice is None:
            card_id = state["players"][state["active_side"]]["removed"][-1]
            nation = ENTRY_NATIONS[card_id]
            state["war_nations"][nation] = True
            state["events"][card_id] = state["turn"]
            state["flags"]["neutral_entry_turn"] = state["turn"]
            if nation == "GR":
                if not state["events"].get("SALONIKA"):
                    units = sorted(uid for uid, static in load_data().units.items() if static["nation"] == "GR")
                    for unit_id, place in zip(units, ("ATHENS", "FLORINA", "LARISA")):
                        state["units"][unit_id]["location"] = place
                return _end_event(state)
            if nation == "IT":
                return _end_event(state)
            units = sorted(uid for uid, static in load_data().units.items()
                           if static["nation"] == nation and state["units"][uid]["location"] is None)
            state["neutral_entry"] = {"nation": nation, "pending": units[:4]}
            state["phase"] = "NEUTRAL_ENTRY"
        else:
            if choice not in self.legal_choices(state):
                raise IllegalActionError("중립국 배치 공간이 잘못되었습니다")
            unit_id, place = choice["unit_id"], choice["to"]
            state["units"][unit_id]["location"] = place
            state["neutral_entry"]["pending"].pop(0)
            if not state["neutral_entry"]["pending"]:
                del state["neutral_entry"]
                return _end_event(state)
        state["decision"] = {"kind": "NEUTRAL_ENTRY", "actor": state["active_side"],
                             "options": self.legal_choices(state)}
        return state


_NEUTRAL = NeutralEntryHandler()


def _apply_neutral(state: FullGameState, action: Action, random_input: object | None) -> None:
    _NEUTRAL.apply(state, action)


register_decision_handler("NEUTRAL_ENTRY", _apply_neutral)


def register_entry_events(registry: dict[str, object]) -> None:
    registry["GUNS_OF_AUGUST"] = GunsOfAugustHandler()
    for card_id in ENTRY_NATIONS:
        registry[card_id] = _NEUTRAL
