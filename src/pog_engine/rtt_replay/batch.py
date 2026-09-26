"""RTT JSON 기보를 게임 단위로 검증하고 엔진 행동으로 정규화."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from pog_engine.replay import replay

from .input import ReplayInputError, load_replay
from .runner import run_replay


SUPPORTED_OPTIONS = {"no_supply_warnings"}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _validation_signature(rules_path: Path) -> str:
    root = Path(__file__).resolve().parents[3]
    files = sorted((root / "src/pog_engine").rglob("*.py"))
    files.append(root / "tools/rtt_trace.cjs")
    digest = sha256()
    for path in files:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    digest.update(rules_path.read_bytes())
    return digest.hexdigest()


def validate_replays(input_dir: Path, rules_path: Path, output_dir: Path,
                     previous_report: dict | None = None) -> dict:
    """현재 입력 파일을 스냅샷으로 검사한다. 실패한 게임도 결과에 남긴다."""
    if not input_dir.is_dir():
        raise ValueError(f"기보 폴더가 없습니다: {input_dir}")
    if not rules_path.is_file():
        raise ValueError(f"RTT rules.js가 없습니다: {rules_path}")
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("원본 기보 폴더와 정규화 출력 폴더를 분리해야 합니다")
    signature = _validation_signature(rules_path)
    previous_rows = {}
    if (isinstance(previous_report, dict)
            and previous_report.get("validation_signature") == signature):
        previous_rows = {row["file"]: row for row in previous_report.get("games", [])
                         if isinstance(row, dict) and isinstance(row.get("file"), str)}
    rows: list[dict] = []
    seen: dict[int, str] = {}
    for path in sorted(input_dir.glob("replay-*.json"), key=lambda item: (len(item.stem), item.name)):
        row: dict = {"file": path.name}
        rows.append(row)
        try:
            raw = path.read_bytes()
            row["source_sha256"] = sha256(raw).hexdigest()
            document = json.loads(raw)
            if not isinstance(document, dict):
                raise ReplayInputError("최상위 값은 객체여야 합니다")
            setup = document.get("setup")
            if not isinstance(setup, dict):
                raise ReplayInputError("setup 객체가 없습니다")
            row["game_id"] = setup.get("game_id")
            if setup.get("scenario") != "Historical":
                row.update(status="unsupported", reason="scenario")
                continue
            options = setup.get("options", {})
            if not isinstance(options, dict):
                raise ReplayInputError("options 객체가 아닙니다")
            if any(key not in SUPPORTED_OPTIONS for key in options):
                row.update(status="unsupported", reason="options")
                continue
            source = load_replay(path)
            row["action_count"] = len(source.actions)
            final = document.get("state")
            if not isinstance(final, dict) or final.get("state") != "game_over":
                row.update(status="incomplete", reason="final_state")
                continue
            if source.actions[-1].name == ".timeout":
                row.update(status="unsupported", reason="timeout")
                continue
            previous = seen.get(source.game_id)
            if previous is not None:
                row.update(status="duplicate" if previous == row["source_sha256"] else "conflict",
                           reason="game_id")
                continue
            seen[source.game_id] = row["source_sha256"]
            cached = previous_rows.get(path.name)
            if (cached and cached.get("source_sha256") == row["source_sha256"]
                    and cached.get("status") in {"verified", "mismatch"}
                    and (cached["status"] != "verified"
                         or (output_dir / f"replay-{source.game_id}.json").is_file())):
                rows[-1] = cached.copy()
                continue
        except (OSError, UnicodeError, json.JSONDecodeError, ReplayInputError) as exc:
            row.update(status="invalid", reason=str(exc))
            continue

        try:
            result = run_replay(path, rules_path)
            row["checked_steps"] = result.checked_steps
            row["processed_steps"] = result.processed_steps
            if not result.ok:
                difference = result.first_difference
                row.update(status="mismatch", first_difference={
                    "index": difference.index, "action": difference.action,
                    "path": difference.path, "phase": difference.phase,
                    "expected": difference.expected, "actual": difference.actual,
                } if difference else None)
                continue
            if replay(result.initial_state, list(result.records)) != result.final_state:
                row.update(status="mismatch", first_difference={"path": "$.deterministic_replay"})
                continue
            row["status"] = "verified"
            row["normalized_file"] = f"replay-{source.game_id}.json"
            row["adjudicated_differences"] = [
                {"index": item.index, "path": item.path, "rule": item.rule}
                for item in result.adjudicated_differences]
            _write_json(output_dir / row["normalized_file"], {
                "schema_version": 1, "game_id": source.game_id,
                "source_sha256": row["source_sha256"],
                "initial_state": result.initial_state, "records": result.records,
                "adjudicated_differences": row["adjudicated_differences"],
            })
        except Exception as exc:
            row.update(status="error", reason=f"{type(exc).__name__}: {exc}")
    verified_ids = {row["game_id"] for row in rows if row["status"] == "verified"}
    if output_dir.is_dir():
        for artifact in output_dir.glob("replay-*.json"):
            match = re.fullmatch(r"replay-(\d+)\.json", artifact.name)
            if match and int(match.group(1)) not in verified_ids:
                artifact.unlink()
    return {"schema_version": 1, "validation_signature": signature,
            "input_count": len(rows),
            "counts": dict(sorted(Counter(row["status"] for row in rows).items())),
            "games": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="RTT 기보 일괄 검증·정규화")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true", help="이전 검사 결과를 재사용하지 않음")
    args = parser.parse_args()
    previous = None
    if args.report.is_file() and not args.refresh:
        try:
            previous = json.loads(args.report.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    report = validate_replays(args.input_dir, args.rules, args.output, previous)
    _write_json(args.report, report)
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
