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

아래 분류는 카드의 인쇄 속성과 룰북 9.5절을 기준으로 한다. 카드별 등록 검사는 110장 전체에 적용하고, 각 계열의 사용 조건과 전이는 본문에 적힌 테스트에서 확인한다. 표의 검증 테스트 열에서 등록 검사만 적힌 행은 개별 효과를 독립적으로 검증했다는 뜻이 아니다.

증원 카드 36장의 인쇄된 유닛 이름·수량·진영은 `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units`에서 카드별로 검증한다. 같은 파일은 9.5.3의 첫 턴 금지, 국가별 턴당 1장, 미군 참전, 군/군단 배치와 특수 배치 장소를 검증한다. 다른 종류의 카드는 작업 15–18에서 효과를 확인한다.

`tests/cards/test_entry_politics.py`는 Guns of August, Italy·Romania·Bulgaria·Greece, Tsar Takes Command·Fall of the Tsar·Bolshevik Revolution·Treaty of Brest-Litovsk, Zimmermann Telegram·Over There의 선행 조건과 핵심 효과를 검증한다. 5.7.4.7 이벤트 후 OPS, 9.5.2.2 턴당 중립국 한 장, 16.4.9 러시아군 제한도 포함한다.

`tests/cards/test_persistent_events.py`는 Blockade·Lusitania·Rape of Belgium·14 Points·Reichstag Truce의 VP, U-boats·Convoy·Zeppelin Raids·Walter Rathenau·Independent Air Force의 RP, High Seas Fleet·Grand Fleet 대응, French Mutiny 공격 벌점, War in Africa 선택, 카드 보충 및 마지막 턴 종료를 검증한다.

`tests/cards/test_combat_events.py`는 기본 전투 카드 27장의 등록, 국적·진영·계절·참호·선행 이벤트 조건, 전투 순서, DRM·CRT 반영, 측면 공격, Withdrawal, 단일 전투 사용 및 카드 영역 이동을 검증한다. 전투 카드의 개별 사용 조건은 `rules/events/combat.py`에서 카드 ID별로 판정한다.

`tests/cards/test_operational_events.py`는 참호·Landwehr·Salonika 선택, Moltke·Süd Army·11th Army·Everyone into Battle 활성화 비용, Yanks and Tanks·Kerensky·Brusilov 공세, Great Retreat의 전투 전 후퇴를 확인한다. `tests/test_view_replay.py`는 상대 손패·덱·RNG 비노출, 전투 카드 임의 버림, 기록 재생을 확인한다. `tests/test_full_game.py`는 Historical 초기 상태에서 합법 행동만 선택해 종료하고 같은 기록을 재생한다.

사용자 제공 [LOG1 대조 검증](log1-validation.md)은 실제 기록의 전투 결과 60줄과 대표 전투·후퇴·진격 사례를 검사한다. 기록에 빠진 주사위 눈과 덱 순서 때문에 전체 기보의 상태 동일성 검사는 할 수 없다.

