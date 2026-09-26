# Historical 캠페인 엔진 구현 계획

> **작업 에이전트 필수 지침:** 이 계획을 작업별로 실행할 때 `superpowers:subagent-driven-development`(권장) 또는 `superpowers:executing-plans` 스킬을 사용한다. 진행 상태는 각 `- [ ]` 항목에 기록한다.

**목표:** Paths of Glory Historical 캠페인을 처음부터 종료까지 합법적으로 진행하고 재생할 수 있는 UI 독립 엔진을 만든다.

**구조:** 직렬화 가능한 `FullGameState`와 명시적 선택 창을 통해 `generate_legal_actions`와 `apply_action`을 구동한다. 불변 규칙 데이터는 진행 상태와 분리하고, 각 규칙 모듈이 자신의 합법성 판단과 상태 전이를 담당한다. 실물 주사위와 테스트 주사위는 같은 확률 결과 창으로 들어와 기록된다.

**기술:** Python 3.12 이상, `uv`, `pytest`, 표준 라이브러리의 타입·자료형·JSON 기능. 웹·AI 의존성은 두지 않는다.

**설계 문서:** `docs/superpowers/specs/2026-09-26-historical-engine-design.md`

## 공통 제약

- 2022 Deluxe 영문 룰북의 Historical 캠페인만 지원한다. 5.7절이 요구하는 8장 손패와 11.2.10 참호 규칙을 포함한다.
- 영문 PDF가 규칙 해석의 최종 기준이다. RTT 소스와 다른 점은 조항 번호, 해석, 회귀 테스트를 기록한다.
- 공개 ID는 안정적인 영문 문자열이다. 한글 규칙 ID와 RTT 숫자 ID를 공개 API에 노출하지 않는다.
- `apply_action`은 입력 상태를 변경하지 않는다. 전투 중 추가 선택과 실물 주사위 결과까지 재생 가능해야 한다.
- `get_player_view`는 상대 손패·덱 순서·RNG 상태를 숨긴다. AI는 `CHANCE` 결과를 선택하지 않는다.
- RTT 원본, PDF, 카드 이미지는 Git에서 제외한다. 정규화한 규칙 데이터와 출처 기록만 커밋한다.
- 이 작업 공간에서 `uv` 실행 시 `UV_CACHE_DIR=.uv-cache`를 사용하고 `.uv-cache/`를 `.gitignore`에 추가한다.

## 집중 검토 항목

1. 행동의 행위자, 카드 ID 또는 필드가 잘못되면 원 상태를 바꾸지 않고 실패해야 한다(작업 1).
2. 어느 진영의 뷰에도 상대 손패, 정렬된 덱, RNG 내부 상태가 나타나면 안 된다(작업 19).
3. 일반 인접성 검사 때문에 제한 연결선이나 Near East SR 제한이 우회되면 안 된다(작업 7·8).
4. 같은 시드와 기록으로 카드 섞기·다시 섞기·주사위 결과를 재생하면 같은 상태가 나와야 한다(작업 3·19).
5. 종료 상태에서는 합법 행동이 없어야 하며 최종 VP 판정에는 Historical 조건을 적용해야 한다(작업 13).

## 파일 배치

