"""의무 공세의 주사위 표와 국가별 예외."""

from pog_engine.data import load_data


def _all_capitals_occupied(state: dict, nation: str) -> bool:
    capitals = [
        space for space in load_data().spaces.values()
        if space["nation"] == nation and space["capital"]
    ]
    return bool(capitals) and all(
        state["spaces"][space["id"]]["control"] != space["side"] for space in capitals
    )


def mandatory_offensive(state: dict, side: str, die: int) -> str | None:
    if side not in ("AP", "CP") or not isinstance(die, int) or isinstance(die, bool) or not 1 <= die <= 6:
        raise ValueError("의무 공세 주사위 또는 진영이 잘못되었습니다")

    if side == "AP":
        result = {1: "FR", 2: "FR", 3: "BR", 4: "IT", 5: "IT", 6: "RU"}[die]
        if result == "FR" and _all_capitals_occupied(state, "FR"):
            result = "BR"
        if result == "BR" and _all_capitals_occupied(state, "BR"):
            result = "IT"
        if result == "IT":
            if not state["war_nations"]["IT"]:
                return None
            if _all_capitals_occupied(state, "IT"):
                result = "RU"
        if result == "RU" and (
            _all_capitals_occupied(state, "RU") or state["events"].get("BOLSHEVIK_REVOLUTION")
        ):
            return None
        if state["turn"] == 1 and result == "BR":
            result = "FR"
        return result

    die = min(6, die + int(bool(state["events"].get("HOFFMANN"))))
    result = {1: "AH", 2: "AH_IT", 3: "TU", 4: "GE", 5: None, 6: None}[die]
    if result in ("AH", "AH_IT") and _all_capitals_occupied(state, "AH"):
        result = "TU"
    if result == "AH_IT" and (not state["war_nations"]["IT"] or _all_capitals_occupied(state, "IT")):
        result = "AH"
    if result == "TU":
        if not state["war_nations"]["TU"]:
            return None
        if _all_capitals_occupied(state, "TU"):
            result = "GE"
    if result == "GE" and (_all_capitals_occupied(state, "GE") or state["events"].get("H_L_TAKES_COMMAND")):
        return None
    return result
