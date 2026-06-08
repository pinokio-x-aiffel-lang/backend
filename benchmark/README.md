# KOSIS 조회 벤치마크

KOSIS 통계표 조회(검색 → `getMeta` → `getList`) 속도를 재는 스크립트 모음.
**네트워크 바운드라 숫자는 실행마다 흔들린다** — 절대값보다 *상대 비교*를 본다.
한 표 조회 = `getMeta(ITM)`(코드 해소) + `getList`(데이터), 최대 2콜.

## 스크립트

| 파일 | 용도 | 방식 |
|---|---|---|
| `bench_fetch_kosis.py` | 한 claim의 후보 표를 **①1개 ②전체 순차 ③전체 동시(gather)** 3방식으로 1회 조회·비교 | aiohttp 네이티브 async (src.kosis 미사용) |
| `bench_concurrent_vs_sequential.py` | 한 claim의 후보 표 전체를 **동시 vs 순차로 N회 반복** 측정. 표별 소요시간·실패사유 기록, `result.json` 저장 후 회차별 요약 표 출력 | 동시=aiohttp async / 순차=requests 동기 for 루프 |

## 실행

```bash
uv run python benchmark/bench_fetch_kosis.py [--claim "subject:pop:period:unit"]
uv run python benchmark/bench_concurrent_vs_sequential.py [--repeats N] [--claim "subject:pop:period:unit"]
```

- claim 형식: `subject:population:period:unit` (예: `총인구수:전국:2023:명`)
- `bench_concurrent_vs_sequential.py` 는 실행할 때마다 `benchmark/result.json` 을 생성/갱신(매 회 기록). 기본 `--repeats 10`.

## 참고

- 측정 함정·기록 원칙: 노션 "성능 평가 기록 원칙(벤치마크/측정)" 참고.
- 최근 결과(예, 후보 10개): 동시 ~0.9s vs 순차 ~2.6s → **동시가 약 3배** 빠름.