| 경로 | 책임 |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.gitignore` | Python 패키지, 개발 도구, 재현 가능한 환경 |
| `src/pog_engine/model.py` | `Action`, `FullGameState`, `Transition`, `GameResult` 자료형과 검증 |
| `src/pog_engine/engine.py`, `__init__.py` | 공개 API, 행동 분배, 입력 불변 전이 경계 |
| `src/pog_engine/randomness.py`, `replay.py`, `view.py` | 시드·외부 주사위, 전이 기록, 플레이어 뷰 |
| `src/pog_engine/data/` | 공간·연결·유닛·카드·Historical 배치와 원본 ID 대응 |
| `src/pog_engine/rules/setup.py`, `turn.py`, `cards.py` | 시나리오 초기화, 턴 순서, 카드 수명 주기 |
| `src/pog_engine/rules/ops.py`, `movement.py`, `trenches.py`, `sr.py`, `supply.py` | OPS, 이동, 참호, 전략재배치, 보급 |
| `src/pog_engine/rules/combat.py`, `forts.py`, `replacements.py` | 전투 선택 창, 요새, 보충 |
| `src/pog_engine/rules/war.py`, `victory.py` | 전쟁 상태, 의무 공세, VP, 종료 |
| `src/pog_engine/rules/events/` | 카드별 사용 조건, 효과, 만료 |
| `tests/` | 규칙 사례, 카드 검증표, 재생, 전체 게임 진행 |
| `docs/rules-coverage.md`, `docs/rule-differences.md` | 규칙·카드 검증 현황과 공식 룰북/RTT 차이 |

각 작업의 대상 테스트와 기존 전체 테스트를 통과한 뒤 해당 작업의 소스·테스트·문서만 커밋한다. 아래의 검증 명령은 작업 대상 테스트용이며 전체 테스트 명령은 `UV_CACHE_DIR=.uv-cache uv run pytest -q`다.

### 작업 1: 패키지와 안전한 공개 전이 경계

**파일:** `pyproject.toml`, `src/pog_engine/{__init__,model,engine}.py`, `tests/test_engine_contract.py` 생성; `.gitignore` 수정.

**인터페이스:** JSON 호환 `Action`, `FullGameState`, `Transition(state, record)`, `generate_legal_actions(state) -> list[Action]`, `apply_action(state, action, random_input=None) -> Transition`, `IllegalActionError`, `InvalidStateError`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_engine_contract.py -q`.

- [ ] `test_wrong_actor_preserves_state`, `test_malformed_action_preserves_state` 작성: 오류 전후 `state == deepcopy(before)`, 합법 행동의 정규화 값에 중복이 없음을 검증한다.
- [ ] 대상 테스트 실행: import 또는 검증 실패를 확인한다.
- [ ] `uv` 패키지와 `pytest` 개발 의존성을 정의하고 자료형·검증·행동 분배 뼈대를 구현한다. JSON 왕복으로 상태가 보존되게 한다.
- [ ] 대상·전체 테스트, `UV_CACHE_DIR=.uv-cache uv lock --check`, `git diff --check`가 통과하는지 확인한다.
- [ ] `feat: uv 엔진 계약 추가`로 커밋한다.

### 작업 2: 정규화된 규칙 데이터

**파일:** `src/pog_engine/data/{__init__,loader}.py`, `data/{spaces,edges,units,cards,historical,source_ids}.json`, `tests/test_data.py`, `docs/rules-coverage.md` 생성.

