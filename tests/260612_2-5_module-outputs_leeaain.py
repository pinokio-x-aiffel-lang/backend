"""gold src 100문장 → 2~5단계 실행 → 모듈별 결과값을 번호 매겨 md 저장.

### N번 모듈 섹션 아래 "k. 원문문장 | 결과값" 형식.
전체 model_dump 는 동명 .json 에 저장(재분석용).

    uv run x python tests/260612_2-5_module-outputs_leeaain.py

대상 모듈: [2] extract / [3] normalize / [4] retrieve_kosis_candidates / [5] fetch_kosis_data
작성자: leeaain2027  작성일: 2026-06-12
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from src.modules.extract_statistical_claims import extract_statistical_claims
from src.modules.fetch_kosis_data import fetch_kosis_data
from src.modules.normalize_claim import normalize_claim
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.schemas.runtime import Article, MasterSchema

GOLD = Path("benchmark/data/3_normalize_claim_100_gold.jsonl")
OUT_DIR = Path("tests/results")
BASE_NAME = "260612_2-5_module-outputs_leeaain_3"  # _01·_2=프롬프트 수정 후, _3=population 보정+스키마(required 4) 후
CONCURRENCY = 5

STEPS = [
    (2, extract_statistical_claims),
    (3, normalize_claim),
    (4, retrieve_kosis_candidates),
    (5, fetch_kosis_data),
]


async def _run_one(sem: asyncio.Semaphore, row: dict, total: int, done: list) -> dict:
    async with sem:
        ms = MasterSchema(article=Article(
            article_id=f"gold-{row['id']:03d}", content=row["src"],
            published_at=row["base"],
        ))
        failed_step = error = None
        for step, fn in STEPS:
            try:
                await fn(ms)
            except Exception as exc:
                failed_step, error = step, str(exc)
                break
        done[0] += 1
        print(f"[{done[0]:>3}/{total}] id={row['id']}" + (f" FAIL@{failed_step}" if error else ""))
        return {"id": row["id"], "base": row["base"], "src": row["src"],
                "failed_step": failed_step, "error": error, "dump": ms.model_dump()}


def _vs(slot: dict | None) -> str:
    if not slot:
        return ""
    return f"{slot['raw']}→{slot['llm_value']}"


def _mod2_line(d: dict) -> str:
    claims = d["dump"].get("claims") or []
    if not claims:
        return "claim 없음"
    return " ; ".join(
        f"[{c['claim_type']}] subject={c['subject']}, value={c['value']['raw']}, "
        f"unit={c['unit']}, period={c['period_value']['raw']}, population={c['population']}"
        for c in claims)


def _mod3_line(d: dict) -> str:
    claims = d["dump"].get("claims") or []
    if not claims:
        return "claim 없음"
    parts = []
    for c in claims:
        seg = f"value {_vs(c['value'])}; period {_vs(c['period_value'])}"
        if c.get("compare_period_value"):
            seg += f"; compare {_vs(c['compare_period_value'])}"
        parts.append(seg)
    return " ‖ ".join(parts)


def _mod4_line(d: dict) -> str:
    analysis = d["dump"].get("analysis") or []
    if not analysis:
        return "분석 없음(claim 없음 또는 NONE)"
    parts = []
    for a in analysis:
        s = a["kosis_search"]
        sel = f"{s['selected_tbl_id']}({s['selected_tbl_name']})" if s.get("selected_tbl_id") else "선정 실패"
        parts.append(f"검색 \"{s['query']}\" hits={s['hits']}, 후보 {len(a.get('candidates') or [])}개 → {sel}")
    return " ‖ ".join(parts)


def _mod5_line(d: dict) -> str:
    analysis = d["dump"].get("analysis") or []
    if not analysis:
        return "—"
    parts = []
    for a in analysis:
        evs = a.get("evidences") or []
        if evs:
            parts.append(" / ".join(
                f"{e['period']}={e['value']}{e['unit']} @{e['kosis_tbl_id']}({e['table_name']})"
                for e in evs))
        else:
            parts.append(f"매칭 0건 (셀 조회 시도 {len(a.get('cell_attempts') or [])}회)")
    return " ‖ ".join(parts)


async def main() -> None:
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("{")]
    sem = asyncio.Semaphore(CONCURRENCY)
    done = [0]
    t0 = time.perf_counter()
    results = sorted(await asyncio.gather(*[_run_one(sem, r, len(rows), done) for r in rows]),
                     key=lambda r: r["id"])
    wall = time.perf_counter() - t0

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{BASE_NAME}.json").write_text(
        json.dumps({"input": str(GOLD), "stages": "2-5", "wall_s": round(wall, 1),
                    "items": results}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")

    sections = [
        ("2번 모듈 — extract_statistical_claims (claim 추출)", _mod2_line),
        ("3번 모듈 — normalize_claim (정규화: raw→표준값)", _mod3_line),
        ("4번 모듈 — retrieve_kosis_candidates (KOSIS 통계표 검색)", _mod4_line),
        ("5번 모듈 — fetch_kosis_data (셀 조회·매칭 evidence)", _mod5_line),
    ]
    md = ["# 2~5단계 모듈별 결과 — gold src 100문장",
          "",
          "| 항목 | 내용 |", "|---|---|",
          "| ① 목적 | 각 모듈의 문장별 출력값 일람 (오류 분석용 원자료) |",
          "| ② 대상 모듈 | [2] extract / [3] normalize / [4] retrieve / [5] fetch |",
          "| ③ 입력 | `3_normalize_claim_100_gold.jsonl` src+base (1단계 생략) |",
          "| ④ 일자/작성자 | 2026-06-12 / leeaain2027 |",
          "",
          f"- 원자료(전체 dump): `{BASE_NAME}.json` / 실행 {wall:.0f}s",
          ""]
    for title, fn in sections:
        md.append(f"### {title}")
        md.append("")
        for d in results:
            line = f"{d['id']}. {d['src']} | {fn(d)}"
            if d["error"] and (d["failed_step"] or 9) <= int(title[0]):
                line = f"{d['id']}. {d['src']} | (단계 {d['failed_step']} 오류: {d['error'][:60]})"
            md.append(line)
        md.append("")
    (OUT_DIR / f"{BASE_NAME}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"저장: {OUT_DIR}/{BASE_NAME}.{{md,json}}  ({wall:.0f}s)")


if __name__ == "__main__":
    asyncio.run(main())
