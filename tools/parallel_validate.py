"""기존 RTT 배치 검증기를 게임 ID별 독립 프로세스로 실행한다."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from multiprocessing import get_context
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from pog_engine.rtt_replay.batch import _has_digest, _validation_signature, _write_json, validate_replays


def _candidate_files(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise ValueError(f"기보 폴더가 없습니다: {input_dir}")
    candidates = (path for path in input_dir.iterdir() if path.is_file()
                  and (path.name.startswith("replay-") and path.suffix == ".json"
                       or path.stem.isdigit() and path.suffix == ".json"))
    return sorted(candidates, key=lambda path: (len(path.stem), path.name))


def _game_id(path: Path) -> tuple[bool, object]:
    try:
        document = json.loads(path.read_bytes())
        setup = document.get("setup") if isinstance(document, dict) else None
        if not isinstance(setup, dict) or "game_id" not in setup:
            raise ValueError("게임 ID 없음")
        return True, setup["game_id"]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return False, None


def _shard_number(path: Path, workers: int) -> int:
    has_id, game_id = _game_id(path)
    if has_id:
        key = "id:" + json.dumps(game_id, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
    else:
        key = "file:" + path.name
    return int.from_bytes(sha256(key.encode("utf-8")).digest()[:8], "big") % workers


def _previous_for_files(previous_report: dict | None, files: list[Path]) -> dict | None:
    if not isinstance(previous_report, dict):
        return None
    current_ids = {}
    for path in files:
        has_id, game_id = _game_id(path)
        if has_id:
            current_ids[path.name] = game_id
    return {**previous_report, "games": [row for row in previous_report.get("games", [])
                                         if (isinstance(row, dict) and row.get("file") in current_ids
                                             and type(row.get("game_id")) is type(current_ids[row["file"]])
                                             and row.get("game_id") == current_ids[row["file"]])]}


def _run_shard(input_dir: Path, rules_path: Path, output_dir: Path,
               previous_report: dict | None) -> dict:
    return validate_replays(input_dir, rules_path, output_dir, previous_report)


def merge_shard_reports(reports: list[dict], assigned_files: list[list[str]],
                        ordered_files: list[str]) -> dict:
    """모든 입력이 정확히 한 번 처리됐고 검증 서명이 같을 때만 병합한다."""
    if len(reports) != len(assigned_files) or not reports:
        raise ValueError("샤드 보고서 수가 맞지 않습니다")
    signatures = {report.get("validation_signature") for report in reports}
    if len(signatures) != 1 or not next(iter(signatures)):
        raise ValueError("validation signature가 동일하지 않습니다")
    rows_by_file: dict[str, dict] = {}
    for report, assigned in zip(reports, assigned_files, strict=True):
        rows = report.get("games")
        if report.get("schema_version") != 1 or not isinstance(rows, list):
            raise ValueError("샤드 보고서 형식이 잘못되었습니다")
        names = [row.get("file") for row in rows if isinstance(row, dict)]
        if (report.get("input_count") != len(assigned) or len(names) != len(rows)
                or Counter(names) != Counter(assigned)):
            raise ValueError("샤드 결과의 입력 파일이 누락되거나 중복됐습니다")
        for row in rows:
            if row["file"] in rows_by_file:
                raise ValueError("샤드 사이에 중복 파일이 있습니다")
            rows_by_file[row["file"]] = row
    if len(ordered_files) != len(rows_by_file) or set(ordered_files) != set(rows_by_file):
        raise ValueError("병합 결과에 입력 파일이 누락되거나 추가됐습니다")
    rows = [rows_by_file[name] for name in ordered_files]
    return {"schema_version": 1, "validation_signature": next(iter(signatures)),
            "input_count": len(rows),
            "counts": dict(sorted(Counter(row["status"] for row in rows).items())),
            "games": rows}


def _cleanup_old_artifacts(previous_report: dict | None, report: dict,
                           output_dir: Path) -> None:
    if (not isinstance(previous_report, dict)
            or previous_report.get("validation_signature") != report["validation_signature"]):
        return
    verified_ids = {row["game_id"] for row in report["games"] if row["status"] == "verified"}
    for old in previous_report.get("games", []):
        if not isinstance(old, dict):
            continue
        game_id = old.get("game_id")
        if (old.get("status") == "verified" and isinstance(game_id, int)
                and game_id not in verified_ids):
            artifact = output_dir / f"replay-{game_id}.json"
            if _has_digest(artifact, old.get("normalized_sha256")):
                artifact.unlink()


def validate_parallel(input_dir: Path, rules_path: Path, output_dir: Path,
                      workers: int, previous_report: dict | None = None,
                      progress: Callable[[str], None] | None = None) -> dict:
    if workers < 1:
        raise ValueError("workers는 1 이상이어야 합니다")
    if not rules_path.is_file():
        raise ValueError(f"RTT rules.js가 없습니다: {rules_path}")
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("원본 기보 폴더와 정규화 출력 폴더를 분리해야 합니다")
    files = _candidate_files(input_dir)
    if not files:
        report = {"schema_version": 1, "validation_signature": _validation_signature(rules_path),
                  "input_count": 0, "counts": {}, "games": []}
        _cleanup_old_artifacts(previous_report, report, output_dir)
        return report
    groups: list[list[Path]] = [[] for _ in range(workers)]
    for path in files:
        groups[_shard_number(path, workers)].append(path)
    with TemporaryDirectory(prefix="pog-parallel-") as temporary:
        tasks = []
        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("fork")) as executor:
            for index, group in enumerate(groups):
                if not group:
                    continue
                shard_dir = Path(temporary) / str(index)
                shard_dir.mkdir()
                for path in group:
                    (shard_dir / path.name).symlink_to(path.resolve())
                names = [path.name for path in group]
                cached = _previous_for_files(previous_report, group)
                tasks.append((index, names, executor.submit(_run_shard, shard_dir, rules_path,
                                                            output_dir, cached)))
            reports = [None] * len(tasks)
            future_indices = {future: task_number for task_number, (_, _, future) in enumerate(tasks)}
            for future in as_completed(future_indices):
                task_number = future_indices[future]
                shard_number, names, _ = tasks[task_number]
                report = future.result()
                reports[task_number] = report
                if progress is not None:
                    progress(f"샤드 {shard_number + 1}/{workers}: "
                             f"{report['input_count']}개 처리, status counts "
                             f"{json.dumps(report['counts'], ensure_ascii=False, sort_keys=True)}")
        report = merge_shard_reports(reports, [names for _, names, _ in tasks],
                                     [path.name for path in files])
        _cleanup_old_artifacts(previous_report, report, output_dir)
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="RTT 기보 병렬 검증·정규화")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--refresh", action="store_true", help="이전 검사 결과를 재사용하지 않음")
    args = parser.parse_args()
    previous = None
    if args.report.is_file() and not args.refresh:
        try:
            previous = json.loads(args.report.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    report = validate_parallel(args.input_dir, args.rules, args.output, args.workers, previous,
                               progress=lambda message: print(message, flush=True))
    _write_json(args.report, report)
    print(f"전체 병합: {report['input_count']}개 처리, status counts "
          f"{json.dumps(report['counts'], ensure_ascii=False, sort_keys=True)}", flush=True)


if __name__ == "__main__":
    main()
