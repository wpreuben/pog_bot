from pog_engine import apply_action, create_game, generate_legal_actions
from pog_engine.rules.turn import advance_automatic_phases, complete_action, mandatory_offensive


def roll(state, value):
    purpose = state["decision"]["purpose"]
    return apply_action(
        state,
        {"type": "RECORD_DIE_RESULT", "actor": "CHANCE", "purpose": purpose, "value": value},
    ).state


def after_opening_rolls():
    state = roll(create_game(seed=4), 3)
    return roll(state, 5)


def test_ap_roll_precedes_cp_and_turn_one_british_mo_becomes_french():
    state = create_game(seed=4)
    assert state["decision"]["purpose"] == "AP_MANDATORY_OFFENSIVE"

    state = roll(state, 3)
    assert state["players"]["AP"]["mandatory_offensive"] == "FR"
    assert state["decision"]["purpose"] == "CP_MANDATORY_OFFENSIVE"

    state = roll(state, 5)
    assert state["players"]["CP"]["mandatory_offensive"] is None
    assert state["phase"] == "ACTION"
    assert state["active_side"] == "CP"


def test_first_cp_action_is_guns_of_august_event_only():
    state = after_opening_rolls()
    assert [action for action in generate_legal_actions(state) if action["type"] == "PLAY_CARD"] == [
        {"type": "PLAY_CARD", "actor": "CP", "card_id": "GUNS_OF_AUGUST", "mode": "EVENT"}
    ]
    assert {"type": "RESIGN", "actor": "CP"} in generate_legal_actions(state)


def test_six_action_rounds_alternate_cp_then_ap_without_seventh_round():
    state = after_opening_rolls()
    sequence = []
    for _ in range(12):
        sequence.append((state["action_round"], state["active_side"]))
        state = complete_action(state)

    assert sequence == [(round_no, side) for round_no in range(1, 7) for side in ("CP", "AP")]
    assert state["phase"] == "ATTRITION"
    assert state["action_round"] == 6


def test_post_action_phases_follow_rulebook_order():
    state = after_opening_rolls()
    for _ in range(12):
        state = complete_action(state)

    phases = [state["phase"]]
    for _ in range(7):
        state = advance_automatic_phases(state)
        while state["phase"] == "DRAW" and state["decision"] is not None:
            state = apply_action(state, {"type": "END_DRAW_DISCARD",
                                         "actor": state["decision"]["actor"]}).state
        phases.append(state["phase"])

    assert phases == [
        "ATTRITION", "SIEGE", "WAR_STATUS", "REPLACEMENT_AP",
        "REPLACEMENT_CP", "DRAW", "END_TURN", "MANDATORY_OFFENSIVE",
    ]
    assert state["turn"] == 2
    assert state["decision"]["purpose"] == "AP_MANDATORY_OFFENSIVE"


def test_neutral_italy_cancels_italian_mandatory_offensive():
    state = create_game(seed=4)
    assert mandatory_offensive(state, "AP", 4) is None
