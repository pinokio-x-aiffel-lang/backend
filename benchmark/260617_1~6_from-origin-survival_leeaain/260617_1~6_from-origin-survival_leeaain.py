"""from_origin 1~6단계 생존 러너 — "6단계까지 몇 개나 살아남나".

benchmark/data/from_origin_212_source.jsonl 의 고유 기사(source_sentence 168건)를
  load_article(1) → extract_statistical_claims(2) → normalize_claim(3)
  → retrieve_kosis_candidates(4) → fetch_kosis_data(5) → rank_evidence(6)
까지만 흘려보내,
  (1) 어느 단계에서 죽는지(raise),
  (2) 6단계 후 evidence 가 붙은 claim 이 몇 개인지(=생존)
를 센다. 한 건이 실패해도 다음 건으로 계속한다(스모크).

생존 정의: 6단계(rank_evidence) 후 그 claim 의 analysis.evidences 가 ≥1 인 claim
          (= KOSIS 셀값을 찾아 랭킹까지 통과 → 7단계 비교 대상으로 살아남음).

산출(test-convention):
  - <folder>_result.json : 기사별 MasterSchema model_dump(파이프라인이 채운 부분) + 실패지점
  - <folder>_report.md   : 개요·테스트 내용·지표(퍼널)

실행(시크릿 주입):
    uv run x python benchmark/260617_1~6_from-origin-survival_leeaain/260617_1~6_from-origin-survival_leeaain.py [--limit N] [--concurrency K]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.load_article import load_article
from src.modules.normalize_claim import normalize_claim
from src.modules.rank_evidence import rank_evidence
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import MasterSchema

HERE = Path(__file__).resolve().parent
BASE = HERE.name  # 폴더명 = 파일 베이스명
DATA = HERE.parent / "data" / "from_origin_212_source.jsonl"
RESULT_JSON = HERE / f"{BASE}_result.json"
REPORT_MD = HERE / f"{BASE}_report.md"

# 1~6단계만 (production runner.py 의 앞 6단계와 동일 순서·함수)
STEPS = [
    (1, "기사 내용 확인", load_article),
    (2, "클레임 추출", extract_statistical_claims),
    (3, "한국어 수사 산술로 변환", normalize_claim),
    (4, "KOSIS 통계표 n개 찾기", retrieve_kosis_candidates),
    (5, "KOSIS 셀 값 조회", fetch_kosis_data),
    (6, "증거 랭킹", rank_evidence),
]


@dataclass
class RunResult:
    """기사 1건의 1~6단계 결과 — 입력·산출 스키마·실패 지점."""

    idx: int
    source_id: int
    article_id: str
    content: str
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
    """1~6단계를 차례로 실행. 단계가 raise 하면 그 지점 기록 후 중단(이후 단계 생략)."""
    content = row["source_sentence"]
    res = RunResult(idx=idx, source_id=row.get("source_id", -1),
                    article_id=row.get("article_id", ""), content=content)
    master = MasterSchema(content=content)
    t0 = time.perf_counter()
    for step, name, fn in STEPS:
        try:
            await fn(master)
        except Exception as exc:  # 단계 raise → 기록하고 이 기사 중단
            res.failed_step, res.failed_name, res.error = step, name, str(exc)
            break
    res.master = master
    res.duration_s = time.perf_counter() - t0
    return res


# ── 생존 집계 (claim 단위) ────────────────────────────────────────────────────

def _claim_funnel(res: RunResult) -> tuple[int, int, int]:
    """(추출 claim, candidate≥1 claim, evidence≥1 claim=생존) 을 센다."""
    if res.master is None:
        return (0, 0, 0)
    n_claims = len(res.master.claims)
    n_cand = sum(1 for a in res.master.analysis if a.candidates)
    n_evi = sum(1 for a in res.master.analysis if a.evidences)
    return (n_claims, n_cand, n_evi)


def _print_progress(res: RunResult, total: int) -> None:
    head = res.content[:36].replace("\n", " ")
    nc, ncand, nevi = _claim_funnel(res)
    if res.ok:
        print(f"[{res.idx:>3}/{total}] OK   {res.duration_s:5.1f}s  "
              f"claim×{nc} cand×{ncand} evi×{nevi}  | {head}…")
    else:
        print(f"[{res.idx:>3}/{total}] FAIL {res.duration_s:5.1f}s  "
              f"@[{res.failed_step}] {res.failed_name}: {res.error}  | {head}…")


def _dump_result_json(results: list[RunResult]) -> None:
    """기사별 산출 스키마(파이프라인이 채운 부분 = MasterSchema model_dump)를 그대로 저장."""
    payload = []
    for r in sorted(results, key=lambda x: x.idx):
        nc, ncand, nevi = _claim_funnel(r)
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
            "n_claims": nc,
            "n_claims_with_candidate": ncand,
            "n_claims_survived": nevi,  # evidence≥1 = 6단계 생존
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

    # claim 단위 퍼널 합산
    tot_claims = tot_cand = tot_evi = 0
    arts_with_evi = 0
    for r in results:
        nc, ncand, nevi = _claim_funnel(r)
        tot_claims += nc
        tot_cand += ncand
        tot_evi += nevi
        if nevi:
            arts_with_evi += 1

    def pct(a: int, b: int) -> str:
        return f"{100*a/b:.1f}%" if b else "—"

    L = ["# from_origin 1~6단계 — 생존 카운트 결과", ""]
    L += ["## 1. 개요",
          "- 목적: `from_origin_212_source.jsonl`(고유 기사)을 1→6단계만 돌려, 어느 단계에서 죽는지와 "
          "6단계 후 evidence 가 붙는 claim(=생존) 수를 센다(스모크).",
          "- 생존 정의: 6단계(rank_evidence) 후 그 claim 의 `analysis.evidences` ≥1 "
          "(= KOSIS 셀값을 찾아 랭킹까지 통과 → 7단계 비교 대상).",
          f"- 입력: `{DATA.name}` — 고유 기사 {len(results)}건(source_sentence 중복 제거).",
          f"- 원자료: `{RESULT_JSON.name}` (기사별 MasterSchema model_dump).", ""]
    L += ["## 2. 테스트 내용",
          "- 각 기사를 1~6단계만 실행, 단계 raise 는 흡수해 실패 단계로 기록하고 다음 기사로 계속.",
          "- production `src/pipeline/runner.py` 의 앞 6단계와 동일 함수·순서.", ""]
    L += ["## 3. 지표",
          f"- 기사 완주(1~6 무중단): **{len(ok)}/{len(results)}**  | 실패: {len(fail)}/{len(results)}",
          f"- 총 소요: {total_s:.0f}s" + (f" (평균 {total_s/len(results):.1f}s/건)" if results else ""),
          "",
          "### claim 퍼널 (전체 기사 합산)",
          f"- 추출 claim: **{tot_claims}**",
          f"- ④ candidate 보유 claim: {tot_cand} ({pct(tot_cand, tot_claims)} of 추출)",
          f"- ⑥ **생존 claim(evidence≥1): {tot_evi}** "
          f"({pct(tot_evi, tot_claims)} of 추출, {pct(tot_evi, tot_cand)} of candidate)",
          f"- 생존 claim 보유 기사: {arts_with_evi}/{len(results)}", ""]
    if fail_by_step:
        L.append("- 단계별 실패: " + ", ".join(
            f"[{s}] {n} ×{c}건" for (s, n), c in sorted(fail_by_step.items(), key=lambda x: -x[1])))
        L.append("")

    if fail:
        L += ["## 4. 실패 상세", ""]
        for r in fail:
            head = r.content[:90].replace("\n", " ")
            L.append(f"- [{r.idx}] @[{r.failed_step}] {r.failed_name} — `{r.error}`  | {head}…")
        L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="from_origin 1~6단계 생존 카운트 러너")
    ap.add_argument("--limit", type=int, default=0, help="앞 N개 고유 기사만 (0=전체)")
    ap.add_argument("--concurrency", type=int, default=6, help="동시 실행 기사 수")
    args = ap.parse_args()

    rows = _read_articles(DATA, args.limit)
    if not rows:
        raise SystemExit(f"실행할 기사 없음: {DATA}")
    print(f"1~6단계 생존 카운트 시작 — 고유 기사 {len(rows)}건, 동시 {args.concurrency}\n")

    results = asyncio.run(_run_all(rows, args.concurrency))

    _dump_result_json(results)
    REPORT_MD.write_text(_build_report(results), encoding="utf-8")
    ok = sum(r.ok for r in results)
    tot_evi = sum(_claim_funnel(r)[2] for r in results)
    tot_claims = sum(_claim_funnel(r)[0] for r in results)
    print(f"\n완료 {ok}/{len(results)} | 생존 claim {tot_evi}/{tot_claims}")
    print(f"원자료: {RESULT_JSON}")
    print(f"리포트: {REPORT_MD}")


if __name__ == "__main__":
    main()
