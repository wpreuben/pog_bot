"""의무 공세의 주사위 표와 국가별 예외."""

from copy import deepcopy

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
    if result == "GE" and (_all_capitals_occupied(state, "GE") or state["events"].get("H_L_TAKE_COMMAND")):
        return None
    return result


def apply_vp_change(state: dict, amount: int, reason: str) -> dict:
    """승점 변경을 기록한다. 자동 승리는 전쟁 상태 단계에서만 검사한다."""
    if not isinstance(amount, int) or isinstance(amount, bool) or not reason:
        raise ValueError("승점 변경 수치와 사유가 필요합니다")
    result = deepcopy(state)
    result["vp"] += amount
    result["flags"].setdefault("vp_history", []).append(
        {"turn": result["turn"], "amount": amount, "reason": reason}
    )
    return result


def satisfies_mandatory_offensive(
    state: dict, side: str, attacker_ids: list[str], defender_ids: list[str], defender_space: str
) -> bool:
    """12절의 실제 적 유닛 공격이 7.1 의무 공세를 만족하는지 확인한다."""
    mo = state["players"][side]["mandatory_offensive"]
    if mo is None or not defender_ids:
        return False
    data = load_data()
    nation = "AH" if mo == "AH_IT" else mo
    if not any(data.units[unit_id]["nation"] == nation for unit_id in attacker_ids):
        return False
    defender_nations = {data.units[unit_id]["nation"] for unit_id in defender_ids}
    location = data.spaces[defender_space]["nation"]
    if nation in {"FR", "BR", "GE"} and location not in {"FR", "BE", "GE"}:
        return False
    if nation in {"FR", "BR"} and "GE" not in defender_nations:
        return False
    if nation == "GE" and not defender_nations.intersection({"BE", "FR", "BR", "US"}):
        return False
    if mo == "AH_IT" and location != "IT" and "IT" not in defender_nations:
        return False
    return True


def _russian_vp_spaces(state: dict) -> list[str]:
    data = load_data()
    return [space_id for space_id, dynamic in state["spaces"].items()
            if dynamic["vp"] and data.spaces[space_id]["nation"] == "RU"]


def update_entry_markers(state: dict) -> None:
    """전쟁 상태와 러시아 점령에 따른 이벤트 선행 조건을 갱신한다."""
    combined = sum(state["players"][side]["war_status"] for side in ("AP", "CP"))
    if state["events"].get("OVER_THERE"):
        state["us_entry"] = 3
    elif state["events"].get("ZIMMERMANN_TELEGRAM"):
        state["us_entry"] = 2
    elif combined >= 30:
        state["us_entry"] = max(1, state["us_entry"])
    state["war_nations"]["US"] = state["us_entry"] >= 2

    russian = _russian_vp_spaces(state)
    controlled = sum(state["spaces"][space_id]["control"] == "CP" for space_id in russian)
    marker = state["russian_capitulation"]
    events = state["events"]
    if events.get("TREATY_OF_BREST_LITOVSK"):
        marker = 7
    elif events.get("BOLSHEVIK_REVOLUTION"):
        marker = 6
    elif events.get("FALL_OF_THE_TSAR"):
        snapshot = state["flags"].setdefault("tsar_fell_russian_vp", controlled)
        all_seven = all(state["spaces"][space_id]["control"] == "CP" for space_id in (
            "RIGA", "KOVNO", "VILNA", "WARSAW", "LODZ", "KIEV", "ODESSA"
        ))
        marker = 5 if controlled > snapshot or all_seven else 4
    elif events.get("TSAR_TAKES_COMMAND"):
        marker = 3 if combined + controlled >= 33 else 2
    else:
        marker = 1 if controlled >= 3 else 0
    state["russian_capitulation"] = marker


def _advance_commitment(state: dict, side: str, commitment: str) -> None:
    player = state["players"][side]
    player["commitment"] = commitment
    cards = load_data().cards
    entering = [card_id for card_id in player["set_aside"]
                if cards[card_id]["commitment"] == commitment]
    player["set_aside"] = [card_id for card_id in player["set_aside"] if card_id not in entering]
    player["deck"].extend(entering)
    player["shuffle_pending"] = True
    if side == "CP" and commitment == "LIMITED":
        state["war_nations"]["TU"] = True
    if side == "CP" and commitment == "TOTAL":
        state["flags"]["cp_first_total_war_turn"] = state["turn"]


def resolve_war_status(state: dict) -> dict:
    if state["phase"] != "WAR_STATUS":
        raise ValueError("전쟁 상태 단계가 아닙니다")
    result = deepcopy(state)
    if result["events"].get("BLOCKADE") and result["turn"] % 4 == 0:
        result = apply_vp_change(result, -1, "BLOCKADE")
    if result["players"]["AP"]["mandatory_offensive"]:
        if not (result["events"].get("FRENCH_MUTINY") and
                result["players"]["AP"]["mandatory_offensive"] == "FR"):
            result = apply_vp_change(result, 1, "AP_MANDATORY_OFFENSIVE")
    if result["players"]["CP"]["mandatory_offensive"]:
        result = apply_vp_change(result, -1, "CP_MANDATORY_OFFENSIVE")
    if not result["war_nations"]["IT"] and result["players"]["AP"]["commitment"] == "TOTAL":
        result = apply_vp_change(result, 1, "ITALIAN_NEUTRALITY")
    for side in ("AP", "CP"):
        result["players"][side]["mandatory_offensive"] = None
    update_entry_markers(result)
    from .victory import finish_game, game_result

    victory = game_result(result)
    if victory is not None:
        return finish_game(result, victory)
    if result["turn"] >= 2:
        for side in ("AP", "CP"):
            player = result["players"][side]
            if player["commitment"] == "MOBILIZATION" and player["war_status"] >= 4:
                _advance_commitment(result, side, "LIMITED")
            if player["commitment"] == "LIMITED" and player["war_status"] >= 11:
                _advance_commitment(result, side, "TOTAL")
    return result
