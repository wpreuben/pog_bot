# Paths of Glory Historical 게임 엔진

2022 Deluxe 규칙의 Historical 캠페인을 진행하는 Python 규칙 엔진이다. 화면이나 AI 정책에 의존하지 않으며 상태, 합법 행동, 상태 전이를 JSON으로 저장할 수 있다.

## 실행

```bash
uv sync --group dev
uv run pytest -q
```

## 공개 API

```python
from pog_engine import apply_action, create_game, game_result, generate_legal_actions, get_player_view
from pog_engine.replay import replay

initial = create_game(seed=42)
state = initial
records = []

while game_result(state) is None or state["phase"] != "GAME_OVER":
    actions = generate_legal_actions(state)
    action = choose_action(actions)  # 사람 또는 AI가 합법 행동 하나를 고른다.
    transition = apply_action(state, action)
    state = transition.state
    records.append(transition.record)

assert replay(initial, records) == state
visible = get_player_view(state, "AP")
```

자동 단계에도 `ADVANCE_AUTOMATIC_PHASE`라는 합법 행동이 주어진다. `CHANCE` 행위자의 주사위 행동은 1~6 중 하나를 선택하며, 선택한 값이 기록의 `random_input`에 저장된다. `get_player_view`는 자기 손패와 공개 정보만 제공하고 상대 손패, 덱 순서, RNG 상태를 숨긴다.

현재 지원 범위는 Historical 기본 캠페인과 기본 카드 110장이다. 추가 시나리오와 Valiant 덱은 포함하지 않는다. 규칙 범위와 자료 출처는 [검증표](docs/rules-coverage.md), 영문 룰북과 RTT 구현의 확인된 차이는 [차이 기록](docs/rule-differences.md)에 정리했다.

## RTT JSON 기보 재현

258629번 Historical 게임의 익명화된 JSON 기보를 RTT 참고 엔진과 함께 재현하는 검증기가 있다. `RTT_RULES_PATH`에 별도로 보관한 RTT `rules.js` 경로를 지정하고 `uv run pytest tests/test_rtt_runner.py -q`를 실행한다. 완료 기준은 1,447개 입력의 종료까지 합법 행동 적용, 8턴·VP 7·AP 승리, 그리고 Python 전이 기록의 결정적 재생이다. 실행 방법과 판정 차이는 [RTT 검증 기록](docs/rtt-validation.md)에 정리했다.

여러 RTT JSON 기보는 `python -m pog_engine.rtt_replay.batch`로 일괄 검사한다. 입력 폴더의 `<게임 ID>.json`과 `replay-*.json`을 Historical 기본 캠페인 지원 범위에 따라 분류하고, 재현에 성공한 게임의 익명화된 엔진 초기 상태와 행동 기록을 저장한다. 실행 명령과 결과 형식은 [일괄 검증 안내](docs/rtt-batch-validation.md)에 정리했다.