**인터페이스:** `load_data() -> RuleData`, `validate_data(data) -> None`. `RuleData`는 영문 ID로 조회하고 인쇄된 카드 속성·국가·연결·유닛 수치·초기 배치를 보관한다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_data.py -q`.

- [ ] 기본 카드 110장, 유닛 정의 193개, 지도 공간 281개와 별도 박스, 유일한 ID, 연결의 대칭성과 제한, 초기 배치 참조의 유효성을 검증하는 테스트를 쓴다.
- [ ] 대상 테스트가 데이터 누락으로 실패하는지 확인한다.
- [ ] 제공된 RTT `data.js`를 정규화하고 지형·제한 연결·카드 수치·배치를 영문 룰북과 대조한다. 이미지와 카드 설명 문장은 복제하지 않는다.
- [ ] 대상·전체 테스트를 통과시키고 데이터 해시로 우발적 변경을 탐지한다.
- [ ] `feat: Historical 규칙 데이터 추가`로 커밋한다.

### 작업 3: Historical 초기화와 결정적 카드 순서

**파일:** `src/pog_engine/rules/setup.py`, `src/pog_engine/randomness.py`, `tests/test_setup.py` 생성.

**인터페이스:** `create_game(scenario: str = "HISTORICAL", seed: int = 0) -> FullGameState`, `shuffle_with_state(cards, rng_state) -> (cards, rng_state)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_setup.py -q`.

- [ ] `turn == 1`, `vp == 10`, 양측 손패가 각 8장, Historical 참호·통제·유닛 사례, 기본 카드만 포함한 덱을 검증한다. 같은 시드 상태는 같고 다른 시드는 덱 순서가 달라야 한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 모든 설계 상태 필드를 초기화하고 배치·예비·Historical 변경·시드 덱·첫 의무 공세 확률 창을 구성한다. 미지원 시나리오는 거부한다.
- [ ] 대상·전체 테스트를 통과시키고 RTT 초기 배치와 수량을 비교한다.
- [ ] `feat: Historical 캠페인 초기화`로 커밋한다.

### 작업 4: 턴 단계와 의무 공세

**파일:** `src/pog_engine/rules/{turn,war}.py`, `tests/test_turn.py` 생성.

**인터페이스:** `legal_turn_actions(state)`, `apply_turn_action(state, action)`, `advance_automatic_phases(state)`, `mandatory_offensive(state, side, die)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_turn.py -q`.

- [ ] 여섯 행동 라운드마다 CP→AP, 첫 CP 행동의 `GUNS_OF_AUGUST` 이벤트 강제, 첫 턴 British MO의 French MO 전환, 의무 공세→행동→소모→공성→전쟁 상태→보충→카드 보충→종료 순서를 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 단계와 행위자를 명시적으로 전환한다. 첫 카드 효과는 턴 흐름 시험용으로만 처리하고 작업 15에서 실제 핸들러로 교체한다.
- [ ] 대상·전체 테스트를 통과시키고 일곱 번째 행동 라운드가 열리지 않는지 확인한다.
- [ ] `feat: Historical 턴 순서 추가`로 커밋한다.

### 작업 5: 카드 영역·모드·덱 수명 주기

**파일:** `src/pog_engine/rules/cards.py`, `tests/test_cards.py` 생성; `docs/rules-coverage.md` 수정.

**인터페이스:** `legal_card_actions(state, side)`, `play_card(state, card_id, mode)`, `draw_to_hand(state, side)`, `discard_combat_cards(state, side)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_cards.py -q`.

- [ ] 카드 소유, EVENT/OPS/SR/RP 제한, 지연 다시 섞기, 8장까지 보충, 전투 카드 자발적 버림, 제거 카드의 재등장 금지, 상대 카드 위조 거부를 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 카드 영역 불변식과 모드별 진입 창을 구현한다. 110장 모두에 이벤트 분류와 규칙 조항이 있는 검증표를 만든다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 전략 카드 수명 주기 추가`로 커밋한다.

### 작업 6: OPS 활성화와 이동

**파일:** `src/pog_engine/rules/{ops,movement}.py`, `tests/test_ops_movement.py` 생성.

**인터페이스:** `activation_cost(state, space_id, kind) -> int`, `legal_movement_actions(state)`, `apply_movement_action(state, action)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_ops_movement.py -q`.

- [ ] 정상 이동, OPS 부족, 다국적 활성화 비용, 스택 한도 3, 감소 전투력의 이동력, 적 점유 목적지, 중복 이동, 국적 제한 연결을 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 공간 활성화·경로별 이동·통제 변경·지형/국적 제한·5.7.4.6 이탈리아 제한을 구현한다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: OPS와 이동 규칙 추가`로 커밋한다.

### 작업 7: 참호와 전략재배치

**파일:** `src/pog_engine/rules/{trenches,sr}.py`, `tests/test_trenches_sr.py` 생성.

**인터페이스:** `legal_entrench_actions(state)`, `apply_entrench_result(state, action)`, `legal_sr_actions(state)`, `apply_sr_action(state, action)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_trenches_sr.py -q`.

- [ ] Historical 11.2.10 굴림 수정, 참호 최대 단계·실패 표식, SR 비용·해상/예비 SR·국적 제한·Near East 제한 경로 거부를 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 참호 확률 창과 SR 유닛·목적지 선택 창을 구현하고 연결선 제한 및 턴별 Near East 사용량을 적용한다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 참호와 전략재배치 추가`로 커밋한다.

