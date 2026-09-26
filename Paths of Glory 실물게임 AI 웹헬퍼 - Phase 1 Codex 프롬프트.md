# Paths of Glory 실물 보드게임 AI 웹헬퍼 프로젝트

## 프로젝트 최종 목표

이 프로젝트의 최종 목표는 **Paths of Glory 실물 보드게임에서 사람과 대전할 수 있는 AI 상대 웹헬퍼**를 만드는 것이다.

완전한 디지털 보드게임을 만드는 것이 목적이 아니다.

사용자는 실제 보드, 카드, 말, 주사위를 사용하여 게임을 진행한다.\
웹앱은 AI 플레이어의 상태를 관리하고, 상대 플레이어의 행동 및 실물 게임에서 발생한 필요한 정보만 입력받아 AI의 다음 행동을 결정하는 역할을 한다.

최종적으로 다음 순서로 개발한다.

1. Game Engine
2. Rally the Troops 기보 Parser + 정제
3. DL Policy
4. 기본 Evaluation Function
5. Greedy Baseline
6. Beam Search + Policy
7. MCTS + Policy
8. DL Value
9. Policy + Value + MCTS
10. LLM Strategic Layer

현재 작업 범위는 **1. Game Engine만**이다.

AI, 탐색 알고리즘, DL, LLM은 아직 구현하지 않는다.

---

# Phase 1 목표

**Paths of Glory의 전체 규칙을 처리할 수 있는 UI 독립적인 게임엔진을 구현한다.**

엔진은 향후 다음 시스템들이 동일한 인터페이스를 사용할 수 있어야 한다.

- 사람 입력
- Greedy
- Beam Search
- MCTS
- DL Policy
- DL Value
- LLM Strategic Layer
- Web UI

핵심 인터페이스는 가능하면 다음 개념을 중심으로 설계한다.

```text
GameState
    ↓
generate_legal_actions(state)
    ↓
Action
    ↓
apply_action(state, action)
    ↓
Next GameState
```

즉 AI든 사람이든 최종적으로는 엔진이 제공하는 `legal_actions` 중 하나를 선택하여 `apply_action()`에 전달하는 구조여야 한다.

---

# 참고 자료

프로젝트 폴더에 다음 자료를 제공할 예정이다.

## 1. Rally the Troops Paths of Glory 소스

기존 Rally the Troops 구현을 중요한 참고 자료로 사용한다.

특히 다음 내용을 분석한다.

- 게임 상태 표현
- 카드 처리
- 이벤트 처리
- 이동
- 전투
- 보급
- 참호
- 요새
- 전략재배치
- RP
- War Status
- Mandatory Offensive
- 턴 진행
- 승리조건
- 특수 규칙
- 예외 처리

단, Rally the Troops의 웹 UI나 네트워크 구조를 그대로 재현하는 것이 목적은 아니다.

필요한 것은 **규칙 구현 방식과 게임 데이터**다.

가능하면 게임 규칙을 UI와 완전히 분리된 형태로 재구성한다.

라이선스가 코드 직접 재사용을 허용하지 않는다면 동작과 규칙을 참고하여 별도로 구현한다.

---

## 2. 영문 공식 룰북

게임 규칙 해석의 최우선 기준이다.

Rally the Troops 구현과 룰북이 다르게 보이는 부분이 있다면 해당 내용을 조사하고 코드에 주석 또는 문서로 남긴다.

명확한 근거 없이 임의로 규칙을 단순화하지 않는다.

---

## 3. 기타 제공 자료

한글 룰북

- 한글 카드 이미지 또는 카드 데이터
- 한글 표시용 자료

이 자료들은 주로 **표시 계층(UI/localization)** 과 규칙 검증을 위한 것이다.

게임엔진 내부는 영어 기준으로 작성한다.

예:

```text
BRUSSELS
TRENCH
ARMY
OPS
REPLACEMENT_POINTS
STRATEGIC_REDEPLOYMENT
```

한글 문자열을 게임 규칙 로직의 식별자로 사용하지 않는다.

향후 필요한 경우 별도의 localization mapping을 사용한다.

---

# 매우 중요한 프로젝트 특성

이 프로젝트는 **실물 보드게임 보조 앱**이다.

따라서 엔진이 완전한 게임 상태를 관리한다고 해서 최종 UI가 디지털 보드를 그대로 구현해야 하는 것은 아니다.

최종적으로 사용자는 실제 보드에서 게임을 진행하고 웹앱에는 주로 다음 정보만 입력하게 될 것이다.

- 상대가 사용한 카드
- 카드 사용 방식(Event / OPS / SR / RP 등)
- 상대의 이동
- 상대의 전투 선언
- 상대의 선택
- 상대의 Combat Card 사용
- 실물 주사위 결과 등 외부에서 발생한 결과

