# RTT JSON 기보 재현 검증

## 입력과 실행

`tests/fixtures/replay-258629.json`은 258629번 Historical 기보에서 참가자 이름을 제거한 고정 입력이다. 원본 `replays/replay-258629.json`은 Git에 넣지 않는다. RTT 참조 엔진은 별도 폴더의 `rules.js`를 사용한다.

```bash
cd /home/pc/project/pog_bot/.worktrees/historical-engine
export RTT_RULES_PATH=/home/pc/project/pog_bot/'Rally the Troops_paths-of-glory-master'/rules.js
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_rtt_runner.py -q
UV_CACHE_DIR=.uv-cache uv run pytest -q
```

다른 위치에서 실행할 때는 첫 줄의 작업 폴더와 `RTT_RULES_PATH`를 실제 경로로 바꾸면 된다. 테스트는 일반 체크아웃 또는 `.worktrees`의 상위 폴더에 RTT 참조 엔진이 있으면 이를 자동 탐색한다. Node.js와 `uv`가 필요하다.

Python에서 직접 보고서를 얻는 방법:

```python
from pathlib import Path
from pog_engine.replay import replay
from pog_engine.rtt_replay.runner import run_replay

report = run_replay(
    Path("tests/fixtures/replay-258629.json"),
    Path("/실제/RTT/폴더/rules.js"),
)
assert report.ok, report.first_difference
assert report.processed_steps == 1447
assert replay(report.initial_state, list(report.records)) == report.final_state
print(report.final_state["turn"], report.final_state["vp"], report.final_state["result"])
print(report.adjudicated_differences)
```

## 검증 결과

RTT 입력 1,447개에는 되돌리기 85회와 마지막 항복이 포함된다. 되돌리기를 정제한 뒤 각 선택을 Python 엔진의 합법 행동으로 적용한다. RTT의 행동 단계와 종료 상태에서 보드, 유닛, 카드 구역, 전쟁 상태, 참여 수준, VP, 승자를 대조한다. 적용된 Python 행동 기록은 `replay(initial_state, records)`로 같은 최종 상태를 재현한다.

최종 상태는 8턴, VP 7, CP 항복에 따른 AP 승리다. 공식 영문 룰북을 우선한 아라비아 보급 판정과 RTT 항복 승자 필드의 모순은 [차이 기록](rtt-differences.md)에 입력 번호와 근거를 남겼다. `ReplayReport.adjudicated_differences`에서도 두 차이를 확인할 수 있다. 다른 불일치는 첫 원본 입력 번호, 상태 경로, RTT 기대값, Python 실제값, 합법 행동 후보를 담은 `first_difference`로 보고된다.

기존 LOG1 문자열 회귀 검사는 제거했다. 후퇴 취소, 두 칸 후퇴 뒤 진격, 유닛별 후퇴 등 실제 규칙 전이 사례는 `tests/test_historical_regression.py`에서 입력 파일 없이 계속 검사한다.
