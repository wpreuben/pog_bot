"""Historical 캠페인의 종료 사유와 최종 승점 판정."""

from pog_engine.model import FullGameState


def final_vp(state: FullGameState) -> int:
    """5.7.4.8–9를 휴전 또는 최종 턴 판정에만 적용한다."""
    result = state["vp"]
    for card_id in ("USA_REINFORCEMENTS_US_1", "USA_REINFORCEMENTS_US_2"):
        if not state["events"].get(card_id):
            result += 1
    if not state["events"].get("FALL_OF_THE_TSAR"):
        result -= 2
    return result


def game_result(state: FullGameState) -> dict | None:
    """E.2/E.3와 5.5 종료 시점에서만 결과를 돌려준다."""
    if state["result"] is not None:
        return state["result"]
    if state["phase"] == "WAR_STATUS":
        if state["vp"] >= 20:
            return {"winner": "CP", "reason": "AUTOMATIC_VICTORY", "vp": state["vp"]}
        if state["vp"] <= 0:
            return {"winner": "AP", "reason": "AUTOMATIC_VICTORY", "vp": state["vp"]}
        combined = sum(state["players"][side]["war_status"] for side in ("AP", "CP"))
        if combined >= 40:
            reason = "ARMISTICE"
        else:
            return None
    elif state["phase"] == "END_TURN" and state["turn"] >= 20:
        reason = "TURN_LIMIT"
    else:
        return None
    vp = final_vp(state)
    cp_threshold = 11 if state["events"].get("TREATY_OF_BREST_LITOVSK") else 13
    return {"winner": "CP" if vp >= cp_threshold else "AP", "reason": reason, "vp": vp}


def resignation_result(state: FullGameState, side: str) -> dict:
    if side not in {"AP", "CP"}:
        raise ValueError("항복 진영은 AP 또는 CP여야 합니다")
    return {"winner": "AP" if side == "CP" else "CP", "reason": "RESIGN", "vp": state["vp"]}


def finish_game(state: FullGameState, result: dict) -> FullGameState:
    state["result"] = result
    state["phase"] = "GAME_OVER"
    state["decision"] = None
    state["active_side"] = "NONE"
    return state
