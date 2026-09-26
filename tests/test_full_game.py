import json

from pog_engine import apply_action, create_game, generate_legal_actions, game_result
from pog_engine.replay import replay


def choose_action(actions):
    for kind in ("END_COMBAT", "END_DRAW_DISCARD", "FINISH_ACTIVATION", "END_MOVEMENT", "END_SR", "END_SIEGE",
                 "END_REPLACEMENT", "SKIP_EVENT_TRENCH", "END_LANDWEHR", "END_SALONIKA",
                 "PASS_GREAT_RETREAT", "PASS_TRENCH_CARDS", "SKIP_FLANK", "PASS_COMBAT_CARDS",
                 "END_LOSSES", "END_ADVANCE", "PASS", "PLAY_CARD"):
        candidates = [action for action in actions if action["type"] == kind]
        if candidates:
            if kind == "PLAY_CARD":
                candidates.sort(key=lambda action: (action["mode"] != "RP", action["mode"] != "OPS", action["card_id"]))
            return candidates[0]
    return actions[0]


def test_historical_game_can_reach_turn_limit_and_replay():
    initial = create_game(seed=17)
    state = initial
    records = []
    for _ in range(2000):
        if state["phase"] == "GAME_OVER":
            break
        actions = generate_legal_actions(state)
        assert actions, f"공개 API로 진행할 수 없는 단계: {state['phase']}"
        action = choose_action(actions)
        transition = apply_action(state, action)
        state = transition.state
        records.append(transition.record)
    assert state["phase"] == "GAME_OVER"
    assert game_result(state) == state["result"]
    assert generate_legal_actions(state) == []
    assert replay(initial, json.loads(json.dumps(records))) == state
