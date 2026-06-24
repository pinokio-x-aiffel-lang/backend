# leeaain_260624_04_7e2bacb-dirty — e2e 성능 평가

### 개요
e2e 전체 평가 — funnel·verdict 분포·coverage + 최종 verdict vs 독립 gold.

### 테스트 방법
f4d9ef9 revert(7e2bacb) 효과 A/B. **상류 동결**: f4d9ef9 캡처(260624_02)의 after6(랭킹後)를 그대로 고정하고 현재(revert) 코드로 7→8→9만 재실행한 캡처(260624_capture_v2_revert.jsonl). 상류 2~6단계가 동일 입력이라 변경은 오직 compare.py(stage7) → 두 결과 차이는 순수 revert 효과(상류 LLM 노이즈 0). funnel/분포/coverage=캡처 집계, 정답대조=after9 vs 독립 gold(7·8 v2 testset).

### 성능 수치
| 지표 | 값 | 95% CI | 비고 |
|---|---|---|---|
| 기사 완주율 | 1.000 (213/213) | [0.982, 1.000] | raise 0 기대 |
| 추출 claim 수 | 395 | — | 213 완주 기사 |
| [4] 검색 hit>0 | 1.000 (395/395) | [0.990, 1.000] | retrieve |
| [5] evidence 확보 | 0.387 (153/395) | [0.341, 0.436] | fetch |
| 판정값 도달(value-reach) | 0.387 (153/395) | [0.341, 0.436] | kosis_value |
| 최종 판정 분포 | T 20 · F 64 · M 19 · N 292 | — | claim(after9) |
| coverage(생존율) | 0.261 (103/395) | [0.220, 0.306] | (T+F+M)/total |
| gap(값 도달−coverage) | 0.127 | — | 값 왔는데 NEI |
| macro-F1 | 0.611 | — | after9 vs gold(T/F/N) |
| recall[T] | 0.256 (10/39) | [0.146, 0.411] | 진짜 T→T |
| recall[F] | 0.639 (23/36) | [0.476, 0.775] | 거짓→F |
| recall[N] | 1.000 (51/51) | [0.930, 1.000] | 불가→N |
| M-recall | 0.486 (18/37) | [0.334, 0.641] | 왜곡 탐지 |
| M-precision | 0.947 (18/19) | [0.754, 0.991] |  |

### 분석
완주 213/213, claim 395, 분포 {'T': 20, 'N': 292, 'F': 64, 'M': 19}, coverage 103/395.

### 개선 전후 비교
f4d9ef9(population-fallback F→NEI 강등) 회귀를 revert 로 되돌린 결과. **동일 after6 고정 A/B**라 차이는 순수 compare.py revert.

| 지표 | f4d9ef9 (260624_03) | **revert (7e2bacb)** | 8b9c397 (직전 목표) |
|---|---|---|---|
| recall[F] | 0.444 (16/36) | **0.639 (23/36)** | 0.639 (23/36) |
| macro-F1 | 0.553 | **0.611** | 0.582 |
| coverage | 0.203 (80/395) | **0.261 (103/395)** | 0.276 (110/399) |
| gap(값→NEI) | 0.185 | 0.127 | 0.120 |
| recall[T] | 0.256 | 0.256 (불변) | 0.205 |
| recall[N] | 1.000 | 1.000 (불변) | 1.000 |
| M-recall | 0.486 | 0.486 (불변) | 0.432 |
| verdict 분포 | N315·T20·F41·M19 | N292·T20·F64·M19 | N289·T18·F75·M17 |

- f4d9ef9 가 NEI 로 강등했던 **진짜 F 7건 복구**(recall[F] 16→23/36, 8b9c397 수준 회복). macro-F1 +0.058, coverage +23.
- **recall[T]·recall[N]·M-recall 전부 불변** → revert 효과가 정확히 F 에만 국한(= f4d9ef9 는 false-F 가 아니라 true-F 를 demote). 강등 정책이 과교정이었음을 확인.
- 결론: revert 유지. 향후 재도입 시 "fallback population 이 판정 방향을 실제로 뒤집을 때만" 으로 조건 협소화 필요(BACKLOG).

### 한계·주의
최종 verdict 지표는 scorable claim만 분모. coverage 가 8b9c397(110) 대비 103 인 차이·macro-F1 미세 상회는 상류 after6 캡처가 다른 fresh-run 이라 생긴 잔여 노이즈로, compare.py 와 무관. cascade라 상류 셀-매칭 오류가 상한을 누름.
