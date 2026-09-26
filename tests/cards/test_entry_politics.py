import pytest

from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.cards import EVENT_HANDLERS, legal_card_actions
from pog_engine.rules.events.politics import RUSSIAN_VP_SPACES
from pog_engine.rules.war import update_entry_markers
from pog_engine.rules.ops import activation_cost
from pog_engine.rules.movement import _can_enter
from pog_engine.rules.combat import _valid_group
from pog_engine.rules.replacements import legal_replacement_actions, apply_replacement_action


def action_state(side="AP", turn=2):
    state = create_game(seed=4)
    state["turn"] = turn
    state["phase"] = "ACTION"
    state["active_side"] = side
    state["decision"] = {"kind": "ACTION_PHASE", "actor": side, "options": []}
    return state


def with_card(state, card_id):
    state["players"][state["active_side"]]["hand"].append(card_id)
    state["decision"]["options"] = legal_card_actions(state, state["active_side"])
    return state


def play_event(state, card_id):
    state["decision"]["options"] = legal_card_actions(state, state["active_side"])
    return apply_action(state, {"type": "PLAY_CARD", "actor": state["active_side"],
                                "card_id": card_id, "mode": "EVENT"}).state


def test_guns_of_august_destroys_liege_fort_and_opens_combat():
    state = create_game(seed=4)
    for value in (3, 5):
        action = next(a for a in generate_legal_actions(state) if a["value"] == value)
        state = apply_action(state, action).state
    state = play_event(state, "GUNS_OF_AUGUST")
    assert state["spaces"]["LIEGE"]["fort_destroyed"]
    assert state["spaces"]["LIEGE"]["control"] == "CP"
    assert state["units"]["GE_1_ARMY_1"]["location"] == "LIEGE"
    assert state["units"]["GE_2_ARMY_1"]["location"] == "LIEGE"
    assert state["phase"] == "COMBAT"
    assert {"LIEGE", "KOBLENZ"} <= set(state["activated"]["ATTACK"])


@pytest.mark.parametrize("card_id,nation", [
    ("ITALY", "IT"), ("ROMANIA", "RO"), ("BULGARIA", "BU"), ("GREECE", "GR")
])
def test_neutral_entry_events_and_shared_turn_limit(card_id, nation):
    side = "CP" if nation == "BU" else "AP"
    state = with_card(action_state(side), card_id)
    assert EVENT_HANDLERS[card_id].can_play(state, card_id)
    state = play_event(state, card_id)
    assert state["war_nations"][nation]
    assert state["flags"]["neutral_entry_turn"] == 2
    assert not EVENT_HANDLERS["ITALY"].can_play(state, "ITALY")


def test_late_italian_and_romanian_cards_are_event_only():
    state = with_card(action_state("AP"), "ITALY")
    state["players"]["CP"]["commitment"] = "TOTAL"
    state["decision"]["options"] = legal_card_actions(state, "AP")
    assert {a["mode"] for a in generate_legal_actions(state) if a["card_id"] == "ITALY"} == {"EVENT"}


def test_russian_political_chain_and_event_ops():
    state = with_card(action_state("CP", 5), "TSAR_TAKES_COMMAND")
    assert not EVENT_HANDLERS["TSAR_TAKES_COMMAND"].can_play(state, "TSAR_TAKES_COMMAND")
    for space_id in RUSSIAN_VP_SPACES[:3]:
        state["spaces"][space_id]["control"] = "CP"
    state = play_event(state, "TSAR_TAKES_COMMAND")
    assert state["events"]["TSAR_TAKES_COMMAND"] == 5
    assert state["phase"] == "OPS"
    assert state["ops_remaining"] == 4

    state = with_card(action_state("CP", 6), "FALL_OF_THE_TSAR")
    state["events"]["TSAR_TAKES_COMMAND"] = 5
    for space_id in RUSSIAN_VP_SPACES[:3]:
        state["spaces"][space_id]["control"] = "CP"
    state["players"]["CP"]["war_status"] = 30
    assert EVENT_HANDLERS["FALL_OF_THE_TSAR"].can_play(state, "FALL_OF_THE_TSAR")
    state = play_event(state, "FALL_OF_THE_TSAR")
    assert state["vp"] == 13  # Romania가 참전하지 않았다.
    assert state["phase"] == "OPS"


