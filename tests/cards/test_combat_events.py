import pytest

from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.data import load_data
from pog_engine.rules.cards import EVENT_HANDLERS
from pog_engine.rules.combat import combat_snapshot, fire_column, legal_combat_actions
from pog_engine.rules.combat import _valid_group
from pog_engine.rules.events.combat import combat_card_eligible


COMBAT_CARDS = [card_id for card_id, card in load_data().cards.items() if card["combat_card"]]


def combat_state(attacker="CP", defender_space="LIEGE", attacker_ids=("GE_1_ARMY_1",),
                 defender_ids=("BE_1_ARMY_1",)):
    state = create_game(seed=4)
    state["phase"] = "COMBAT"
    state["active_side"] = attacker
    state["turn"] = 4
    for uid in attacker_ids:
        state["units"][uid]["location"] = "AACHEN"
    for uid in defender_ids:
        state["units"][uid]["location"] = defender_space
    state["combat_context"] = {
        "attacker": attacker, "defender": "AP" if attacker == "CP" else "CP",
        "attackers": list(attacker_ids), "defender_space": defender_space,
        "defending_units": list(defender_ids), "stage": "ATTACKER_CARDS",
        "cards": {"AP": [], "CP": []}, "results": {}, "rolls": {},
        "fire_order": [attacker, "AP" if attacker == "CP" else "CP"], "fire_index": 0,
        "loss_queue": [], "loss_side": None, "loss_remaining": 0, "advanced": [],
    }
    state["attacked_units"] = []
    state["attacked_spaces"] = []
    state["decision"] = {"kind": "COMBAT", "actor": attacker, "options": []}
    return state


@pytest.mark.parametrize("card_id", COMBAT_CARDS)
def test_all_27_combat_cards_registered(card_id):
    assert card_id in EVENT_HANDLERS
    assert hasattr(EVENT_HANDLERS[card_id], "can_play")


def test_combat_event_adds_its_war_status_when_played():
    state = combat_state(defender_space="VERDUN", defender_ids=("FR_1_ARMY_1",))
    state["events"]["FALKENHAYN"] = 1
    state["players"]["CP"]["hand"].append("PLACE_OF_EXECUTION")
    state["decision"]["options"] = legal_combat_actions(state)
    before = state["players"]["CP"]["war_status"]
    action = {"type": "PLAY_COMBAT_CARD", "actor": "CP", "card_id": "PLACE_OF_EXECUTION"}
    assert action in generate_legal_actions(state)
    state = apply_action(state, action).state
    assert state["players"]["CP"]["war_status"] == before + 1


def test_nationality_and_side_requirements_limit_combat_cards():
    state = combat_state()
    assert not combat_card_eligible(state, "VON_FRANCOIS", "ATTACKER_CARDS")
    state["units"]["RU_1_ARMY_1"]["location"] = "LIEGE"
    state["combat_context"]["defending_units"].append("RU_1_ARMY_1")
    assert combat_card_eligible(state, "VON_FRANCOIS", "ATTACKER_CARDS")
    assert not combat_card_eligible(state, "CHLORINE_GAS", "DEFENDER_CARDS")
    assert not combat_card_eligible(state, "PUTNIK", "DEFENDER_CARDS")


def test_putnik_expires_after_turn_seven():
    state = combat_state(attacker="CP", defender_ids=("SB_1_ARMY_1",))
    state["combat_context"]["stage"] = "DEFENDER_CARDS"
    state["turn"] = 7
    assert combat_card_eligible(state, "PUTNIK", "DEFENDER_CARDS")
    state["turn"] = 8
    assert not combat_card_eligible(state, "PUTNIK", "DEFENDER_CARDS")


def test_combat_card_drm_modifies_actual_crt_die():
    state = combat_state()
    state["players"]["CP"]["hand"].append("CHLORINE_GAS")
    state["decision"]["options"] = legal_combat_actions(state)
    play = {"type": "PLAY_COMBAT_CARD", "actor": "CP", "card_id": "CHLORINE_GAS"}
    assert play in generate_legal_actions(state)
    state = apply_action(state, play).state
    assert state["combat_context"]["drm"]["CP"] == 1
    state = apply_action(state, {"type": "PASS_COMBAT_CARDS", "actor": "CP"}).state
    state = apply_action(state, {"type": "PASS_COMBAT_CARDS", "actor": "AP"}).state
    column = fire_column(combat_snapshot(state, state["combat_context"]), "CP")
    from pog_engine.rules.combat import crt_result

    expected = crt_result("ARMY", column, 4)
    state = apply_action(state, {"type": "RECORD_COMBAT_DIE", "actor": "CHANCE", "side": "CP", "value": 3}).state
    assert state["combat_context"]["results"]["CP"] == expected