### 작업 8: 보급과 소모

**파일:** `src/pog_engine/rules/supply.py`, `tests/test_supply.py` 생성.

**인터페이스:** `supply_status(state, unit_id) -> SupplyStatus`, `supplied_spaces(state, side) -> frozenset[str]`, `resolve_attrition(state)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_supply.py -q`.

- [ ] 보급원 경로, 적 통제의 차단, 요새 예외, 항구·해상·Near East 제한, OOS 효과, OOS 군단의 보충 가능 제거와 군의 영구 제거를 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 14절 예외가 있는 진영별 그래프 탐색과 소모 단계를 구현한다. 비결정적 캐시는 공개 상태에 넣지 않는다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 보급과 소모 규칙 추가`로 커밋한다.

### 작업 9: 공격 합법성·측면 공격·CRT

**파일:** `src/pog_engine/rules/combat.py`, `tests/test_combat_math.py` 생성.

**인터페이스:** `legal_attack_declarations(state)`, `combat_strength(state, context, side)`, `fire_column(context, side)`, `crt_result(table, column, die)`, `flank_modifier(state, context)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_combat_math.py -q`.

- [ ] 방어 공간 하나 제한, 여러 공간·국가의 합동 공격, 공격 유닛 재사용 금지, 지형·참호·요새 열 수정, 군/군단 표, 측면 공격, CRT 양 끝 열을 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 공식 CRT 자료를 정규화하고 공격 선언·순수 계산을 구현한다. 주사위는 `CHANCE` 창으로 받는다.
- [ ] 대상·전체 테스트를 통과시키고 인쇄된 보조표의 경계 칸과 비교한다.
- [ ] `feat: 전투 합법성과 CRT 추가`로 커밋한다.

### 작업 10: 전투 선택 창과 결과

**파일:** `src/pog_engine/rules/combat.py` 확장, `tests/test_combat_sequence.py` 생성.

**인터페이스:** `legal_combat_actions(state)`, `apply_combat_action(state, action)`; `combat_context`는 각 추가 선택 사이에 유지한다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_combat_sequence.py -q`.

- [ ] 공격·방어측 전투 카드 사용/통과, 손실 배분과 군→군단 교체, 후퇴 취소·1/2칸 후퇴, 공격측 진격, 고정 주사위 재현을 검증한다. 단계마다 행위자를 확인한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 12.2절 전투 순서를 상태 기계로 구현한다. 작업 9 계산과 작업 8 보급을 사용하고 카드별 효과는 작업 17에서 연결한다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 전투 중간 선택 처리`로 커밋한다.

### 작업 11: 요새와 공성 단계

**파일:** `src/pog_engine/rules/forts.py`, `tests/test_forts.py` 생성.

**인터페이스:** `fort_status(state, space_id)`, `resolve_fort_combat(state, context)`, `legal_siege_actions(state)`, `apply_siege_result(state, action)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_forts.py -q`.

- [ ] 무인 요새 공격, 공성 선행 조건, 공성 주사위 항복, 파괴 요새 유지, 점령 전 요새를 통한 불법 진격을 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 고정 주사위 결과로 요새 상태를 전투·턴의 공성 단계와 연결한다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 요새와 공성 규칙 추가`로 커밋한다.

### 작업 12: RP와 유닛 보충

**파일:** `src/pog_engine/rules/replacements.py`, `tests/test_replacements.py` 생성.

**인터페이스:** `legal_replacement_actions(state, side)`, `apply_replacement_action(state, action)`, `close_replacement_phase(state, side)`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_replacements.py -q`.

- [ ] AP→CP 지출, 국가별 RP, 감소 유닛 회복, 제거된 군/군단의 보충, 보급·배치 제한, 미사용 RP 소멸, Historical Sedan 보너스 조건을 검증한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] RP 지출 창과 합법 배치 선택을 구현하고 영구 제거와 군/군단 차이를 보존한다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 보충 단계 추가`로 커밋한다.

