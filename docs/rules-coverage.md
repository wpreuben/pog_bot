# Historical 규칙·카드 검증표

## 자료 출처

- 규칙 기준: 제공된 `PoG-DeluxeRules2022Final.pdf`와 동일 판본의 RTT `info/rules.html`.
- 정적 카드·유닛·지도·초기 배치 대조 자료: 제공된 RTT `data.js`, `rules.js`.
- 정규화 데이터: 기본 카드 110장, 유닛 정의 193개, 지도 공간 281개, 별도 상자 80개, 연결선 476개.
- RTT 원본의 카드 이미지, 카드 효과 설명문, UI·서버 코드는 프로젝트 패키지에 포함하지 않는다.

## 단계별 검증 책임

| 룰북 | 영역 | 계획 작업 |
| --- | --- | --- |
| 4, 5.7 | Historical 설정 | 2–3 |
| 6–8 | 턴·의무 공세·행동 | 4, 13 |
| 9 | 전략 카드와 이벤트 | 5, 14–18 |
| 10–11 | 스택·이동·참호 | 6–7 |
| 12 | 전투·전투 카드 | 9–10, 17 |
| 13 | 전략재배치 | 7 |
| 14 | 보급·소모 | 8 |
| 15 | 요새·공성 | 11 |
| 16 | 전쟁·평화 | 13, 15–16 |
| 17 | 보충 | 12, 14 |

아래 분류는 카드의 인쇄 속성과 룰북 9.5절을 기준으로 한다. 카드별 합법 조건·효과·회귀 테스트는 작업 14–18에서 검증표에 추가한다.

