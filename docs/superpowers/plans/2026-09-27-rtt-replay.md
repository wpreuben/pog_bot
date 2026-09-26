# RTT JSON 기보 교차 재현 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 258629번 Historical JSON 기보를 Python 엔진의 합법 행동으로 종료까지 재현하고 RTT와 의미 상태를 대조한다.

**Architecture:** 이름을 제거한 JSON 입력을 Node 기반 RTT 관측기로 재생해 행동별 상태를 얻는다. Python 측에서 ID·상태를 정규화하고 확정된 입력을 합법 행동에 연결하며, 첫 차이 보고와 `Transition.record` 재생으로 결과를 검증한다.

**Tech Stack:** Python 3.12+, uv, pytest, Node.js(CommonJS), 제공된 RTT `rules.js`.

**Spec:** `docs/superpowers/specs/2026-09-27-rtt-replay-design.md`

## Global Constraints

- 규칙 기준은 2022 Deluxe 영문 룰북이며 RTT는 관측 자료다.
- 입력은 `replays/replay-258629.json`의 Historical 게임 1,447개 행동이다. `undo` 85개와 마지막 `.resign`을 포함한다.
- `players` 이름과 불필요한 원본 상태는 커밋하지 않는다. 테스트용 자료는 이름을 제거한다.
- Python 엔진은 `create_game`, `generate_legal_actions`, `apply_action`, `replay` 공개 계약을 사용하며 일반 초기화의 난수 알고리즘은 바꾸지 않는다.
- RTT `rules.js` 경로는 실행 시 명시적으로 받으며 외부 RTT 폴더를 저장소에 복사하지 않는다.
- 최종 턴 8, VP 7, CP 항복, AP 승리를 Python 합법 행동과 상태 투영으로 확인한다.
- 작업은 기존 `feat/historical-engine`의 격리된 worktree에서 하고 `uv`로 테스트한다.

## Review Focus

- 잘못된 역할·알 수 없는 RTT ID가 들어오면 원본 행동 인덱스를 가진 오류가 나야 한다(Task 1, 3).
- RTT가 중간 선택을 되돌리면 Python 상태가 변경되지 않아야 한다(Task 4).
- 같은 이름의 복수 군단은 개별 ID를 보존해야 한다(Task 3, 5).
- 주사위 관측이 없거나 여러 굴림에 모호하게 대응하면 추정하지 않고 실패해야 한다(Task 4, 6).
- RTT와 룰북이 다른 결과를 낼 때 보고서가 첫 차이와 근거를 보존해야 한다(Task 8).

---

## 파일 경계

| 파일 | 책임 |
| --- | --- |
| `tests/fixtures/replay-258629.json` | `players`와 불필요한 원본 최종 상태를 뺀 고정 기보 |
| `tools/rtt_trace.cjs` | RTT `rules.js`를 호출해 입력별 관측을 JSON Lines로 출력 |
| `src/pog_engine/rtt_replay/input.py` | 기보 형식 검사와 행동 인덱스 보존 |
| `src/pog_engine/rtt_replay/ids.py` | `source_ids.json`의 숫자 ID ↔ 엔진 ID 검증 |
| `src/pog_engine/rtt_replay/projection.py` | 양쪽 상태의 의미 필드 투영과 첫 차이 |
| `src/pog_engine/rtt_replay/normalize.py` | `undo`가 반영된 RTT 미세 입력을 확정 선택으로 정제 |
| `src/pog_engine/rtt_replay/bootstrap.py` | RTT 첫 상태의 카드 순서와 초기 의미 상태를 Python에 대응 |
| `src/pog_engine/rtt_replay/translate.py` | 정제 선택을 현재 Python 합법 행동 중 하나로 매칭 |
| `src/pog_engine/rtt_replay/runner.py` | RTT 관측, Python 전이, 단계별 비교, 재생 기록, 보고서 |
| `src/pog_engine/engine.py`, `src/pog_engine/rules/victory.py` | 합법적인 `RESIGN`과 종료 결과 |
| `tests/test_rtt_*.py` | 각 경계와 전체 게임 회귀 테스트 |