def test_us_entry_requires_combined_status_and_next_turn():
    state = with_card(action_state("AP", 8), "ZIMMERMANN_TELEGRAM")
    assert not EVENT_HANDLERS["ZIMMERMANN_TELEGRAM"].can_play(state, "ZIMMERMANN_TELEGRAM")
    state["players"]["AP"]["war_status"] = 15
    state["players"]["CP"]["war_status"] = 15
    update_entry_markers(state)
    state = play_event(state, "ZIMMERMANN_TELEGRAM")
    assert state["us_entry"] == 2
    assert state["vp"] == 9
    assert state["phase"] == "OPS"
    next_turn = with_card(action_state("AP", 9), "OVER_THERE")
    next_turn["events"]["ZIMMERMANN_TELEGRAM"] = 8
    assert EVENT_HANDLERS["OVER_THERE"].can_play(next_turn, "OVER_THERE")
    next_turn = play_event(next_turn, "OVER_THERE")
    assert next_turn["us_entry"] == 3
    assert next_turn["war_nations"]["US"]


def test_romania_disallowed_after_fall_of_tsar():
    state = with_card(action_state("AP", 8), "ROMANIA")
    state["events"]["FALL_OF_THE_TSAR"] = 7
    assert not EVENT_HANDLERS["ROMANIA"].can_play(state, "ROMANIA")


def test_bolshevik_and_treaty_require_chain_and_apply_restrictions():
    state = with_card(action_state("CP", 9), "BOLSHEVIK_REVOLUTION")
    state["events"]["FALL_OF_THE_TSAR"] = 8
    state["flags"]["tsar_fell_russian_vp"] = 3
    for space_id in RUSSIAN_VP_SPACES[:4]:
        state["spaces"][space_id]["control"] = "CP"
    assert EVENT_HANDLERS["BOLSHEVIK_REVOLUTION"].can_play(state, "BOLSHEVIK_REVOLUTION")
    state["players"]["AP"]["mandatory_offensive"] = "RU"
    state = play_event(state, "BOLSHEVIK_REVOLUTION")
    assert state["phase"] == "OPS"
    assert state["players"]["AP"]["mandatory_offensive"] is None
    assert state["russian_capitulation"] == 6

    state = with_card(action_state("CP", 10), "TREATY_OF_BREST_LITOVSK")
    state["events"]["BOLSHEVIK_REVOLUTION"] = 9
    state["units"]["RU_1_ARMY_1"]["location"] = "PARIS"
    state = play_event(state, "TREATY_OF_BREST_LITOVSK")
    assert state["russian_capitulation"] == 7
    assert state["units"]["RU_1_ARMY_1"]["eliminated"]


@pytest.mark.parametrize("card_id", ["ROMANIA", "BULGARIA"])
def test_neutral_entry_places_four_additional_corps(card_id):
    side = "AP" if card_id == "ROMANIA" else "CP"
    state = with_card(action_state(side), card_id)
    state = play_event(state, card_id)
    assert state["phase"] == "NEUTRAL_ENTRY"
    for _ in range(4):
        action = generate_legal_actions(state)[0]
        state = apply_action(state, action).state
    assert state["phase"] == "ACTION"


def test_fall_of_tsar_russian_attack_activation_costs_per_unit():
    state = action_state("AP", 8)
    state["units"]["RU_1_ARMY_1"]["location"] = "KOVNO"
    state["units"]["RU_2_ARMY_1"]["location"] = "KOVNO"
    state["units"]["RU_3_ARMY_1"]["location"] = "KOVNO"
    state["events"]["FALL_OF_THE_TSAR"] = 7
    assert activation_cost(state, "KOVNO", "ATTACK") == 3
    assert activation_cost(state, "KOVNO", "MOVE") == 1


def test_treaty_prohibits_russian_attack_and_mixing():
    state = action_state("AP", 10)
    state["events"]["TREATY_OF_BREST_LITOVSK"] = 9
    state["units"]["RU_1_ARMY_1"]["location"] = "KOVNO"
    state["units"]["GE_1_ARMY_1"]["location"] = "VILNA"
    assert not _valid_group(state, ("RU_1_ARMY_1",), "VILNA")
    assert not _can_enter(state, "RU_1_ARMY_1", "PARIS")
    state["units"]["FR_1_ARMY_1"]["location"] = "RIGA"
    assert not _can_enter(state, "RU_1_ARMY_1", "RIGA")


def test_bolshevik_revolution_limits_russian_replacement_points():
    state = action_state("AP", 10)
    state["phase"] = "REPLACEMENT_AP"
    state["events"]["BOLSHEVIK_REVOLUTION"] = 9
    state["players"]["AP"]["replacement_points"] = {"RU": 3}
    state["units"]["RU_1_ARMY_1"]["reduced"] = True
    state["units"]["RU_2_ARMY_1"]["reduced"] = True
    state["decision"] = {"kind": "REPLACEMENT", "actor": "AP", "options": []}
    first = next(a for a in legal_replacement_actions(state, "AP") if a["type"] == "FLIP_UNIT"
                 and a["unit_id"] == "RU_1_ARMY_1")
    state = apply_replacement_action(state, first)
    assert not any(a.get("unit_id") == "RU_2_ARMY_1" for a in legal_replacement_actions(state, "AP"))
