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
    return _run_parallel_with_output(inputs, outputs, report)[0]


def _run_parallel_with_output(inputs: Path, outputs: Path, report: Path,
                              workers: int = 3) -> tuple[dict, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(inputs), "--rules", str(RULES),
         "--output", str(outputs), "--report", str(report), "--workers", str(workers)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "전체 병합" in result.stdout
    if any(inputs.iterdir()):
        assert "샤드" in result.stdout
    return json.loads(report.read_text(encoding="utf-8")), result.stdout


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


def test_fixed_shard_checkpoints_resume_and_verify_input_hash(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    first = _run_parallel(inputs, output, report_path)
    checkpoint_dir = tmp_path / ".report.json.shards"
    checkpoints = sorted(checkpoint_dir.glob("shard-*.json"))
    assert checkpoints
    assert all(json.loads(path.read_text())["complete"] for path in checkpoints)

    report_path.unlink()
    second, stdout = _run_parallel_with_output(inputs, output, report_path, workers=1)
    assert second == first
    assert "체크포인트 재사용" in stdout

    report_path.unlink()
    source_path = inputs / "replay-258629.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["players"] = {"Central Powers": "changed input"}
    source_path.write_text(json.dumps(source), encoding="utf-8")
    changed, stdout = _run_parallel_with_output(inputs, output, report_path)
    assert changed["input_count"] == first["input_count"]
    changed_row = next(row for row in changed["games"] if row["file"] == source_path.name)
    assert changed_row["source_sha256"] == sha256(source_path.read_bytes()).hexdigest()
    assert "체크포인트 무효" in stdout


def test_partial_checkpoint_resumes_same_shard(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    first = _run_parallel(inputs, output, report_path)
    checkpoint_dir = tmp_path / ".report.json.shards"
    checkpoint = next(path for path in checkpoint_dir.glob("shard-*.json")
                      if len(json.loads(path.read_text())["report"]["games"]) == 2)
    payload = json.loads(checkpoint.read_text())
    payload["complete"] = False
    payload["report"]["games"] = payload["report"]["games"][:1]
    payload["report"]["input_count"] = 1
    payload["report"]["counts"] = {payload["report"]["games"][0]["status"]: 1}
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    report_path.unlink()

    actual, stdout = _run_parallel_with_output(inputs, output, report_path)
    assert actual == first
    assert "체크포인트 재개" in stdout
    assert json.loads(checkpoint.read_text())["complete"] is True


def test_resume_cleans_removed_input_without_previous_final_report(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    _run_parallel(inputs, output, report_path)
    assert (output / "replay-258630.json").is_file()
    report_path.unlink()
    (inputs / "replay-258630.json").unlink()

    report = _run_parallel(inputs, output, report_path)
    assert report["input_count"] == 4
    assert not (output / "replay-258630.json").exists()


def test_refresh_resume_does_not_reuse_old_final_report(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    first = _run_parallel(inputs, output, report_path)
    checkpoint_dir = tmp_path / ".report.json.shards"
    checkpoint = next(path for path in checkpoint_dir.glob("shard-*.json")
                      if any(row["status"] == "verified"
                             for row in json.loads(path.read_text())["report"]["games"]))
    checkpoint.unlink()
    stale = json.loads(report_path.read_text())
    next(row for row in stale["games"] if row["status"] == "verified")["status"] = "mismatch"
    report_path.write_text(json.dumps(stale), encoding="utf-8")
    marker = checkpoint_dir / "run.json"
    marker.write_text(json.dumps({"schema_version": 1,
                                  "validation_signature": first["validation_signature"],
                                  "refresh": True}), encoding="utf-8")

    actual = _run_parallel(inputs, output, report_path)
    assert actual == first
    assert not marker.exists()


def test_checkpoint_signature_mismatch_is_not_reused(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    first = _run_parallel(inputs, output, report_path)
    checkpoint_dir = tmp_path / ".report.json.shards"
    checkpoint = next(path for path in checkpoint_dir.glob("shard-*.json")
                      if any(row["status"] == "verified"
                             for row in json.loads(path.read_text())["report"]["games"]))
    payload = json.loads(checkpoint.read_text())
    payload["validation_signature"] = "old rules"
    payload["report"]["games"][0]["status"] = "mismatch"
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    report_path.unlink()

    actual, stdout = _run_parallel_with_output(inputs, output, report_path)
    assert actual == first
    assert "체크포인트 무효" in stdout


def test_checkpoint_rechecks_normalized_artifact_hash(tmp_path):
    inputs = tmp_path / "inputs"
    _inputs(inputs)
    output, report_path = tmp_path / "parallel", tmp_path / "report.json"
    expected = _run_parallel(inputs, output, report_path)
    normalized = output / "replay-258629.json"
    normalized.write_bytes(b"changed by another process")
    report_path.unlink()

    actual, stdout = _run_parallel_with_output(inputs, output, report_path)
    assert actual == expected
    verified = next(row for row in actual["games"] if row["status"] == "verified"
                    and row["game_id"] == 258629)
    assert sha256(normalized.read_bytes()).hexdigest() == verified["normalized_sha256"]
    assert "체크포인트 무효" in stdout


def test_parallel_lock_rejects_concurrent_output_use(tmp_path):
    path_lock = runpy.run_path(str(SCRIPT))["_path_lock"]
    output_key = tmp_path / "normalized" / ".parallel-validate"
    with path_lock(output_key):
        with pytest.raises(RuntimeError, match="이미 같은 경로"):
            with path_lock(output_key):
                pass


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
