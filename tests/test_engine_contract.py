import copy
import json
import unittest

from pog_engine import IllegalActionError, apply_action, generate_legal_actions


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
