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
- 입력 문장: **지난해(2023년) 한국의 경제성장률은 1.5%에 그쳤다.**
- overall_verdict: **F**

**추출 claims**

| 유형 | subject | population | 값(raw→정규화) | 시점 |
|---|---|---|---|---|
| absolute | 한국의 경제성장률 | 한국 전체 | 1.5%→1.5 | Y:2023 |

**검증 결과**

| verdict | 주장값 | KOSIS값 | 표 | 설명 |
|---|---|---|---|---|
| F | 1.5 | 1.6 | 경제성장률(시도) | 기사의 2023년 한국의 경제성장률 1.5%는 KOSIS 공식 수치(1.6%)와 다릅니다. 불일치 유형: magnitude. (출처: 경제성장률(시도)) |
