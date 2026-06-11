# 2단계 claim 추출 — detection P/R/F1

| 항목 | 내용 |
|---|---|
| ① 테스트 목적 | claim 추출기가 "문장에 통계 claim이 있는지"를 맞히는지(탐지) Precision/Recall/F1 측정 |
| ② 검증 대상 모듈 | `src.modules.extract_statistical_claims` (파이프라인 2단계) |
| ③ 도구로만 쓰인 모듈 | 없음 — **load_article 미사용**, `Article(content=문장)` 직접 구성해 2단계만 호출 |
| ④ 일자 / 작성자 | 2026-06-11 / leeaain2027 |

- 입력: `benchmark/data/2_single_sentence_for_claim_extractor.jsonl` (양성 50 + 음성 50: clean 36 + 경계 14)
- 모델: **HCX-007** (alias `hyperclova`), max_tokens=2048, **temperature=0.0** — `EXTRACT_CLAIMS` preset 경유(preset + 호출부 모두 적용)
- 판정: **non-NONE claim ≥1 → predicted positive**
- 실행: 100문장 × **3회** / 167.8s / 동시성 6 (HCX 429 rate-limit은 retry-with-delay로 흡수, 전 run 100건 완료)
- 원자료: `260611_2_claim-extractor_leeaain.json`

## 결과 (3회, mean[min~max])

| 컷 | Precision | Recall | F1 |
|---|---|---|---|
| 전체 (양성50 + 음성50) | 0.837 [0.83~0.85] | 0.993 [0.98~1.0] | 0.909 [0.899~0.917] |
| **엄격 (양성50 + clean음성36, 경계14 제외)** | **0.914 [0.91~0.93]** | **0.993** | **0.952 [0.942~0.962]** |

> ⚠ **Precision 은 hard-negative 기준 보수치(운영 대표값 아님).**
> ⚠ **temperature=0이어도 완전 결정적 아님** — 3회 중 2문장(id44, id77)의 pred가 run마다 바뀜(HCX 서버측 비결정성). 단일 run F1은 ±0.01 수준 변동.

## 오답 (마지막 run: FP 10 / FN 0)
- clean 음성 FP 5: id56·64(물가 목표치 2%), id58(전망 인원수), id71(잠재성장률 정의), id77(취업자 1위 순위)
- 경계 음성 FP 5: id87·89·93·95·98 (전망·견해·기록기간 — claim으로 볼 여지 있음)
- FN: 마지막 run 0건 (run1에선 id44 "기준금리 동결·연 3%" 1건 miss)

## 해석
- **Recall ≈ 0.99** — 실제 claim 거의 안 놓침(추출 단계에 바람직한 프로필).
- **Precision(엄격) ≈ 0.91** — 과추출은 목표치·용어정의·순위·전망 인원수 같은 "수치처럼 보이는 비-측정값"에 집중.
- 경계 5건 FP는 전망치/견해/기록기간으로, 운영 기준으론 정상 추출일 수 있음.
