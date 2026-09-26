"""정적 규칙 자료의 로딩과 참조 무결성 검사."""

from dataclasses import dataclass
from importlib.resources import files
import json


@dataclass
class RuleData:
    cards: dict[str, dict]
    units: dict[str, dict]
    spaces: dict[str, dict]
    edges: list[dict]
    historical: dict
    source_ids: dict

    def neighbors(self, space_id: str, nation: str | None = None) -> frozenset[str]:
        if space_id not in self.spaces:
            raise ValueError(f"알 수 없는 공간: {space_id}")
        result = set()
        for edge in self.edges:
            allowed = edge["allowed_nations"]
            if allowed is not None and (nation is None or nation not in allowed):
                continue
            if edge["a"] == space_id:
                result.add(edge["b"])
            elif edge["b"] == space_id:
                result.add(edge["a"])
        return frozenset(result)


def _read_json(name: str):
    return json.loads(files(__package__).joinpath(f"{name}.json").read_text(encoding="utf-8"))


def _index(records: list[dict], label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for record in records:
        key = record["id"]
        if key in result:
            raise ValueError(f"중복 {label} ID: {key}")
        result[key] = record
    return result


def load_data() -> RuleData:
    data = RuleData(
        cards=_index(_read_json("cards"), "카드"),
        units=_index(_read_json("units"), "유닛"),
        spaces=_index(_read_json("spaces"), "공간"),
        edges=_read_json("edges"),
        historical=_read_json("historical"),
        source_ids=_read_json("source_ids"),
    )
    validate_data(data)
    return data


def validate_data(data: RuleData) -> None:
    if len(data.cards) != 110 or len(data.units) != 193 or len(data.spaces) != 361:
        raise ValueError("Historical 데이터 수량이 맞지 않습니다")
    for label, records in (("카드", data.cards), ("유닛", data.units), ("공간", data.spaces)):
        for key, record in records.items():
            if key != record.get("id"):
                raise ValueError(f"{label} ID가 일치하지 않습니다: {key}")
    seen_edges: set[tuple[str, str]] = set()
    for edge in data.edges:
        a, b = edge["a"], edge["b"]
        if a not in data.spaces or b not in data.spaces or a == b:
            raise ValueError(f"잘못된 연결선: {a}, {b}")
        pair = tuple(sorted((a, b)))
        if pair in seen_edges:
            raise ValueError(f"중복 연결선: {a}, {b}")
        seen_edges.add(pair)
        allowed = edge["allowed_nations"]
        if allowed is not None and (not allowed or len(allowed) != len(set(allowed))):
            raise ValueError(f"잘못된 제한 연결선: {a}, {b}")
    used_units: set[str] = set()
    for placement in data.historical["placements"]:
        unit_id, space_id = placement["unit_id"], placement["space_id"]
        if unit_id not in data.units:
            raise ValueError(f"초기 배치에 없는 유닛: {unit_id}")
        if space_id not in data.spaces:
            raise ValueError(f"초기 배치에 없는 공간: {space_id}")
        if unit_id in used_units:
            raise ValueError(f"유닛 중복 배치: {unit_id}")
        used_units.add(unit_id)
    for reserve in data.historical["reserve_corps"]:
        if reserve["space_id"] not in data.spaces:
            raise ValueError(f"예비 상자가 없습니다: {reserve['space_id']}")
        for unit_id in reserve["unit_ids"]:
            if unit_id not in data.units or unit_id in used_units:
                raise ValueError(f"예비 유닛이 잘못되었습니다: {unit_id}")
            used_units.add(unit_id)
    for trench in data.historical["trenches"]:
        if trench["space_id"] not in data.spaces:
            raise ValueError(f"참호 공간이 없습니다: {trench['space_id']}")
    for space_id in data.historical["vp_included"] + data.historical["vp_excluded"]:
        if space_id not in data.spaces:
            raise ValueError(f"VP 공간이 없습니다: {space_id}")
