"""전체 메타 JSONL(+patch) 를 표 단위 CSV 로 변환.

- 원본: kosis_meta_full.jsonl (3.67GB, 표 1줄)
- patch: kosis_meta_patch.jsonl (재처리로 복구한 79건) → 같은 키면 덮어씀
- list:  kosis_tables_async.csv (tblNm, vwCd, listId 매핑)

출력 CSV 컬럼 (표 1행):
    orgId, tblId, tblNm, vwCd, listId,
    prdSe, startPrdDe, endPrdDe,
    itmCount, objNames, itmNames, units,
    embedText  (임베딩 입력용 합성 문자열)

ITM 항목이 매우 많은 표(최대 15102)가 있어 itmNames/embedText 는 상한을 둔다.

실행:
    uv run python kosis/innnn/_meta_to_csv.py
"""
from __future__ import annotations

import csv
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10 * 1024 * 1024)

FULL = "kosis/innnn/kosis_meta_full.jsonl"
PATCH = "kosis/innnn/kosis_meta_patch.jsonl"
LIST_CSV = "kosis/innnn/kosis_tables_async.csv"
OUT = "kosis/innnn/kosis_meta_final.csv"

# itmNames / embedText 합성 시 ITM_NM 최대 개수 (긴 표 노이즈 방지)
MAX_ITM_NAMES = 60
MAX_EMBED_CHARS = 1000


def load_patch() -> dict[tuple[str, str], dict]:
    patch: dict[tuple[str, str], dict] = {}
    try:
        with open(PATCH, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                patch[(r["orgId"], r["tblId"])] = r
    except FileNotFoundError:
        pass
    return patch


def load_list() -> dict[tuple[str, str], dict]:
    info: dict[tuple[str, str], dict] = {}
    with open(LIST_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            info[(r["orgId"], r["tblId"])] = {
                "tblNm": r.get("tblNm", ""),
                "vwCd": r.get("vwCd", ""),
                "listId": r.get("listId", ""),
            }
    return info


def extract(rec: dict) -> dict:
    """한 표의 메타에서 CSV 필드 추출."""
    items = rec.get("items", {})

    # PRD
    prd = items.get("PRD")
    prd_obj = prd[0] if isinstance(prd, list) and prd else (prd if isinstance(prd, dict) else {})
    prd_se = prd_obj.get("PRD_SE", "") if isinstance(prd_obj, dict) else ""
    start_prd = prd_obj.get("STRT_PRD_DE", "") if isinstance(prd_obj, dict) else ""
    end_prd = prd_obj.get("END_PRD_DE", "") if isinstance(prd_obj, dict) else ""

    # ITM
    itm = items.get("ITM")
    obj_names: list[str] = []
    itm_names: list[str] = []
    units: list[str] = []
    itm_count = 0
    if isinstance(itm, list):
        itm_count = len(itm)
        seen_obj, seen_unit = set(), set()
        for x in itm:
            if not isinstance(x, dict):
                continue
            o = x.get("OBJ_NM")
            if o and o not in seen_obj:
                seen_obj.add(o)
                obj_names.append(o)
            nm = x.get("ITM_NM")
            if nm and len(itm_names) < MAX_ITM_NAMES:
                itm_names.append(nm)
            u = x.get("UNIT_NM")
            if u and u not in seen_unit:
                seen_unit.add(u)
                units.append(u)

    return {
        "prdSe": prd_se,
        "startPrdDe": start_prd,
        "endPrdDe": end_prd,
        "itmCount": itm_count,
        "objNames": " | ".join(obj_names),
        "itmNames": " | ".join(itm_names),
        "units": " | ".join(units),
    }


def build_embed_text(tbl_nm: str, fields: dict) -> str:
    parts = [tbl_nm]
    if fields["objNames"]:
        parts.append(f"분류: {fields['objNames']}")
    if fields["itmNames"]:
        parts.append(f"항목: {fields['itmNames']}")
    if fields["units"]:
        parts.append(f"단위: {fields['units']}")
    if fields["prdSe"]:
        parts.append(f"주기: {fields['prdSe']} ({fields['startPrdDe']}~{fields['endPrdDe']})")
    text = " / ".join(parts)
    return text[:MAX_EMBED_CHARS]


def main() -> None:
    patch = load_patch()
    list_info = load_list()
    print(f"patch {len(patch)}건, list {len(list_info)}건 로드")

    cols = [
        "orgId", "tblId", "tblNm", "vwCd", "listId",
        "prdSe", "startPrdDe", "endPrdDe",
        "itmCount", "objNames", "itmNames", "units", "embedText",
    ]

    n = 0
    patched = 0
    no_itm = 0
    with open(FULL, encoding="utf-8") as fin, \
         open(OUT, "w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=cols)
        writer.writeheader()

        for line in fin:
            if not line.strip():
                continue
            rec = json.loads(line)
            key = (rec["orgId"], rec["tblId"])

            # patch 우선
            if key in patch:
                rec = patch[key]
                patched += 1

            fields = extract(rec)
            if fields["itmCount"] == 0:
                no_itm += 1

            info = list_info.get(key, {})
            tbl_nm = info.get("tblNm", "")
            row = {
                "orgId": rec["orgId"],
                "tblId": rec["tblId"],
                "tblNm": tbl_nm,
                "vwCd": info.get("vwCd", ""),
                "listId": info.get("listId", ""),
                **fields,
                "embedText": build_embed_text(tbl_nm, fields),
            }
            writer.writerow(row)
            n += 1
            if n % 50000 == 0:
                print(f"  {n:,} 행 처리...")

    print(f"\n완료: {n:,} 행 → {OUT}")
    print(f"  patch 적용: {patched}건")
    print(f"  ITM 비어있는 표: {no_itm}건")


if __name__ == "__main__":
    main()
