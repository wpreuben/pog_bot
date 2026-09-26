"""남은 기본 작전 이벤트와 지속 표식."""

from pog_engine.data import load_data
from pog_engine.model import Action, FullGameState


EVENT_OPS = {
    "CLOAK_AND_DAGGER", "LANDSHIPS", "YANKS_AND_TANKS", "KERENSKY_OFFENSIVE",
    "BRUSILOV_OFFENSIVE", "MATA_HARI",
}
ACTION_EFFECTS = {"YANKS_AND_TANKS", "KERENSKY_OFFENSIVE", "BRUSILOV_OFFENSIVE"}


class MiscEventHandler:
    def can_play(self, state: FullGameState, card_id: str) -> bool:
        events = state["events"]
        if card_id == "MOLTKE":
            return state["turn"] <= 2
        if card_id == "HOFFMANN":
            return bool(events.get("H_L_TAKE_COMMAND"))
        if card_id == "KERENSKY_OFFENSIVE":
            return bool(events.get("FALL_OF_THE_TSAR")) and not events.get("BOLSHEVIK_REVOLUTION")
        if card_id == "EVERYONE_INTO_BATTLE":
            return any(events.get(name) for name in ("MICHAEL", "BLUCHER", "PEACE_OFFENSIVE"))
        return True

    def legal_choices(self, state: FullGameState) -> list[Action]:
        return []

    def apply(self, state: FullGameState, choice: Action | None) -> FullGameState:
        side = state["active_side"]
        card_id = state["players"][side]["removed"][-1]
        state["events"][card_id] = state["turn"]
        if card_id in ACTION_EFFECTS:
            state["temporary_effects"][card_id] = state["turn"]
        if card_id in {"CLOAK_AND_DAGGER", "MATA_HARI"}:
            enemy = "CP" if side == "AP" else "AP"
            state["temporary_effects"]["revealed_hand"] = {
                "viewer": side, "owner": enemy, "cards": list(state["players"][enemy]["hand"])
            }
        if card_id in EVENT_OPS:
            from pog_engine.rules.cards import begin_ops

            return begin_ops(state, load_data().cards[card_id]["ops"])
        from pog_engine.rules.turn import complete_action

        state["phase"] = "ACTION"
        next_state = complete_action(state)
        state.clear()
        state.update(next_state)
        return state


_HANDLER = MiscEventHandler()


def register_misc_events(registry: dict[str, object]) -> None:
    for card_id in (
        "MOLTKE", "CLOAK_AND_DAGGER", "GREAT_RETREAT", "LANDSHIPS",
        "YANKS_AND_TANKS", "KERENSKY_OFFENSIVE", "BRUSILOV_OFFENSIVE",
        "SINAI_PIPELINE", "EVERYONE_INTO_BATTLE", "RACE_TO_THE_SEA",
        "SUD_ARMY", "OBEROST", "MATA_HARI", "11TH_ARMY", "HOFFMANN",
    ):
        registry[card_id] = _HANDLER