### Task 1: 기보 형식과 이름 없는 fixture

**Files:** Create `src/pog_engine/rtt_replay/__init__.py`, `src/pog_engine/rtt_replay/input.py`, `tests/fixtures/replay-258629.json`, `tests/test_rtt_input.py`.

**Interfaces:** `load_replay(path: Path) -> ReplayInput`; `ReplayInput`에는 `game_id: int`, `seed: int`, `scenario: str`, `options: dict`, `actions: tuple[ReplayStep, ...]`; `ReplayStep`에는 `index`, `role`, `name`, `argument`를 둔다.

- [ ] **Step 1: 실패 테스트 작성.** 이름 없는 fixture의 행동 수 1,447·첫 시드 10762091171·시나리오 Historical·마지막 `.resign`을 검증한다. 잘못된 역할과 잘못된 배열에는 인덱스를 포함한 `ReplayInputError`가 나야 한다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_input.py -q` → 새 모듈 없음으로 실패.
- [ ] **Step 3: 최소 구현.** 원본 `/home/pc/project/pog_bot/replays/replay-258629.json`에서 `setup`과 `replay`만 복사해 fixture를 만들고, `input.py`에서 JSON과 모든 행동 구조를 검증한다. `players`와 전체 `state`를 복사하지 않는다.
- [ ] **Step 4: 통과 확인.** 같은 테스트 명령 → 통과; fixture에 `players` 키가 없음을 확인한다.
- [ ] **Step 5: 커밋.** `git add src/pog_engine/rtt_replay tests/fixtures/replay-258629.json tests/test_rtt_input.py && git commit -m 'feat: RTT 재생 입력 검증 추가'`.

### Task 2: RTT 원본 재생 관측기

**Files:** Create `tools/rtt_trace.cjs`, `tests/test_rtt_trace.py`.

**Interfaces:** `node tools/rtt_trace.cjs <fixture-path> <rules.js-path>`는 표준 출력에 입력별 `{index, role, name, before, after, log_delta}` JSON Lines를 쓰고, 마지막 줄에 `{kind:"final", turn, vp, state, victory, seed}`를 쓴다. 에러는 표준 오류와 0이 아닌 종료 코드로 낸다.

- [ ] **Step 1: 실패 테스트 작성.** fixture로 도구를 실행해 1,447개 관측과 최종 턴 8·VP 7·`game_over`·`Central Powers resigned.`를 확인한다. 파손된 행동은 인덱스가 있는 오류를 낸다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_trace.py -q` → 도구 없음으로 실패.
- [ ] **Step 3: 최소 구현.** `rules.js`의 `setup`·`action`·`resign`을 순서대로 호출한다. 관측은 필요한 필드만 포함하고 RTT 소스를 수정하지 않는다. 전체 원본 JSON이 있을 때 내보낸 최종 상태와 플랫폼 표현 차이(`active`, `result`, 로그 공백)만 정규화해 별도 검사한다.
- [ ] **Step 4: 통과 확인.** 해당 pytest와 `node tools/rtt_trace.cjs tests/fixtures/replay-258629.json '/home/pc/project/pog_bot/Rally the Troops_paths-of-glory-master/rules.js' | tail -1` → 최종 요약 일치.
- [ ] **Step 5: 커밋.** `git add tools/rtt_trace.cjs tests/test_rtt_trace.py && git commit -m 'feat: RTT 기보 관측기 추가'`.

### Task 3: ID와 의미 상태 투영

**Files:** Create `src/pog_engine/rtt_replay/ids.py`, `src/pog_engine/rtt_replay/projection.py`, `tests/test_rtt_projection.py`.

