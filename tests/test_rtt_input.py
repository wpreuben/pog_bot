"""RTT 기보 입력의 고정 계약."""

import json
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "replay-258629.json"


def test_historical_fixture_is_anonymous_and_complete():
    from pog_engine.rtt_replay.input import load_replay

    replay = load_replay(FIXTURE)
    assert replay.game_id == 258629
    assert replay.seed == 10762091171
    assert replay.scenario == "Historical"
    assert len(replay.actions) == 1447
    assert replay.actions[0].name == ".setup"
    assert replay.actions[-1].name == ".resign"
    assert "players" not in json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("broken, index", [
    (["Unknown Side", "next"], 1),
    (["Central Powers"], 1),
    (["Central Powers", 42], 1),
])
def test_invalid_step_reports_original_index(tmp_path, broken, index):
    from pog_engine.rtt_replay.input import ReplayInputError, load_replay

    payload = {"setup": {"game_id": 258629, "scenario": "Historical", "options": {}},
               "replay": [[None, ".setup", [10762091171, "Historical", {}]], broken]}
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReplayInputError, match=f"{index}"):
        load_replay(path)
