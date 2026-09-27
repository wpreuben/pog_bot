"""병렬 기보 검증은 순차 검증과 같은 보고서를 만든다."""

from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from rtt_test_support import rules_path

from pog_engine.rtt_replay.batch import validate_replays


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/parallel_validate.py"
RULES = rules_path(__file__)


def _inputs(path: Path) -> None:
    path.mkdir()
    source = json.loads((ROOT / "tests/fixtures/replay-258629.json").read_text(encoding="utf-8"))
    source["replay"] = [source["replay"][0], ["Allied Powers", ".resign"]]
    source["state"] = {"state": "game_over"}
    payload = json.dumps(source)
    (path / "replay-258629.json").write_text(payload, encoding="utf-8")
    (path / "replay-258629-z.json").write_text(payload, encoding="utf-8")
    source["setup"]["game_id"] = 258630
    (path / "replay-258630.json").write_text(json.dumps(source), encoding="utf-8")
    (path / "replay-7.json").write_text("{broken", encoding="utf-8")
    unsupported = {"setup": {"game_id": 8, "scenario": "Historical", "options": {"other": True}}}
    (path / "replay-8.json").write_text(json.dumps(unsupported), encoding="utf-8")


def _run_parallel(inputs: Path, outputs: Path, report: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(inputs), "--rules", str(RULES),
         "--output", str(outputs), "--report", str(report), "--workers", "3"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "전체 병합" in result.stdout
    if any(inputs.iterdir()):
        assert "샤드" in result.stdout
    return json.loads(report.read_text(encoding="utf-8"))


def test_parallel_cli_matches_sequential_and_cleans_only_matching_old_artifacts(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    expected = validate_replays(inputs, RULES, tmp_path / "sequential")
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"

    report = _run_parallel(inputs, output, report_path)
    assert report == expected
    assert [row["status"] for row in report["games"] if row.get("game_id") == 258629] == [
        "verified", "duplicate"]
    assert (output / "replay-258629.json").is_file()
    assert (output / "replay-258630.json").is_file()

    foreign = output / "replay-777.json"
    foreign.write_bytes(b"other shard normalized data")
    changed = output / "replay-778.json"
    changed.write_bytes(b"externally changed data")
    report_path.write_text(json.dumps({**report, "games": report["games"] + [
        {"file": "replay-777.json", "game_id": 777, "status": "verified",
         "normalized_sha256": sha256(foreign.read_bytes()).hexdigest()},
        {"file": "replay-778.json", "game_id": 778, "status": "verified",
         "normalized_sha256": sha256(b"original data").hexdigest()},
    ]}), encoding="utf-8")
    assert _run_parallel(inputs, output, report_path) == expected
    assert not foreign.exists()
    assert changed.read_bytes() == b"externally changed data"


def test_deleted_input_and_changed_game_id_remove_old_verified_artifacts(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    sequential_output = tmp_path / "sequential"
    previous_sequential = validate_replays(inputs, RULES, sequential_output)
    parallel_output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    previous_parallel = _run_parallel(inputs, parallel_output, report_path)
    assert previous_parallel == previous_sequential

    for name in ("replay-258629.json", "replay-258629-z.json"):
        path = inputs / name
        source = json.loads(path.read_text(encoding="utf-8"))
        source["setup"]["game_id"] = 258631
        path.write_text(json.dumps(source), encoding="utf-8")
    (inputs / "replay-258630.json").unlink()
    # 해시가 다른 산출물은 순차 검증기와 마찬가지로 보존한다.
    (sequential_output / "replay-258630.json").write_bytes(b"changed")
    (parallel_output / "replay-258630.json").write_bytes(b"changed")

    expected = validate_replays(inputs, RULES, sequential_output, previous_sequential)
    actual = _run_parallel(inputs, parallel_output, report_path)
    assert actual == expected
    assert not (parallel_output / "replay-258629.json").exists()
    assert (parallel_output / "replay-258630.json").read_bytes() == b"changed"
    assert (parallel_output / "replay-258631.json").is_file()
    assert sorted(path.name for path in parallel_output.iterdir()) == sorted(
        path.name for path in sequential_output.iterdir())


def test_empty_input_cleans_previous_verified_artifact(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    previous = _run_parallel(inputs, output, report_path)
    assert previous["counts"]["verified"] == 2
    for path in inputs.iterdir():
        path.unlink()

    report = _run_parallel(inputs, output, report_path)
    assert report["input_count"] == 0
    assert list(output.iterdir()) == []


def test_merge_rejects_missing_rows_and_different_signatures():
    assert SCRIPT.is_file()
    merge_shard_reports = runpy.run_path(str(SCRIPT))["merge_shard_reports"]

    first = {"schema_version": 1, "validation_signature": "same", "input_count": 1,
             "games": [{"file": "a.json", "status": "invalid"}]}
    second = {"schema_version": 1, "validation_signature": "other", "input_count": 1,
              "games": [{"file": "b.json", "status": "invalid"}]}
    with pytest.raises(ValueError, match="signature"):
        merge_shard_reports([first, second], [["a.json"], ["b.json"]], ["a.json", "b.json"])
    second["validation_signature"] = "same"
    with pytest.raises(ValueError, match="missing|누락"):
        merge_shard_reports([first, second], [["a.json"], ["b.json"]], ["a.json", "b.json", "c.json"])
