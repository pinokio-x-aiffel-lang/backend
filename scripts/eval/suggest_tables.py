"""claim(sentence)마다 KOSIS 후보 통계표 top 10을 제안한다.

파이프라인:
  1. HCX-007 로 claim 의 통계 주제 → KOSIS 검색용 BEST 키워드(1~3개) 추출
  2. 각 키워드로 KOSIS 통합검색(statisticsSearch.do) top 10 조회
  3. (org_id, tbl_id) 기준 dedup + 최선 순위로 병합 → 최종 top 10
  4. data/eval/table_suggestions.jsonl / .csv 로 저장

원천:
  - data/eval/labeling_base_success.jsonl  (101 success, 634 claim)

재사용:
  - src.llm.llm_caller.LlmCaller            (HCX-007 호출)
  - src.kosis.search_tables (KOSIS 통합검색, KOSIS_API_KEY from .env)

키 출처:
  - CLOVASTUDIO_API_KEY  : Infisical CLI 주입
  - KOSIS_API_KEY        : .env

실행:
  infisical run -- uv run python scripts/eval/suggest_tables.py            # 전체(634)
  infisical run -- uv run python scripts/eval/suggest_tables.py --limit 3  # 파일럿
  (재실행 시 이미 처리된 claim_id 는 건너뜀 — 중단/재개 안전)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.llm.client import LlmError  # noqa: E402
from src.llm.llm_caller import LlmCaller  # noqa: E402
from src.kosis import search_tables, KosisError  # noqa: E402

OUT_DIR = ROOT / "data" / "eval"
SUCCESS_JSONL = OUT_DIR / "labeling_base_success.jsonl"
OUT_JSONL = OUT_DIR / "table_suggestions.jsonl"
OUT_CSV = OUT_DIR / "table_suggestions.csv"

MODEL_NAME = "HCX-007"
TOP_N = 10

# extract_best_keyword.py 의 프롬프트를 다중 키워드 버전으로 확장.
SYSTEM_PROMPT = """당신은 KOSIS(국가통계포털) 통계표 검색용 키워드 추출기다.
사용자가 찾고자 하는 통계 주제로부터, KOSIS 통합검색 API에 그대로 넣을 BEST
키워드를 최대 3개까지, 적합도 높은 순으로 추출한다.

KOSIS 검색은 통계표명(TBL_NM)에 대한 부분 문자열 매칭이다. 따라서:

1. 통계표 명칭에 실제로 등장할 핵심 명사구만 남긴다.
2. 연도(예: 2023, 2020년)는 키워드에서 제외한다. 시점은 표명에 들어가지 않는다.
3. 지역 한정어(전국, 서울, 대구 등)는 통계표 분류 차원에 들어가는 경우가 많고
   표명에는 잘 들어가지 않는다. 가능하면 제외한다.
4. 자연어에서 띄어 쓴 합성어는 표명에서 붙어 있는 경우가 흔하다
   (예: "소비자 물가 지수" → "소비자물가지수"). 자연스러우면 공백을 제거한다.
5. 첫 번째 키워드는 가장 식별력 있는 짧은 명사구, 이후 키워드는 더 일반적이거나
   대체 표현으로 폴백 검색용이다.