def test_wireless_intercepts_makes_russian_flank_automatic():
    state = combat_state(attacker_ids=("GE_1_ARMY_1", "GE_2_ARMY_1"),
                         defender_ids=("RU_1_ARMY_1",))
    state["units"]["GE_2_ARMY_1"]["location"] = "KOBLENZ"
    state["combat_context"]["stage"] = "FLANK"
    state["players"]["CP"]["hand"].append("WIRELESS_INTERCEPTS")
    state["decision"]["options"] = legal_combat_actions(state)
    action = {"type": "PLAY_COMBAT_CARD", "actor": "CP", "card_id": "WIRELESS_INTERCEPTS"}
    assert action in generate_legal_actions(state)
    state = apply_action(state, action).state
    assert state["combat_context"]["flank_success"]
    assert state["combat_context"]["stage"] == "ATTACKER_CARDS"


def test_wireless_intercepts_requires_a_real_flank():
    state = combat_state(defender_ids=("RU_1_ARMY_1",))
    state["combat_context"]["stage"] = "FLANK"
    assert not combat_card_eligible(state, "WIRELESS_INTERCEPTS", "FLANK")


def test_trench_cancel_card_plays_before_flank():
    state = combat_state(defender_ids=("IT_1_ARMY_1",))
    state["combat_context"]["stage"] = "TRENCH_CARDS"
    state["players"]["CP"]["hand"].append("VON_BELOW")
    state["spaces"]["LIEGE"]["trenches"]["AP"] = 2
    state["decision"]["options"] = legal_combat_actions(state)
    play = {"type": "PLAY_COMBAT_CARD", "actor": "CP", "card_id": "VON_BELOW"}
    assert play in generate_legal_actions(state)
    state = apply_action(state, play).state
    assert state["combat_context"]["trench_negated"]
    snapshot = combat_snapshot(state, state["combat_context"])
    assert snapshot["shifts"]["CP"] == 0


def test_weather_card_requires_matching_season_and_terrain():
    state = combat_state(attacker="AP", attacker_ids=("FR_1_ARMY_1",), defender_ids=("GE_1_ARMY_1",))
    state["turn"] = 4  # Winter
    state["combat_context"]["stage"] = "DEFENDER_CARDS"
    assert not combat_card_eligible(state, "SEVERE_WEATHER_CP", "DEFENDER_CARDS")
    original = load_data().spaces["LIEGE"]["terrain"]
    try:
        load_data().spaces["LIEGE"]["terrain"] = "MOUNTAIN"
        assert combat_card_eligible(state, "SEVERE_WEATHER_CP", "DEFENDER_CARDS")
    finally:
        load_data().spaces["LIEGE"]["terrain"] = original


def test_starred_card_removed_after_combat_and_single_use_card_discarded():
    from pog_engine.rules.combat import _finish_combat

    state = combat_state()
    state["combat_context"]["cards"]["CP"] = ["CHLORINE_GAS", "KEMAL"]
    state["combat_context"]["results"] = {"CP": 3, "AP": 1}
    _finish_combat(state)
    assert "CHLORINE_GAS" in state["players"]["CP"]["removed"]
    assert "KEMAL" in state["players"]["CP"]["discard"]


def test_withdrawal_forces_only_one_retreat_space_even_when_losses_differ_by_two():
    from pog_engine.rules.combat import _after_losses

    state = combat_state(attacker="CP")
    context = state["combat_context"]
    context.update({"withdrawal": True, "results": {"CP": 4, "AP": 1},
                    "fire_order": ["CP", "AP"], "fire_index": 1})
    _after_losses(state)
    assert context["stage"] == "RETREAT"
    assert context["retreat_total"] == 1


def test_retained_combat_card_can_be_used_once_per_round():
    state = combat_state(attacker="CP", defender_ids=("RU_1_ARMY_1",))
    state["players"]["CP"]["in_play"] = ["VON_FRANCOIS"]
    state["decision"]["options"] = legal_combat_actions(state)
    use = {"type": "USE_COMBAT_CARD", "actor": "CP", "card_id": "VON_FRANCOIS"}
    assert use in generate_legal_actions(state)
    state = apply_action(state, use).state
    assert state["combat_context"]["drm"]["CP"] == 1
    state["combat_context"]["cards"]["CP"] = []
    state["decision"]["options"] = legal_combat_actions(state)
    assert use not in generate_legal_actions(state)


def test_they_shall_not_pass_is_retained_on_tie():
    from pog_engine.rules.combat import _finish_combat

    state = combat_state(attacker="CP")
    state["combat_context"]["cards"]["AP"] = ["THEY_SHALL_NOT_PASS"]
    state["combat_context"]["results"] = {"CP": 2, "AP": 2}
    _finish_combat(state)
    assert "THEY_SHALL_NOT_PASS" in state["players"]["AP"]["in_play"]