**Interfaces:** `SourceIds.from_data() -> SourceIds`; `SourceIds.lookup(kind: str, source_id: int) -> str`; `project_rtt(state: dict, ids: SourceIds) -> dict`; `project_engine(state: FullGameState) -> dict`; `first_difference(expected: dict, actual: dict) -> Difference | None`.

- [ ] **Step 1: 실패 테스트 작성.** 카드 66 → `GUNS_OF_AUGUST`, 복수 군단 ID는 서로 다른 ID, 첫 턴 VP·유닛 위치·공간 통제 투영 일치를 검사한다. 알 수 없는 ID에는 종류와 인덱스 문맥을 가진 오류를 확인한다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_projection.py -q` → 새 함수 없음으로 실패.
- [ ] **Step 3: 최소 구현.** 기존 `source_ids.json`을 읽고 양쪽 상태에서 동일한 의미 필드만 투영한다. 리스트 순서가 규칙상 무의미한 곳만 정렬한다. `first_difference`는 가장 앞의 JSON 경로와 양쪽 값을 반환한다.
- [ ] **Step 4: 통과 확인.** 해당 pytest → 통과.
- [ ] **Step 5: 커밋.** `git add src/pog_engine/rtt_replay/ids.py src/pog_engine/rtt_replay/projection.py tests/test_rtt_projection.py && git commit -m 'feat: RTT 상태와 ID 대조 추가'`.

### Task 4: 초기 카드 순서와 확정 선택 정제

**Files:** Create `src/pog_engine/rtt_replay/bootstrap.py`, `src/pog_engine/rtt_replay/normalize.py`, `tests/test_rtt_normalize.py`.

**Interfaces:** `bootstrap_historical(seed: int, rtt_setup_state: dict, ids: SourceIds) -> FullGameState`; `normalize_steps(steps: tuple[ReplayStep, ...], observations: Iterable[dict]) -> tuple[Intent, ...]`; `Intent`는 원본 인덱스 범위·역할·의미 종류·RTT 전후 투영·관측 난수를 가진다.

- [ ] **Step 1: 실패 테스트 작성.** 초기 손패·덱이 RTT와 같은 순서이고 지도·유닛 차이는 숨기지 않음을 확인한다. `play_ops → undo → play_event`는 `play_event`만 확정하며 원본 인덱스를 보존한다. 난수 관측이 빠지거나 모호하면 오류를 낸다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_normalize.py -q` → 새 함수 없음으로 실패.
- [ ] **Step 3: 최소 구현.** RTT 첫 관측 상태에서 카드 배열을 ID 변환해 `create_game(seed)` 복사본에 넣는다. `undo` 이후 RTT 상태로 돌아간 선택을 버리고 확정 경계를 RTT 상태 전이와 행동 종류로 판정한다. RNG 호출·주사위는 관측기에서 추적해 `Intent`에 기록한다.
- [ ] **Step 4: 통과 확인.** 해당 pytest → 통과; 제공 기보 전체에서 `undo` 85개가 처리되는지 확인한다.
- [ ] **Step 5: 커밋.** `git add src/pog_engine/rtt_replay/bootstrap.py src/pog_engine/rtt_replay/normalize.py tests/test_rtt_normalize.py tools/rtt_trace.cjs && git commit -m 'feat: RTT 확정 행동과 초기 순서 정제'`.

### Task 5: 카드·OPS·이동·SR·RP 번역

**Files:** Create `src/pog_engine/rtt_replay/translate.py`, `tests/test_rtt_translate.py`.

**Interfaces:** `translate_intent(state: FullGameState, intent: Intent, ids: SourceIds) -> tuple[Action, ...]`; 반환하는 모든 행동은 각 적용 시점의 `generate_legal_actions`에 포함되어야 한다.

