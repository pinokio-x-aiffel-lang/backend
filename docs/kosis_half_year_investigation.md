# KOSIS 반기(S) 데이터 조회 가능 여부 조사 결과

**작성일:** 2026-06-02  
**작성자:** 인님  
**목적:** normalize 전처리 항목으로 반기 시점 처리가 필요한지 판단하기 위한 조사

---

## 결론 요약

> **반기(S) 데이터는 KOSIS에 존재하지만, MCP와 우리 파이프라인 모두 안정적 조회가 불가능하다. 반기가 포함된 주장은 `verdict=판단불가`로 처리한다.**

---

## 전체 흐름

### Step 1 — 반기 테이블 존재 확인
> MCP로 검색하면 `prd_se` 가 전부 Y로 나와서 반기가 없는 것처럼 보인다.

```
mcp.search_statistics("반기", org_id="101")
→ 결과 10건, prd_se 전부 "Y"

mcp.search_statistics("반기", org_id="301")
→ 결과 1건: DT_105Y001 (예금규모별 계좌수 및 금액), prd_se: "Y"
```

그런데 해당 테이블 메타데이터를 직접 조회하면 실제로는 `S`였다.

```
mcp.get_table_metadata("301", "DT_105Y001")
→ prd_se: "S"
→ period_range: "2002 1/2~2025 2/2"
```

**→ 반기 데이터는 존재함. 검색 결과의 prd_se는 신뢰 불가.**

---

### Step 2 — MCP로 반기 데이터 조회 시도
> 다양한 날짜 형식으로 시도했지만 전부 빈 결과.

```python
# 시도한 형식들
mcp.get_statistics_data("301", "DT_105Y001", "2023 1/2", "2025 2/2", prd_se="S")  → 데이터 없음
mcp.get_statistics_data("301", "DT_105Y001", "20231",    "20252",    prd_se="S")  → 데이터 없음
mcp.get_statistics_data("301", "DT_105Y001", "202401",   "202402",   prd_se="S")  → 데이터 없음
mcp.get_statistics_data("301", "DT_105Y001", "2020",     "2025",     prd_se="Y")  → 데이터 없음
```

**→ MCP로는 이 테이블 조회 불가.**

---

### Step 3 — MCP 소스코드 분석으로 형식 확인
> `korean-stat-mcp` 패키지 소스(`kosis_tools/data.py`)에서 변환 로직 발견.

```python
# kosis_tools/data.py normalize_period()
# 분기: "2025 3/4" → "202503"  (year + quarter 2자리)
# 반기: "2025 1/2" → "202501"  (year + half 2자리)
#       "2025 2/2" → "202502"
```

또한 반기 실패 시 연간으로 폴백하는 로직도 존재:

```python
# 4. 반기(S) 실패 시 년간(Y) 폴백 시도
if actual_prd_se == "S" and len(prd_info) > 1:
    ...
```

**→ 형식은 확인됨. 실패 시 폴백 로직도 있으나 여기서도 실패.**

---

### Step 4 — KOSIS API 직접 호출로 원인 파악
> Python으로 직접 API 호출 → `objL` 파라미터 필수 에러 발생.

```
GET statisticsParameterData.do?prdSe=S&startPrdDe=202401&...&objL=ALL
→ {'err': '20', 'errMsg': '필수요청변수값이 누락되었습니다. (objL)'}

# objL=ALL, objL1=ALL, 둘 다, 없음 — 4가지 모두 동일한 에러
```

**→ 이 테이블은 `objL`에 특정 분류 코드값이 필요함.**

---

### Step 5 — OBJ_VAR 자동 탐색 가능 여부 확인
> MCP는 `get_obj_vars()` 로 분류 코드를 자동 탐색하는 로직이 있다. 10개 테이블 모두 테스트.

```
GET statisticsData.do?method=getMeta&type=OBJ_VAR&tblId=DT_105Y001
→ {'err': '30', 'errMsg': '데이터가 존재하지 않습니다.'}
```

| # | 테이블 | prd_se | OBJ_VAR 결과 |
|---|--------|--------|--------------|
| 1 | DT_2KAA207 (합계출산율) | Y | ✗ 데이터 없음 |
| 2 | DT_1B81A17 (시군구/출산율) | Y | ✗ 데이터 없음 |
| 3 | DT_1DA7104S (실업률) | Y | ✗ 데이터 없음 |
| 4 | DT_1B040A3 (인구수) | Y | ✗ 데이터 없음 |
| 5 | DT_1BPA101 (장래출산율) | Y | ✗ 데이터 없음 |
| 6 | DT_1B81A21 (시도/출산율) | Y | ✗ 데이터 없음 |
| 7 | DT_200Y104 (GDP 분기) | Q | ✗ 데이터 없음 |
| 8 | DT_200Y160 (GDP 명목) | Y | ✗ 데이터 없음 |
| 9 | DT_105Y001 (예금 반기) | **S** | ✗ 데이터 없음 |
| 10 | DT_133001N_1459 (근로장려금) | Y | ✗ 데이터 없음 |

**→ OBJ_VAR 메타데이터는 전 테이블 비어 있음. 자동 탐색 불가.**

---

### Step 6 — 그럼 MCP가 Y/Q는 어떻게 되는 거야?
> MCP가 OBJ_VAR 없이도 Y/Q를 성공하는 이유를 코드에서 확인.

```python
# kosis_tools/data.py get_data_with_smart_retry()
if obj_levels == 0:  # OBJ_VAR 없을 때
    result = self._try_no_obj_metadata_strategies(...)
    # → objL2="" / "ALL" / "0" 등을 순서대로 자동 시도
```

실제로 우리 `client.py`로 직접 호출하면 `objL2="ALL"` 고정이라 실패하는 테이블을 MCP는 성공함:

```python
# 우리 client.py (objL2="ALL" 고정)
DT_2KAA207 (합계출산율) → ✗ err:21 잘못된 요청
DT_200Y104 (GDP 분기)   → ✗ err:21 잘못된 요청

# MCP (스마트 재시도)
DT_2KAA207 (합계출산율) → ✓ 452건  (대한민국: 0.72)
DT_1B040A3 (인구수)     → ✓ 1746건 (전국: 51,325,329명)
```

**→ MCP는 스마트 재시도 덕분에 Y/Q 조회 가능. 반기(S)만 실패.**

---

## 최종 결론

| 구분 | MCP | 우리 `client.py` |
|------|-----|-----------------|
| Y (연간) | ✓ | 테이블에 따라 실패 |
| Q (분기) | ✓ | 테이블에 따라 실패 |
| S (반기) | ✗ | ✗ |

### 반기에 대한 처리 방향
- `PeriodType`에 `"S"` 추가하지 않음
- normalize 단계에서 `"상반기"`, `"하반기"` 등 반기 표현 감지 시 → `verdict=판단불가` 마킹
- 우리 `client.py`의 `objL2` 문제는 `fetch_kosis_data` 구현 시 별도 해결 필요

### 부수적 발견
- KOSIS 검색 결과의 `prd_se` 필드는 실제 기간 유형을 반영하지 않는 경우가 있음 (신뢰 불가)
- OBJ_VAR 자동 탐색 엔드포인트는 현재 모든 테이블에서 빈 값 반환
- 분기 `PRD_DE` 형식: `"202401"` = 2024년 1분기, `"202404"` = 2024년 4분기 (실제 데이터로 확인)
- 반기 `PRD_DE` 형식: `"202401"` = 2024년 상반기, `"202402"` = 2024년 하반기 (소스코드로 확인, 실데이터 미확인)
