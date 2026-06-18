# from_origin 1~6단계 — 생존 카운트 결과

## 1. 개요
- 목적: `from_origin_212_source.jsonl`(고유 기사)을 1→6단계만 돌려, 어느 단계에서 죽는지와 6단계 후 evidence 가 붙는 claim(=생존) 수를 센다(스모크).
- 생존 정의: 6단계(rank_evidence) 후 그 claim 의 `analysis.evidences` ≥1 (= KOSIS 셀값을 찾아 랭킹까지 통과 → 7단계 비교 대상).
- 입력: `from_origin_212_source.jsonl` — 고유 기사 168건(source_sentence 중복 제거).
- 원자료: `260617_1~6_from-origin-survival_leeaain_result.json` (기사별 MasterSchema model_dump).

## 2. 테스트 내용
- 각 기사를 1~6단계만 실행, 단계 raise 는 흡수해 실패 단계로 기록하고 다음 기사로 계속.
- production `src/pipeline/runner.py` 의 앞 6단계와 동일 함수·순서.

## 3. 지표
- 기사 완주(1~6 무중단): **168/168**  | 실패: 0/168
- 총 소요: 3011s (평균 17.9s/건)

### claim 퍼널 (전체 기사 합산)
- 추출 claim: **358**
- ④ candidate 보유 claim: 247 (69.0% of 추출)
- ⑥ **생존 claim(evidence≥1): 57** (15.9% of 추출, 23.1% of candidate)
- 생존 claim 보유 기사: 34/168
