"""RTT 참고 엔진에서 추출한 관측의 계약."""

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/replay-258629.json"
RULES = Path("/home/pc/project/pog_bot/Rally the Troops_paths-of-glory-master/rules.js")
SCRIPT = ROOT / "tools/rtt_trace.cjs"


def test_full_trace_reaches_exported_result():
    result = subprocess.run(["node", str(SCRIPT), str(FIXTURE), str(RULES)],
                            capture_output=True, text=True, check=True)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 1448
    assert [row["index"] for row in rows[:-1]] == list(range(1447))
    assert rows[0]["before"] is None
    assert rows[-1] == {"kind": "final", "turn": 8, "vp": 7,
                        "state": "game_over", "victory": "Central Powers resigned.",
                        "seed": 27367842750}


def test_invalid_rtt_action_reports_index(tmp_path):
    payload = {"setup": {"game_id": 1, "scenario": "Historical", "options": {}},
               "replay": [[None, ".setup", [10762091171, "Historical", {}]],
                          ["Central Powers", "not_a_real_action"]]}
    fixture = tmp_path / "bad.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(["node", str(SCRIPT), str(fixture), str(RULES)],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "index 1" in result.stderr
