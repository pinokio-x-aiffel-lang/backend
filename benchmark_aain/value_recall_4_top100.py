"""4단계 값-기반 Recall@100 — 후보 풀을 100-deep로 새로 생성해 천장(ceiling) 진단.

목적: 임베딩 리랭킹 도입 여부 게이트.
  - R@100 ≫ R@10  → 정답표는 풀에 있는데 순위만 낮음 → 리랭킹 효과 큼
  - R@100 ≈ R@10  → 정답표가 풀에도 없음 → lexical recall 병목(리랭킹 무의미)

비순환: 값=SSOT figure(사람검수), 후보=파이프라인 검색 출력(예측), 확인=raw call_kosis.
faithful: 후보 생성은 retrieve 모듈의 실제 헬퍼를 그대로 재사용(POOL_N=100만 다름).
R@10·R@100을 같은 100-deep 풀에서 산출 → 내부 비교가 깨끗.

실행: uv run x python benchmark_aain/value_recall_4_top100.py
출력: benchmark/4_retrieve/leeaain_<날짜>_NN.{jsonl,md}  (save_result)
"""
from __future__ import annotations

from pathlib import Path

from src.kosis import KosisError, resolve_api_key, search_tables_many
from src.kosis.keyword_expand import expand_subject
from src.modules.retrieve_kosis_candidates import (
    MAX_VARIANTS,
    _dedup_keep_order,
    _llm_expand_keywords,
    _merge_dedup,
    _rerank_hits,
)

from benchmark.reporting import save_result, blank_sections, load_ssot
from benchmark.scoring import score_retrieve
# 값-스캔/기간파싱/로더는 기존 러너 재사용(중복·발산 방지).
from benchmark_aain.value_recall_4 import has_value, _period, _load

ROOT = Path(__file__).resolve().parent.parent
# 테스트셋 이동(8053f9c) 후 현재 경로. SSOT 는 정본 로더(load_ssot)로 일원화.
S4 = ROOT / "benchmark/data/4_retrieve/4_source_1.jsonl"
POOL_N = 100  # 후보 풀 깊이(=천장). search_tables resultCount 상한 1000 이내.


def build_pool(subject: str, api_key: str, pool_n: int = POOL_N):
    """retrieve._search_one_claim 의 sync·deep 버전 — variants→검색→병합·재랭킹→top pool_n.

    pool_n 만 빼면 파이프라인 후보 생성 경로와 동일(LLM 폴백은 풀이 빌 때만).
    """
    variants = expand_subject(subject, max_variants=MAX_VARIANTS)
    if not variants:
        return []
    try:
        hits_by_kw = search_tables_many(variants, api_key, top_n=pool_n)
    except (KosisError, ValueError):
        return []
    pool = _rerank_hits(_merge_dedup(variants, hits_by_kw))[:pool_n]
    if not pool:  # 룰 검색 0건 = 진짜 미스 → LLM 폴백 검색어로 재검색.
        extra = [e for e in _dedup_keep_order(_llm_expand_keywords(subject))
                 if e not in set(variants)][:MAX_VARIANTS]
        if extra:
            try:
                more = search_tables_many(extra, api_key, top_n=pool_n)
                pool = _rerank_hits(_merge_dedup(variants + extra, {**hits_by_kw, **more}))[:pool_n]
            except (KosisError, ValueError):
                pass
    return pool


def main():
    api_key = resolve_api_key()
    ssot = {r["row_id"]: r for r in load_ssot()}
    subj = {r["row_id"]: r.get("subject", "") for r in _load(S4)}

    records = []
    for rid, row in ssot.items():
        if row["label"] != "T":
            continue
        subject = subj.get(rid, "")
        hits = build_pool(subject, api_key) if subject else []
        cands = [(h.tbl_id, h.org_id) for h in hits]  # 이미 랭크순
        print(f"row{rid} {subject!r}: pool={len(cands)}", flush=True)

        for gf in (row.get("gold_figures") or []):
            v = gf.get("value")
            if v is None or isinstance(v, list):
                continue
            pde, pse = _period(gf.get("period"))
            if not pde:
                continue
            vrank = None
            for i, (tbl, org) in enumerate(cands, 1):
                if has_value(org, tbl, pde, pse, v, api_key):
                    vrank = i
                    break
            records.append({"row_id": rid, "stage": 4, "label": "T",
                            "input": {"claims": [{"item": gf.get("item"), "subject": subject}]},
                            "output": {"candidates": [t for t, _ in cands]},
                            "gold": {"figure_value": v, "period": pde},
                            "gold_rank": vrank, "success": bool(cands)})
            print(f"  {'✓' if vrank else '·'} {gf.get('item')!r} {pde}={v} → rank={vrank} (pool={len(cands)})", flush=True)

    m = score_retrieve(records, ns=(1, 3, 10, 100))
    sec = blank_sections()
    sec["개요"] = ("4단계 **값-기반 Recall@100 (천장 진단)** — 후보 풀을 100-deep로 새로 생성해, "
                 "임베딩 리랭킹이 도달 가능한 최대 recall을 측정. R@100≫R@10이면 리랭킹 효과 큼, "
                 "R@100≈R@10이면 정답표가 풀에도 없어 리랭킹 무의미(lexical recall 병목).")
    sec["테스트 방법"] = (f"T {len(records)}개 figure 대상. 후보 풀은 retrieve 모듈 헬퍼(expand_subject→"
                      f"search_tables_many top_n={POOL_N}→merge·rerank)로 100-deep 재생성(파이프라인과 동일 경로, "
                      "깊이만 다름). 각 figure 값을 후보표에서 raw call_kosis로 순위대로 조회 → 첫 발견 순위=gold_rank "
                      "→ R@1/3/10/100·MRR. R@10·R@100을 같은 풀에서 산출해 내부 비교가 깨끗. 비순환(값=SSOT 독립).")
    sec["분석"] = ("**천장 읽는 법**: R@100은 풀 안에 정답표가 들어오는 비율(=리랭킹으로 도달 가능한 상한). "
                 "R@10은 현재 검색 랭킹이 실제로 top10에 올린 비율. 둘의 격차 = 리랭킹으로 회수 가능한 양.\n\n"
                 "델타(증감) figure는 단일 셀에 값이 없어 자연 미검출 → R@100에서도 못 잡힘(검색 탓 아님).")
    sec["개선 전후 비교"] = ("10-deep 캡처 기반(leeaain_260619_02, R@10=0.350)과 달리 100-deep 풀을 새로 생성. "
                      "동일 run의 R@10 vs R@100 격차가 리랭킹 도입의 직접 근거.")
    sec["한계·주의"] = ("① 후보 풀은 이 run에서 재생성(KOSIS 인덱스 시점 = 실행일). ② 델타 figure 미검출(검색 탓 아님). "
                    "③ 값-일치는 셀이 그 값을 담는다는 의미일 뿐, 항목/축 정합성은 별도(stage5). "
                    "④ R@100은 lexical 검색 천장 — 임베딩이 풀에 없는 표를 새로 끌어오진 못함(별도 전수 인덱스 영역).")
    j, d = save_result(4, "leeaain", records, m, sec)
    n = sum(1 for r in records if r["gold_rank"])
    print(f"\n값-기반 hit {n}/{len(records)} → {j.name}, {d.name}", flush=True)
    for row in m:
        print("  ", row["지표"], row["값"], row.get("95% CI", ""), flush=True)


if __name__ == "__main__":
    main()