### 작업 13: 전쟁 상태·VP·승리

**파일:** `src/pog_engine/rules/war.py` 확장, `src/pog_engine/rules/victory.py`, `tests/test_war_victory.py` 생성.

**인터페이스:** `resolve_war_status(state)`, `apply_vp_change(state, reason)`, `game_result(state) -> GameResult | None`.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_war_victory.py -q`.

- [ ] 전쟁 단계 카드 추가, US 참전·러시아 항복, 의무 공세 벌점, E.2의 VP 20/0 자동 승리, 휴전, 20턴의 Brest-Litovsk 여부별 판정, 5.7.4.8–9 조정을 검증한다. 종료 후 합법 행동은 `[]`여야 한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] E 단계와 5.5/5.7절 임계값을 종료 사유와 함께 구현한다. 다른 단계에서 자동 승리를 잘못 판정하지 않는다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 전쟁 상태와 Historical 승리 추가`로 커밋한다.

### 작업 14: 증원 카드 이벤트

**파일:** `src/pog_engine/rules/events/{__init__,reinforcements}.py`, `tests/cards/test_reinforcements.py` 생성.

**인터페이스:** `EventHandler.can_play(state, card_id) -> bool`, `.legal_choices(state) -> list[Action]`, `.apply(state, choice) -> FullGameState`; 영문 카드 ID로 등록한다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/cards/test_reinforcements.py -q`.

- [ ] 모든 기본 증원 카드의 인쇄된 유닛·국가·배치 제한·제거를 매개변수 테스트로 확인한다. 사용할 수 없는 증원은 선택할 수 없어야 한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 군/군단 배치 창과 시나리오 제한을 가진 데이터 기반 증원 핸들러를 구현하고 검증표를 갱신한다.
- [ ] 대상·전체 테스트를 통과시킨다.
- [ ] `feat: 증원 카드 이벤트 추가`로 커밋한다.

### 작업 15: 중립국 참전과 정치 이벤트

**파일:** `src/pog_engine/rules/events/{entry,politics}.py`, `tests/cards/test_entry_politics.py` 생성.

**인터페이스:** 작업 14의 `EventHandler`를 사용한다. 참전 이벤트는 `war`를 갱신하고 필요한 추가 선택 창을 연다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/cards/test_entry_politics.py -q`.

- [ ] Guns of August 첫 행동, Romania/Italy/Bulgaria/Greece 참전, 너무 이른 참전 거부, 러시아 정치 연쇄, Historical 이벤트 후 OPS 카드를 검증한다. 카드 영역·전쟁 상태·US 참전·러시아 항복을 함께 확인한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 정치·참전 핸들러를 구현하고 작업 4의 임시 첫 이벤트 처리를 교체한다. 5.7.4.7의 이벤트→OPS 순서를 적용한다.
- [ ] 대상·전체 테스트를 통과시키고 해당 카드 검증표를 갱신한다.
- [ ] `feat: 참전과 정치 이벤트 추가`로 커밋한다.

### 작업 16: 지속 경제·전쟁 이벤트

**파일:** `src/pog_engine/rules/events/{war_status,economy}.py`, `tests/cards/test_persistent_events.py` 생성; `docs/rule-differences.md` 수정.

**인터페이스:** 작업 14의 `EventHandler`와 턴 엔진용 `expire_effects(state, phase)`를 제공한다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/cards/test_persistent_events.py -q`.

- [ ] Blockade, U-boats/Convoy, RP 수정, VP·전쟁 상태 이벤트, 평화·휴전, 지속 플래그를 카드별로 검증한다. 사용 조건·정확한 수치·만료 단계·카드 영역을 확인한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 지속 효과와 만료를 구현하고 작업 12–13에 연결한다. 공식 룰북과 RTT의 차이가 있으면 기록한다.
- [ ] 대상·전체 테스트를 통과시키고 검증표를 갱신한다.
- [ ] `feat: 지속 전쟁 이벤트 추가`로 커밋한다.

### 작업 17: 전투 카드 이벤트

**파일:** `src/pog_engine/rules/events/combat.py`, `tests/cards/test_combat_events.py` 생성.

**인터페이스:** 작업 14의 `EventHandler`를 사용한다. 작업 10에 카드 사용 시점·조건·수정치·지속·버림/제거 규칙을 제공한다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/cards/test_combat_events.py -q`.

