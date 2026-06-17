"""마스터 스파인 + 기존 실제 캡처 → 단계별 평가셋(jsonl) 결정적 생성.

무생성 원칙: 모든 값은 ①마스터(260614_master_eval_213_parsed_human_checked.jsonl) ②기존 실제 gold
(2_claim_extractor_output / 3_normalize_claim_100_gold) ③라이브 캡처(260614_capture_*)
에서만 온다. 지어낸 값 없음. 기존 파일은 읽기만 한다. 출력은 benchmark_aain/data/ 신규만.

verdict 정답은 캡처가 아니라 마스터 라벨(옵션 ②). 캡처값은 입력/표시용이며 source 표시.

단계별 의존:
  결정적(지금): 2 extract, 3 normalize, 9 decide_verdict
  캡처 필요(2차): 4 retrieve, 5 fetch, 6 rank, 7 calculate_metric, 8 check_alignment, 10 explain
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "benchmark_aain/data"
SPINE = DATA / "260614_master_eval_213_parsed_human_checked.jsonl"

# 기존 실제 gold (읽기 전용)
EXIST_EXTRACT = ROOT / "benchmark/data/2_claim_extractor_output.jsonl"
EXIST_NORMALIZE = ROOT / "benchmark/data/3_normalize_claim_100_gold.jsonl"
CAPTURE = DATA / "260614_capture_master_stage1to8.json"

PFX = "260614_source_from_origin_for_"


def _key(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _read_jsonl(p: Path, skip_comments: bool = False) -> list[dict]:
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        if skip_comments and ln.lstrip().startswith(("#", "//")):
            continue
        out.append(json.loads(ln))
    return out


def _write_jsonl(name: str, rows: list[dict]) -> None:
    p = DATA / name
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {len(rows):4d} rows -> {p.name}")


def load_spine() -> list[dict]:
    return _read_jsonl(SPINE)


# --------------------------------------------------------------------------- #
# [2] extract_statistical_claims
#   입력=기사 텍스트, gold=추출 claim/슬롯. 기존 100(양성50+음성50, 슬롯 gold) 재사용 +
#   마스터 213(전부 수치문장=양성, 슬롯 gold 미주석 → null) 보강.
# --------------------------------------------------------------------------- #
def build_stage2(spine: list[dict]) -> None:
    rows: list[dict] = []
    exist = _read_jsonl(EXIST_EXTRACT)
    exist_keys = set()
    for e in exist:
        sent = e.get("sentence", "")
        exist_keys.add(_key(sent))
        rows.append({
            "provenance": "claim_extractor_100",  # 기존 슬롯 gold 보유
            "src_id": e.get("id"),
            "label": e.get("label"),                # positive | negative
            "claim_type_gold": e.get("claim_type_gold"),
            "src_text": sent,
            "gold_n_claims": e.get("n_claims"),
            "gold_claims": e.get("claims", []),
        })
    # 마스터 213: 전부 수치 주장 문장(양성). 슬롯 gold 미주석 → null(지어내지 않음).
    for s in spine:
        rows.append({
            "provenance": "master",
            "row_id": s["row_id"],
            "verdict_label": s["label"],
            "label": "positive",                    # 수치 주장 보유 = 추출 양성
            "src_text": s["text"],
            "is_claim_bearing": True,
            "gold_claims": None,                     # 슬롯 gold 미주석(추출 여부만 검증 가능)
            "_also_in_claim_extractor_100": _key(s["text"]) in exist_keys,
        })
    _write_jsonl(f"{PFX}extract_statistical_claims.jsonl", rows)


# --------------------------------------------------------------------------- #
# [3] normalize_claim
#   입력=base + value/period/compare raw, gold=정규화 expected. 기존 100 재사용.
# --------------------------------------------------------------------------- #
def build_stage3(spine: list[dict]) -> None:
    by_key = {_key(s["text"]): s["row_id"] for s in spine}
    gold = _read_jsonl(EXIST_NORMALIZE, skip_comments=True)
    rows = []
    for g in gold:
        v = g.get("value") or {}
        p = g.get("period_value") or {}
        c = g.get("compare_period_value")
        rows.append({
            "provenance": "normalize_100",
            "src_id": g.get("id"),
            "row_id": by_key.get(_key(g.get("src", ""))),  # 마스터 매칭 시 연결, 없으면 null
            "base": g.get("base"),
            "value": {"raw": v.get("raw")},
            "period_value": {"raw": p.get("raw")},
            "compare_period_value": {"raw": c.get("raw")} if c else None,
            "gold": {
                "value": {"expected": v.get("expected"), "match": v.get("match"), "kind": v.get("kind")},
                "period": {"expected": p.get("expected"), "match": p.get("match")},
                "compare": ({"expected": c.get("expected"), "match": c.get("match")} if c else None),
            },
            "src_text": g.get("src"),
        })
    _write_jsonl(f"{PFX}normalize_claim.jsonl", rows)


# --------------------------------------------------------------------------- #
# [9] decide_verdict (결정적 집계)
#   입력=claim별 verdict 묶음, gold=verdict_counts/overall_confidence/coverage(스펙 산식).
#   verdict 값은 전부 실제 마스터 라벨. 그룹은 '실제 라벨로 구성한 테스트 시나리오'.
# --------------------------------------------------------------------------- #
def _spec_metrics(verdicts: list[str]) -> dict:
    """decide_verdict 스펙 산식(독립 계산). NEI→N."""
    codes = ["T", "F", "M", "N"]
    counts = {c: 0 for c in codes}
    for v in verdicts:
        counts[v if v in counts else "N"] += 1
    total = len(verdicts)
    resolved = counts["T"] + counts["F"] + counts["M"]
    return {
        "verdict_counts": counts,
        "overall_confidence": (counts["T"] / resolved) if resolved else 0.0,
        "coverage": (resolved / total) if total else 0.0,
    }


def build_stage9(spine: list[dict]) -> None:
    def code(lbl: str) -> str:
        return "N" if lbl == "NEI" else lbl
    by_label = {"T": [], "F": [], "M": [], "N": []}
    for s in spine:
        by_label[code(s["label"])].append(s["row_id"])

    groups: list[tuple[str, list[str], list]] = []  # (scenario, verdicts, member_row_ids)

    def grp(name, member_ids_by_code):
        verdicts, members = [], []
        for c, ids in member_ids_by_code:
            verdicts += [c] * len(ids)
            members += [{"row_id": i, "verdict": c} for i in ids]
        groups.append((name, verdicts, members))

    # 1) 전체 실제 분포
    grp("all_213", [(c, by_label[c]) for c in ("T", "F", "M", "N")])
    # 2) 라벨 순수 그룹(실제 전수)
    for c in ("T", "F", "M", "N"):
        grp(f"pure_{c}", [(c, by_label[c])])
    # 3) 실제 라벨 혼합(결정적 표본: 각 라벨 앞 k개)
    def head(c, k): return by_label[c][:k]
    grp("mixed_TFMN_5each", [(c, head(c, 5)) for c in ("T", "F", "M", "N")])
    grp("mixed_T8_F2", [("T", head("T", 8)), ("F", head("F", 2))])
    grp("mixed_T3_M3_N3", [("T", head("T", 3)), ("M", head("M", 3)), ("N", head("N", 3))])
    # 4) 경계 케이스(실제 라벨 1개씩 / 빈 그룹)
    grp("boundary_single_T", [("T", head("T", 1))])
    grp("boundary_single_N", [("N", head("N", 1))])
    grp("boundary_empty", [])

    rows = []
    for gid, (name, verdicts, members) in enumerate(groups, 1):
        rows.append({
            "group_id": f"grp-{gid:02d}",
            "scenario": name,
            "note": "verdict 값은 실제 마스터 라벨; 그룹은 집계 산식 검증용 시나리오(NEI→N).",
            "claim_results": members,            # 입력: 각 claim의 verdict
            "gold": _spec_metrics(verdicts),     # 정답: 스펙 산식 독립 계산
        })
    _write_jsonl(f"{PFX}decide_verdict.jsonl", rows)


def main() -> None:
    spine = load_spine()
    print("== 결정적 단계 생성 ==")
    build_stage2(spine)
    build_stage3(spine)
    build_stage9(spine)
    if CAPTURE.exists():
        print("(캡처 파일 감지됨 — 4~8·10단계는 build_eval_sets_from_capture.py 로 생성)")
    else:
        print("(캡처 미완료 — 4~8·10단계는 캡처 완료 후 생성)")


if __name__ == "__main__":
    main()
