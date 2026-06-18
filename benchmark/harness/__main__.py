"""`python -m benchmark.harness` — 하니스 상태 점검(읽기 전용).

SSOT 로드 확인 + 라벨 분포 + 결과 폴더 레이아웃 + 단계별 채점기 목록을 출력한다.
실제 모듈 실행·채점은 단계별 작성자 스크립트가 공개 API(save_result 등)로 수행한다.
"""
from __future__ import annotations

from collections import Counter

from . import BENCH_DIR, SSOT_PATH, STAGE_FOLDERS, STAGE_MODULES, load_ssot
from .scoring import STAGE_SCORERS


def main() -> None:
    print(f"BENCH_DIR : {BENCH_DIR}")
    print(f"SSOT      : {SSOT_PATH.name}  ({'OK' if SSOT_PATH.exists() else '없음!'})")

    if SSOT_PATH.exists():
        rows = load_ssot()
        dist = Counter(r.get("label") for r in rows)
        print(f"  rows={len(rows)}  labels={dict(dist)}")

    print("\n단계 폴더 / 모듈 / 채점기:")
    for s in range(1, 11):
        folder = BENCH_DIR / STAGE_FOLDERS[s]
        scorer = STAGE_SCORERS.get(s)
        scorer_nm = scorer.__name__ if scorer else "— (결정적/해당없음)"
        mark = "" if folder.exists() else "  [폴더없음]"
        print(f"  [{s:>2}] {STAGE_FOLDERS[s]:<14} {STAGE_MODULES[s]:<26} {scorer_nm}{mark}")
    e2e = BENCH_DIR / "e2e"
    print(f"  [e2e] {'e2e':<14} {'(전 파이프라인)':<26} {'(해당 단계 scorer 조합)'}{'' if e2e.exists() else '  [폴더없음]'}")


if __name__ == "__main__":
    main()
