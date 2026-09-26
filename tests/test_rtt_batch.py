"""여러 RTT 기보의 검증·정규화 결과."""

import json
from pathlib import Path

from rtt_test_support import rules_path

from pog_engine.replay import replay
from pog_engine.rtt_replay.batch import validate_replays


ROOT = Path(__file__).resolve().parents[1]
RULES = rules_path(__file__)


def test_batch_keeps_unsupported_and_duplicate_games_out_of_normalized_data(tmp_path):
    source = json.loads((ROOT / "tests/fixtures/replay-258629.json").read_text(encoding="utf-8"))
    source["players"] = {"Central Powers": "Private Name"}
    source["state"] = {"state": "game_over"}
    inputs = tmp_path / "replays"
    outputs = tmp_path / "normalized"
    inputs.mkdir()
    (inputs / "replay-258629.json").write_text(json.dumps(source), encoding="utf-8")
    (inputs / "replay-258629-z.json").write_text(json.dumps(source), encoding="utf-8")
    (inputs / "replay-7.json").write_text("{broken", encoding="utf-8")
    valiant = {"setup": {"game_id": 8, "scenario": "Historical", "options": {"valiant": True}},
               "replay": [[None, ".setup", [1, "Historical", {"valiant": True}]]],
               "state": {"state": "game_over"}}
    (inputs / "replay-8.json").write_text(json.dumps(valiant), encoding="utf-8")
    unfinished = {"setup": {"game_id": 9, "scenario": "Historical", "options": {}},
                  "replay": [[None, ".setup", [1, "Historical", {}]]],
                  "state": {"state": "action_phase"}}
    (inputs / "replay-9.json").write_text(json.dumps(unfinished), encoding="utf-8")
    timeout = {"setup": {"game_id": 10, "scenario": "Historical", "options": {}},
               "replay": [[None, ".setup", [1, "Historical", {}]],
                          ["Allied Powers", ".timeout"]],
               "state": {"state": "game_over"}}
    (inputs / "replay-10.json").write_text(json.dumps(timeout), encoding="utf-8")

    report = validate_replays(inputs, RULES, outputs)

    assert report["counts"] == {"duplicate": 1, "incomplete": 1, "invalid": 1,
                                "unsupported": 2, "verified": 1}
    games = {row["file"]: row for row in report["games"]}
    assert games["replay-258629.json"]["status"] == "verified"
    assert games["replay-258629-z.json"]["status"] == "duplicate"
    assert games["replay-8.json"]["status"] == "unsupported"
    assert games["replay-10.json"]["reason"] == "timeout"
    assert games["replay-9.json"]["status"] == "incomplete"
    assert games["replay-7.json"]["status"] == "invalid"
    normalized = outputs / "replay-258629.json"
    assert normalized.exists()
    assert len(list(outputs.glob("*.json"))) == 1
    text = normalized.read_text(encoding="utf-8")
    assert "Private Name" not in text
    data = json.loads(text)
    assert data["game_id"] == 258629
    assert data["source_sha256"] == games["replay-258629.json"]["source_sha256"]
    assert replay(data["initial_state"], data["records"])["result"]["winner"] == "AP"

    saved_time = normalized.stat().st_mtime_ns
    repeated = validate_replays(inputs, RULES, outputs, previous_report=report)
    assert repeated["counts"] == report["counts"]
    assert normalized.stat().st_mtime_ns == saved_time

    source["state"]["state"] = "action_phase"
    (inputs / "replay-258629.json").write_text(json.dumps(source), encoding="utf-8")
    (inputs / "replay-258629-z.json").write_text(json.dumps(source), encoding="utf-8")
    changed = validate_replays(inputs, RULES, outputs, previous_report=repeated)
    changed_games = {row["file"]: row for row in changed["games"]}
    assert changed_games["replay-258629.json"]["status"] == "incomplete"
    assert not normalized.exists()
