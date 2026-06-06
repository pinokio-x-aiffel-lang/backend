# KOSIS 조회 성능 벤치마크

KOSIS 조회(통계표 검색 → 메타 → 셀값) 속도를 재는 스크립트 모음.
**네트워크 바운드라 숫자는 실행마다 흔들린다** — 절대값보다 *상대 비교·결론*을 본다.

## 스크립트

| 파일 | 무엇을 재나 | HTTP |
|---|---|---|
| `bench_fetch_kosis.py` | 한 claim의 후보 10개를 ①1개 ②전체 순차 ③전체 동시(gather)로 조회 비교 | aiohttp (네이티브 async) |
| `bench_fetch_kosis_seq.py` | 여러 claim을 **순차**로 조회 (gather 없이 for-await) | `src.kosis` (requests + to_thread) |
| `bench_fetch_kosis_single.py` | claim 1건 → 표 1개 조회(메타+데이터 2콜) 베이스라인 | `src.kosis` |

한 표 조회 = `getMeta(ITM)`(메타, 코드 해소) + `getList`(데이터). resolve 실패 시 메타 1콜만.

## 실행

```bash
uv run python benchmark/bench_fetch_kosis.py [--claim "subject:pop:period:unit"]
uv run python benchmark/bench_fetch_kosis_seq.py [--repeats N] [--claims "spec,spec,..."]
uv run python benchmark/bench_fetch_kosis_single.py [--claim "subject:pop:period:unit"]
```
spec 형식: `subject:population:period:unit` (예: `총인구수:전국:2023:명`).

## 결론 (측정일 2026-06-06, claim=총인구수/전국/2023)

- **한 표 조회 ≈ 0.1~0.9s** — 메타 크기·성공여부·첫 연결에 따라 편차 큼.
- **후보 10개: 순차 ~2.5s vs 동시 ~1.0s → 동시가 ~2.5x 빠름.** 동시는 "가장 느린 한 표" 시간으로 수렴.
- **네이티브 async(aiohttp) ≈ 동기+to_thread.** I/O 바운드라 차이 미미(스레드 오버헤드 무시할 수준). 네이티브 async 이점은 수백~수천 동시 규모에서 드러남.
- **결정**: 다건 조회는 동시(gather) 채택. rate limit은 KOSIS 한도 **1000/min** 기준(lock sliding-window).

## 측정 주의 (숫자 해석 함정)

- **네트워크 바운드** → 실행/시간대마다 흔들림. 단일값 말고 범위·평균 + 측정일로 기록.
- **첫 호출은 TCP/TLS 연결 비용** 포함(이후 표는 연결 재사용으로 빠름).
- **표마다 메타(ITM) 크기가 달라 시간 제각각** — 예: 행정구역별 인구표는 시군구까지 다 담겨 무거움(~0.9s), 작은 표는 ~0.1s.
- **resolve 실패 표는 메타 1콜만**(데이터 콜 생략)이라 더 빠름 → 성공/실패가 섞이면 "순차 합이 1표×N이 아닌" 이유가 됨.
- **success 개수는 claim이 그 표 구조에 매칭되는지**에 달림(성능과 별개; 매칭 품질 문제).