- [ ] **Step 1: 실패 테스트 작성.** 첫 `play_event 66`, OPS 카드, `activate_move`·`piece`·`space`·`done`, SR, RP 각각을 실제 기보 구간에서 추출해 예상 Python 행동형과 RTT ID 대응을 확인한다. 동일한 군단 둘 중 하나를 선택한 기록은 정확한 개별 ID에만 매칭한다. 후보 0개·복수에는 진단 오류를 확인한다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_translate.py -q` → 번역기 없음으로 실패.
- [ ] **Step 3: 최소 구현.** RTT 의미 종류별 어댑터를 작성하고 현재 Python 합법 행동만 후보로 사용한다. `end_rp`, `end_action`, `next`, `stop`, `pass`와 자동 단계도 현재 결정 창에 맞춰 처리한다. 임의의 합법 행동을 기본값으로 선택하지 않는다.
- [ ] **Step 4: 통과 확인.** 해당 pytest → 통과.
- [ ] **Step 5: 커밋.** `git add src/pog_engine/rtt_replay/translate.py tests/test_rtt_translate.py && git commit -m 'feat: RTT 카드와 작전 행동 번역'`.

### Task 6: 전투·주사위·이벤트 선택 번역

**Files:** Modify `src/pog_engine/rtt_replay/translate.py`, `src/pog_engine/rtt_replay/normalize.py`, `tools/rtt_trace.cjs`; create `tests/test_rtt_combat_translate.py`.

**Interfaces:** Task 5의 `translate_intent`를 유지한다. 전투 선택과 굴림은 `Intent`의 관측값을 소비하며 `CHANCE` 행동에는 명시적 `value`를 넣는다.

- [ ] **Step 1: 실패 테스트 작성.** 첫 Sedan 전투에서 공격 선언·측면 공격·양측 주사위·손실·후퇴·진격을 실제 RTT 입력 범위와 Python 행동에 대응시킨다. 전투 카드의 `card`·`done`과 참호·공성·이벤트 추가 선택도 기보에 등장하는 구간에서 검사한다. 난수가 누락되면 정지한다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_combat_translate.py -q` → 해당 대응 실패.
- [ ] **Step 3: 최소 구현.** RTT의 공격 선택 상태와 로그·RNG 관측을 사용해 순서 있는 Python 합법 행동으로 변환한다. 미세 입력 `attack`, `flank`, `confirm_pass_attack`, `entrench`, `select_all`을 해당 선택 창과 연결한다.
- [ ] **Step 4: 통과 확인.** 해당 pytest → 통과.
- [ ] **Step 5: 커밋.** `git add src/pog_engine/rtt_replay/translate.py src/pog_engine/rtt_replay/normalize.py tools/rtt_trace.cjs tests/test_rtt_combat_translate.py && git commit -m 'feat: RTT 전투와 난수 선택 번역'`.

### Task 7: 항복의 합법 행동과 종료 결과

**Files:** Modify `src/pog_engine/engine.py`, `src/pog_engine/rules/victory.py`, `tests/test_engine_contract.py`.

**Interfaces:** `RESIGN`은 현재 살아 있는 게임의 AP 또는 CP가 선택할 수 있고, 적용 후 `game_result`는 상대 승리를 반환한다. Task 8의 `run_replay`가 마지막 `.resign`을 이 행동으로 처리한다.

