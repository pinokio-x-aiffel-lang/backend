"""1_e2e.txt 의 각 기사를 파이프라인 끝까지 돌려보는 E2E 스모크 러너.

benchmark/data/1_e2e.txt 한 줄 = 기사 본문 1건. 각 줄을 Pipeline.run(content) 으로
load_article → … → generate_explanation(9단계)까지 흘려보내 (1) 중단 없이 도는지와
(2) 최종 판정(verifications)을 모은다. 한 줄이 실패해도 다음 줄로 계속 진행한다.
결과는 콘솔 요약 + 마크다운 리포트(e2e_result.md)로 남긴다.

실행(시크릿 주입):
    uv run x python benchmark/run_e2e.py [--limit N] [--concurrency K]
환경에 KOSIS/HCX 키가 이미 있으면:
    uv run python benchmark/run_e2e.py
"""
from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.pipeline.events import ResultEvent, StepEvent
from src.pipeline.runner import Pipeline
from src.schemas.runtime import MasterSchema

DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "1_e2e.txt"
DEFAULT_OUT = Path(__file__).resolve().parent / "e2e_result.md"


@dataclass
class E2EResult:
    """기사 1건의 E2E 실행 결과 — 단계 이벤트·최종 스키마·실패 지점."""

    idx: int                                       # 1-based 줄 번호
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


async def _run_one(idx: int, content: str) -> E2EResult:
    """기사 1건을 파이프라인 끝까지 실행. 단계 raise 는 흡수해 실패로 기록하고 계속(스모크)."""
    res = E2EResult(idx=idx, content=content)
    t0 = time.perf_counter()
    try:
        async for ev in Pipeline().run(content):
            if isinstance(ev, StepEvent):
                res.steps.append(ev)
                if ev.status == "error":
                    res.failed_step, res.failed_name, res.error = ev.step, ev.name, ev.error
            elif isinstance(ev, ResultEvent):
                res.master = ev.master_schema
    except Exception as exc:                       # 단계 함수 raise → runner 가 재raise
        if res.error is None:                      # error 이벤트를 못 받은 경우 대비
            last = res.steps[-1] if res.steps else None
            res.failed_step = last.step if last else None
            res.failed_name = last.name if last else None
            res.error = str(exc)
    res.duration_s = time.perf_counter() - t0
    return res


def _print_progress(res: E2EResult, total: int) -> None:
    head = res.content[:40].replace("\n", " ")
    if res.ok:
        v = res.master.verifications
        verdict = v.summary.overall_verdict if v else "?"
        n = v.summary.total_claims if v else 0
        print(f"[{res.idx:>2}/{total}] OK   {res.duration_s:5.1f}s  verdict={verdict} claims={n}  | {head}…")
    else:
        print(f"[{res.idx:>2}/{total}] FAIL {res.duration_s:5.1f}s  @[{res.failed_step}] {res.failed_name}: {res.error}  | {head}…")


async def _run_all(lines: list[tuple[int, str]], concurrency: int) -> list[E2EResult]:
    """줄들을 세마포어로 동시 실행 상한을 두고 돌린다. 완료 순으로 진행 출력."""
    sem = asyncio.Semaphore(concurrency)
    total = len(lines)

    async def _guarded(idx: int, content: str) -> E2EResult:
        async with sem:
            res = await _run_one(idx, content)
            _print_progress(res, total)
            return res

    results = await asyncio.gather(*(_guarded(i, c) for i, c in lines))
    return sorted(results, key=lambda r: r.idx)


def _read_lines(path: Path, limit: int) -> list[tuple[int, str]]:
    """파일을 (1-based 줄번호, 본문) 목록으로. 빈 줄 제외, limit>0 이면 앞 N건만."""
    raw = path.read_text(encoding="utf-8").splitlines()
    lines = [(i, ln) for i, ln in enumerate(raw, 1) if ln.strip()]
    return lines[:limit] if limit else lines


