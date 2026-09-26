"""RTT 숫자 ID와 Python 의미 상태의 대응."""

import json
from pathlib import Path
import subprocess

from rtt_test_support import rules_path

import pytest

from pog_engine import create_game


RULES = rules_path(__file__)


def rtt_setup():
    code = "const r=require(process.argv[1]);process.stdout.write(JSON.stringify(r.setup(10762091171,'Historical',{no_supply_warnings:true})))"
    result = subprocess.run(["node", "-e", code, str(RULES)],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_source_ids_preserve_individual_corps():
    from pog_engine.rtt_replay.ids import SourceIds, SourceIdError

    ids = SourceIds.from_data()
    assert ids.lookup("cards", 66) == "GUNS_OF_AUGUST"
    assert ids.lookup("units", 68) == "GEC_CORPS_1"
    assert ids.lookup("units", 69) == "GEC_CORPS_2"
    with pytest.raises(SourceIdError, match="units.*999.*index 17"):
        ids.lookup("units", 999, index=17)


def test_setup_projects_same_board_facts():
    from pog_engine.rtt_replay.ids import SourceIds
    from pog_engine.rtt_replay.projection import project_engine, project_rtt, first_difference

    rtt = project_rtt(rtt_setup(), SourceIds.from_data())
    engine = project_engine(create_game(seed=10762091171))
    assert rtt["turn"] == engine["turn"] == 1
    assert rtt["vp"] == engine["vp"] == 10
    assert rtt["units"]["GE_1_ARMY_1"] == engine["units"]["GE_1_ARMY_1"]
    assert rtt["spaces"]["AACHEN"]["control"] == engine["spaces"]["AACHEN"]["control"]
    assert "AUSTRIA_HUNGARY_REINFORCEMENTS_BOX_320" not in rtt["spaces"]
    assert "AUSTRIA_HUNGARY_REINFORCEMENTS_BOX_320" not in engine["spaces"]
    assert first_difference({"turn": rtt["turn"], "vp": rtt["vp"]},
                            {"turn": engine["turn"], "vp": engine["vp"]}) is None


def test_first_difference_reports_nested_path():
    from pog_engine.rtt_replay.projection import first_difference

    diff = first_difference({"vp": 7, "units": {"GE_1": {"reduced": True}}},
                            {"vp": 7, "units": {"GE_1": {"reduced": False}}})
    assert diff.path == "$.units.GE_1.reduced"
    assert diff.expected is True
    assert diff.actual is False


def test_eliminated_box_matches_engine_elimination_without_step_state():
    from pog_engine.rtt_replay.ids import SourceIds
    from pog_engine.rtt_replay.projection import project_engine, project_rtt

    rtt = rtt_setup()
    rtt["location"][59] = 284  # AP_ELIMINATED_BOX
    rtt["reduced"] = [unit for unit in rtt["reduced"] if unit != 59]
    expected = project_rtt(rtt, SourceIds.from_data())["units"]["RU_8_ARMY_1"]
    engine = create_game(seed=4)
    engine["units"]["RU_8_ARMY_1"].update(location=None, eliminated=True, reduced=True)
    actual = project_engine(engine)["units"]["RU_8_ARMY_1"]
    assert expected == actual == {"location": None, "reduced": None,
                                  "eliminated": True, "permanent": False}


def test_projection_checks_round_replacement_points_and_major_events():
    from pog_engine.rtt_replay.ids import SourceIds
    from pog_engine.rtt_replay.projection import first_difference, project_engine, project_rtt

    rtt = rtt_setup()
    engine = create_game(seed=10762091171)
    expected = project_rtt(rtt, SourceIds.from_data())
    actual = project_engine(engine)
    assert expected["round"] == actual["round"] == {"AP": 0, "CP": 0}
    assert expected["rp"] == actual["rp"] == {}
    assert expected["major_events"] == actual["major_events"] == {}
    rtt["rp"]["ge"] = 2
    rtt["events"]["sud_army"] = 1
    changed = project_rtt(rtt, SourceIds.from_data())
    assert first_difference({"rp": changed["rp"]}, {"rp": actual["rp"]}).path == "$.rp.GE"
    assert changed["major_events"]["SUD_ARMY"] == 1
