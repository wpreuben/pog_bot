"""기존 RTT 배치 검증기를 게임 ID별 독립 프로세스로 실행한다."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
from multiprocessing import get_context
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from pog_engine.rtt_replay.batch import _has_digest, _validation_signature, _write_json, validate_replays


SHARD_COUNT = 64


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


def _manifest(files: list[Path]) -> tuple[str, dict[str, str]]:
    digest = sha256()
    sources = {}
    for path in files:
        source_hash = sha256(path.read_bytes()).hexdigest()
        sources[path.name] = source_hash
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), sources


def _checkpoint_payload(report: dict, signature: str, manifest: str,
                        complete: bool) -> dict:
    return {"schema_version": 1, "validation_signature": signature,
            "manifest_sha256": manifest, "complete": complete, "report": report}


def _load_checkpoint(path: Path, signature: str, manifest: str,
                     names: list[str], sources: dict[str, str], output_dir: Path
                     ) -> tuple[dict, bool] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        report = payload["report"]
        rows = report["games"]
        if (payload.get("schema_version") != 1
                or payload.get("validation_signature") != signature
                or payload.get("manifest_sha256") != manifest
                or report.get("schema_version") != 1
                or report.get("validation_signature") != signature
                or not isinstance(rows, list)
                or report.get("input_count") != len(rows)
                or len(rows) > len(names)
                or [row["file"] for row in rows] != names[:len(rows)]
                or any(row.get("source_sha256") != sources[row["file"]] for row in rows)
                or report.get("counts") != dict(sorted(Counter(row["status"] for row in rows).items()))):
            return None
        complete = payload.get("complete") is True
        if complete and (len(rows) != len(names) or any(
                row["status"] == "verified"
                and not _has_digest(output_dir / f"replay-{row['game_id']}.json",
                                    row.get("normalized_sha256")) for row in rows)):
            return None
        return report, complete
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _run_shard(input_dir: Path, rules_path: Path, output_dir: Path,
               previous_report: dict | None, checkpoint_path: Path | None,
               signature: str, manifest: str, shard_index: int) -> dict:
    if checkpoint_path is None:
        return validate_replays(input_dir, rules_path, output_dir, previous_report)

    def save_checkpoint(partial: dict) -> None:
        _write_json(checkpoint_path, _checkpoint_payload(partial, signature, manifest, False))
        print(f"샤드 {shard_index + 1}/{SHARD_COUNT}: "
              f"{partial['input_count']}개 체크포인트, status counts "
              f"{json.dumps(partial['counts'], ensure_ascii=False, sort_keys=True)}", flush=True)

    report = validate_replays(input_dir, rules_path, output_dir, previous_report, save_checkpoint)
    if report["validation_signature"] != signature:
        raise ValueError("검증 중 rules/engine 서명이 변경됐습니다")
    _write_json(checkpoint_path, _checkpoint_payload(report, signature, manifest, True))
    return report


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


def _combine_cached(previous: dict | None, partial: dict | None,
                    signature: str) -> dict | None:
    rows = {}
    for report in (previous, partial):
        if isinstance(report, dict) and report.get("validation_signature") == signature:
            rows.update((row["file"], row) for row in report.get("games", [])
                        if isinstance(row, dict) and isinstance(row.get("file"), str))
    return {"validation_signature": signature, "games": list(rows.values())} if rows else None


def _cleanup_history(previous_report: dict | None, checkpoint_dir: Path | None,
                     signature: str) -> dict | None:
    rows = []
    if (isinstance(previous_report, dict)
            and previous_report.get("validation_signature") == signature):
        rows.extend(row for row in previous_report.get("games", []) if isinstance(row, dict))
    if checkpoint_dir is not None and checkpoint_dir.is_dir():
        for path in checkpoint_dir.glob("shard-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                report = payload["report"]
                if (payload.get("validation_signature") == signature
                        and report.get("validation_signature") == signature):
                    rows.extend(row for row in report["games"] if isinstance(row, dict))
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
                continue
    return {"validation_signature": signature, "games": rows} if rows else None


def validate_parallel(input_dir: Path, rules_path: Path, output_dir: Path,
                      workers: int, previous_report: dict | None = None,
                      progress: Callable[[str], None] | None = None,
                      checkpoint_dir: Path | None = None) -> dict:
    if workers < 1:
        raise ValueError("workers는 1 이상이어야 합니다")
    if not rules_path.is_file():
        raise ValueError(f"RTT rules.js가 없습니다: {rules_path}")
    if input_dir.resolve() == output_dir.resolve():
        raise ValueError("원본 기보 폴더와 정규화 출력 폴더를 분리해야 합니다")
    signature = _validation_signature(rules_path)
    cleanup_history = _cleanup_history(previous_report, checkpoint_dir, signature)
    files = _candidate_files(input_dir)
    if not files:
        report = {"schema_version": 1, "validation_signature": signature,
                  "input_count": 0, "counts": {}, "games": []}
        _cleanup_old_artifacts(cleanup_history, report, output_dir)
        return report
    if checkpoint_dir is not None:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
    groups: list[list[Path]] = [[] for _ in range(SHARD_COUNT)]
    for path in files:
        groups[_shard_number(path, SHARD_COUNT)].append(path)
    with TemporaryDirectory(prefix="pog-parallel-") as temporary:
        tasks = []
        resuming = set()
        input_hashes = {}
        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("fork")) as executor:
            for index, group in enumerate(groups):
                if not group:
                    continue
                names = [path.name for path in group]
                manifest, sources = _manifest(group)
                input_hashes.update(sources)
                checkpoint_path = (checkpoint_dir / f"shard-{index:03d}.json"
                                   if checkpoint_dir is not None else None)
                checkpoint = (_load_checkpoint(checkpoint_path, signature, manifest, names,
                                               sources, output_dir)
                              if checkpoint_path is not None and checkpoint_path.is_file() else None)
                if checkpoint_path is not None and checkpoint_path.is_file() and checkpoint is None:
                    if progress is not None:
                        progress(f"체크포인트 무효: 샤드 {index + 1}/{SHARD_COUNT}")
                if checkpoint is not None and checkpoint[1]:
                    tasks.append((index, names, None, checkpoint[0]))
                    if progress is not None:
                        progress(f"체크포인트 재사용: 샤드 {index + 1}/{SHARD_COUNT}, "
                                 f"{checkpoint[0]['input_count']}개 처리, status counts "
                                 f"{json.dumps(checkpoint[0]['counts'], ensure_ascii=False, sort_keys=True)}")
                    continue
                shard_dir = Path(temporary) / str(index)
                shard_dir.mkdir()
                for path in group:
                    (shard_dir / path.name).symlink_to(path.resolve())
                cached = _previous_for_files(previous_report, group)
                cached = _combine_cached(cached, checkpoint[0] if checkpoint else None, signature)
                future = executor.submit(_run_shard, shard_dir, rules_path, output_dir, cached,
                                         checkpoint_path, signature, manifest, index)
                if checkpoint is not None:
                    resuming.add(len(tasks))
                tasks.append((index, names, future, None))
            reports = [cached_report for _, _, _, cached_report in tasks]
            future_indices = {future: task_number for task_number, (_, _, future, _) in enumerate(tasks)
                              if future is not None}
            for future in as_completed(future_indices):
                task_number = future_indices[future]
                shard_number, names, _, _ = tasks[task_number]
                report = future.result()
                reports[task_number] = report
                if progress is not None:
                    progress(f"{'체크포인트 재개: ' if task_number in resuming else ''}"
                             f"샤드 {shard_number + 1}/{SHARD_COUNT}: "
                             f"{report['input_count']}개 처리, status counts "
                             f"{json.dumps(report['counts'], ensure_ascii=False, sort_keys=True)}")
        report = merge_shard_reports(reports, [names for _, names, _, _ in tasks],
                                     [path.name for path in files])
        if (report["validation_signature"] != signature
                or _validation_signature(rules_path) != signature):
            raise ValueError("검증 중 rules/engine 서명이 변경됐습니다")
        if ([path.name for path in _candidate_files(input_dir)] != [path.name for path in files]
                or any(sha256(path.read_bytes()).hexdigest() != input_hashes[path.name]
                       for path in files)):
            raise ValueError("검증 중 입력 파일 목록 또는 내용이 변경됐습니다")
        _cleanup_old_artifacts(cleanup_history, report, output_dir)
        return report


@contextmanager
def _path_lock(path: Path):
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"이미 같은 경로를 검증 중입니다: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser(description="RTT 기보 병렬 검증·정규화")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--refresh", action="store_true",
                        help="기존 보고서·체크포인트를 무시하고 새 검증 시작(재개할 때는 제외)")
    args = parser.parse_args()
    output_lock = args.output.with_name(f".{args.output.name}.parallel-validate")
    with _path_lock(args.report), _path_lock(output_lock):
        checkpoint_dir = args.report.with_name(f".{args.report.name}.shards")
        marker = checkpoint_dir / "run.json"
        if args.refresh and checkpoint_dir.is_dir():
            for path in checkpoint_dir.glob("shard-*.json"):
                path.unlink()
        if args.refresh:
            _write_json(marker, {"schema_version": 1,
                                 "validation_signature": _validation_signature(args.rules),
                                 "refresh": True})
        resume_refresh = False
        if marker.is_file():
            state = json.loads(marker.read_text(encoding="utf-8"))
            resume_refresh = (state.get("schema_version") == 1
                              and state.get("validation_signature") == _validation_signature(args.rules)
                              and state.get("refresh") is True)
        previous = None
        if args.report.is_file() and not args.refresh and not resume_refresh:
            try:
                previous = json.loads(args.report.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        report = validate_parallel(args.input_dir, args.rules, args.output, args.workers, previous,
                                   progress=lambda message: print(message, flush=True),
                                   checkpoint_dir=checkpoint_dir)
        _write_json(args.report, report)
        marker.unlink(missing_ok=True)
        print(f"전체 병합: {report['input_count']}개 처리, status counts "
              f"{json.dumps(report['counts'], ensure_ascii=False, sort_keys=True)}", flush=True)


if __name__ == "__main__":
    main()
