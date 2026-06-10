# 테스트 결과 기록 규칙 (팀 공용)

테스트를 돌린 결과는 아래 규칙으로 **항상 `tests/results/`** 에 저장한다.

## 1. 파일명
`[날짜]_[단계]_[대상]_[작성자][_시리얼].md`  +  **동일 이름의 `.json`**

| 필드 | 규칙 |
|---|---|
| 날짜 | `YYMMDD` (예: `260610`) |
| 단계 | 파이프라인 단계 번호 — `src/pipeline/runner.py`(10단계) 기준. 여러 단계 걸치면 하이픈(`7-8`). 단계에 1:1 대응 안 되는 공통/하위 모듈은 가장 관련된 단계 번호(없으면 `x`) |
| 대상 | 검증 대상 모듈/주제. **모듈명의 `_` 는 하이픈으로** (`calculate_metric` → `calculate-metric`) |
| 작성자 | 영문 ID (예: `leeaain`) |
| 시리얼 | 같은 (날짜·단계·대상·작성자)로 **여러 번** 돌렸으면 끝에 `_01`, `_02` … |

예)
- `260610_5_metadata_leeaain.md`
- `260610_7-8_check-alignment_leeaain_02.md`

> 필드 구분은 `_`. 대상에 `_`를 쓰지 않으므로(하이픈 치환) 파싱이 모호하지 않다:
> 맨 앞=날짜, 2번째=단계, 맨 뒤=작성자(+시리얼), 가운데=대상.

## 2. .md(사람용) + .json(기계용) 한 쌍
- **`.md`**: 사람용 리포트. 아래 §3 헤더 필수.
- **`.json`**: 실제 결과(원자료)를 **동일 파일명**으로 별도 저장. `.md` 본문에서 이 json을 참조·요약한다.
  - 예: `260610_5_metadata_leeaain.md` ↔ `260610_5_metadata_leeaain.json`

## 3. .md 상단 필수 항목
1. 테스트 목적
2. 검증 대상 모듈
3. 도구로만 쓰인 모듈 (검증대상 아님)
4. 테스트 일자 / 작성자

**헤더 레벨**: 결과 `.md` 는 **문서 제목만 `#`**, 그 외 모든 섹션 제목은 **`###`** 를 쓴다 (`##` 금지).

## 4. 템플릿
```markdown
# 260610_5_metadata_leeaain

### 1. 테스트 목적
<무엇을 왜 검증하는지 한두 줄>

### 2. 검증 대상 모듈
- src/kosis/metadata.py — fetch_table_metadata, fetch_meta_item, TableMetadata

### 3. 도구로만 쓰인 모듈 (검증대상 아님)
- src/kosis/cell.py — KosisQuery, build_params
- src/kosis/client.py — call_kosis, resolve_api_key, KosisError

### 4. 테스트 일자 / 작성자
- 일자: 2026-06-10
- 작성자: leeaain

### 5. 결과  (원자료: 260610_5_metadata_leeaain.json)
- PASS n / INCONCLUSIVE n / FAIL n
- <요약·특이사항>

### 6. 한계 / 범위 밖  (선택)
- <무엇을 검증하지 않았는지>
```

## 5. 테스트 코드 파일(.py)
- **테스트한 코드(.py)도 같은 명명 규칙**을 따르고 **`tests/`** 에 저장한다: `[날짜]_[단계]_[대상]_[작성자].py` (코드 파일엔 보통 시리얼 없음).
  - 예: `260610_7_compare_leeaain.py`, `260609_5_metadata_leeaain.py`
- pytest 자동 수집을 위해 `pyproject.toml [tool.pytest.ini_options] python_files` 에
  `[0-9][0-9][0-9][0-9][0-9][0-9]_*.py` 패턴이 추가돼 있다(`test_*.py` 와 병행).

## 6. 테스트 소스(입력 데이터) 파일
- 테스트에 쓰이는 입력 데이터는 같은 규칙에 **`data_` 접두사**를 붙여 `tests/` 에 둔다:
  `data_[날짜]_[단계]_[대상]_[작성자].확장자`
  - 예: `data_260610_4_kosis-search_leeaain.txt`, `data_260610_4-5_kosis-value-fetch_leeaain.txt`
