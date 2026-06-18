"""gold-true-123 — 1~10단계 E2E, "몇 개나 살아남고 T로 맞히나".

benchmark/data/2~6_from_labeled_true_source.jsonl 은 사람이 라벨링한 claim 123건으로,
전부 label=True 이고 gold figure(원본 통계표 수치)가 붙어 있다 — 즉 KOSIS에서 확실히
찾아지는 것들만 모은 셋이다. from_origin_212(비KOSIS·해외·시세 다수 혼입)와 달리
"검색 불가" 노이즈가 없으므로, 파이프라인의 진짜 생존율을 측정할 수 있다.

각 claim 을 Pipeline.run(claim) 으로 load_article(1)→…→generate_explanation(10) 까지
흘려보내,
  (1) 어느 단계에서 죽는지(raise),
  (2) [4] 검색·[5] evidence 깔때기,
  (3) 최종 판정 분포 — 전부 True 이므로 **T = 정답**, F/M = 오답, N(NEI) = 검증실패.
를 센다. 한 건이 실패해도 계속한다(스모크).

발행일은 production load_article 의 더미 2025-04 (현 파이프라인 상태 그대로).

실행:  uv run x python benchmark/260617_1~10_gold-true-123_leeaain/260617_1~10_gold-true-123_leeaain.py [--limit N] [--concurrency K]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.pipeline.events import ResultEvent, StepEvent
from src.pipeline.runner import Pipeline
from src.schemas.runtime import MasterSchema

HERE = Path(__file__).resolve().parent
BASE = HERE.name
DATA = HERE.parent / "data" / "2~6_from_labeled_true_source.jsonl"
RESULT_JSON = HERE / f"{BASE}_result.json"
REPORT_MD = HERE / f"{BASE}_report.md"


@dataclass
class RunResult:
    """claim 1건의 E2E 결과 — 입력·단계 이벤트·산출 스키마·실패 지점."""

    idx: int
    rec_id: int
    claim: str
    gold: list = field(default_factory=list)
    steps: list[StepEvent] = field(default_factory=list)
    master: MasterSchema | None = None
    failed_step: int | None = None
    failed_name: str | None = None
    error: str | None = None
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None and self.master is not None


def _read_rows(path: Path, limit: int) -> list[dict]:
    out: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s.startswith("{"):
            continue
        out.append(json.loads(s))
        if limit and len(out) >= limit:
            break
    return out


async def _run_one(idx: int, row: dict) -> RunResult:
    claim = row["claim"]
    res = RunResult(idx=idx, rec_id=row.get("id", -1), claim=claim, gold=row.get("gold", []))
    t0 = time.perf_counter()
    try:
        async for ev in Pipeline().run(claim):
            if isinstance(ev, StepEvent):
                res.steps.append(ev)
                if ev.status == "error":
                    res.failed_step, res.failed_name, res.error = ev.step, ev.name, ev.error
            elif isinstance(ev, ResultEvent):
                res.master = ev.master_schema
    except Exception as exc:  # 단계 raise
        if res.error is None:
            last = res.steps[-1] if res.steps else None
            res.failed_step = last.step if last else None
            res.failed_name = last.name if last else None
            res.error = str(exc)
    res.duration_s = time.perf_counter() - t0
    return res


def _verdicts(res: RunResult) -> list[str]:
    if not res.ok or res.master.verifications is None:
        return []
    return [cr.verdict for cr in res.master.verifications.claim_results]


def _n_evidence(res: RunResult) -> int:
    if not res.ok:
        return 0
    return sum(len(a.evidences or []) for a in (res.master.analysis or []))


def _n_hits(res: RunResult) -> int:
    """[4] 검색 결과 > 0 인 claim 수(이 입력 record 내)."""
    if not res.ok:
        return 0
    return sum(1 for a in (res.master.analysis or []) if a.kosis_search and a.kosis_search.hits > 0)


def _print_progress(res: RunResult, total: int) -> None:
    head = res.claim[:34].replace("\n", " ")
    if res.ok:
        dist = ", ".join(f"{k}×{c}" for k, c in sorted(Counter(_verdicts(res)).items())) or "no-claim"
        print(f"[{res.idx:>3}/{total}] OK   {res.duration_s:5.1f}s ev={_n_evidence(res)} {dist} | {head}…")
    else:
        print(f"[{res.idx:>3}/{total}] FAIL {res.duration_s:5.1f}s @[{res.failed_step}] {res.failed_name}: {res.error} | {head}…")


def _dump_result_json(results: list[RunResult]) -> None:
    payload = [{
        "idx": r.idx, "rec_id": r.rec_id, "claim": r.claim[:120], "gold": r.gold,
        "ok": r.ok, "failed_step": r.failed_step, "failed_name": r.failed_name, "error": r.error,
        "duration_s": round(r.duration_s, 2),
        "master": r.master.model_dump(mode="json") if r.master else None,
    } for r in sorted(results, key=lambda x: x.idx)]
    RESULT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _run_all(rows: list[dict], concurrency: int) -> list[RunResult]:
    sem = asyncio.Semaphore(concurrency)
    total = len(rows)
    done: list[RunResult] = []
    lock = asyncio.Lock()

    async def _guarded(idx: int, row: dict) -> RunResult:
        async with sem:
            res = await _run_one(idx, row)
            _print_progress(res, total)
            async with lock:
                done.append(res)
                _dump_result_json(done)
            return res

    results = await asyncio.gather(*(_guarded(i, r) for i, r in enumerate(rows, 1)))
    return sorted(results, key=lambda r: r.idx)


def _build_report(results: list[RunResult]) -> str:
    ok = [r for r in results if r.ok]
    fail = [r for r in results if not r.ok]
    total_s = sum(r.duration_s for r in results)

    fail_by_step = Counter((r.failed_step, r.failed_name) for r in fail)
    verdicts: Counter = Counter()
    for r in ok:
        verdicts.update(_verdicts(r))
    total_claims = sum(verdicts.values())
    survivors = sum(c for k, c in verdicts.items() if k and k.upper() not in ("N", "NEI"))
    t_correct = verdicts.get("T", 0)  # 전부 True → T가 정답

    # 깔때기 (claim 단위)
    claims_with_hit = sum(_n_hits(r) for r in ok)
    claims_with_ev = sum(1 for r in ok for a in (r.master.analysis or []) if (a.evidences or []))

    L = ["# gold-true-123 — 1~10단계 E2E (생존 + 정답률)", ""]
    L += ["## 1. 개요",
          f"- 입력: `{DATA.name}` — 사람이 라벨링한 claim **{len(results)}건, 전부 label=True**(KOSIS에서 확실히 찾아지는 것만).",
          "- 목적: 검색불가 노이즈가 없는 셋으로 1→10단계 **진짜 생존율 + T 정답률** 측정.",
          "- 발행일: production 더미 `2025-04` (현 파이프라인 그대로).",
          f"- 원자료: `{RESULT_JSON.name}`.", ""]
    L += ["## 2. 결과",
          f"- 기사 완주(무중단 raise 0): **{len(ok)}/{len(results)}** | 실패 {len(fail)}",
          f"- 총 소요: {total_s:.0f}s" + (f" (평균 {total_s/len(results):.1f}s/건)" if results else ""),
          f"- 재추출 claim 총계: {total_claims}",
          f"- **최종 생존 claim(NEI 아님): {survivors}/{total_claims}** "
          f"({survivors/total_claims:.1%})" if total_claims else "- 생존 claim: 0",
          f"- **T 정답(전부 True 이므로 T=정답): {t_correct}/{total_claims}** "
          f"({t_correct/total_claims:.1%})" if total_claims else "",
          ""]
    if verdicts:
        L.append("- 판정 분포: " + ", ".join(f"`{k}`×{c}" for k, c in sorted(verdicts.items())))
    L.append("")
    L += ["## 3. 깔때기 (재추출 claim 기준)",
          "| 관문 | 통과 |",
          "|---|---|",
          f"| [2] claim 추출 | {total_claims} |",
          f"| [4] KOSIS 검색 hit>0 | {claims_with_hit} |",
          f"| [5] evidence 확보 | {claims_with_ev} |",
          f"| [7~9] 실판정(NEI 아님) | {survivors} |",
          f"| 그중 T(정답) | {t_correct} |", ""]
    if fail_by_step:
        L.append("- 단계별 실패: " + ", ".join(
            f"[{s}] {n} ×{c}" for (s, n), c in sorted(fail_by_step.items(), key=lambda x: -x[1])))
        L.append("")
    if fail:
        L += ["## 4. 실패 상세", ""]
        for r in fail:
            L.append(f"- [{r.idx}] @[{r.failed_step}] {r.failed_name} — `{r.error}` | {r.claim[:70]}…")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    rows = _read_rows(DATA, args.limit)
    if not rows:
        raise SystemExit(f"실행할 claim 없음: {DATA}")
    print(f"gold-true-123 E2E 시작 — claim {len(rows)}건, 동시 {args.concurrency}\n")

    results = asyncio.run(_run_all(rows, args.concurrency))
    _dump_result_json(results)
    REPORT_MD.write_text(_build_report(results), encoding="utf-8")
    ok = sum(r.ok for r in results)
    print(f"\n완료 {ok}/{len(results)} | 실패 {len(results)-ok}")
    print(f"원자료: {RESULT_JSON}\n리포트: {REPORT_MD}")


if __name__ == "__main__":
    main()
