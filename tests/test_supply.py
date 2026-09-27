from pog_engine import create_game
from pog_engine.rules.supply import resolve_attrition, supplied_spaces, supply_status


def test_historical_units_trace_to_correct_friendly_sources():
    state = create_game(seed=4)
    assert supply_status(state, "GE_1_ARMY_1").supplied
    assert supply_status(state, "FR_1_ARMY_1").supplied
    assert "AACHEN" in supplied_spaces(state, "CP")
    assert "LONDON" in supplied_spaces(state, "AP")


def test_enemy_control_and_unit_block_supply_path():
    state = create_game(seed=4)
    state["units"]["GE_1_ARMY_1"]["location"] = "PARIS"
    state["spaces"]["PARIS"]["control"] = "CP"
    assert not supply_status(state, "GE_1_ARMY_1").supplied


def test_besieged_enemy_fort_can_carry_supply_path():
    state = create_game(seed=4)
    state["units"]["GE_1_ARMY_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["fort_besieged"] = True
    assert supply_status(state, "GE_1_ARMY_1").supplied


def test_allied_port_can_trace_to_london_by_sea():
    state = create_game(seed=4)
    state["units"]["BR_BEFC_CORPS_1"]["location"] = "PORT_SAID"
    assert supply_status(state, "BR_BEFC_CORPS_1").supplied


def test_russian_corps_cannot_use_allied_sea_supply():
    state = create_game(seed=4)
    state["units"]["RUC_CORPS_1"]["location"] = "PORT_SAID"
    assert not supply_status(state, "RUC_CORPS_1").supplied


def test_special_always_supplied_units_and_serbia():
    state = create_game(seed=4)
    state["units"]["MNC_CORPS_1"]["location"] = "CETINJE"
    assert supply_status(state, "MNC_CORPS_1").supplied
    state["units"]["SBC_CORPS_1"]["location"] = "BELGRADE"
    assert supply_status(state, "SBC_CORPS_1").supplied


def test_attrition_removes_oos_army_permanently_and_converts_isolated_space():
    state = create_game(seed=4)
    state["units"]["GE_1_ARMY_1"]["location"] = "PARIS"
    state["spaces"]["PARIS"]["control"] = "CP"
    state["spaces"]["PARIS"]["fort_destroyed"] = True
    result = resolve_attrition(state)
    assert result["units"]["GE_1_ARMY_1"]["permanent"]
    assert result["units"]["GE_1_ARMY_1"]["location"] is None
    assert result["spaces"]["PARIS"]["control"] == "AP"
    assert state["units"]["GE_1_ARMY_1"]["location"] == "PARIS"


def test_montenegrin_unit_keeps_cetinje_supplied_during_attrition():
    state = create_game(seed=4)
    state["spaces"]["MOSTAR"]["control"] = "CP"
    state["spaces"]["TIRANA"]["control"] = "CP"
    assert "CETINJE" not in supplied_spaces(state, "AP")
    assert supply_status(state, "MNC_CORPS_1", purpose="ATTRITION").supplied
    result = resolve_attrition(state)
    assert result["spaces"]["CETINJE"]["control"] == "AP"


def test_albanian_spaces_use_valona_and_taranto_supply_exception():
    state = create_game(seed=4)
    for place in ("CETINJE", "SKOPJE", "FLORINA"):
        state["spaces"][place]["control"] = "CP"
    assert "VALONA" in supplied_spaces(state, "AP")
    assert "TIRANA" in supplied_spaces(state, "AP")
    assert resolve_attrition(state)["spaces"]["TIRANA"]["control"] == "AP"
    state["spaces"]["VALONA"]["control"] = "CP"
    assert "TIRANA" not in supplied_spaces(state, "AP")


def test_oos_unit_cannot_move_entrench_or_sr():
    from pog_engine.rules.movement import legal_movement_actions
    from pog_engine.rules.sr import legal_sr_actions
    from pog_engine.rules.trenches import legal_entrench_actions

    state = create_game(seed=4)
    state["units"]["GE_1_ARMY_1"]["location"] = "PARIS"
    state["spaces"]["PARIS"]["control"] = "CP"
    state["phase"] = "MOVEMENT"
    state["active_side"] = "CP"
    state["events"]["ENTRENCH"] = 1
    state["activated"]["MOVE"] = ["PARIS"]
    state["movement"] = {"unit": None, "spent": 0, "done": []}
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in legal_movement_actions(state))
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in legal_entrench_actions(state))
    state["phase"] = "SR"
    state["sr_remaining"] = 4
    state["sr"] = {"unit": None, "done": [], "near_east_sea_used": False}
    assert not any(a.get("unit_id") == "GE_1_ARMY_1" for a in legal_sr_actions(state))


def test_attrition_phase_applies_resolution_before_siege():
    from pog_engine.rules.turn import advance_automatic_phases

    state = create_game(seed=4)
    state["units"]["GE_1_ARMY_1"]["location"] = "PARIS"
    state["spaces"]["PARIS"]["control"] = "CP"
    state["spaces"]["PARIS"]["fort_destroyed"] = True
    state["phase"] = "ATTRITION"
    state["decision"] = None
    result = advance_automatic_phases(state)
    assert result["phase"] == "SIEGE"
    assert result["units"]["GE_1_ARMY_1"]["permanent"]


def test_neutral_nation_units_and_spaces_ignore_attrition():
    state = create_game(seed=4)
    italian = next(uid for uid in state["units"] if uid.startswith("IT_") and state["units"][uid]["location"])
    original_location = state["units"][italian]["location"]
    result = resolve_attrition(state)
    assert result["units"][italian]["location"] == original_location
    assert result["spaces"]["ROME"]["control"] == state["spaces"]["ROME"]["control"]
    assert result["spaces"]["MEF1"]["control"] == state["spaces"]["MEF1"]["control"]


def test_oos_corps_is_eliminated_but_stays_replaceable():
    state = create_game(seed=4)
    state["units"]["GEC_CORPS_1"]["location"] = "PARIS"
    state["spaces"]["PARIS"]["control"] = "CP"
    result = resolve_attrition(state)
    assert result["units"]["GEC_CORPS_1"]["eliminated"]
    assert not result["units"]["GEC_CORPS_1"]["permanent"]


def test_german_corps_supplied_from_constantinople_cannot_sr_to_reserve():
    from pog_engine.rules.sr import legal_sr_actions

    state = create_game(seed=4)
    state["war_nations"]["TU"] = True
    state["units"]["GEC_CORPS_1"]["location"] = "CONSTANTINOPLE"
    assert supply_status(state, "GEC_CORPS_1").supplied
    state["phase"] = "SR"
    state["active_side"] = "CP"
    state["sr_remaining"] = 1
    state["sr"] = {"unit": "GEC_CORPS_1", "done": [], "near_east_sea_used": False}
    assert not any(a.get("to") == "CP_RESERVE_BOX" for a in legal_sr_actions(state))
