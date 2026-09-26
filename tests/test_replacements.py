from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.replacements import (
    _army_spaces, apply_replacement_action, begin_replacement_phase,
    close_replacement_phase, legal_replacement_actions,
)


def test_greece_entry_allows_serbian_army_rebuild_at_allied_salonika():
    state = create_game(seed=4)
    state["events"]["GREECE"] = 3
    state["war_nations"]["GR"] = True
    state["spaces"]["SALONIKA"]["control"] = "AP"
    assert "SALONIKA" in _army_spaces(state, "SB_1_ARMY_1")


def test_public_api_advances_replacement_phases_without_rp():
    state = rp_state("AP")
    state = begin_replacement_phase(state, "AP")
    assert state["decision"] is None
    action = generate_legal_actions(state)[0]
    state = apply_action(state, action).state
    assert state["phase"] == "REPLACEMENT_CP"
    state = apply_action(state, generate_legal_actions(state)[0]).state
    assert state["phase"] == "DRAW"


def rp_state(side="CP"):
    state = create_game(seed=4)
    state["phase"] = f"REPLACEMENT_{side}"
    state["active_side"] = side
    state["decision"] = {"kind": "REPLACEMENT", "actor": side, "options": []}
    return state


def choose(state, action_type, **fields):
    action = next(a for a in generate_legal_actions(state) if a["type"] == action_type and all(a.get(k) == v for k, v in fields.items()))
    return apply_action(state, action).state


def test_allied_rp_card_uses_same_pool_as_minor_nation_units():
    state = create_game(seed=4)
    for value in (1, 5):
        purpose = state["decision"]["purpose"]
        state = apply_action(state, {"type": "RECORD_DIE_RESULT", "actor": "CHANCE", "purpose": purpose, "value": value}).state
    state = apply_action(state, {"type": "PLAY_CARD", "actor": "CP", "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"}).state
    state = apply_action(state, {"type": "END_COMBAT", "actor": "CP"}).state
    state["players"]["AP"]["hand"] = ["BLOCKADE"]
    state["decision"]["options"] = [{"type": "PLAY_CARD", "actor": "AP", "card_id": "BLOCKADE", "mode": "RP"}]
    state = apply_action(state, {"type": "PLAY_CARD", "actor": "AP", "card_id": "BLOCKADE", "mode": "RP"}).state
    assert state["players"]["AP"]["replacement_points"]["ALLIED"] == 1


def test_flip_reduced_army_costs_one_rp():
    state = rp_state()
    state["players"]["CP"]["replacement_points"] = {"GE": 1}
    state["units"]["GE_1_ARMY_1"]["reduced"] = True
    state = begin_replacement_phase(state, "CP")
    assert {"type": "FLIP_UNIT", "actor": "CP", "unit_id": "GE_1_ARMY_1"} in legal_replacement_actions(state, "CP")
    state = choose(state, "FLIP_UNIT", unit_id="GE_1_ARMY_1")
    assert not state["units"]["GE_1_ARMY_1"]["reduced"]
    assert state["players"]["CP"]["replacement_points"]["GE"] == 0


def test_eliminated_corps_rebuilds_reduced_in_reserve_for_half_rp():
    state = rp_state()
    state["players"]["CP"]["replacement_points"] = {"GE": 0.5}
    state["units"]["GEC_CORPS_1"]["location"] = None
    state["units"]["GEC_CORPS_1"]["eliminated"] = True
    state = begin_replacement_phase(state, "CP")
    state = choose(state, "REBUILD_CORPS", unit_id="GEC_CORPS_1")
    assert state["units"]["GEC_CORPS_1"]["location"] == "CP_RESERVE_BOX"
    assert state["units"]["GEC_CORPS_1"]["reduced"]
    assert not state["units"]["GEC_CORPS_1"]["eliminated"]


def test_eliminated_army_rebuilds_reduced_at_supplied_capital():
    state = rp_state("AP")
    state["players"]["AP"]["replacement_points"] = {"FR": 1}
    state["units"]["FR_1_ARMY_1"]["location"] = None
    state["units"]["FR_1_ARMY_1"]["eliminated"] = True
    state = begin_replacement_phase(state, "AP")
    assert any(a["type"] == "REBUILD_ARMY" and a["space_id"] == "PARIS" for a in generate_legal_actions(state))
    state = choose(state, "REBUILD_ARMY", unit_id="FR_1_ARMY_1", space_id="PARIS")
    assert state["units"]["FR_1_ARMY_1"]["location"] == "PARIS"
    assert state["units"]["FR_1_ARMY_1"]["reduced"]


