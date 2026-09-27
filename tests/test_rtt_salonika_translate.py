"""Salonika 이벤트의 RTT 화면 선택을 합법 행동에 대응한다."""

from pog_engine import create_game, generate_legal_actions
from pog_engine.rtt_replay.ids import SourceIds
from pog_engine.rtt_replay.normalize import Intent
from pog_engine.rtt_replay.translate import translate_intent
from pog_engine.rules.events.operations import SalonikaHandler


def salonika_state():
    state = create_game(seed=4)
    state["phase"] = "SALONIKA"
    state["active_side"] = "AP"
    state["salonika"] = {"remaining": 3}
    state["decision"] = {"kind": "SALONIKA", "actor": "AP",
                         "options": SalonikaHandler().legal_choices(state)}
    return state


def test_piece_redeploys_observed_corp_to_salonika():
    state = salonika_state()
    before_location = [0] * 151
    before_location[150] = 282  # FRC_CORPS_5 in AP reserve
    after_location = before_location.copy()
    after_location[150] = 117  # Salonika
    intent = Intent(2390, 2390, "Allied Powers", "piece", 150,
                    {"state": "salonika", "location": before_location},
                    {"state": "salonika", "location": after_location}, ())

    actions = translate_intent(state, intent, SourceIds.from_data())
    assert actions == ({"type": "SALONIKA_SR", "actor": "AP", "unit_id": "FRC_CORPS_5"},)
    assert actions[0] in generate_legal_actions(state)


def test_done_finishes_salonika_redeployment():
    state = salonika_state()
    state["units"]["FRC_CORPS_5"]["location"] = "SALONIKA"
    state["salonika"]["remaining"] = 2
    state["decision"]["options"] = SalonikaHandler().legal_choices(state)
    intent = Intent(2391, 2391, "Allied Powers", "done", None,
                    {"state": "salonika"}, {"state": "confirm_event"}, ())

    actions = translate_intent(state, intent, SourceIds.from_data())
    assert actions == ({"type": "END_SALONIKA", "actor": "AP"},)
    assert actions[0] in generate_legal_actions(state)
