"""Historical 캠페인의 모든 초기 규칙 상태."""

from pog_engine.data import load_data
from pog_engine.model import FullGameState
from pog_engine.randomness import shuffle_with_state


def _side_cards(data, side: str, seed: int) -> tuple[dict, int]:
    cards = [card for card in data.cards.values() if card["side"] == side]
    deck = [card["id"] for card in cards if card["commitment"] == "MOBILIZATION"]
    set_aside = [card["id"] for card in cards if card["commitment"] != "MOBILIZATION"]
    hand = ["GUNS_OF_AUGUST"] if side == "CP" else []
    if hand:
        deck.remove(hand[0])
    deck, seed = shuffle_with_state(deck, seed)
    while len(hand) < 8:
        hand.append(deck.pop())
    return {
        "hand": hand,
        "deck": deck,
        "discard": [],
        "removed": [],
        "set_aside": set_aside,
        "commitment": "MOBILIZATION",
        "war_status": 0,
        "mandatory_offensive": None,
        "replacement_points": {},
        "actions_taken": 0,
        "last_action_mode": None,
        "shuffle_pending": False,
    }, seed


def create_game(scenario: str = "HISTORICAL", seed: int = 0) -> FullGameState:
    if scenario != "HISTORICAL":
        raise ValueError(f"지원하지 않는 시나리오: {scenario}")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("시드는 0 이상의 정수여야 합니다")
    data = load_data()
    initial = data.historical
    rng_state = seed & 0xFFFFFFFF or 0x6D2B79F5
    ap, rng_state = _side_cards(data, "AP", rng_state)
    cp, rng_state = _side_cards(data, "CP", rng_state)

    units = {
        unit_id: {"location": None, "reduced": False, "eliminated": False, "permanent": False}
        for unit_id in data.units
    }
    for placement in initial["placements"]:
        unit = units[placement["unit_id"]]
        unit["location"] = placement["space_id"]
        unit["reduced"] = placement["reduced"]
    for reserve in initial["reserve_corps"]:
        for unit_id in reserve["unit_ids"]:
            units[unit_id]["location"] = reserve["space_id"]

    excluded = set(initial["vp_excluded"])
    included = set(initial["vp_included"])
    spaces = {
        space_id: {
            "control": space["side"],
            "trenches": {"AP": 0, "CP": 0},
            "fort_destroyed": False,
            "fort_besieged": False,
            "vp": space_id in included or (space["vp"] and space_id not in excluded),
        }
        for space_id, space in data.spaces.items()
    }
    for trench in initial["trenches"]:
        spaces[trench["space_id"]]["trenches"][trench["side"]] = trench["level"]

    decision = {
        "kind": "MANDATORY_OFFENSIVE_ROLL",
        "actor": "CHANCE",
        "purpose": "AP_MANDATORY_OFFENSIVE",
        "options": [
            {"type": "RECORD_DIE_RESULT", "actor": "CHANCE", "purpose": "AP_MANDATORY_OFFENSIVE", "value": value}
            for value in range(1, 7)
        ],
    }
    return {
        "schema_version": 1,
        "scenario": scenario,
        "data_version": "2022_DELUXE_HISTORICAL_1",
        "seed": seed,
        "rng_state": rng_state,
        "turn": initial["turn"],
        "action_round": 1,
        "phase": "MANDATORY_OFFENSIVE",
        "active_side": "CHANCE",
        "decision": decision,
        "vp": initial["vp"],
        "hand_size": initial["hand_size"],
        "players": {"AP": ap, "CP": cp},
        "units": units,
        "spaces": spaces,
        "war_nations": {nation: False for nation in ("IT", "TU", "BU", "US", "RO", "GR")},
        "us_entry": 0,
        "russian_capitulation": 0,
        "events": {},
        "temporary_effects": {},
        "flags": {"mef_beachhead": "MEF1", "mef_beachhead_captured": False},
        "combat_context": None,
        "activated": {"MOVE": [], "ATTACK": []},
        "ops_remaining": 0,
        "result": None,
    }
