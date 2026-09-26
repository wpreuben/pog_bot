"""진영별 공개 상태 투영."""

from copy import deepcopy

from .model import FullGameState


def get_player_view(state: FullGameState, side: str) -> dict:
    if side not in {"AP", "CP"}:
        raise ValueError("플레이어 진영은 AP 또는 CP여야 합니다")
    public_keys = (
        "schema_version", "scenario", "data_version", "turn", "action_round", "phase",
        "active_side", "vp", "hand_size", "units", "spaces", "war_nations", "us_entry",
        "russian_capitulation", "events", "combat_context", "activated", "ops_remaining", "result",
    )
    view = {key: deepcopy(state[key]) for key in public_keys if key in state}
    view["players"] = {}
    for player_side in ("AP", "CP"):
        player = state["players"][player_side]
        visible = {key: deepcopy(player[key]) for key in (
            "commitment", "war_status", "mandatory_offensive", "replacement_points",
            "actions_taken", "last_action_mode", "discard", "removed", "in_play",
        ) if key in player}
        visible["hand_count"] = len(player["hand"])
        visible["deck_count"] = len(player["deck"])
        if player_side == side:
            visible["hand"] = deepcopy(player["hand"])
        view["players"][player_side] = visible
    decision = state.get("decision")
    view["decision"] = deepcopy(decision) if decision and decision["actor"] == side else None
    reveal = state.get("temporary_effects", {}).get("revealed_hand")
    if reveal and reveal["viewer"] == side:
        view["revealed_hand"] = deepcopy(reveal["cards"])
    return view