| 진영 | 카드 ID | 이벤트 종류 | 기본 조항 | 검증 테스트 |
| --- | --- | --- | --- | --- |
| AP | `BRITISH_REINFORCEMENTS_BR_2` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `BLOCKADE` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `RUSSIAN_REINFORCEMENTS_RU_11` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `PLEVE` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `PUTNIK` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `WITHDRAWAL` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `SEVERE_WEATHER_AP` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `RUSSIAN_REINFORCEMENTS_2_CORPS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `MOLTKE` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_moltke_and_falkenhayn_change_cp_activation_cost` |
| AP | `FRENCH_REINFORCEMENTS_FR_10` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `RUSSIAN_REINFORCEMENTS_RU_9_RU_10` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `ENTRENCH_AP` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_entrench_event_forbidden_on_first_turn_and_places_level_one` |
| AP | `RAPE_OF_BELGIUM` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `BRITISH_REINFORCEMENTS_BR_1` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `BRITISH_REINFORCEMENTS_BR_4` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `ROMANIA` | 중립 참전 | 9.5.2  `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `ITALY` | 중립 참전 | 9.5.2  `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `HURRICANE_BARRAGE` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `AIR_SUPERIORITY_AP` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `BRITISH_REINFORCEMENTS_AUS_CND` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `PHOSGENE_GAS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `ITALIAN_REINFORCEMENTS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `CLOAK_AND_DAGGER` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `FRENCH_REINFORCEMENTS_FR_7` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `RUSSIAN_REINFORCEMENTS_RU_6_RU_7` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `LUSITANIA` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `GREAT_RETREAT` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_great_retreat_opens_russian_precombat_retreat` |
| AP | `LANDSHIPS` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `YUDENITCH_RU_REINFORCEMENTS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `SALONIKA` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_salonika_places_neutral_greeks_and_redeploys_corps` |
| AP | `MEF_BR_REINFORCEMENTS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `RUSSIAN_REINFORCEMENTS_RU_12` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `GRAND_FLEET` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `BRITISH_REINFORCEMENTS_BR_3` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `YANKS_AND_TANKS` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_yanks_and_tanks_adds_two_drm_to_us_attack` |
| AP | `MINE_ATTACK` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `INDEPENDENT_AIR_FORCE` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `USA_REINFORCEMENTS_1_CORPS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `THEY_SHALL_NOT_PASS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `14_POINTS` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `ARAB_NORTHERN_ARMY_BR_REINFORCEMENTS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `BRITISH_REINFORCEMENTS_BR_5` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `USA_REINFORCEMENTS_US_1` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `GREECE` | 중립 참전 | 9.5.2  `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `KERENSKY_OFFENSIVE` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_kerensky_and_brusilov_offer_event_combat_choices` |
| AP | `BRUSILOV_OFFENSIVE` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_kerensky_and_brusilov_offer_event_combat_choices` |
| AP | `USA_REINFORCEMENTS_US_2` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `ROYAL_TANK_CORPS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| AP | `SINAI_PIPELINE` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `ALLENBY_BR_REINFORCEMENTS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `EVERYONE_INTO_BATTLE` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_sud_army_eleventh_and_everyone_into_battle_modify_ops_cost` |
| AP | `CONVOY` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `ARMY_OF_THE_ORIENT_FR_REINFORCEMENTS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| AP | `ZIMMERMANN_TELEGRAM` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| AP | `OVER_THERE` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `GUNS_OF_AUGUST` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `WIRELESS_INTERCEPTS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `VON_FRANCOIS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `SEVERE_WEATHER_CP` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `LANDWEHR` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_landwehr_flips_reduced_german_units_without_rp` |
| CP | `ENTRENCH_CP` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_entrench_event_forbidden_on_first_turn_and_places_level_one` |
| CP | `GERMAN_REINFORCEMENTS_GE_9` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `RACE_TO_THE_SEA` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `REICHSTAG_TRUCE` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `SUD_ARMY` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_sud_army_eleventh_and_everyone_into_battle_modify_ops_cost` |
| CP | `OBEROST` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `GERMAN_REINFORCEMENTS_GE_10` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `FALKENHAYN` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_moltke_and_falkenhayn_change_cp_activation_cost` |
| CP | `AUSTRIA_HUNGARY_REINFORCEMENTS_AH_7` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `CHLORINE_GAS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `LIMAN_VON_SANDERS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `MATA_HARI` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `FORTIFIED_MACHINE_GUNS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `FLAMETHROWERS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `AUSTRIA_HUNGARY_REINFORCEMENTS_AH_10` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `GERMAN_REINFORCEMENTS_GE_11` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `GERMAN_REINFORCEMENTS_GE_12` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `AUSTRIA_HUNGARY_REINFORCEMENTS_AH_11` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `LIBYAN_REVOLT_TU_REINFORCEMENTS` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `HIGH_SEAS_FLEET` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `PLACE_OF_EXECUTION` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `ZEPPELIN_RAIDS` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `TSAR_TAKES_COMMAND` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `11TH_ARMY` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_sud_army_eleventh_and_everyone_into_battle_modify_ops_cost` |
| CP | `ALPENKORPS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `KEMAL` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `WAR_IN_AFRICA` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `WALTER_RATHENAU` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `BULGARIA` | 중립 참전 | 9.5.2  `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `MUSTARD_GAS` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `U_BOATS_UNLEASHED` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `HOFFMANN` | 일반 | 9.5.1 | `tests/cards/test_operational_events.py::test_hoffmann_requires_h_l_and_increases_cp_mo_die` |
| CP | `GERMAN_REINFORCEMENTS_2_CORPS_CP_38` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `GERMAN_REINFORCEMENTS_2_CORPS_CP_39` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `AIR_SUPERIORITY_CP` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `GERMAN_REINFORCEMENTS_GE_14` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `TURKISH_REINFORCEMENTS_YLD` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `VON_BELOW` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `VON_HUTIER` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `TREATY_OF_BREST_LITOVSK` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `GERMAN_REINFORCEMENTS_GE_17_GE_18` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `FRENCH_MUTINY` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `TURKISH_REINFORCEMENTS_AOI` | 증원 | 9.5.3 | `tests/cards/test_reinforcements.py::test_all_reinforcement_cards_have_handler_and_unique_unused_units` |
| CP | `MICHAEL` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `BLUCHER` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `PEACE_OFFENSIVE` | 전투 | 9.5.4 | `tests/cards/test_combat_events.py::test_all_27_combat_cards_registered` |
| CP | `FALL_OF_THE_TSAR` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `BOLSHEVIK_REVOLUTION` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `H_L_TAKE_COMMAND` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
| CP | `LLOYD_GEORGE` | 일반 | 9.5.1 | `tests/cards/test_event_inventory.py::test_every_historical_base_card_has_a_registered_handler` |