def test_capital_loss_oos_and_permanent_elimination_block_replacements():
    state = rp_state("AP")
    state["players"]["AP"]["replacement_points"] = {"FR": 3}
    state["units"]["FR_1_ARMY_1"]["reduced"] = True
    state["spaces"]["PARIS"]["control"] = "CP"
    state = begin_replacement_phase(state, "AP")
    assert not any(a.get("unit_id") == "FR_1_ARMY_1" for a in generate_legal_actions(state))
    state["spaces"]["PARIS"]["control"] = "AP"
    state["units"]["FR_1_ARMY_1"]["permanent"] = True
    state["decision"]["options"] = legal_replacement_actions(state, "AP")
    assert not any(a.get("unit_id") == "FR_1_ARMY_1" for a in generate_legal_actions(state))


def test_unspent_rps_expire_and_ap_phase_precedes_cp():
    state = rp_state("AP")
    state["players"]["AP"]["replacement_points"] = {"FR": 2}
    state["players"]["CP"]["replacement_points"] = {"GE": 1}
    state = begin_replacement_phase(state, "AP")
    state = choose(state, "END_REPLACEMENT")
    assert state["players"]["AP"]["replacement_points"] == {}
    assert state["phase"] == "REPLACEMENT_CP"
    assert state["decision"]["actor"] == "CP"
    state = choose(state, "END_REPLACEMENT")
    assert state["phase"] == "DRAW"
    assert state["players"]["CP"]["replacement_points"] == {}


def test_historical_sedan_bonus_requires_total_war_and_three_spaces():
    state = rp_state("CP")
    state["players"]["CP"]["commitment"] = "TOTAL"
    for place in ("SEDAN", "LIEGE", "BRUSSELS"):
        state["spaces"][place]["control"] = "CP"
    state = begin_replacement_phase(state, "CP")
    assert state["players"]["CP"]["replacement_points"]["GE"] == 1
    state = begin_replacement_phase(state, "CP")
    assert state["players"]["CP"]["replacement_points"]["GE"] == 1


def test_oos_reduced_unit_and_unreplaceable_unit_have_no_rp_action():
    state = rp_state("AP")
    state["players"]["AP"]["replacement_points"] = {"FR": 2, "BR": 2}
    state["units"]["FR_1_ARMY_1"]["location"] = "ESSEN"
    state["units"]["FR_1_ARMY_1"]["reduced"] = True
    state["units"]["BR_BEF_ARMY_1"]["reduced"] = True
    state = begin_replacement_phase(state, "AP")
    assert not any(a.get("unit_id") in {"FR_1_ARMY_1", "BR_BEF_ARMY_1"} for a in generate_legal_actions(state))


def test_cannot_skip_replacement_decision_with_automatic_phase_advance():
    import pytest
    from pog_engine import InvalidStateError
    from pog_engine.rules.turn import advance_automatic_phases

    state = rp_state("CP")
    state["players"]["CP"]["replacement_points"] = {"GE": 1}
    state = begin_replacement_phase(state, "CP")
    with pytest.raises(InvalidStateError):
        advance_automatic_phases(state)


def test_belgian_army_uses_calais_when_belgian_sites_unavailable():
    state = rp_state("AP")
    state["players"]["AP"]["replacement_points"] = {"ALLIED": 1}
    state["units"]["BE_1_ARMY_1"]["location"] = None
    state["units"]["BE_1_ARMY_1"]["eliminated"] = True
    for place in ("BRUSSELS", "ANTWERP", "OSTEND"):
        state["spaces"][place]["control"] = "CP"
    state = begin_replacement_phase(state, "AP")
    destinations = {a["space_id"] for a in generate_legal_actions(state)
                    if a["type"] == "REBUILD_ARMY" and a["unit_id"] == "BE_1_ARMY_1"}
    assert destinations == {"CALAIS"}


def test_serbian_army_cannot_rebuild_at_belgrade_after_nis_falls():
    state = rp_state("AP")
    state["players"]["AP"]["replacement_points"] = {"ALLIED": 1}
    state["units"]["SB_1_ARMY_1"]["location"] = None
    state["units"]["SB_1_ARMY_1"]["eliminated"] = True
    state["spaces"]["NIS"]["control"] = "CP"
    state = begin_replacement_phase(state, "AP")
    assert not any(a["type"] == "REBUILD_ARMY" and a["unit_id"] == "SB_1_ARMY_1"
                   and a["space_id"] == "BELGRADE" for a in generate_legal_actions(state))
