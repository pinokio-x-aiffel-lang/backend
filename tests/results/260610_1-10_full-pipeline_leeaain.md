# 260610_1-10_full-pipeline_leeaain

### 1. 테스트 목적
문장 1개를 넣어 runner.py 전체 파이프라인([1]~[10])이 끝까지 동작하고 verdict·설명을 산출하는지 확인.
### 2. 검증 대상 모듈
- src/pipeline/runner.py (Pipeline) + src/modules/* [1]~[10] 전 단계
### 3. 도구로만 쓰인 모듈
- 없음 (Pipeline().run 직접 호출)
### 4. 일자 / 작성자
- 2026-06-10 / leeaain

### 5. 결과 · 원자료: 260610_1-10_full-pipeline_leeaain.json
- 입력 문장: **지난달인 2025년 3월의 전체 연령대 실업률은 3%대였다.**
- overall_verdict: **T**

**추출 claims**

| 유형 | subject | population | 값(raw→정규화) | 시점 |
|---|---|---|---|---|
| absolute | 실업률 | 전체 연령대 | 3%→3.0 | M:2025-03 |

**검증 결과**

| verdict | 주장값 | KOSIS값 | 표 | 설명 |
|---|---|---|---|---|
| T | 3.0 | 3.1 | 성/교육정도별 실업률 | 기사의 2025년 3월 실업률 3.0%는 KOSIS 공식 수치와 일치합니다. (출처: 성/교육정도별 실업률) |