def test_withdrawal_restores_a_corps_step_before_forced_retreat():
    from pog_engine.rules.combat import _after_losses

    state = combat_state()
    context = state["combat_context"]
    context.update({"withdrawal": True, "results": {"CP": 2, "AP": 1},
                    "fire_index": 1, "loss_history": [{"unit_id": "BEC_CORPS_1",
                    "location": "LIEGE", "was_reduced": False}]})
    state["units"]["BEC_CORPS_1"]["location"] = "LIEGE"
    state["units"]["BEC_CORPS_1"]["reduced"] = True
    _after_losses(state)
    assert context["stage"] == "WITHDRAWAL_NEGATE"
    state["decision"]["actor"] = "AP"
    state["decision"]["options"] = legal_combat_actions(state)
    state = apply_action(state, {"type": "NEGATE_WITHDRAWAL_LOSS", "actor": "AP",
                                 "unit_id": "BEC_CORPS_1"}).state
    assert not state["units"]["BEC_CORPS_1"]["reduced"]
    assert state["combat_context"]["stage"] == "RETREAT"


def test_withdrawal_negates_defender_loss_before_attacker_takes_losses():
    from pog_engine.rules.combat import _after_losses

    state = combat_state()
    context = state["combat_context"]
    context.update({"stage": "LOSSES", "withdrawal": True,
                    "loss_side": "AP", "loss_queue": ["CP"],
                    "results": {"CP": 2, "AP": 1},
                    "loss_history": [{"unit_id": "BE_1_ARMY_1", "location": "LIEGE",
                                      "was_reduced": False}]})
    state["units"]["BE_1_ARMY_1"]["reduced"] = True

    _after_losses(state)

    assert state["combat_context"]["stage"] == "WITHDRAWAL_NEGATE"
    assert state["combat_context"]["loss_queue"] == ["CP"]


def test_flank_defers_withdrawal_until_attacker_losses_are_complete():
    from pog_engine.rules.combat import _after_losses

    state = combat_state()
    state["combat_context"].update({"stage": "LOSSES", "withdrawal": True,
                                    "flank_success": True, "loss_side": "AP",
                                    "loss_queue": ["CP"],
                                    "results": {"CP": 2, "AP": 1},
                                    "loss_history": [{"unit_id": "BE_1_ARMY_1",
                                                      "location": "LIEGE", "was_reduced": False}]})

    _after_losses(state)

    assert state["combat_context"]["stage"] == "LOSSES"
    assert state["combat_context"]["loss_side"] == "CP"


def test_destroyed_defenders_cannot_fire_after_first_strike():
    from pog_engine.rules.combat import _after_losses

    state = combat_state(defender_space="SEDAN", defender_ids=("FR_1_ARMY_1",))
    state["units"]["FR_1_ARMY_1"]["location"] = None
    state["combat_context"].update({"stage": "LOSSES", "loss_side": "AP",
                                    "results": {"CP": 7}, "fire_index": 0,
                                    "loss_queue": []})

    _after_losses(state)

    assert state["combat_context"]["stage"] == "ADVANCE"
    assert state["combat_context"]["results"]["AP"] == 0


def test_withdrawal_requires_retreat_even_after_attackers_are_eliminated():
    from pog_engine.rules.combat import _after_losses

    state = combat_state(attacker_ids=("AHC_CORPS_3",), defender_ids=("RU_8_ARMY_1",))
    state["units"]["AHC_CORPS_3"]["location"] = None
    state["combat_context"].update({"stage": "LOSSES", "loss_side": "CP",
                                    "results": {"CP": 0, "AP": 3}, "fire_index": 1,
                                    "loss_queue": [], "withdrawal": True,
                                    "withdrawal_negated": True})

    _after_losses(state)

    assert state["combat_context"]["stage"] == "RETREAT"
    assert state["combat_context"]["retreat_total"] == 1


def test_lloyd_george_blocks_british_attack_on_german_level_two_trench():
    state = combat_state(attacker="AP", attacker_ids=("BR_1_ARMY_1",),
                         defender_ids=("GE_1_ARMY_1",))
    state["events"]["LLOYD_GEORGE"] = state["turn"]
    state["spaces"]["LIEGE"]["trenches"]["CP"] = 2
    assert not _valid_group(state, ("BR_1_ARMY_1",), "LIEGE")
    state["flags"]["lloyd_george_canceled"] = True
    assert _valid_group(state, ("BR_1_ARMY_1",), "LIEGE")
