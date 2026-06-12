"""3단계 normalize_claim 단독 채점 — gold 100건, R1~R4 수정 후 재측정 + 건별 소요시간.

benchmark/data/3_normalize_claim_100_gold.jsonl 의 raw 슬롯을 Claim 에 직접 넣어
(2단계 미경유) normalize_claim 모듈을 실행하고 expected 와 비교한다.
건별 소요시간 측정을 위해 순차 실행.

    uv run x python tests/260612_3_normalize_leeaain.py

대상 모듈: src.modules.normalize_claim (모듈 엔트리포인트 경유)
작성자: leeaain2027  작성일: 2026-06-12
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

from src.modules.normalize_claim import normalize_claim
from src.schemas.runtime import Article, Claim, ClaimType, MasterSchema, ValueSlot

GOLD = Path("benchmark/data/3_normalize_claim_100_gold.jsonl")
OUT_DIR = Path("tests/results")
BASE_NAME = "260612_3_normalize_leeaain"


def _matched(expected: str, got: str, rule: str) -> bool:
    if rule == "num":
        try:
            return float(expected.replace(",", "")) == float(got.replace(",", ""))
        except (ValueError, AttributeError):
            return expected == got
    if rule == "contains":
        return expected in got
    return expected == got


def _build_claim(row: dict) -> Claim:
    def slot(key: str) -> ValueSlot | None:
        g = row.get(key)
        if not g:
            return None
        return ValueSlot(raw=g["raw"], llm_value="", is_inferred=False)

    return Claim(
        claim_id=f"gold-{row['id']:03d}", article_id=f"gold-{row['id']:03d}",
        sentence=row.get("src", ""), claim_type=ClaimType.VERIFIABLE,
        subject="", value=slot("value"), unit="", aggregation="값",
        period_type="Y", period_value=slot("period_value") or ValueSlot(raw="", llm_value="", is_inferred=False),
        compare_period_value=slot("compare_period_value"),
        population="", cited_source="",
    )


async def main() -> None:
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]

    results, durations = [], []
    for row in rows:
        claim = _build_claim(row)
        ms = MasterSchema(
            article=Article(article_id=f"gold-{row['id']:03d}", content=row.get("src", ""),
                            published_at=row["base"]),
            claims=[claim],
        )
        t0 = time.perf_counter()
        await normalize_claim(ms)
        dur = time.perf_counter() - t0
        durations.append(dur)

        rec = {"id": row["id"], "base": row["base"], "duration_s": round(dur, 3), "slots": []}
        for key, got in (
            ("value", claim.value.llm_value),
            ("period_value", claim.period_value.llm_value),
            ("compare_period_value",
             claim.compare_period_value.llm_value if claim.compare_period_value else None),
        ):
            g = row.get(key)
            if not g:
                continue
            ok = _matched(g["expected"], got or "", g.get("match", "exact"))
            rec["slots"].append({"slot": key, "raw": g["raw"], "expected": g["expected"],
                                 "got": got, "ok": ok})
        results.append(rec)
        print(f"  {row['id']:3d}  {dur*1000:6.0f}ms  "
              f"{sum(s['ok'] for s in rec['slots'])}/{len(rec['slots'])}")

    flat = [s | {"id": r["id"]} for r in results for s in r["slots"]]
    by_slot = {}
    for key in ("value", "period_value", "compare_period_value"):
        ss = [s for s in flat if s["slot"] == key]
        by_slot[key] = {"n": len(ss), "ok": sum(s["ok"] for s in ss),
                        "acc": round(sum(s["ok"] for s in ss) / len(ss), 4) if ss else 0}
    n_all, ok_all = len(flat), sum(s["ok"] for s in flat)

    t_stats = {
        "mean_s": round(statistics.mean(durations), 3),
        "median_s": round(statistics.median(durations), 3),
        "min_s": round(min(durations), 3),
        "max_s": round(max(durations), 3),
        "total_s": round(sum(durations), 1),
    }

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{BASE_NAME}.json").write_text(json.dumps({
        "module": "normalize_claim (모듈 엔트리포인트, 2단계 미경유)",
        "input": str(GOLD), "n_sentences": len(rows), "n_slots": n_all,
        "note": "R1~R4 수정 후 재측정. 건별 소요시간 측정 위해 순차 실행.",
        "accuracy": {"total": round(ok_all / n_all, 4), "by_slot": by_slot},
        "timing": t_stats,
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    fails = [s for s in flat if not s["ok"]]
    rowmd = lambda s: (f"| {s['id']} | {s['slot']} | {s['raw']} | {s['expected']} | "
                       f"{s['got']} |")
    md = f"""# 3단계 normalize_claim 단독 채점 — R1~R4 수정 후 재측정

| 항목 | 내용 |
|---|---|
| ① 목적 | 기간 룰 수정(R1~R4) 후 정규화 정확도 재측정 + 건별 소요시간 |
| ② 검증 대상 모듈 | `src.modules.normalize_claim` (모듈 엔트리포인트) |
| ③ 도구로만 쓰인 모듈 | `src.llm` (LLM 폴백 경로) |
| ④ 일자/작성자 | 2026-06-12 / leeaain2027 |

- 입력: `{GOLD}` 100건 → 슬롯 {n_all}개. **2단계 미경유** — gold raw 를 Claim 에 직접 주입
- 건별 시간 측정 위해 **순차 실행** (병렬 아님 — 운영 지연과 다름)
- 비교 기준: 260611_3 (수정 전) 전체 0.559 / value 0.540 / period 0.792 / compare 0.295
- 원자료: `{BASE_NAME}.json`

## 정확도

| 전체 | value | period_value | compare_period_value |
|---|---|---|---|
| **{ok_all}/{n_all} ({ok_all/n_all:.1%})** | {by_slot['value']['ok']}/{by_slot['value']['n']} ({by_slot['value']['acc']:.1%}) | {by_slot['period_value']['ok']}/{by_slot['period_value']['n']} ({by_slot['period_value']['acc']:.1%}) | {by_slot['compare_period_value']['ok']}/{by_slot['compare_period_value']['n']} ({by_slot['compare_period_value']['acc']:.1%}) |

## 소요시간 (건=문장 1건, value·period·compare 슬롯 내부 병렬)

| 평균 | 중앙값 | 최소 | 최대 | 합계 |
|---|---|---|---|---|
| {t_stats['mean_s']}s | {t_stats['median_s']}s | {t_stats['min_s']}s | {t_stats['max_s']}s | {t_stats['total_s']}s |

## 오답 ({len(fails)}건)

| id | slot | raw | expected | got |
|--|--|--|--|--|
{chr(10).join(rowmd(s) for s in fails) if fails else '_없음_'}
"""
    (OUT_DIR / f"{BASE_NAME}.md").write_text(md, encoding="utf-8")

    print(f"\n전체 {ok_all}/{n_all} ({ok_all/n_all:.1%})")
    for k, v in by_slot.items():
        print(f"  {k}: {v['ok']}/{v['n']} ({v['acc']:.1%})")
    print(f"소요시간: 평균 {t_stats['mean_s']}s / 중앙값 {t_stats['median_s']}s / "
          f"최대 {t_stats['max_s']}s / 합계 {t_stats['total_s']}s")
    print(f"저장: {OUT_DIR}/{BASE_NAME}.{{md,json}}")


if __name__ == "__main__":
    asyncio.run(main())