- [ ] 기본 전투 카드 27장의 소유·시점 검증표와 참호 무효화, DRM, Withdrawal, 날씨, 전차·항공, 승자 카드 유지, 강제 버림/제거 사례를 작성한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 핸들러를 전투의 공격·방어 선택 창과 연결하고 효과를 전투 종료까지 보존한다.
- [ ] 대상·전체 테스트를 통과시키고 전투 카드 검증표를 갱신한다.
- [ ] `feat: 전투 카드 이벤트 추가`로 커밋한다.

### 작업 18: 작전 이벤트와 남은 기본 카드

**파일:** `src/pog_engine/rules/events/{operations,misc}.py`, `tests/cards/{test_operational_events,test_event_inventory}.py` 생성; `docs/rules-coverage.md` 수정.

**인터페이스:** 모든 기본 이벤트를 등록한다. 작전 이벤트는 OPS·이동·공격·보급·참호 선택 창을 열 수 있다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/cards/test_operational_events.py tests/cards/test_event_inventory.py -q`.

- [ ] 작업 14–17에 배정되지 않은 모든 카드의 공세·이동·보급·참호·이벤트 후 OPS 동작을 검증한다. 기본 카드 110장과 검증된 핸들러 ID를 비교해 누락·무효 핸들러를 실패로 처리한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 작전 핸들러와 첫 턴 Entrench 이벤트 금지를 구현한다. 모든 카드 행에 룰북 조항과 실제 테스트 이름을 채운다.
- [ ] 대상·전체 테스트를 통과시키고 미배정 카드가 0장인지 확인한다.
- [ ] `feat: 기본 카드 이벤트 완성`으로 커밋한다.

### 작업 19: 플레이어 뷰·재생·전체 게임 검증

**파일:** `src/pog_engine/{view,replay}.py`, `tests/{test_view_replay,test_full_game}.py` 생성; `src/pog_engine/__init__.py`, 두 규칙 문서 수정.

**인터페이스:** `get_player_view(state, side) -> PlayerVisibleState`, `replay(initial_state, records) -> FullGameState`, `game_result(state)`; 패키지에서 설계 문서의 다섯 공개 함수를 내보낸다.

**검증 명령:** `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_view_replay.py tests/test_full_game.py -q`.

- [ ] 양측 뷰의 상대 손패·덱 순서·RNG 비노출, 섞기·주사위 기록의 JSON 단위 동일 재생, 합법 행동만 고르는 테스트 드라이버의 종료 도달과 종료 후 행동 없음 검증을 작성한다.
- [ ] 대상 테스트 실패를 확인한다.
- [ ] 뷰 투영과 재생 검증기를 구현한다. 테스트 드라이버는 AI 정책이 아니다. 규칙·카드 검증표와 확인된 룰북/RTT 차이를 마무리한다.
- [ ] 대상·전체 테스트, `UV_CACHE_DIR=.uv-cache uv lock --check`, `git diff --check`를 통과시키고 Historical 전 단계와 기본 카드 110장의 검증표를 확인한다.
- [ ] `feat: Historical 엔진 재생과 전체 검증 완성`으로 커밋한다.

## 실행 메모

작업 순서를 지킨다. 공식 룰북이나 보조표가 계획과 다르면 조항을 기록하고 계획·테스트를 먼저 고친다. 각 작업의 테스트는 작은 유효 상태를 직접 만들 수 있으며 전체 게임 테스트는 작업 19에서 시작한다. 버그를 발견하면 수정 전에 재현 테스트를 추가한다. 작업 19의 전체 게임과 카드 검증표가 통과하기 전에는 Phase 1 완료로 표시하지 않는다.