반대로 AI 자신의 행동은 엔진이 이미 알고 있기 때문에 사용자가 다시 입력할 필요가 없어야 한다.

이 원칙을 고려하여 엔진 API를 설계한다.

하지만 **현재 Phase 1에서는 Web UI를 구현하지 않는다.**

---

# GameState

게임의 모든 규칙 상태는 UI와 독립적인 `GameState`에 표현되어야 한다.

최소한 다음을 포함할 수 있어야 한다.

- scenario
- turn
- action round
- active side
- spaces
- space control
- units
- unit location
- full / reduced strength
- eliminated units
- reserve boxes
- forts
- trenches
- supply
- VP
- AP War Status
- CP War Status
- Combined War Status
- Mandatory Offensive
- cards
- draw deck
- hands
- discard pile
- removed cards
- RP
- persistent events
- temporary effects
- scenario-specific flags
- victory status

Rally the Troops에서 더 필요한 상태가 발견되면 추가한다.

---

# Hidden Information

향후 AI는 상대 손패를 알 수 없어야 한다.

따라서 내부적으로 모든 정보를 가진 상태와 플레이어가 볼 수 있는 정보를 구분할 수 있도록 설계한다.

예:

```text
FullGameState
    ↓
get_player_view(state, side)
    ↓
PlayerVisibleState
```

AI가 자기 손패는 볼 수 있지만 상대 손패를 직접 조회할 수 있는 구조로 만들지 않는다.

MCTS 및 DL을 나중에 구현할 예정이므로 이 구분은 중요하다.

---

# Action Model

모든 플레이 선택은 가능한 한 **구조화된 Action**으로 표현한다.

예:

```json
{
  "type": "PLAY_CARD",
  "card_id": "GUNS_OF_AUGUST",
  "mode": "EVENT"
}
```

```json
{
  "type": "MOVE",
  "units": ["GE_1_ARMY"],
  "from": "ESSEN",
  "to": "KOBLENZ"
}
```

```json
{
  "type": "PASS_COMBAT_CARD"
}
```

AI와 UI가 자연어 없이 이 Action 구조만으로 게임을 진행할 수 있어야 한다.

---

# Decision Window / Interrupt 구조

Paths of Glory에는 하나의 행동 도중 추가적인 선택이 발생할 수 있다.

특히 다음과 같은 경우를 고려한다.

- Combat Card 사용 여부
- 손실 배분
- 후퇴
- 진격
- 이벤트 선택
- 특정 카드의 추가 대상 선택
- 기타 interrupt / reaction 성격의 선택

따라서

```text
Action
→ 즉시 모든 처리 완료
```

만 가능한 단순 구조로 만들지 않는다.

필요하면 엔진은 중간 상태를 생성하여 다음 플레이어의 선택을 기다릴 수 있어야 한다.

예:

```text
Combat declared
    ↓
CombatContext
    ↓
Combat Card decision window
    ↓
Combat resolution
    ↓
Loss allocation
    ↓
Retreat decision
    ↓
Advance decision
```

각 단계에서도 `generate_legal_actions()`가 유효한 선택지만 반환하도록 설계한다.

---

# Combat Card

Combat Card도 일반적인 Action 시스템 내부에서 처리한다.

예:

```text
PLAY_COMBAT_CARD
PASS_COMBAT_CARD
```

AI의 Combat Card 사용 여부는 향후 AI가 결정해야 하므로 별도의 UI 특수 로직으로 구현하지 않는다.

카드의 효과와 사용 가능 조건은 게임엔진이 판단한다.

가능하면 다음 개념을 분리한다.

- timing
- eligibility condition
- effect
- duration
- expiration
- discard / remove behavior

카드별 특수 처리 필요 시 handler 구조를 사용해도 된다.

---

# Randomness

주사위 등 랜덤 요소는 테스트 가능해야 한다.

랜덤 호출을 코드 깊숙한 곳에 직접 박지 않는다.

예:

```text
roll_die()
```

또는 RNG 객체를 주입할 수 있도록 한다.

테스트에서는 특정 주사위 값을 강제로 지정할 수 있어야 한다.

---

# Replay 가능성

향후 Rally the Troops 기보를 학습 데이터로 만들 예정이므로 게임을 Action sequence로 재생할 수 있어야 한다.

이상적인 구조:

```text
initial_state
action_1
action_2
action_3
...
random_result_1
...
final_state
```

동일한 입력과 동일한 랜덤 결과를 제공하면 동일한 상태를 재현할 수 있도록 설계한다.

이 기능은 이후 다음 단계에서 중요하다.

- 기보 parsing
- training dataset 생성
- regression test
- AI evaluation
- debugging

현재 전체 replay 시스템을 완성할 필요는 없지만 replay가 불가능한 구조는 피한다.

