"""주제별(MT_ZTITLE) 트리에서 '취업자(1963~현재)' 폴더 아래 통계표 리스트.
실행: uv run x python tests/_explore_kosis_list.py
"""
from src.kosis import KosisError, kosis_get, resolve_api_key

LIST_URL = "https://kosis.kr/openapi/statisticsList.do"


def _list(parent_id=None) -> list[dict]:
    """parent_id 폴더 바로 아래 자식(폴더/표). parent_id 생략 시 최상위 주제.

    KOSIS err 30(데이터 없음)=자식 없는 잎 → 빈 리스트로 처리(재귀 안전)."""
    p = {"method": "getList", "apiKey": resolve_api_key(), "vwCd": "MT_ZTITLE"}
    if parent_id is not None:
        p["parentListId"] = parent_id
    try:
        return kosis_get(LIST_URL, p, require_list=True)
    except KosisError as e:
        if str(e).startswith("30"):                # "30: 데이터가 존재하지 않습니다."
            return []
        raise


def find_folder(name: str, parent_id=None) -> str | None:
    """parent_id 하위에서 LIST_NM 에 name 이 포함된 첫 '폴더'의 LIST_ID (깊이 가변 → 재귀)."""
    kids = _list(parent_id)
    for it in kids:                                # 1) 직접 자식부터 검사
        if not it.get("TBL_ID") and name in (it.get("LIST_NM") or ""):
            return it["LIST_ID"]
    for it in kids:                                # 2) 없으면 하위 폴더로 재귀
        if it.get("TBL_ID"):
            continue
        hit = find_folder(name, it["LIST_ID"])
        if hit:
            return hit
    return None


def tables_under(list_id: str) -> list[dict]:
    """list_id 폴더 바로 아래의 통계표(TBL_ID 있는 항목)만."""
    return [it for it in _list(list_id) if it.get("TBL_ID")]


def emp_tables() -> list[dict]:
    labor = find_folder("노동")                     # 최상위 → 노동
    eai   = find_folder("경제활동인구조사", labor)    # 노동 하위 → 경제활동인구조사
    emp   = find_folder("취업자(1963", eai)          # 그 하위 → 취업자(1963~현재)
    if emp is None:
        raise RuntimeError("취업자 폴더를 찾지 못함")
    return tables_under(emp)


def main():
    tables = emp_tables()
    print(f"취업자(1963~현재) 아래 통계표 {len(tables)}개")
    print("keys:", list(tables[0].keys()) if tables else "(없음)")
    for t in tables:
        print(f"  [{t.get('ORG_ID')}/{t.get('TBL_ID')}] {t.get('TBL_NM')}")


if __name__ == "__main__":
    main()
