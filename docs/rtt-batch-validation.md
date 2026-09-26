# RTT 기보 일괄 검증·정규화

## 실행

프로젝트 루트에서 실행한다. `replays/`에는 RTT에서 내려받은 `<게임 ID>.json` 또는 `replay-<게임 ID>.json`을 둔다. `:Zone.Identifier` 파일은 무시한다.

```bash
UV_CACHE_DIR=.uv-cache uv run python -m pog_engine.rtt_replay.batch \
  /home/pc/project/pog_bot/replays \
  --rules '/home/pc/project/pog_bot/Rally the Troops_paths-of-glory-master/rules.js' \
  --output /home/pc/project/pog_bot/replays/normalized \
  --report /home/pc/project/pog_bot/replays/validation-report.json
```

다른 PC에서는 경로를 실제 위치로 바꾼다. 10개마다 보고서를 저장하므로 중단 후 재실행하면 이전 결과를 재사용한다. 입력 파일, Python 코드·규칙 데이터 JSON, RTT `rules.js`·`data.js`·`lz4.js`, 정규화 결과의 SHA-256이 같을 때 `verified` 결과를 재사용한다. 전체를 다시 검사하려면 `--refresh`를 붙인다. 다운로드 중인 파일은 `invalid`로 표시될 수 있으며, 파일 내용이 바뀐 뒤 다시 실행하면 재검사한다. 입력은 읽은 직후 임시 스냅샷으로 고정해 검사한다.

보고서 `games`에는 게임 ID, 원본 파일명, SHA-256, 행동 수, 검사 상태가 들어간다. `mismatch`는 첫 원본 행동 인덱스와 상태 경로·기대값·실제값을 기록한다. 상태는 다음과 같다.

| 상태 | 뜻 |
| --- | --- |
| `verified` | RTT·Python 의미 상태와 결정적 행동 재생 검증 완료 |
| `mismatch` | 두 엔진의 첫 행동 또는 상태 불일치 |
| `error` | RTT 관측 또는 변환 중 예외 발생 |
| `invalid` | JSON 또는 입력 형식 오류 |
| `incomplete` | RTT 최종 상태가 `game_over`가 아님 |
| `unsupported` | Historical 외 시나리오, 지원하지 않는 옵션 또는 `.timeout` 종료 |
| `duplicate` / `conflict` | 같은 게임 ID의 동일 / 다른 파일이 이미 있음 |

`verified` 게임만 `normalized/replay-<게임 ID>.json`으로 저장한다. 각 파일은 익명화된 엔진 초기 상태, 선택 행동과 주사위 기록, 명시적으로 판정한 RTT 차이를 포함한다. 이 초기 상태에는 **두 진영의 비공개 카드와 미래 카드 보충 정보**가 있으므로 그대로 정책 모델의 관측값으로 쓰면 안 된다. 학습 자료를 만들 때는 행동 직전 상태에서 해당 진영의 `get_player_view`를 계산하고 게임 단위로 학습·평가를 나눈다. 원본 기보와 정규화 파일은 `replays/` 아래에 보관하며 Git에서 제외한다.

## 초기 입력 점검

2026-09-27에 총 3,687개를 검사했다. 결과는 다음과 같다.

| 상태 | 게임 수 |
| --- | ---: |
| `verified` | 17 |
| `mismatch` | 2,705 |
| `error` | 857 |
| `unsupported` | 101 |
| `duplicate` | 4 |
| `incomplete` | 3 |

`unsupported`는 `.timeout` 종료 100개와 Valiant 옵션 1개다. `error`의 대부분은 RTT 참조 엔진이 기록된 `done`(455개)·`card`(314개) 행동을 거부한 경우다. `mismatch`의 가장 흔한 첫 행동은 `piece`(804개), `retreat`(715개), `flag_supply_warnings`(234개)다. 이는 현재 RTT 관측기·행동 번역기와 여러 시기의 기보가 맞지 않음을 보여준다. 분류만으로 특정 규칙 오류의 원인을 단정하지 않는다.

정규화 파일 17개의 SHA-256은 보고서와 일치했고 누락·초과 파일이 없었다. 현재 검증된 게임만으로 DL policy 학습을 시작하면 표본이 지나치게 적다. 다음 작업은 첫 실패가 많은 행동 형식과 RTT 버전 차이를 조사해 검증 게임 수를 늘리는 것이다. 원본 기보와 전체 파일별 결과는 Git에서 제외된 `replays/validation-report.json`에 둔다.