def _build_report(results: list[E2EResult], data_path: Path) -> str:
    ok = [r for r in results if r.ok]
    fail = [r for r in results if not r.ok]
    total_s = sum(r.duration_s for r in results)

    by_step: dict[tuple[int | None, str | None], int] = {}
    for r in fail:
        by_step[(r.failed_step, r.failed_name)] = by_step.get((r.failed_step, r.failed_name), 0) + 1
    verdicts: dict[str, int] = {}
    for r in ok:
        v = r.master.verifications
        code = v.summary.overall_verdict if v else "?"
        verdicts[code] = verdicts.get(code, 0) + 1

    out = ["# E2E 파이프라인 스모크 결과", ""]
    out.append(f"- 데이터: `{data_path}` ({len(results)}건)")
    out.append(f"- 완료: {len(ok)}/{len(results)} | 실패: {len(fail)}/{len(results)}")
    if results:
        out.append(f"- 총 소요: {total_s:.1f}s (평균 {total_s / len(results):.1f}s/건)")
    if by_step:
        hist = ", ".join(
            f"[{s}] {n} ×{c}건" for (s, n), c in sorted(by_step.items(), key=lambda x: -x[1])
        )
        out.append(f"- 단계별 실패: {hist}")
    if verdicts:
        vh = ", ".join(f"{k} ×{c}건" for k, c in sorted(verdicts.items()))
        out.append(f"- 최종 판정 분포(완료건): {vh}")
    out.append("")

    for r in results:
        head = r.content[:120].replace("\n", " ")
        if r.ok:
            v = r.master.verifications
            verdict = v.summary.overall_verdict if v else "?"
            out.append(f"## [{r.idx}] OK — overall={verdict} ({r.duration_s:.1f}s)")
            out.append(f"입력: {head}…")
            out.append("")
            claims = {c.claim_id: c for c in r.master.claims}
            if v and v.claim_results:
                for cr in v.claim_results:
                    c = claims.get(cr.claim_id)
                    subj = c.subject if c else cr.claim_id
                    unit = (c.unit if c else "") or ""
                    kosis = f"{cr.kosis_value}{unit}" if cr.kosis_value is not None else "—"
                    out.append(
                        f"- **{subj}**: 기사 `{cr.claim_value}{unit}` vs KOSIS `{kosis}` → `{cr.verdict}`"
                    )
                    if cr.explanation:
                        out.append(f"    - {cr.explanation}")
            else:
                out.append("- (추출된 claim 없음)")
        else:
            out.append(f"## [{r.idx}] FAIL @ [{r.failed_step}] {r.failed_name} ({r.duration_s:.1f}s)")
            out.append(f"입력: {head}…")
            out.append(f"오류: `{r.error}`")
        out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="1_e2e.txt 각 기사를 파이프라인 끝까지 실행하는 E2E 스모크 러너"
    )
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="기사 데이터 파일(한 줄=1건)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="마크다운 리포트 출력 경로")
    ap.add_argument("--limit", type=int, default=0, help="앞 N건만 실행 (0=전체)")
    ap.add_argument("--line", type=int, default=0, help="특정 줄 번호(1-based)만 실행 (0=비활성, --limit 무시)")
    ap.add_argument("--concurrency", type=int, default=1, help="동시 실행 기사 수 (기본 1=순차)")
    args = ap.parse_args()

    if args.line:
        lines = [(i, c) for i, c in _read_lines(args.data, 0) if i == args.line]
    else:
        lines = _read_lines(args.data, args.limit)
    if not lines:
        raise SystemExit(f"실행할 기사 없음: {args.data}")
    print(f"E2E 스모크 시작 — {len(lines)}건, 동시 {args.concurrency}\n")

    results = asyncio.run(_run_all(lines, args.concurrency))

    args.out.write_text(_build_report(results, args.data), encoding="utf-8")
    ok = sum(r.ok for r in results)
    print(f"\n완료 {ok}/{len(results)} | 실패 {len(results) - ok}/{len(results)} | 리포트: {args.out}")


if __name__ == "__main__":
    main()
