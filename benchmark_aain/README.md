# benchmark_aain

2~10단계 **모듈별 독립 평가셋**. 다른 벤치마크(`benchmark/`)와 섞이지 않도록 분리한 폴더.

## 원칙
- **단일 진실 원천**: 모든 평가셋은 마스터셋 1개에서 파생, 각 행은 `row_id` 로 마스터 역추적.
- **무생성**: 값은 ①마스터 xlsx ②기존 실제 gold ③라이브 캡처(실제 KOSIS/LLM)에서만 온다. 지어낸 값 없음.
- **기존 파일 불변**: 기존 파일은 읽기 전용. 출력은 이 폴더 신규 파일만.
- **verdict 정답 = 사람 라벨**(옵션 ②). 캡처 공식값은 입력/표시용(`*_source` 표시) + 정합성 플래그.

자세한 설계·단계별 지표·데이터 형태·최소 수는 **`2단계~10단계_테스트_계획.md`** 참조.

## 파일
### 마스터 / 중간 산출물
- `data/260605_평가셋_T_F_M_NEI_모음.xlsx` — 마스터(213행: T123/F30/M30/NEI30). 원본 CSV에서 추출·라벨링.
- `data/260614_master_eval_213_parsed.jsonl` — 마스터 읽기전용 파싱 스파인.
- `data/260614_capture_master_stage1to8.json` — 마스터 213문장을 1~8단계에 통과시킨 실제 캡처(입력 재료).

### 단계별 평가셋 (`data/260614_source_from_origin_for_<모듈>.jsonl`)
| 단계 | 파일 | 행수 | 비고 |
|---|---|---|---|
| 2 extract | `…extract_statistical_claims.jsonl` | 313 | 기존 슬롯 gold 100 + 마스터 양성 213 |
| 3 normalize | `…normalize_claim.jsonl` | 100 | 기존 hand-labeled gold 재사용 |
| 4 retrieve | `…retrieve_kosis_candidates.jsonl` | 411 | 후보 캡처. `gold_tbl_id` 주석 보강 필요 |
| 5 fetch | `…fetch_kosis_data.jsonl` | 411 | 캡처 evidence 132건. gold: T=공식값/F·M=캡처값/NEI=없음 |
| 6 rank | `…rank_evidence.jsonl` | 68 | 후보≥2 claim만. `gold_best_index` 15건 도출 |
| 7 calculate_metric | `…calculate_metric.jsonl` | 411 | has_evidence 132. gold=라벨(M→T 매핑) |
| 8 check_alignment | `…check_alignment.jsonl` | 106 | label∈{T,M}+evidence. T76/M30. M 차원 주석 보강 |
| 9 decide_verdict | `…decide_verdict.jsonl` | 11 | 결정적 시나리오(라벨+스펙 산식) |
| 10 generate_explanation | `…generate_explanation.jsonl` | 411 | 캡처값+라벨 verdict. 템플릿=스냅샷 비교 |

### 빌드 스크립트 (재생성)
```bash
uv run python benchmark_aain/build_master_spine.py            # xlsx → 스파인
uv run x  python benchmark_aain/run_capture.py                # 213문장 1~8단계 라이브 캡처
uv run python benchmark_aain/build_eval_sets.py               # 결정적 단계(2·3·9)
uv run python benchmark_aain/build_eval_sets_from_capture.py  # 캡처 기반(4·5·6·7·8·10)
```

## 추가 주석 필요 (gold 보강 — 모두 같은 실제 행에 주석)
- **4·5·6**: 정답 `tbl_id`/`org_id` (검색 Recall·셀조회·랭킹 gold). 4단계는 `gold_tbl_id` 전부 null.
- **6**: `gold_best_index` 미도출분(68중 15만 도출).
- **8**: M 30행의 오도 **차원(dimension)** 주석.
- **5·7**: F·M 행 캡처 공식값의 `consistency_flag` 가 `mismatch`/`no_evidence` 인 행은 검토 분리.

## 알려진 한계 (정직 보고)
- 라이브 캡처 verdict 분포 = N 398 / F 13 / T 0 → 현 파이프라인 KOSIS recall이 낮아 evidence 확보가 적음. 그래서 5·7·8단계의 **실제 채점 표본은 evidence가 잡힌 행으로 제한**됨(5·7: 132, 8: 106). gold verdict는 라벨이라 무관하나, 비교 자체는 표본 한정.
- 클래스 불균형(T 우세) + 조선일보 단일 도메인 → 일반화 지표 과신 금지, 신뢰구간 명시.
