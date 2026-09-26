"""RTT 정수 ID와 엔진의 안정적인 문자열 ID 대응."""

from dataclasses import dataclass

from pog_engine.data import load_data


class SourceIdError(ValueError):
    """RTT ID가 없거나 잘못된 경우."""


@dataclass(frozen=True)
class SourceIds:
    mappings: dict[str, dict[str, str]]

    @classmethod
    def from_data(cls) -> "SourceIds":
        data = load_data().source_ids
        return cls({kind: dict(data[kind]) for kind in ("cards", "units", "spaces")})

    def lookup(self, kind: str, source_id: int, *, index: int | None = None) -> str:
        context = "" if index is None else f" at index {index}"
        if not isinstance(source_id, int) or isinstance(source_id, bool):
            raise SourceIdError(f"{kind} ID {source_id!r}{context}: 정수가 아닙니다")
        value = self.mappings.get(kind, {}).get(str(source_id))
        if value is None:
            raise SourceIdError(f"{kind} ID {source_id}{context}: 대응이 없습니다")
        return value