출력은 JSON 객체 하나. 형식:
{"keywords": ["키워드1", "키워드2", "키워드3"]}
설명·주석 없이 JSON 만 출력한다."""

_KEYWORDS_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        }
    },
    "required": ["keywords"],
}


def build_query(claim: dict) -> str:
    """claim 에서 키워드 추출용 자연어 주제를 만든다.

    HCX 가 이미 뽑은 subject 가 가장 깨끗하다. 비거나 sentinel("불명")이면
    원문 문장으로 폴백한다.
    """
    subject = (claim.get("subject") or "").strip()
    if subject and subject != "불명":
        return subject
    return (claim.get("sentence") or "").strip()


def extract_keywords(llm: LlmCaller, query: str, cache: dict[str, list[str]]) -> list[str]:
    if query in cache:
        return cache[query]
    resp = llm.chat(
        model_alias="hyperclova",
        model_name=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        json_structure=_KEYWORDS_SCHEMA,
        max_tokens=256,
        temperature=0.0,
    )
    keywords: list[str] = []
    try:
        obj = json.loads(resp.text)
        for kw in obj.get("keywords", []):
            kw = str(kw).strip().strip("\"'`").rstrip(".").strip()
            if kw and kw not in keywords:
                keywords.append(kw)
    except (json.JSONDecodeError, AttributeError):
        # 구조화 출력이 깨지면 원문 한 줄을 키워드로 폴백
        fallback = resp.text.strip().splitlines()[0].strip().strip("\"'`")
        if fallback:
            keywords = [fallback]
    cache[query] = keywords
    return keywords


def search_top(
    keywords: list[str], cache: dict[str, list]
) -> list[dict]:
    """키워드들로 검색 → (org_id,tbl_id) dedup → 최선 순위 top 10."""
    merged: dict[tuple[str, str], dict] = {}
    for kw_rank, kw in enumerate(keywords, 1):
        if kw in cache:
            hits = cache[kw]
        else:
            try:
                hits_obj = search_tables(kw, None, top_n=TOP_N)
                hits = [
                    {
                        "org_id": h.org_id,
                        "tbl_id": h.tbl_id,
                        "tbl_nm": h.tbl_nm,
                        "org_nm": h.org_nm,
                        "stat_nm": h.stat_nm,
                    }
                    for h in hits_obj
                ]
            except (KosisError, Exception) as exc:  # noqa: BLE001
                print(f"    [warn] KOSIS 검색 실패 '{kw}': {exc}", file=sys.stderr)
                hits = []
            cache[kw] = hits
        for pos, h in enumerate(hits, 1):
            key = (h["org_id"], h["tbl_id"])
            score = (kw_rank, pos)  # 낮을수록 우선
            if key not in merged or score < merged[key]["_score"]:
                merged[key] = {**h, "matched_keyword": kw, "kw_rank": kw_rank, "_score": score}
    ranked = sorted(merged.values(), key=lambda d: d["_score"])[:TOP_N]
    out = []
    for rank, d in enumerate(ranked, 1):
        d.pop("_score", None)
        out.append({"rank": rank, **d})
    return out


def load_done_ids() -> set[str]:
    done: set[str] = set()
    if OUT_JSONL.exists():
        with OUT_JSONL.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["claim_id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
    return done


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="처리할 claim 수 제한(파일럿). 0=전체")
    ap.add_argument("--restart", action="store_true", help="기존 출력 무시하고 처음부터")
    args = ap.parse_args()

    if not os.getenv("CLOVASTUDIO_API_KEY"):
        print("ERROR: CLOVASTUDIO_API_KEY 없음. `infisical run -- uv run ...` 로 실행하세요.",
              file=sys.stderr)
        return 1
    if not SUCCESS_JSONL.exists():
        print(f"ERROR: {SUCCESS_JSONL} 없음.", file=sys.stderr)
        return 1

    with SUCCESS_JSONL.open(encoding="utf-8") as f:
        articles = [json.loads(l) for l in f if l.strip()]
    claims = [
        {"article_id": a["article_id"], **c}
        for a in articles
        for c in a.get("claims", [])
    ]
    print(f"총 claim: {len(claims)}")

    done = set() if args.restart else load_done_ids()
    if args.restart and OUT_JSONL.exists():
        OUT_JSONL.unlink()
    if done:
        print(f"이미 처리됨(skip): {len(done)}")

    todo = [c for c in claims if c.get("claim_id") not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"이번 실행 처리 대상: {len(todo)}")

    llm = LlmCaller()
    kw_cache: dict[str, list[str]] = {}
    search_cache: dict[str, list] = {}

    n_ok = 0
    with OUT_JSONL.open("a", encoding="utf-8") as fout:
        for i, claim in enumerate(todo, 1):
            cid = claim.get("claim_id", "")
            query = build_query(claim)
            try:
                keywords = extract_keywords(llm, query, kw_cache) if query else []
            except LlmError as exc:
                print(f"  [{i}/{len(todo)}] {cid} HCX 실패: {exc}", file=sys.stderr)
                keywords = []
            candidates = search_top(keywords, search_cache) if keywords else []
            rec = {
                "article_id": claim["article_id"],
                "claim_id": cid,
                "sentence": claim.get("sentence", ""),
                "subject": claim.get("subject", ""),
                "query": query,
                "keywords": keywords,
                "candidates": candidates,
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            n_ok += 1
            top1 = candidates[0]["tbl_nm"] if candidates else "(없음)"
            print(f"  [{i}/{len(todo)}] {cid}  kw={keywords}  → {len(candidates)}개, top1: {top1}")
            time.sleep(0.2)  # HCX/KOSIS rate limit 완충

    print(f"\n✅ {n_ok}건 처리 → {OUT_JSONL}")

    # --- 사람이 읽기 좋은 flat CSV 도 생성 ---
    rows = []
    with OUT_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not rec["candidates"]:
                rows.append({
                    "claim_id": rec["claim_id"], "article_id": rec["article_id"],
                    "subject": rec["subject"], "keywords": " | ".join(rec["keywords"]),
                    "rank": "", "org_id": "", "tbl_id": "", "tbl_nm": "(후보없음)", "org_nm": "",
                })
                continue
            for c in rec["candidates"]:
                rows.append({
                    "claim_id": rec["claim_id"], "article_id": rec["article_id"],
                    "subject": rec["subject"], "keywords": " | ".join(rec["keywords"]),
                    "rank": c["rank"], "org_id": c["org_id"], "tbl_id": c["tbl_id"],
                    "tbl_nm": c["tbl_nm"], "org_nm": c["org_nm"],
                })
    cols = ["claim_id", "article_id", "subject", "keywords", "rank",
            "org_id", "tbl_id", "tbl_nm", "org_nm"]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"✅ flat CSV → {OUT_CSV} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
