"""2축 표 DT_1DE9046S(연령별 경제활동상태) 로 A↔C1, B↔C2 대응을 유효 시점/항목으로 검증.

trace_axis_column_mapping.py 의 2축 케이스 보강판. 메타에서 유효한 항목(ITEM)·주기(PRD)를
먼저 받아 올바른 prdSe/시점으로 데이터를 호출해야 error 30(데이터 없음)을 피할 수 있어,
유효 시점을 탐색한 뒤 2축 대응을 검증한다.

요청/응답 예시 (itmId=T22 실업률, prdSe=M, 202505):
  [메타 ITM] 축 A(연령별): A.20 15~29세 …,  축 B(수학여부): B.00 전체 …
  [메타 PRD] PRD_SE="월", STRT=2004.05 ~ END=2025.05  → 시점은 YYYYMM(예: 202505)
  [값]  getList itmId=T22 objL1=ALL objL2=ALL prdSe=M startPrdDe=endPrdDe=202505
        응답 샘플행: {C1:"A.11", C1_NM:"15~19세", C2:"B.00", C2_NM:"전체",
                     ITM_NM:"실업률", DT:"3.8", PRD_DE:"202505"}
  → 검증: 축1 A('연령별') ↔ C1('연령별'),  축2 B('수학여부') ↔ C2('수학여부')  모두 동일

실행:  uv run x python tests/trace_2axis_check.py

작성일: 2026-06-09
작성자: leeaain2027
"""
from __future__ import annotations

from src.kosis.client import DATA_URL, META_URL, kosis_get, resolve_api_key

KEY = resolve_api_key()
ORG, TBL = "101", "DT_1DE9046S"


def meta(mtype):
    return kosis_get(META_URL, {"method": "getMeta", "apiKey": KEY,
                                "type": mtype, "orgId": ORG, "tblId": TBL})


itm = meta("ITM")
items = [r for r in itm if r.get("OBJ_ID") == "ITEM"]
axes = {}
for r in itm:
    oid = r.get("OBJ_ID")
    if oid and oid != "ITEM":
        axes.setdefault(oid, []).append(r)

print("항목(ITEM):", [(r.get("ITM_ID"), r.get("ITM_NM")) for r in items])
for oid in sorted(axes):
    rows = axes[oid]
    print(f"축 {oid} ({rows[0].get('OBJ_NM')}):",
          [(r.get("ITM_ID"), r.get("ITM_NM")) for r in rows])

prd = meta("PRD")
print("\nPRD 메타 일부:", prd[:2])

# 유효 주기/시점 추정: PRD 응답에서 PRD_SE / 최신 시점
prd_se = prd[0].get("PRD_SE") if prd else "Y"
# 최신 수록 시점 후보
last = prd[0].get("PRD_DE") or prd[0].get("END_PRD_DE")
print(f"\n추정 prdSe={prd_se!r}, 시점 후보={last!r}")

first_itm = items[0].get("ITM_ID")
for prd_se_try, prd_try in [(prd_se, last), ("Y", "2020"), ("Q", "2020Q1"),
                            ("M", "202001"), ("Y", "2017")]:
    params = {
        "method": "getList", "apiKey": KEY, "orgId": ORG, "tblId": TBL,
        "itmId": first_itm, "objL1": "ALL", "objL2": "ALL", "objL": "ALL",
        "prdSe": prd_se_try, "startPrdDe": str(prd_try), "endPrdDe": str(prd_try),
    }
    try:
        rows = kosis_get(DATA_URL, params, require_list=True)
    except Exception as e:  # noqa: BLE001
        print(f"  prdSe={prd_se_try} {prd_try}: 실패 {e}")
        continue
    if rows:
        r0 = rows[0]
        cols = {f"C{k}": r0.get(f"C{k}_OBJ_NM") for k in range(1, 5)
                if r0.get(f"C{k}_OBJ_NM") is not None}
        print(f"\n✅ 성공 prdSe={prd_se_try} {prd_try}: C-컬럼={cols}")
        print("대응 검증:")
        for i, oid in enumerate(sorted(axes)):
            meta_nm = axes[oid][0].get("OBJ_NM")
            data_nm = cols.get(f"C{i+1}")
            print(f"  축{i+1} {oid}({meta_nm!r}) ↔ C{i+1}({data_nm!r}) "
                  f"{'✅' if meta_nm == data_nm else '❌'}")
        print("샘플 행:", {k: r0.get(k) for k in
                         ("C1", "C1_NM", "C2", "C2_NM", "DT", "PRD_DE")})
        break
