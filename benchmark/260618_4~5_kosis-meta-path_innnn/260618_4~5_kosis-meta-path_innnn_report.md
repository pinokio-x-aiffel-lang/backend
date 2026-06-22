# 260618 · [4+5 대안] map_claim_via_meta smoke · innnn

## 1. Overview

기존 [4] 트리 드릴다운 + [5] 규칙/LLM 폴백 경로와 **병행**하는 새 경로
`src/modules/map_claim_via_meta.py`(검색 → 메타 직접 판독 → LLM이 표·코드 선택 → 셀 조회)의
배관을 실제 KOSIS로 검증한다. 절차 명세: `.claude/skills/kosis-lookup/SKILL.md`.

## 2. What was tested

대표 5건(260617 10건 중, 주제·연산 다양 + 난이도 포인트 포함)으로 두 모드 점검:
- **MOCK 배관**: LLM 선택을 정답으로 주입 → 검색/메타/조회/YoY/숨은 C1축/이름매칭만 검증 (KOSIS 키만 필요, 지금 실행)
- **HCX 실호출**: HCX-007 구조화 선택 (CLOVASTUDIO_API_KEY 필요 — 사용자 테스트 예정)

난이도 포인트:
- 2축 표(청년실업률: 성별×연령)
- 지수→**YoY 직접계산**(CPI·석유류: 지수만 있는 표)
- **숨은 C1축**(제조업: `DT_1DA7E43S_NEW`, 메타 2축이나 데이터 3레벨)

## 3. 결과

### HCX-007 실호출: **5/5 PASS** (변동성 있음, 안정 4/5)

Infisical 시크릿 주입 후 HCX-007 로 실제 선택·트레이싱(Langfuse). 제 수동 결과값을 재현:

| claim | 기대 | HCX 경로 조회 | |
|---|---|---|---|
| 취업자 수 | 28,589 | 28,589 | ✅ |
| 청년 실업률 | 7.5 | 7.5 | ✅(런별 변동) |
| 소비자물가 상승률 | 2.2 | 2.2444 (지수 YoY) | ✅ |
| 석유류 물가 상승률 | 6.3 | 6.2694 (지수 YoY) | ✅ |
| 제조업 취업자 | 4,414 | 4,413.6 (숨은 C1축) | ✅ |

→ 제 수동 조회 과정을 모듈에 이식해 도달: **키워드 생성(범주어→부모 차원어, 차원
키워드 먼저) → 순차 병합 → 기간필터 → 조사명 티어 재정렬 → 메타 판독 → HCX 표·축
선택 → objL 자동레벨(20/21/30 재시도)+'계' 기본매칭 → 지수 YoY**.

**변동성**: HCX-007 은 temp 0 에도 런마다 청년실업률에서 표(7102S↔7105S)·축 지정이
흔들려 4/5↔5/5 를 오간다. → Langfuse 트레이스로 프롬프트 개선/모델 비교할 지점
(사용자 계획대로). 결정적 배관(아래 MOCK)은 5/5 고정.

### MOCK 배관: **5/5 PASS** (실제 KOSIS 대조, 결정적)

| claim | 표 | 기대 | 조회 | 판정 |
|---|---|---|---|---|
| 취업자 수 (2025.03) | DT_1DA7001S | 28,589 | 28,589 | ✅ |
| 청년 실업률 (2025.03) | DT_1DA7102S | 7.5 | 7.5 | ✅ |
| 소비자물가 상승률 (2025.01) | DT_1J22003 | 2.2 | 2.2444 (지수 YoY) | ✅ |
| 석유류 물가 상승률 (2025.02) | DT_1J22002 | 6.3 | 6.2694 (지수 YoY) | ✅ |
| 제조업 취업자 (2025.06) | DT_1DA7E43S_NEW | 4,414 | 4,413.6 (숨은 C1축) | ✅ |

→ 검색→메타→조회→**지수 YoY 직접계산**→**objL 레벨 자동조정(숨은 C1축)**→**위치 독립 이름 매칭** 전 구간 정상.

### HCX 실호출: 키 없이 **우아한 degrade 확인**
- `success=0`, error="환경변수 CLOVASTUDIO_API_KEY 를 찾을 수 없습니다." (크래시 없음)
- Langfuse도 키 없으면 자동 비활성(no-op)
- → `CLOVASTUDIO_API_KEY`(+ `LANGFUSE_*`) 설정 시 HCX-007 선택이 그대로 동작·트레이싱

## 4. 추가/변경 파일
- `.claude/skills/kosis-lookup/SKILL.md` — 절차·휴리스틱 단일 명세
- `src/prompts/prompts.py` — `SELECT_KOSIS_CELL_SYSTEM/USER`
- `src/llm/model_presets.py` — `SELECT_KOSIS_CELL` (HCX-007, structured, temp 0)
- `src/modules/map_claim_via_meta.py` — 새 경로 (기존 [4][5]·`Pipeline.run` 불변)

## 5. 다음 단계 (사용자)
1. `CLOVASTUDIO_API_KEY` + `LANGFUSE_*` 설정 → 기본 모드로 HCX-007 실호출
2. Langfuse 트레이스에서 선택 품질 확인, 성능 부족 시 다른 모델로 `SELECT_KOSIS_CELL` 교체 후 A/B
3. 만족 시 `Pipeline`에 새 경로를 옵션으로 배선(현재는 독립 호출)
