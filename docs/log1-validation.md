# LOG1 대조 검증과 이어서 작업하기

## 입력과 범위

- 원본: 사용자가 작업 폴더에 둔 `LOG1.txt`. 같은 파일을 `tests/fixtures/LOG1.txt`에 보존했다.
- 기록 범위: 1914년 8월(1턴)부터 1915년 봄 5턴 4번째 CP 행동까지, 총 55개의 카드 행동 기록. 마지막은 AP 항복이다.
- 이 파일은 RTT의 사람이 읽는 게임 로그다. 초기 시드·덱 순서·주사위 눈·중복 군단의 개별 ID·되돌리기 전 행동 내역이 없다. 따라서 원문만으로 **동일한 전체 상태의 기보 재생**은 결정할 수 없다. `replay` API의 정확한 재생 입력은 `apply_action`이 반환한 `Transition.record` 배열이다.

## 검증한 사례

`tests/test_log1_regression.py`는 다음을 실제 로그 문자열과 연결해 검사한다.

1. 1턴 Guns of August: GE 1·2·3군의 Sedan 공격, Koblenz에서 측면 공격 +1, 공격 5 대 방어 1 손실, 감소한 FR 5군이 예비 프랑스 군단으로 교체되며 후퇴 취소(규칙 12.5.3).
2. 1턴 러시아 공세: AH 3군이 Tarnopol에서 Lemberg와 Przemysl로 두 칸 후퇴한 뒤 RU 3·8군이 Lemberg까지 진격(12.7.3). 경로를 직접 주입하는 경계 테스트와 공격 선언부터 실제 행동으로 이어 가는 테스트를 모두 둔다.
3. 2턴 Kovno의 Withdrawal 전투: RU 1군은 Grodno, 러시아 군단은 Vilna로 **각자** 후퇴(12.5.5).
4. 원문에 등장한 카드 행동 54개의 이름·진영·인쇄된 사용 방식(이벤트/OPS/SR/RP)이 정적 카드 자료와 맞는지 확인. 나머지 한 줄은 되돌리기 안내다.
5. 로그에 표시된 전투 결과표 60줄 모두에 대해 표·열·DRM에 맞는 주사위 눈이 하나 이상 존재하는지 확인. 원문의 실제 주사위 눈을 복원한 검사는 아니다.

이 대조에서 발견해 수정한 엔진 문제는 감소한 군의 후퇴 취소 시 군단 교체 누락, 두 칸 후퇴 뒤 첫 후퇴 공간까지의 진격 누락, 수비 유닛별 후퇴 경로 선택 누락이다. 코드 리뷰에서 두 번째 진격이 공성 불가능한 적 요새에 들어가는 문제도 확인해 막았다.

## 재개 절차

작업 브랜치는 `feat/historical-engine`, 작업 폴더는 `/home/pc/project/pog_bot/.worktrees/historical-engine`이다. 기본 폴더 `/home/pc/project/pog_bot`의 `main`에는 아직 병합하지 않았다. 수정할 때는 worktree에서 작업한다.

```bash
cd /home/pc/project/pog_bot/.worktrees/historical-engine
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_log1_regression.py -q
UV_CACHE_DIR=.uv-cache uv run pytest -q
UV_CACHE_DIR=.uv-cache uv lock --check
git diff --check
git status --short
```

규칙 우선순위는 제공된 2022 Deluxe 영문 룰북, 그다음 RTT 참고 구현, 마지막으로 LOG1 관측 결과다. 남은 검증은 원문에 명시된 카드 사용·이동·보충을 추가 사례로 재구성하고, 충분한 입력이 확인되는 경우 `apply_action` 기록 형태로 보존하는 것이다. 불완전한 로그에 없는 주사위 눈이나 카드 드로우를 사실처럼 채우지 않는다.