- [ ] **Step 1: 실패 테스트 작성.** CP의 `RESIGN`이 합법 행동이며 AP 승리로 종료되고 `replay`로 재현됨을 검사한다. 종료 후 재항복은 불법이다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_engine_contract.py -q` → 항복 행동 부재로 실패.
- [ ] **Step 3: 최소 구현.** 모든 진행 단계에서 현재 측의 항복을 합법 행동에 포함하고, 적용 시 종료 결과와 종료 단계를 설정한다. 기존 승리 결과 자료형을 따른다.
- [ ] **Step 4: 통과 확인.** 해당 pytest → 통과.
- [ ] **Step 5: 커밋.** `git add src/pog_engine/engine.py src/pog_engine/rules/victory.py tests/test_engine_contract.py && git commit -m 'feat: 항복 행동 추가'`.

### Task 8: 차이 보고와 전체 게임 반복 대조

**Files:** Create `src/pog_engine/rtt_replay/runner.py`, `tests/test_rtt_runner.py`, `docs/rtt-differences.md`; modify 발견된 해당 `src/pog_engine/rules/*.py`와 가까운 회귀 테스트.

**Interfaces:** `run_replay(path: Path, rules_path: Path) -> ReplayReport`; `ReplayReport`에는 `ok`, `processed_steps`, `records`, `final_state`, `first_difference`가 있다. 실패 보고에는 원본 인덱스·행동·Python 단계·합법 후보·첫 상태 경로·기대값·실제값을 담는다.

- [ ] **Step 1: 실패 테스트 작성.** 인위적으로 바꾼 VP는 `$.vp`를 첫 차이로 보고한다. 실제 fixture는 마지막 행동까지 처리해 종료 결과를 일치시킨다. 룰북 차이가 생기면 조항·관측을 `docs/rtt-differences.md`에 기록한다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_runner.py -q` → 실행기 없음으로 실패.
- [ ] **Step 3: 최소 구현.** RTT 관측과 정제 선택을 순차 적용해 의미 경계마다 투영 상태를 비교한다. 첫 불일치마다 그 지점만 재현하는 테스트를 추가하고 공식 룰북으로 판정해 해당 규칙 또는 번역을 수정한다. 이 절차를 1,447번째 입력까지 반복한다. 규칙 차이를 조용히 동등 처리하지 않는다.
- [ ] **Step 4: 통과 확인.** 해당 pytest → 전체 기보 종료까지 통과; `replay(initial_state, report.records) == report.final_state` 확인.
- [ ] **Step 5: 커밋.** `git add src/pog_engine/rtt_replay/runner.py tests/test_rtt_runner.py src/pog_engine/rules tests docs/rtt-differences.md && git commit -m 'feat: RTT 전체 게임 교차 재현'`.

### Task 9: LOG1 정리와 전체 검증

**Files:** Rename `tests/test_log1_regression.py` to `tests/test_historical_regression.py`; create `docs/rtt-validation.md`; modify `README.md`; delete `tests/fixtures/LOG1.txt`, `docs/log1-validation.md`.

**Interfaces:** Task 8의 JSON 전체 게임 검증을 우선 회귀 자료로 사용하고, LOG1에서 발견한 개별 규칙 사례는 파일 의존 없는 테스트로 보존한다.

- [ ] **Step 1: 실패 테스트 작성.** 기존 규칙 전이 검사를 원문 문자열 단언 없이 실행한다. 저장소에 `LOG1.txt`가 없음을 검사한다.
- [ ] **Step 2: 실패 확인.** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_log1_regression.py -q` → 원문 파일 의존으로 실패.
- [ ] **Step 3: 최소 구현.** 원문에서만 얻는 정적 카드·CRT 검사는 제거하고 실제 규칙 전이 검사는 유지한다. LOG1 파일과 문서는 지우고 JSON 재현 방법·결과를 `docs/rtt-validation.md`에 기록한다.
- [ ] **Step 4: 전체 검증.** `UV_CACHE_DIR=.uv-cache uv run pytest -q`, `UV_CACHE_DIR=.uv-cache uv lock --check`, `git diff --check`가 통과하고 최종 턴 8·VP 7·AP 승리를 확인한다.
- [ ] **Step 5: 커밋.** `git add tests docs README.md && git commit -m 'test: JSON 기보 중심으로 회귀 자료 정리'`.

## 완료 후

`superpowers:verification-before-completion`로 실제 전체 테스트와 저장소 상태를 확인하고, 코드 리뷰 후 요청받은 GitHub 원격 브랜치에 푸시한다. 원본 JSON은 사용자 작업 폴더에 남겨 둔다.
