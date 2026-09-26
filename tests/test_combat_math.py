from pog_engine import create_game
from pog_engine.rules.combat import (
    combat_snapshot, combat_strength, crt_result, fire_column,
    flank_modifier, legal_attack_declarations,
)


def combat_state():
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = "CP"
    state["activated"]["ATTACK"] = ["AACHEN", "KOBLENZ"]
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    return state


def declarations(state, destination):
    return [a for a in legal_attack_declarations(state) if a["defender_space"] == destination]


def test_crt_boundary_columns_match_printed_tables():
    assert [crt_result("CORPS", 0, die) for die in range(1, 7)] == [0, 0, 0, 0, 1, 1]
    assert [crt_result("ARMY", 16, die) for die in range(1, 7)] == [5, 5, 7, 7, 7, 7]
    assert crt_result("ARMY", 100, 7) == 7
    assert crt_result("CORPS", -5, 0) == 0


def test_fort_and_trench_change_strength_and_fire_column():
    state = combat_state()
    state["units"]["BE_1_ARMY_1"]["location"] = "LIEGE"
    state["spaces"]["LIEGE"]["trenches"]["AP"] = 2
    context = {"attacker": "CP", "attackers": ["GE_1_ARMY_1"], "defender_space": "LIEGE"}
    assert combat_strength(state, context, "CP") == 5
    assert combat_strength(state, context, "AP") == 5
    snapshot = combat_snapshot(state, context)
    assert fire_column(snapshot, "CP") == 3
    assert fire_column(snapshot, "AP") == 6


def test_attack_declaration_allows_two_spaces_and_single_defending_space():
    state = combat_state()
    actions = declarations(state, "LIEGE")
    assert any(set(a["unit_ids"]) == {"GE_1_ARMY_1", "GE_2_ARMY_1"} for a in actions)
    assert all(a["defender_space"] == "LIEGE" for a in actions)
    state["attacked_units"] = ["GE_1_ARMY_1"]
    state["attacked_spaces"] = ["LIEGE"]
    assert not declarations(state, "LIEGE")


def test_multinational_two_space_attack_requires_common_space():
    state = combat_state()
    state["units"]["AH_1_ARMY_1"]["location"] = "AACHEN"
    selected = {"GE_1_ARMY_1", "AH_1_ARMY_1", "GE_2_ARMY_1"}
    assert any(set(a["unit_ids"]) == selected for a in declarations(state, "LIEGE"))
    state["units"]["AH_1_ARMY_1"]["location"] = "KOBLENZ"
    state["units"]["GE_2_ARMY_1"]["location"] = "AACHEN"
    assert not any(set(a["unit_ids"]) == selected for a in declarations(state, "LIEGE"))


def test_flank_modifier_counts_unpinned_approaches():
    state = combat_state()
    state["units"]["BE_1_ARMY_1"]["location"] = "LIEGE"
    context = {
        "attacker": "CP", "attackers": ["GE_1_ARMY_1", "GE_2_ARMY_1"],
        "defender_space": "LIEGE", "pinning_space": "KOBLENZ",
    }
    assert flank_modifier(state, context) == 1
    state["spaces"]["LIEGE"]["trenches"]["AP"] = 1
    assert flank_modifier(state, context) is None


def test_reduced_strength_and_mountain_shift():
    state = combat_state()
    state["units"]["GE_1_ARMY_1"]["reduced"] = True
    state["units"]["BE_1_ARMY_1"]["location"] = "LIEGE"
    context = {"attacker": "CP", "attackers": ["GE_1_ARMY_1"], "defender_space": "LIEGE"}
    state["spaces"]["LIEGE"]["trenches"]["AP"] = 0
    from pog_engine.data import load_data

    data = load_data()
    original = data.spaces["LIEGE"]["terrain"]
    try:
        data.spaces["LIEGE"]["terrain"] = "MOUNTAIN"
        assert combat_strength(state, context, "CP") == 3
        assert fire_column(combat_snapshot(state, context), "CP") == 2
    finally:
        data.spaces["LIEGE"]["terrain"] = original


def test_london_attack_requires_second_space_in_france_or_belgium():
    state = combat_state()
    state["active_side"] = "AP"
    state["activated"]["ATTACK"] = ["LONDON"]
    state["units"]["BR_BEF_ARMY_1"]["location"] = "LONDON"
    state["spaces"]["CALAIS"]["control"] = "CP"
    state["spaces"]["CALAIS"]["fort_destroyed"] = False
    state["units"]["GE_1_ARMY_1"]["location"] = "CALAIS"
    assert not declarations(state, "CALAIS")
