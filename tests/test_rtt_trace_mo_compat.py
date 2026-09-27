"""오래된 RTT 첫 AP 의무 공세 기록과 현재 관측기의 의미 일치."""

import json
from pathlib import Path
import subprocess

import pytest

from rtt_test_support import rules_path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/rtt_trace.cjs"
RULES = rules_path(__file__)


def _trace(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["node", str(SCRIPT), str(path), str(RULES)],
                          capture_output=True, text=True)


@pytest.mark.parametrize("game_id,early,late", [
    (166206, 9, 30),
    (166209, 9, 35),
    (166239, 11, 25),
    (166243, 9, 24),
    (166569, 10, 38),
])
def test_early_confirmation_and_later_duplicate_preserve_rows(game_id, early, late):
    path = ROOT / f"tests/fixtures/rtt-mo-{game_id}.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    result = _trace(path)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == len(source["replay"]) + 1
    assert [row["index"] for row in rows[:-1]] == list(range(len(source["replay"])))
    assert rows[early - 1]["after"]["state"] == "defender_combat_cards"
    assert rows[early]["before"] == rows[early - 1]["after"]
    assert rows[late]["before"]["state"] == "action_phase"
    assert rows[late]["before"] == rows[late]["after"]
    assert rows[late]["log_delta"] == []
    assert rows[late]["random"]["seeds"] == []
    assert rows[late + 1]["before"] == rows[late]["after"]
    assert rows[-1]["kind"] == "final"


def test_explicit_early_next_is_preserved(tmp_path):
    source = json.loads((ROOT / "tests/fixtures/rtt-mo-166206.json").read_text())
    source["replay"] = (source["replay"][:9]
                        + [["Allied Powers", "next"], ["Allied Powers", "done"],
                           ["Central Powers", ".resign"]])
    path = tmp_path / "explicit-next.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    result = _trace(path)
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert rows[8]["after"]["state"] == "confirm_mo"
    assert rows[9]["name"] == "next"
    assert rows[9]["after"]["state"] == "defender_combat_cards"


def test_other_ap_action_does_not_trigger_virtual_next(tmp_path):
    source = json.loads((ROOT / "tests/fixtures/rtt-mo-166206.json").read_text())
    source["replay"][9] = ["Allied Powers", "piece", 36]
    path = tmp_path / "not-compatible.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    result = _trace(path)
    assert result.returncode != 0
    assert "index 9: Invalid action: piece" in result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert rows[8]["after"]["state"] == "confirm_mo"
