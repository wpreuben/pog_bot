import copy
import json
import unittest

from pog_engine import IllegalActionError, apply_action, create_game, generate_legal_actions
from pog_engine.replay import replay
from pog_engine.rules.victory import game_result


def confirmation_state():
    return {
        "schema_version": 1,
        "phase": "CONFIRM",
        "decision": {
            "kind": "CONFIRM",
            "actor": "CP",
            "options": [{"type": "CONFIRM", "actor": "CP"}],
        },
    }


class EngineContractTests(unittest.TestCase):
    def test_resign_is_replayable_and_ends_game(self):
        initial = create_game(seed=4)
        state = initial
        records = []
        for value in (4, 6):
            action = next(option for option in generate_legal_actions(state)
                          if option["type"] == "RECORD_DIE_RESULT" and option["value"] == value)
            transition = apply_action(state, action)
            records.append(transition.record)
            state = transition.state
        resign = {"type": "RESIGN", "actor": "CP"}
        self.assertIn(resign, generate_legal_actions(state))
        transition = apply_action(state, resign)
        records.append(transition.record)
        self.assertEqual(transition.state["phase"], "GAME_OVER")
        self.assertEqual(game_result(transition.state),
                         {"winner": "AP", "reason": "RESIGN", "vp": 10})
        self.assertEqual(replay(initial, records), transition.state)
        self.assertNotIn(resign, generate_legal_actions(transition.state))
        with self.assertRaises(IllegalActionError):
            apply_action(transition.state, resign)

    def test_wrong_actor_preserves_state(self):
        state = confirmation_state()
        before = copy.deepcopy(state)

        with self.assertRaises(IllegalActionError):
            apply_action(state, {"type": "CONFIRM", "actor": "AP"})

        self.assertEqual(state, before)

    def test_malformed_action_preserves_state(self):
        state = confirmation_state()
        before = copy.deepcopy(state)

        with self.assertRaises(IllegalActionError):
            apply_action(state, {"type": "CONFIRM", "actor": "CP", "extra": 1})

        self.assertEqual(state, before)

    def test_legal_actions_are_unique_and_detached(self):
        state = confirmation_state()
        state["decision"]["options"].append({"type": "CONFIRM", "actor": "CP"})

        actions = generate_legal_actions(state)
        self.assertEqual(actions, [{"type": "CONFIRM", "actor": "CP"}])
        actions[0]["type"] = "FORGED"
        self.assertEqual(state["decision"]["options"][0]["type"], "CONFIRM")

    def test_valid_transition_is_replayable_without_input_mutation(self):
        state = confirmation_state()
        before = copy.deepcopy(state)

        result = apply_action(state, {"type": "CONFIRM", "actor": "CP"})

        self.assertEqual(state, before)
        self.assertIsNone(result.state["decision"])
        self.assertEqual(generate_legal_actions(result.state), [])
        self.assertEqual(result.record["action"], {"type": "CONFIRM", "actor": "CP"})
        self.assertEqual(json.loads(json.dumps(result.state)), result.state)


if __name__ == "__main__":
    unittest.main()
