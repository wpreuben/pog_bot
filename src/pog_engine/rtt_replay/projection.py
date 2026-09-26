"""RTT와 독립 엔진 상태의 공통 의미 투영."""

from dataclasses import dataclass

from pog_engine.data import load_data
from pog_engine.model import FullGameState

from .ids import SourceIds


@dataclass(frozen=True)
class Difference:
    path: str
    expected: object
    actual: object


def _rtt_trenches(player: dict, ids: SourceIds) -> dict[str, int]:
    flat = player.get("trenches", [])
    return {ids.lookup("spaces", flat[i]): flat[i + 1]
            for i in range(0, len(flat), 2)}


def _rtt_cards(player: dict, ids: SourceIds) -> dict:
    cards = {zone: [ids.lookup("cards", card) for card in player[zone]]
             for zone in ("hand", "deck", "discard", "removed")}
    cards["war_status"] = player["ws"]
    cards["commitment"] = player["commitment"].upper()
    return cards


def project_rtt(state: dict, ids: SourceIds) -> dict:
    ap_trenches = _rtt_trenches(state["ap"], ids)
    cp_trenches = _rtt_trenches(state["cp"], ids)
    reduced = set(state["reduced"])
    removed = set(state["removed"])
    destroyed = set(state["forts"]["destroyed"])
    besieged = set(state["forts"]["besieged"])
    units = {}
    for source_id in range(1, len(state["location"])):
        uid = ids.lookup("units", source_id)
        place = state["location"][source_id]
        place_id = ids.lookup("spaces", place) if place else None
        eliminated = bool(place_id and place_id.endswith("_ELIMINATED_BOX"))
        units[uid] = {
            "location": None if eliminated else place_id,
            "reduced": None if eliminated else source_id in reduced,
            "eliminated": eliminated,
            "permanent": source_id in removed or bool(place_id and "PERMANENTLY_ELIMINATED" in place_id),
        }
    spaces = {}
    board = load_data().spaces
    for source, sid in ids.mappings["spaces"].items():
        if board[sid]["kind"] != "BOARD":
            continue
        number = int(source)
        spaces[sid] = {
            "control": "CP" if (state["control"][number >> 5] >> (number & 31)) & 1 else "AP",
            "trenches": {"AP": ap_trenches.get(sid, 0), "CP": cp_trenches.get(sid, 0)},
            "fort_destroyed": number in destroyed,
            "fort_besieged": number in besieged,
        }
    winner = state.get("result")
    if winner in ("ap", "Allied Powers"):
        winner = "AP"
    elif winner in ("cp", "Central Powers"):
        winner = "CP"
    return {
        "turn": state["turn"], "vp": state["vp"],
        "units": units, "spaces": spaces,
        "players": {"AP": _rtt_cards(state["ap"], ids),
                    "CP": _rtt_cards(state["cp"], ids)},
        "war_nations": {nation.upper(): bool(value) for nation, value in state["war"].items()},
        "result": winner,
    }


def project_engine(state: FullGameState) -> dict:
    return {
        "turn": state["turn"], "vp": state["vp"],
        "units": {uid: {key: (None if key in ("location", "reduced") and unit["eliminated"] else value)
                         for key, value in unit.items()
                         if key in ("location", "reduced", "eliminated", "permanent")}
                  for uid, unit in state["units"].items()},
        "spaces": {sid: {key: value for key, value in space.items()
                          if key in ("control", "trenches", "fort_destroyed", "fort_besieged")}
                   for sid, space in state["spaces"].items()
                   if load_data().spaces[sid]["kind"] == "BOARD"},
        "players": {side: {**{zone: list(state["players"][side][zone])
                             for zone in ("hand", "deck", "discard", "removed")},
                            "war_status": state["players"][side]["war_status"],
                            "commitment": state["players"][side]["commitment"]}
                    for side in ("AP", "CP")},
        "war_nations": dict(state["war_nations"]),
        "result": None if state["result"] is None else state["result"].get("winner"),
    }


def first_difference(expected: object, actual: object, path: str = "$") -> Difference | None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            next_path = f"{path}.{key}"
            if key not in expected or key not in actual:
                return Difference(next_path, expected.get(key, "<missing>"), actual.get(key, "<missing>"))
            difference = first_difference(expected[key], actual[key], next_path)
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        for index in range(max(len(expected), len(actual))):
            next_path = f"{path}[{index}]"
            if index >= len(expected) or index >= len(actual):
                return Difference(next_path,
                                  expected[index] if index < len(expected) else "<missing>",
                                  actual[index] if index < len(actual) else "<missing>")
            difference = first_difference(expected[index], actual[index], next_path)
            if difference is not None:
                return difference
        return None
    if expected != actual:
        return Difference(path, expected, actual)
    return None