---

# Rule Modules

구체적인 파일 구조는 현재 저장소를 조사한 후 결정하되, 가능하면 게임 규칙을 책임별로 분리한다.

예:

```text
engine/
    state
    actions
    movement
    combat
    supply
    cards
    events
    replacements
    strategic_redeployment
    turn_sequence
    victory
    setup

data/
    spaces
    map
    units
    cards
    scenarios

tests/
```

파일 이름이나 언어는 프로젝트 환경에 맞게 변경해도 된다.

중요한 것은 관심사의 분리다.

---

# Testing

게임엔진 구현과 동시에 자동 테스트를 작성한다.

테스트는 Phase 1 완료 조건에 포함된다.

다음 항목들을 중점적으로 테스트한다.

### Setup

- 시나리오 초기화
- 초기 부대
- 초기 VP
- 초기 카드/덱

### Movement

- 정상 이동
- 불가능한 이동
- 활성화
- 이동 제한

### Combat

- 일반 전투
- CRT
- 컬럼 계산
- fort
- trench
- flank attack
- loss allocation
- retreat
- advance
- Combat Card

### Supply

- supply 판정
- OOS
- supply path 차단
- 관련 예외

### Cards

- Event
- OPS
- SR
- RP
- Combat Card
- 제거 카드
- 지속 이벤트
- 특수 이벤트

### Turn Flow

- Action Round
- 턴 종료
- RP
- War Status
- Mandatory Offensive
- VP
- 승리조건

버그를 수정할 때는 가능하면 해당 버그를 재현하는 regression test를 추가한다.

---

# 현재 구현하지 않을 것

Phase 1에서는 다음을 구현하지 않는다.

- DL
- Policy Network
- Value Network
- Greedy AI
- Beam Search
- MCTS
- Minimax
- reinforcement learning
- LLM
- 전략 판단
- AI용 heuristic
- 완성형 Web UI
- 실물 보드 이미지 인식

미래 AI를 고려한 API 설계는 하되 실제 AI 로직은 추가하지 않는다.

---

# Phase 1 완료 조건

다음 조건을 만족하면 Game Engine Phase가 완료된 것으로 본다.

1. 지원 시나리오를 구조화된 데이터에서 초기화할 수 있다.
2. 전체 게임 상태가 UI와 독립적으로 존재한다.
3. 현재 상태에서 가능한 합법 Action을 생성할 수 있다.
4. Action을 적용하여 다음 유효 상태를 만들 수 있다.
5. 주요 PoG 규칙이 구현되어 있다.
6. 카드 이벤트 및 주요 예외 규칙이 구현되어 있다.
7. Combat Card 및 중간 decision window를 처리할 수 있다.
8. 게임이 Turn/Action Round를 따라 정상 진행된다.
9. 승리조건을 판정할 수 있다.
10. 자동 테스트가 존재한다.
11. 엔진 API만 사용하여 이론적으로 게임 시작부터 종료까지 진행할 수 있다.
12. 향후 RTT 기보를 replay하여 `(state, action)` 데이터를 생성할 수 있는 구조다.

---

# 첫 작업

바로 대규모 코드를 작성하지 말고 우선 저장소와 제공 자료를 분석한다.

먼저 다음을 수행한다.

1. 프로젝트 내 Rally the Troops 소스 구조 조사
2. Paths of Glory 관련 핵심 파일 식별
3. 영문 룰북 구조 확인
4. RTT의 state / action / card / map / combat / turn logic 분석
5. 재사용할 수 있는 데이터와 규칙 로직 구분
6. UI/network 종속 부분과 순수 게임 규칙 부분 구분
7. 우리 프로젝트에서 사용할 GameState 설계안 작성
8. Action schema 설계안 작성
9. 주요 rule module 구조 제안
10. 테스트 전략 제안

그 결과를 먼저 문서로 정리한 뒤 구현을 시작한다.

분석 단계에서 기존 구조가 합리적이라면 불필요하게 다시 설계하지 않는다.

반대로 Rally the Troops 구조가 UI 및 서버 동작에 지나치게 결합되어 있다면 AI 탐색 및 replay에 적합한 독립 엔진 구조로 분리한다.

---

# 가장 중요한 설계 원칙

이 프로젝트의 중심은 Web UI가 아니라 **게임엔진**이다.

향후 모든 AI는 다음 인터페이스만으로 게임을 플레이할 수 있어야 한다.

```text
state
legal_actions
apply_action
game_result
```

그리고 최종 실물게임 웹헬퍼에서는 동일한 Action 인터페이스를 사람이 사용하는 UI가 호출하게 된다.

따라서 현재 구현에서는

**규칙 정확성 > 테스트 가능성 > AI/replay 호환성 > UI 편의성**

순으로 우선한다.