| 진영 | 카드 ID | 이벤트 종류 | 기본 조항 |
| --- | --- | --- | --- |
| AP | `BRITISH_REINFORCEMENTS_BR_2` | 증원 | 9.5.3 |
| AP | `BLOCKADE` | 일반 | 9.5.1 |
| AP | `RUSSIAN_REINFORCEMENTS_RU_11` | 증원 | 9.5.3 |
| AP | `PLEVE` | 전투 | 9.5.4 |
| AP | `PUTNIK` | 전투 | 9.5.4 |
| AP | `WITHDRAWAL` | 전투 | 9.5.4 |
| AP | `SEVERE_WEATHER_AP` | 전투 | 9.5.4 |
| AP | `RUSSIAN_REINFORCEMENTS_2_CORPS` | 증원 | 9.5.3 |
| AP | `MOLTKE` | 일반 | 9.5.1 |
| AP | `FRENCH_REINFORCEMENTS_FR_10` | 증원 | 9.5.3 |
| AP | `RUSSIAN_REINFORCEMENTS_RU_9_RU_10` | 증원 | 9.5.3 |
| AP | `ENTRENCH_AP` | 일반 | 9.5.1 |
| AP | `RAPE_OF_BELGIUM` | 일반 | 9.5.1 |
| AP | `BRITISH_REINFORCEMENTS_BR_1` | 증원 | 9.5.3 |
| AP | `BRITISH_REINFORCEMENTS_BR_4` | 증원 | 9.5.3 |
| AP | `ROMANIA` | 중립 참전 | 9.5.2 |
| AP | `ITALY` | 중립 참전 | 9.5.2 |
| AP | `HURRICANE_BARRAGE` | 전투 | 9.5.4 |
| AP | `AIR_SUPERIORITY_AP` | 전투 | 9.5.4 |
| AP | `BRITISH_REINFORCEMENTS_AUS_CND` | 증원 | 9.5.3 |
| AP | `PHOSGENE_GAS` | 전투 | 9.5.4 |
| AP | `ITALIAN_REINFORCEMENTS` | 증원 | 9.5.3 |
| AP | `CLOAK_AND_DAGGER` | 일반 | 9.5.1 |
| AP | `FRENCH_REINFORCEMENTS_FR_7` | 증원 | 9.5.3 |
| AP | `RUSSIAN_REINFORCEMENTS_RU_6_RU_7` | 증원 | 9.5.3 |
| AP | `LUSITANIA` | 일반 | 9.5.1 |
| AP | `GREAT_RETREAT` | 일반 | 9.5.1 |
| AP | `LANDSHIPS` | 일반 | 9.5.1 |
| AP | `YUDENITCH_RU_REINFORCEMENTS` | 증원 | 9.5.3 |
| AP | `SALONIKA` | 일반 | 9.5.1 |
| AP | `MEF_BR_REINFORCEMENTS` | 증원 | 9.5.3 |
| AP | `RUSSIAN_REINFORCEMENTS_RU_12` | 증원 | 9.5.3 |
| AP | `GRAND_FLEET` | 일반 | 9.5.1 |
| AP | `BRITISH_REINFORCEMENTS_BR_3` | 증원 | 9.5.3 |
| AP | `YANKS_AND_TANKS` | 일반 | 9.5.1 |
| AP | `MINE_ATTACK` | 전투 | 9.5.4 |
| AP | `INDEPENDENT_AIR_FORCE` | 일반 | 9.5.1 |
| AP | `USA_REINFORCEMENTS_1_CORPS` | 증원 | 9.5.3 |
| AP | `THEY_SHALL_NOT_PASS` | 전투 | 9.5.4 |
| AP | `14_POINTS` | 일반 | 9.5.1 |
| AP | `ARAB_NORTHERN_ARMY_BR_REINFORCEMENTS` | 증원 | 9.5.3 |
| AP | `BRITISH_REINFORCEMENTS_BR_5` | 증원 | 9.5.3 |
| AP | `USA_REINFORCEMENTS_US_1` | 증원 | 9.5.3 |
| AP | `GREECE` | 중립 참전 | 9.5.2 |
| AP | `KERENSKY_OFFENSIVE` | 일반 | 9.5.1 |
| AP | `BRUSILOV_OFFENSIVE` | 일반 | 9.5.1 |
| AP | `USA_REINFORCEMENTS_US_2` | 증원 | 9.5.3 |
| AP | `ROYAL_TANK_CORPS` | 전투 | 9.5.4 |
| AP | `SINAI_PIPELINE` | 일반 | 9.5.1 |
| AP | `ALLENBY_BR_REINFORCEMENTS` | 증원 | 9.5.3 |
| AP | `EVERYONE_INTO_BATTLE` | 일반 | 9.5.1 |
| AP | `CONVOY` | 일반 | 9.5.1 |
| AP | `ARMY_OF_THE_ORIENT_FR_REINFORCEMENTS` | 증원 | 9.5.3 |
| AP | `ZIMMERMANN_TELEGRAM` | 일반 | 9.5.1 |
| AP | `OVER_THERE` | 일반 | 9.5.1 |
| CP | `GUNS_OF_AUGUST` | 일반 | 9.5.1 |
| CP | `WIRELESS_INTERCEPTS` | 전투 | 9.5.4 |
| CP | `VON_FRANCOIS` | 전투 | 9.5.4 |
| CP | `SEVERE_WEATHER_CP` | 전투 | 9.5.4 |
| CP | `LANDWEHR` | 일반 | 9.5.1 |
| CP | `ENTRENCH_CP` | 일반 | 9.5.1 |
| CP | `GERMAN_REINFORCEMENTS_GE_9` | 증원 | 9.5.3 |
| CP | `RACE_TO_THE_SEA` | 일반 | 9.5.1 |
| CP | `REICHSTAG_TRUCE` | 일반 | 9.5.1 |
| CP | `SUD_ARMY` | 일반 | 9.5.1 |
| CP | `OBEROST` | 일반 | 9.5.1 |
| CP | `GERMAN_REINFORCEMENTS_GE_10` | 증원 | 9.5.3 |
| CP | `FALKENHAYN` | 일반 | 9.5.1 |
| CP | `AUSTRIA_HUNGARY_REINFORCEMENTS_AH_7` | 증원 | 9.5.3 |
| CP | `CHLORINE_GAS` | 전투 | 9.5.4 |
| CP | `LIMAN_VON_SANDERS` | 전투 | 9.5.4 |
| CP | `MATA_HARI` | 일반 | 9.5.1 |
| CP | `FORTIFIED_MACHINE_GUNS` | 전투 | 9.5.4 |
| CP | `FLAMETHROWERS` | 전투 | 9.5.4 |
| CP | `AUSTRIA_HUNGARY_REINFORCEMENTS_AH_10` | 증원 | 9.5.3 |
| CP | `GERMAN_REINFORCEMENTS_GE_11` | 증원 | 9.5.3 |
| CP | `GERMAN_REINFORCEMENTS_GE_12` | 증원 | 9.5.3 |
| CP | `AUSTRIA_HUNGARY_REINFORCEMENTS_AH_11` | 증원 | 9.5.3 |
| CP | `LIBYAN_REVOLT_TU_REINFORCEMENTS` | 증원 | 9.5.3 |
| CP | `HIGH_SEAS_FLEET` | 일반 | 9.5.1 |
| CP | `PLACE_OF_EXECUTION` | 전투 | 9.5.4 |
| CP | `ZEPPELIN_RAIDS` | 일반 | 9.5.1 |
| CP | `TSAR_TAKES_COMMAND` | 일반 | 9.5.1 |
| CP | `11TH_ARMY` | 일반 | 9.5.1 |
| CP | `ALPENKORPS` | 전투 | 9.5.4 |
| CP | `KEMAL` | 전투 | 9.5.4 |
| CP | `WAR_IN_AFRICA` | 일반 | 9.5.1 |
| CP | `WALTER_RATHENAU` | 일반 | 9.5.1 |
| CP | `BULGARIA` | 중립 참전 | 9.5.2 |
| CP | `MUSTARD_GAS` | 전투 | 9.5.4 |
| CP | `U_BOATS_UNLEASHED` | 일반 | 9.5.1 |
| CP | `HOFFMANN` | 일반 | 9.5.1 |
| CP | `GERMAN_REINFORCEMENTS_2_CORPS_CP_38` | 증원 | 9.5.3 |
| CP | `GERMAN_REINFORCEMENTS_2_CORPS_CP_39` | 증원 | 9.5.3 |
| CP | `AIR_SUPERIORITY_CP` | 전투 | 9.5.4 |
| CP | `GERMAN_REINFORCEMENTS_GE_14` | 증원 | 9.5.3 |
| CP | `TURKISH_REINFORCEMENTS_YLD` | 증원 | 9.5.3 |
| CP | `VON_BELOW` | 전투 | 9.5.4 |
| CP | `VON_HUTIER` | 전투 | 9.5.4 |
| CP | `TREATY_OF_BREST_LITOVSK` | 일반 | 9.5.1 |
| CP | `GERMAN_REINFORCEMENTS_GE_17_GE_18` | 증원 | 9.5.3 |
| CP | `FRENCH_MUTINY` | 일반 | 9.5.1 |
| CP | `TURKISH_REINFORCEMENTS_AOI` | 증원 | 9.5.3 |
| CP | `MICHAEL` | 전투 | 9.5.4 |
| CP | `BLUCHER` | 전투 | 9.5.4 |
| CP | `PEACE_OFFENSIVE` | 전투 | 9.5.4 |
| CP | `FALL_OF_THE_TSAR` | 일반 | 9.5.1 |
| CP | `BOLSHEVIK_REVOLUTION` | 일반 | 9.5.1 |
| CP | `H_L_TAKE_COMMAND` | 일반 | 9.5.1 |
| CP | `LLOYD_GEORGE` | 일반 | 9.5.1 |
