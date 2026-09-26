"""대량 기보 검사에서 잘못된 검증 완료를 막는 경계."""

import json
from hashlib import sha256
from pathlib import Path

from rtt_test_support import rules_path

from pog_engine.rtt_replay.batch import validate_replays
from pog_engine.rtt_replay import batch


ROOT = Path(__file__).resolve().parents[1]
RULES = rules_path(__file__)


def setup_only_game(game_id: int) -> dict:
    source = json.loads((ROOT / "tests/fixtures/replay-258629.json").read_text(encoding="utf-8"))
    source["setup"]["game_id"] = game_id
    source["replay"] = source["replay"][:1]
    source["state"] = {"state": "game_over"}
    return source


def test_claimed_game_over_requires_actual_rtt_final_state(tmp_path):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    (inputs / "replay-111.json").write_text(json.dumps(setup_only_game(111)), encoding="utf-8")

    report = validate_replays(inputs, RULES, outputs)

    assert report["counts"] == {"mismatch": 1}
    assert report["games"][0]["first_difference"]["path"] == "$.final.state"
    assert not list(outputs.glob("*.json"))


def test_numeric_filenames_are_scanned_and_foreign_output_is_preserved(tmp_path):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    (inputs / "166206.json").write_text("{broken", encoding="utf-8")
    foreign = outputs / "replay-777.json"
    foreign.write_text("user data", encoding="utf-8")

    report = validate_replays(inputs, RULES, outputs)

    assert report["counts"] == {"invalid": 1}
    assert report["games"][0]["file"] == "166206.json"
    assert foreign.read_text(encoding="utf-8") == "user data"


def test_input_is_snapshotted_before_source_file_changes(tmp_path, monkeypatch):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    original = inputs / "111.json"
    original.write_text(json.dumps(setup_only_game(111)), encoding="utf-8")
    first_hash = sha256(original.read_bytes()).hexdigest()
    real_runner = batch.run_replay

    def replace_download_after_scan(path, rules):
        original.write_text("{broken", encoding="utf-8")
        return real_runner(path, rules)

    monkeypatch.setattr(batch, "run_replay", replace_download_after_scan)
    report = validate_replays(inputs, RULES, outputs)

    assert report["games"][0]["status"] == "mismatch"
    assert report["games"][0]["first_difference"]["path"] == "$.final.state"
    assert report["games"][0]["source_sha256"] == first_hash


def test_cache_signature_includes_rtt_data_module(tmp_path):
    rules = tmp_path / "rules.js"
    rules.write_text("rules", encoding="utf-8")
    (tmp_path / "data.js").write_text("first", encoding="utf-8")
    (tmp_path / "lz4.js").write_text("lz4", encoding="utf-8")
    before = batch._validation_signature(rules)

    (tmp_path / "data.js").write_text("second", encoding="utf-8")

    assert batch._validation_signature(rules) != before


def test_batch_checkpoints_before_full_corpus_finishes(tmp_path):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    for game_id in range(12):
        (inputs / f"{game_id}.json").write_text("{broken", encoding="utf-8")
    checkpoints = []

    report = validate_replays(inputs, RULES, outputs,
                              checkpoint=lambda partial: checkpoints.append(partial["input_count"]))

    assert report["input_count"] == 12
    assert checkpoints == [10, 12]


def test_corrupt_cached_artifact_is_revalidated(tmp_path):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    path = inputs / "111.json"
    path.write_text(json.dumps(setup_only_game(111)), encoding="utf-8")
    (outputs / "replay-111.json").write_text("damaged", encoding="utf-8")
    previous = {"validation_signature": batch._validation_signature(RULES),
                "games": [{"file": path.name, "game_id": 111, "status": "verified",
                           "source_sha256": sha256(path.read_bytes()).hexdigest(),
                           "normalized_sha256": sha256(b"original").hexdigest()}]}

    report = validate_replays(inputs, RULES, outputs, previous_report=previous)

    assert report["counts"] == {"mismatch": 1}
    assert report["games"][0]["first_difference"]["path"] == "$.final.state"
    assert (outputs / "replay-111.json").read_text(encoding="utf-8") == "damaged"
