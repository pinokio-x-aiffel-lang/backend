"""비유비교 사전 로더 — metaphor.yaml → MetaphorEntry 튜플.

기사 빈출 비유 기준물(여의도 면적, 축구장 등)의 언론 관행값을 YAML 로
관리한다. value/unit 은 환산용 데이터, source/note 는 사람용 기록.
엔트리 추가·수정은 YAML 만 고치면 되고 코드는 건드리지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).with_name("metaphor.yaml")

_CATEGORIES = {"area", "height", "length", "volume", "weight"}


@dataclass(frozen=True)
class MetaphorEntry:
    """비유 기준물 1건. 필드 의미는 metaphor.yaml 헤더 참조."""

    id: str
    name: str
    aliases: tuple[str, ...]
    category: str
    value: float
    unit: str
    counters: tuple[str, ...] = ("개",)
    source: str = ""
    note: str = ""


def _build_entry(raw: dict) -> MetaphorEntry:
    missing = {"id", "name", "aliases", "category", "value", "unit"} - raw.keys()
    if missing:
        raise ValueError(f"metaphor 엔트리 필수 필드 누락: {sorted(missing)} (raw={raw!r})")
    if raw["category"] not in _CATEGORIES:
        raise ValueError(f"[{raw['id']}] 미정의 category: {raw['category']!r}")
    value = float(raw["value"])
    if value <= 0:
        raise ValueError(f"[{raw['id']}] value 는 양수여야 함: {value}")
    return MetaphorEntry(
        id=raw["id"],
        name=raw["name"],
        aliases=tuple(raw["aliases"]),
        category=raw["category"],
        value=value,
        unit=str(raw["unit"]),
        counters=tuple(raw.get("counters", ["개"])),
        source=raw.get("source", ""),
        note=raw.get("note", ""),
    )


@lru_cache(maxsize=4)
def _load(path_str: str) -> tuple[MetaphorEntry, ...]:
    data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8"))
    entries = tuple(_build_entry(raw) for raw in data.get("entries", []))
    if not entries:
        raise ValueError(f"metaphor 사전이 비어 있음: {path_str}")
    seen_ids: set[str] = set()
    seen_aliases: set[str] = set()
    for e in entries:
        if e.id in seen_ids:
            raise ValueError(f"중복 id: {e.id}")
        seen_ids.add(e.id)
        for a in e.aliases:
            if a in seen_aliases:
                raise ValueError(f"[{e.id}] 중복 alias: {a!r} (전 엔트리 통틀어 유일해야 함)")
            seen_aliases.add(a)
    return entries


def load_entries(path: Path | str | None = None) -> tuple[MetaphorEntry, ...]:
    """사전 로드(캐시). 유효성 위반 시 ValueError."""
    return _load(str(path or _DEFAULT_PATH))
