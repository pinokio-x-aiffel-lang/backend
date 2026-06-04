"""전처리 모듈 통합 테스트 — 단계별 상세 출력.

선별 기사 3건으로 preprocess_article 내부 4단계를 각각 실행하고
중간 결과를 단계별로 출력한다. 라벨링 클레임과도 나란히 비교한다.

실행:
    infisical run --env dev --path /LangFuse -- uv run python tests/test_preprocess_article.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.modules.preprocess_article import (
    _atomize_all,
    _clean_document,
    _clean_sentences,
    _split_sentences,
)
from src.schemas.runtime import Article, MasterSchema

TEST_IDS = [
    "KIO3SWFQ3ND2VOYMOMNJ7P3GL4",  # 미분양 주택 — 클레임 5개
    "RY3AUBJSBRHJXJEHCIKY43YOWU",   # 성심당 매출  — 클레임 17개, 비교문 많음
    "S73YKZJAG5G6RMIWCEKFVLGH2Q",   # 제조업 취업자 — 기자 정보 노이즈 포함
]

ROOT = Path(__file__).parent.parent


# ── 데이터 로더 ───────────────────────────────────────────────────────────────

def _load_articles_md() -> dict[str, str]:
    text = (ROOT / "data/eval/articles.md").read_text(encoding="utf-8")
    result: dict[str, str] = {}
    for section in text.split("## ")[1:]:
        lines = section.strip().splitlines()
        article_id = lines[0].strip()
        body_lines = [
            l for l in lines[1:]
            if l.strip() and not l.startswith("**") and l.strip() != "---"
        ]
        result[article_id] = " ".join(body_lines).strip()
    return result


def _load_jsonl_meta() -> dict[str, dict]:
    path = ROOT / "data/eval/labeling_base_success.jsonl"
    result: dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            result[obj["article_id"]] = obj
    return result


# ── 출력 헬퍼 ────────────────────────────────────────────────────────────────

def _sep(title: str = "", width: int = 65) -> None:
    if title:
        pad = width - len(title) - 4
        print(f"\n── {title} {'─' * max(pad, 2)}")
    else:
        print("─" * width)


def _diff_summary(before: str, after: str) -> None:
    removed = len(before) - len(after)
    pct = removed / len(before) * 100 if before else 0
    print(f"  글자 수: {len(before):,} → {len(after):,}  (제거 {removed:,}자 / {pct:.1f}%)")

    # 제거된 내용 중 눈에 띄는 부분 샘플 출력
    before_lines = set(before.splitlines())
    after_lines = set(after.splitlines())
    removed_lines = [l.strip() for l in before_lines - after_lines if len(l.strip()) > 5]
    if removed_lines:
        print(f"  제거된 라인 예시:")
        for l in removed_lines[:3]:
            print(f"    - {l[:80]}")


# ── 단일 기사 테스트 ──────────────────────────────────────────────────────────

async def _run_one(article_id: str, content: str, meta: dict) -> None:
    print(f"\n{'═' * 65}")
    print(f"  {meta['title']}")
    print(f"  ID: {article_id}  |  라벨 클레임: {meta['n_claims']}개  |  n_atomic(라벨): {meta['n_atomic']}")
    print(f"{'═' * 65}")

    # ── [1] 문서 정제 ────────────────────────────────────────────────────────
    _sep("[1] 문서 정제")
    cleaned = _clean_document(content)
    _diff_summary(content, cleaned)
    print(f"\n  정제 후 본문 (앞 300자):\n  {cleaned[:300]}...")

    # ── [2] 문장 분리 ────────────────────────────────────────────────────────
    _sep("[2] 문장 분리")
    raw_sentences = _split_sentences(cleaned)
    print(f"  분리된 문장: {len(raw_sentences)}개")
    for i, s in enumerate(raw_sentences, 1):
        print(f"  {i:02d}. {s}")

    # ── [3] 원자 문장화 ───────────────────────────────────────────────────────
    _sep("[3] 원자 문장화 (HCX-005)")
    atomic = await _atomize_all(raw_sentences)
    print(f"  {len(raw_sentences)}개 → {len(atomic)}개  (증가: +{len(atomic) - len(raw_sentences)})")

    # 분해된 문장만 표시
    if len(atomic) > len(raw_sentences):
        _sep("  분해된 문장 비교")
        raw_set = set(raw_sentences)
        for s in atomic:
            marker = "  ★" if s not in raw_set else "   "
            print(f"{marker} {s}")
    else:
        for i, s in enumerate(atomic, 1):
            print(f"  {i:02d}. {s}")

    # ── [4] 문장 정제 ────────────────────────────────────────────────────────
    _sep("[4] 문장 정제")
    final = _clean_sentences(atomic)
    print(f"  최종 원자 문장: {len(final)}개")
    for i, s in enumerate(final, 1):
        print(f"  {i:02d}. {s}")

    # ── 라벨 클레임 비교 ──────────────────────────────────────────────────────
    _sep("라벨링 클레임 문장 (중복 제거)")
    seen: set[str] = set()
    label_sentences: list[str] = []
    for c in meta["claims"]:
        if c["sentence"] not in seen:
            seen.add(c["sentence"])
            label_sentences.append(c["sentence"])
    for i, s in enumerate(label_sentences, 1):
        print(f"  {i:02d}. {s}")

    # ── 통계 요약 ─────────────────────────────────────────────────────────────
    _sep("요약")
    print(f"  원본 길이       : {len(content):,}자")
    print(f"  정제 후 길이    : {len(cleaned):,}자")
    print(f"  규칙 분리 문장  : {len(raw_sentences)}개")
    print(f"  원자화 후 문장  : {len(atomic)}개")
    print(f"  최종 문장       : {len(final)}개")
    print(f"  라벨 n_atomic   : {meta['n_atomic']}개")
    print(f"  라벨 대비 비율  : {len(final) / meta['n_atomic'] * 100:.0f}%")


# ── 메인 ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    articles = _load_articles_md()
    metas = _load_jsonl_meta()

    for article_id in TEST_IDS:
        content = articles.get(article_id)
        meta = metas.get(article_id)
        if not content or not meta:
            print(f"[SKIP] {article_id} — 데이터 없음")
            continue
        await _run_one(article_id, content, meta)


if __name__ == "__main__":
    asyncio.run(main())
