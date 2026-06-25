"""로컬 KOSIS 메타 캐시 — getMeta(`fetch_table_metadata`) 라이브 호출을 3.9GB 크롤
스냅샷(`kosis/metadata/kosis_meta_part_*.jsonl`)으로 대체한다.

(org_id, tbl_id) → TableMetadata. 캐시 미스/파싱 실패는 None 을 돌려 호출부가 live
폴백하게 한다(완전 대체 아님 — 스냅샷은 특정 시점이라 staleness/누락 가능).

스냅샷 1줄 = `{"orgId","tblId","tblNm","meta":{"ITM":{"raw":<비표준 JSON 문자열>}, "PRD":{...}}}`.
바깥 줄은 valid JSON, meta.*.raw 만 KOSIS 비표준(키 따옴표 없음)이라 _parse_raw 로 흡수한다.
raw → list[dict] 로 만든 뒤 metadata.py 의 기존 파서를 재사용해 동일 구조를 보장한다.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path
from typing import Optional

from src.kosis.metadata import (
    TableMetadata,
    _parse_axes,
    _parse_items,
    _parse_periods,
)

_META_DIR = Path("kosis/metadata")
_INDEX_PATH = _META_DIR / "_offset_index.json"  # tblId -> [part_idx, byte_offset]

# KEY:"value" 추출(키 따옴표 없음). 값내 escape 안 된 따옴표는 KOSIS 가 거의 안 쓰므로
# 비탐욕으로 흡수(드문 손실은 live 폴백이 메움).
_KV = re.compile(r'(\w+):"((?:[^"\\]|\\.)*)"')

_index: Optional[dict[str, list]] = None
_parts: list[str] = []


def _part_files() -> list[str]:
    global _parts
    if not _parts:
        _parts = sorted(glob.glob(str(_META_DIR / "kosis_meta_part_*.jsonl")))
    return _parts


def _parse_raw(raw: str) -> list[dict]:
    """비표준 getMeta raw(예: `[{OBJ_ID:"ITEM",ITM_NM:"총인구수",...},{...}]`) → list[dict]."""
    if not raw or "{" not in raw:
        return []
    rows: list[dict] = []
    for rec in raw.split("},{"):
        d = {k: v for k, v in _KV.findall(rec)}
        if d:
            rows.append(d)
    return rows


def build_offset_index() -> int:
    """모든 part 파일을 1회 스캔해 tblId → (part_idx, byte_offset) 인덱스를 만들어 저장.

    바깥 줄만 json.loads 해 tblId 를 읽는다(빠름). 반환: 인덱싱한 표 수.
    """
    idx: dict[str, list] = {}
    parts = _part_files()
    for pi, path in enumerate(parts):
        with open(path, "rb") as fh:
            off = 0
            for raw_line in fh:
                try:
                    tid = json.loads(raw_line).get("tblId")
                    if tid:
                        idx[str(tid)] = [pi, off]
                except Exception:
                    pass
                off += len(raw_line)
    _INDEX_PATH.write_text(json.dumps(idx), encoding="utf-8")
    global _index
    _index = idx
    return len(idx)


def _load_index() -> dict[str, list]:
    global _index
    if _index is None:
        if _INDEX_PATH.exists():
            _index = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
        else:
            _index = {}
    return _index


def get_cached_metadata(org_id: str, tbl_id: str) -> Optional[TableMetadata]:
    """(org_id, tbl_id) → TableMetadata (로컬 스냅샷). 미스/파싱실패는 None.

    live `fetch_table_metadata` 와 동일 파서(_parse_items/_parse_axes/_parse_periods)를
    써서 같은 구조를 보장한다.
    """
    idx = _load_index()
    loc = idx.get(str(tbl_id))
    if not loc:
        return None
    pi, off = loc
    parts = _part_files()
    if pi >= len(parts):
        return None
    try:
        with open(parts[pi], "rb") as fh:
            fh.seek(off)
            rec = json.loads(fh.readline())
    except Exception:
        return None
    meta = rec.get("meta", {}) or {}
    itm_rows = _parse_raw((meta.get("ITM", {}) or {}).get("raw", "") or "")
    prd_rows = _parse_raw((meta.get("PRD", {}) or {}).get("raw", "") or "")
    if not itm_rows:
        return None  # 항목/축 못 얻으면 무의미 → live 폴백
    return TableMetadata(
        org_id=str(rec.get("orgId", org_id)),
        tbl_id=str(rec.get("tblId", tbl_id)),
        tbl_nm=str(rec.get("tblNm", "")),
        items=_parse_items(itm_rows),
        axes=_parse_axes(itm_rows),
        periods=_parse_periods(prd_rows),
    )
