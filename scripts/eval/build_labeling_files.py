"""라벨링 작업용 파일 2종 생성.

생성물:
  - data/eval/articles.md           — 101 success 기사의 정제 본문 (라벨러 읽기용)
  - data/eval/labeling_sheet.csv    — 634 HCX claim + gold 빈 컬럼 (라벨러 편집용)

원천:
  - data/eval/labeling_base_success.jsonl  (이미 생성됨, HCX 추론 결과)
  - feat/kosis-fetcher 의 sample_100_v1.csv / sample_backfill_v1.csv  (raw 본문)

content_clean 은 feat/eval-set-100 의 동명 모듈에서 핵심 함수만 인라인.
의존성 회피용 (현재 워크트리에 src/claim 없음).
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "eval"
SUCCESS_JSONL = OUT_DIR / "labeling_base_success.jsonl"
ARTICLES_MD = OUT_DIR / "articles.md"
LABELING_CSV = OUT_DIR / "labeling_sheet.csv"

# ----- inlined content_clean ----- #
_RE_BODY_START = re.compile(
    r"입력\s+\d{4}\.\d{2}\.\d{2}\.\s+\d{1,2}:\d{2}"
    r"(?:\s+업데이트\s+\d{4}\.\d{2}\.\d{2}\.\s+\d{1,2}:\d{2})?"
    r"\s+\d+\s+"
)
_RE_BODY_END_PATTERNS = (
    re.compile(r"\s#[가-힣A-Za-z]"),
    re.compile(r"구독수\s+\d+"),
    re.compile(r"Video Player is loading"),
    re.compile(r"100자평\s+\d+"),
    re.compile(r"Powered by GliaStudios"),
    re.compile(r"By Taboola"),
)


def clean_content(text: str) -> str:
    start = 0
    m = _RE_BODY_START.search(text)
    if m is not None:
        start = m.end()
    end = len(text)
    for pat in _RE_BODY_END_PATTERNS:
        m2 = pat.search(text, pos=start)
        if m2 is not None and m2.start() < end:
            end = m2.start()
    return text[start:end].strip()


# ----- helpers ----- #
def git_show_bytes(ref: str, path: str) -> bytes:
    out = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=str(ROOT),
        capture_output=True,
        check=True,
    )
    return out.stdout


def load_sample_csv_rows(ref: str, path: str) -> list[dict]:
    raw = git_show_bytes(ref, path)
    # CSV from git is UTF-8 with BOM sometimes
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines())
    return list(reader)


def slot_pick(slot: dict | None, key: str = "llm_value") -> str:
    """ValueSlot 또는 None → 표시 문자열."""
    if slot is None:
        return ""
    if isinstance(slot, dict):
        return slot.get(key, "") or ""
    return str(slot)


# ----- main ----- #
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    if not SUCCESS_JSONL.exists():
        print(f"ERROR: {SUCCESS_JSONL} 없음. 먼저 filter_success.py 실행하세요.",
              file=sys.stderr)
        return 1

    print("Reading sample CSVs from feat/kosis-fetcher ...")
    sample_rows = load_sample_csv_rows("feat/kosis-fetcher", "data/eval/sample_100_v1.csv")
    backfill_rows = load_sample_csv_rows("feat/kosis-fetcher", "data/eval/sample_backfill_v1.csv")
    by_aid: dict[str, dict] = {}
    for r in sample_rows + backfill_rows:
        aid = r.get("article_id") or ""
        if aid:
            by_aid[aid] = r
    print(f"  sample_100_v1: {len(sample_rows)} rows")
    print(f"  sample_backfill_v1: {len(backfill_rows)} rows")
    print(f"  unique article_ids: {len(by_aid)}")

    print(f"\nReading success JSONL ...")
    success_articles: list[dict] = []
    with SUCCESS_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                success_articles.append(json.loads(line))
    print(f"  success articles: {len(success_articles)}")
    total_claims = sum(len(a.get("claims", [])) for a in success_articles)
    print(f"  total claims: {total_claims}")

    # --- articles.md ---
    print(f"\nBuilding {ARTICLES_MD} ...")
    md_lines: list[str] = []
    md_lines.append("# 라벨링용 기사 본문 (101 success articles)")
    md_lines.append("")
    md_lines.append("Ctrl+F 로 `article_id` 검색하여 본문 점프.")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    missing_body = 0
    for art in success_articles:
        aid = art["article_id"]
        src = by_aid.get(aid)
        if src is None:
            missing_body += 1
            md_lines.append(f"## {aid}")
            md_lines.append(f"**제목:** {art.get('title','')}")
            md_lines.append(f"**발행일:** {art.get('published_at','')}")
            md_lines.append(f"**URL:** {art.get('url','')}")
            md_lines.append("")
            md_lines.append("> ⚠️ 원본 CSV 매칭 실패 — URL 클릭으로 본문 확인")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")
            continue
        raw_body = src.get("기사 본문 전체", "") or ""
        cleaned = clean_content(raw_body)
        md_lines.append(f"## {aid}")
        md_lines.append(f"**제목:** {src.get('기사제목', art.get('title',''))}")
        md_lines.append(f"**발행일:** {src.get('작성일', art.get('published_at',''))}")
        md_lines.append(f"**URL:** {src.get('URL', art.get('url',''))}")
        md_lines.append("")
        md_lines.append(cleaned if cleaned else "_(정제 결과 빈 본문 — raw 확인 필요)_")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")
    ARTICLES_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  wrote {ARTICLES_MD} ({ARTICLES_MD.stat().st_size:,} bytes)")
    if missing_body:
        print(f"  ⚠️ 본문 매칭 실패: {missing_body} 기사")

    # --- labeling_sheet.csv ---
    print(f"\nBuilding {LABELING_CSV} ...")
    cols = [
        "article_id",
        "claim_id",
        "source_sentence",
        # HCX 참고 (회색)
        "hcx_claim_type",
        "hcx_subject",
        "hcx_value",
        "hcx_unit",
        "hcx_aggregation",
        "hcx_period_type",
        "hcx_period_value",
        "hcx_compare_period_value",
        "hcx_population",
        "hcx_cited_source",
        # gold 편집 (라벨러)
        "is_keep",                  # Y/N — HCX 추출 유지 여부
        "gold_claim_type",
        "gold_subject",
        "gold_value",
        "gold_unit",
        "gold_aggregation",
        "gold_period_type",
        "gold_period_value",
        "gold_compare_period_value",
        "gold_population",
        "gold_cited_source",
        "expected_unknown_fields",   # comma list
        "gold_verdict",              # T/F/M/N
        "gold_kosis_tbl_id",
        "gold_kosis_period",
        "gold_kosis_population",
        "gold_kosis_value",
        "gold_kosis_unit",
        "notes",
    ]

    with LABELING_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        n_rows = 0
        for art in success_articles:
            aid = art["article_id"]
            for c in art.get("claims", []):
                row = {
                    "article_id": aid,
                    "claim_id": c.get("claim_id", ""),
                    "source_sentence": c.get("sentence", ""),
                    "hcx_claim_type": c.get("claim_type", ""),
                    "hcx_subject": c.get("subject", ""),
                    "hcx_value": slot_pick(c.get("value")),
                    "hcx_unit": c.get("unit", ""),
                    "hcx_aggregation": c.get("aggregation", ""),
                    "hcx_period_type": c.get("period_type", ""),
                    "hcx_period_value": slot_pick(c.get("period_value")),
                    "hcx_compare_period_value": slot_pick(c.get("compare_period_value")),
                    "hcx_population": c.get("population", ""),
                    "hcx_cited_source": c.get("cited_source", ""),
                    # gold 컬럼은 빈 상태로 라벨러가 채움
                    "is_keep": "",
                    "gold_claim_type": "",
                    "gold_subject": "",
                    "gold_value": "",
                    "gold_unit": "",
                    "gold_aggregation": "",
                    "gold_period_type": "",
                    "gold_period_value": "",
                    "gold_compare_period_value": "",
                    "gold_population": "",
                    "gold_cited_source": "",
                    "expected_unknown_fields": "",
                    "gold_verdict": "",
                    "gold_kosis_tbl_id": "",
                    "gold_kosis_period": "",
                    "gold_kosis_population": "",
                    "gold_kosis_value": "",
                    "gold_kosis_unit": "",
                    "notes": "",
                }
                w.writerow([row[c] for c in cols])
                n_rows += 1
    print(f"  wrote {LABELING_CSV} ({n_rows} claim rows)")

    print("\n✅ Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
