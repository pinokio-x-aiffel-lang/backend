"""from_origin_212 디버깅 러너 — 1~10단계 E2E, "몇 개나 살아남나".

benchmark/data/from_origin_212_source.jsonl 은 2단계(클레임 추출)를 통과한 claim 212건
(고유 기사 source_sentence 168건)이다. 각 고유 기사를 Pipeline.run(source_sentence) 으로
load_article(1) → … → generate_explanation(10) 까지 흘려보내,
  (1) 어느 단계에서 죽는지(raise),
  (2) 최종까지 살아남아 실제 판정(T/F/M)이 붙는 claim 이 몇 개인지
를 센다. 한 건이 실패해도 다음 건으로 계속한다(스모크).

산출(test-convention):
  - <folder>_result.json : 기사별 MasterSchema model_dump(=파이프라인이 채운 부분) + 실패지점
  - <folder>_report.md   : 개요·테스트 내용·지표

실행(시크릿 주입):
    uv run x python benchmark/260617_1~10_from-origin-212_leeaain/260617_1~10_from-origin-212_leeaain.py [--limit N] [--concurrency K]
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
BASE = HERE.name  # 폴더명 = 파일 베이스명
DATA = HERE.parent / "data" / "from_origin_212_source.jsonl"
RESULT_JSON = HERE / f"{BASE}_result.json"
REPORT_MD = HERE / f"{BASE}_report.md"


@dataclass
class RunResult:
    """기사 1건의 E2E 결과 — 입력·단계 이벤트·산출 스키마·실패 지점."""

    idx: int
    source_id: int
    article_id: str
    content: str
    steps: list[StepEvent] = field(default_factory=list)
    master: MasterSchema | None = None
    failed_step: int | None = None
    failed_name: str | None = None
    error: str | None = None
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None and self.master is not None


def _read_articles(path: Path, limit: int) -> list[dict]:
    """jsonl 읽어 source_sentence 기준 중복 제거(첫 등장 유지). 주석(#)·빈 줄 제외."""
    seen: set[str] = set()
    out: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        row = json.loads(s)
        ss = row["source_sentence"]
        if ss in seen:
            continue
        seen.add(ss)
        out.append(row)
        if limit and len(out) >= limit:
            break
    return out


async def _run_one(idx: int, row: dict) -> RunResult:
    content = row["source_sentence"]
    res = RunResult(idx=idx, source_id=row.get("source_id", -1),
                    article_id=row.get("article_id", ""), content=content)
    t0 = time.perf_counter()
    try:
        async for ev in Pipeline().run(content):
            if isinstance(ev, StepEvent):
                res.steps.append(ev)
                if ev.status == "error":
                    res.failed_step, res.failed_name, res.error = ev.step, ev.name, ev.error
            elif isinstance(ev, ResultEvent):
                res.master = ev.master_schema
    except Exception as exc:  # 단계 raise → runner 가 재raise
        if res.error is None:
            last = res.steps[-1] if res.steps else None
            res.failed_step = last.step if last else None
            res.failed_name = last.name if last else None
            res.error = str(exc)
    res.duration_s = time.perf_counter() - t0
    return res


def _verdicts(res: RunResult) -> list[str]:
    """완료건의 claim별 판정 코드 목록 (없으면 빈 리스트)."""
    if not res.ok or res.master.verifications is None:
        return []
    return [cr.verdict for cr in res.master.verifications.claim_results]


def _print_progress(res: RunResult, total: int) -> None:
    head = res.content[:36].replace("\n", " ")
    if res.ok:
        vs = _verdicts(res)
        dist = ", ".join(f"{k}×{c}" for k, c in sorted(Counter(vs).items())) or "no-claim"
        print(f"[{res.idx:>3}/{total}] OK   {res.duration_s:5.1f}s  {dist}  | {head}…")
    else:
        print(f"[{res.idx:>3}/{total}] FAIL {res.duration_s:5.1f}s  @[{res.failed_step}] {res.failed_name}: {res.error}  | {head}…")


def _dump_result_json(results: list[RunResult]) -> None:
    """기사별 산출 스키마(파이프라인이 채운 부분 = MasterSchema model_dump)를 그대로 저장."""
    payload = []
    for r in sorted(results, key=lambda x: x.idx):
        payload.append({
            "idx": r.idx,
            "source_id": r.source_id,
            "article_id": r.article_id,
            "input_source_sentence": r.content,
            "ok": r.ok,
            "failed_step": r.failed_step,
            "failed_name": r.failed_name,
            "error": r.error,
            "duration_s": round(r.duration_s, 2),
            # content 는 exclude=True 라 model_dump 에서 빠짐 = 파이프라인이 채운 부분만
            "master": r.master.model_dump(mode="json") if r.master else None,
        })
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
            async with lock:  # 중간에 죽어도 결과 보존: 완료 때마다 json 갱신
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
    claim_verdicts: Counter = Counter()
    articles_with_claim = 0
    for r in ok:
        vs = _verdicts(r)
        if vs:
            articles_with_claim += 1
        claim_verdicts.update(vs)
    total_claims = sum(claim_verdicts.values())
    # "살아남음" = 실제 판정(T/F/M)이 붙은 claim. NEI 코드 = "N" (Verdict.NOT_ENOUGH_INFO).
    survivors = sum(c for k, c in claim_verdicts.items() if k and k.upper() not in ("N", "NEI"))

    L = ["# from_origin_212 — 1~10단계 E2E 디버깅 결과", ""]
    L += ["## 1. 개요",
          "- 목적: `from_origin_212_source.jsonl`(2단계 통과 claim)을 1→10단계 끝까지 돌려, 어느 단계에서 죽는지와 최종까지 살아남는 claim 수를 센다(디버깅 스모크).",
          f"- 입력: `{DATA.name}` — claim 212건 중 고유 기사 {len(results)}건(source_sentence 중복 제거).",
          "- 흐름: `Pipeline.run(source_sentence)` (stage 2 재추출 포함).",
          f"- 원자료: `{RESULT_JSON.name}` (기사별 MasterSchema model_dump).", ""]
    L += ["## 2. 테스트 내용",
          "- 각 기사를 파이프라인 끝까지 실행, 단계 raise 는 흡수해 실패 단계로 기록하고 계속.",
          "- 완료건은 claim별 판정 코드(`verdict`)를 집계.", ""]
    L += ["## 3. 지표",
          f"- 기사 완주(무중단): **{len(ok)}/{len(results)}**  | 실패: {len(fail)}/{len(results)}",
          f"- 총 소요: {total_s:.0f}s" + (f" (평균 {total_s/len(results):.1f}s/건)" if results else ""),
          f"- 완주 기사 중 claim 보유: {articles_with_claim}/{len(ok) if ok else 0}",
          f"- 추출 claim 총계: {total_claims}",
          f"- **최종 생존 claim(판정 NEI 아님): {survivors}/{total_claims}**", ""]
    if claim_verdicts:
        L.append("- 판정 분포: " + ", ".join(f"`{k}`×{c}" for k, c in sorted(claim_verdicts.items())))
    if fail_by_step:
        L.append("- 단계별 실패: " + ", ".join(
            f"[{s}] {n} ×{c}건" for (s, n), c in sorted(fail_by_step.items(), key=lambda x: -x[1])))
    L.append("")

    # 실패 상세 (디버깅용)
    if fail:
        L += ["## 4. 실패 상세", ""]
        for r in fail:
            head = r.content[:90].replace("\n", " ")
            L.append(f"- [{r.idx}] @[{r.failed_step}] {r.failed_name} — `{r.error}`  | {head}…")
        L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="from_origin_212 1~10단계 E2E 디버깅 러너")
    ap.add_argument("--limit", type=int, default=0, help="앞 N개 고유 기사만 (0=전체)")
    ap.add_argument("--concurrency", type=int, default=6, help="동시 실행 기사 수")
    args = ap.parse_args()

    rows = _read_articles(DATA, args.limit)
    if not rows:
        raise SystemExit(f"실행할 기사 없음: {DATA}")
    print(f"E2E 디버깅 시작 — 고유 기사 {len(rows)}건, 동시 {args.concurrency}\n")

    results = asyncio.run(_run_all(rows, args.concurrency))

    _dump_result_json(results)
    REPORT_MD.write_text(_build_report(results), encoding="utf-8")
    ok = sum(r.ok for r in results)
    print(f"\n완료 {ok}/{len(results)} | 실패 {len(results)-ok}/{len(results)}")
    print(f"원자료: {RESULT_JSON}")
    print(f"리포트: {REPORT_MD}")


if __name__ == "__main__":
    main()
