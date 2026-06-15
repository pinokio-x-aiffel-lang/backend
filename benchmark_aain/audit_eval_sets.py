"""생성된 단계별 평가셋이 각 모듈 테스트에 충분한지 전수 감사(읽기 전용).

체크: ①모듈이 읽는 입력 필드 누락 ②gold 채점 가능 비율 ③다중 claim 라벨 오배정
④input↔verdict 정합(예: F인데 공식값 null) ⑤9단계 산식 독립 재계산.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CAP = DATA / "260614_capture_master_stage1to8.json"
PFX = "260614_source_from_origin_for_"


def jl(name):
    return [json.loads(l) for l in (DATA / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def hdr(t):
    print(f"\n{'='*70}\n{t}\n{'='*70}")


# ── 0. 다중 claim 라벨 오배정 위험 (capture 기준) ──
hdr("[0] 한 문장→다중 claim : 라벨/공식값 오배정 위험")
cap = json.load(open(CAP, encoding="utf-8"))
per_row = []
multi_true = 0
extra_claims_true = 0
for e in cap:
    res = e.get("result") or {}
    n = len(res.get("claims", []))
    per_row.append(n)
    if e["label"] == "T" and n > 1:
        multi_true += 1
        extra_claims_true += (n - 1)
print("claims/row 분포:", dict(sorted(Counter(per_row).items())))
print(f"claim>1 인 행: {sum(1 for n in per_row if n>1)} / {len(per_row)}")
print(f"True행 중 다중claim: {multi_true} → 공식값이 1개 claim에만 맞는데 전체에 부여된 잉여 claim: {extra_claims_true}")

# ── 2. extract ──
hdr("[2] extract_statistical_claims")
s2 = jl(f"{PFX}extract_statistical_claims.jsonl")
prov = Counter(r["provenance"] for r in s2)
g100 = [r for r in s2 if r["provenance"] == "claim_extractor_100"]
print("provenance:", dict(prov))
print("label(100셋):", dict(Counter(r["label"] for r in g100)))
print("claim_type_gold 보유(100셋):", sum(1 for r in g100 if r.get("claim_type_gold")))
print("gold_claims 보유 행(슬롯 채점 가능):", sum(1 for r in s2 if r.get("gold_claims")))
print("src_text 빈 행:", sum(1 for r in s2 if not (r.get("src_text") or "").strip()))

# ── 3. normalize ──
hdr("[3] normalize_claim")
s3 = jl(f"{PFX}normalize_claim.jsonl")
print("총:", len(s3))
print("value.kind 분포:", dict(Counter((r["gold"]["value"] or {}).get("kind") for r in s3)))


def _ptype(exp):
    if not exp:
        return "none"
    if "Q" in exp:
        return "Q"
    if "H" in exp:
        return "H/S"
    if exp.count("-") == 1:
        return "M"
    return "Y"


print("period 유형 분포:", dict(Counter(_ptype((r["gold"]["period"] or {}).get("expected")) for r in s3)))
print("compare 보유:", sum(1 for r in s3 if r.get("compare_period_value")))
print("value.raw 빈 행:", sum(1 for r in s3 if not (r["value"].get("raw"))))
print("period.raw 빈 행:", sum(1 for r in s3 if not (r["period_value"].get("raw"))))

# ── 4. retrieve ──
hdr("[4] retrieve_kosis_candidates")
s4 = jl(f"{PFX}retrieve_kosis_candidates.jsonl")
print("총:", len(s4))
print("subject 빈:", sum(1 for r in s4 if not (r.get("subject") or "").strip()))
print("candidates 빈(검색0건):", sum(1 for r in s4 if not r.get("candidates")))
print("gold_tbl_id 주석된 행:", sum(1 for r in s4 if r.get("gold_tbl_id")))
print("→ Recall 채점 가능 행:", sum(1 for r in s4 if r.get("gold_tbl_id")), "(0이면 채점 불가)")

# ── 5. fetch ──
hdr("[5] fetch_kosis_data")
s5 = jl(f"{PFX}fetch_kosis_data.jsonl")
print("총:", len(s5))
print("gold.value 보유(채점가능) by label:",
      dict(Counter(r["label"] for r in s5 if r["gold"]["value"] is not None)))
print("candidates 빈:", sum(1 for r in s5 if not r.get("candidates")))
print("captured_evidences 보유:", sum(1 for r in s5 if r.get("captured_evidences")))
print("consistency_flag 분포:", dict(Counter(r["gold"]["consistency_flag"] for r in s5)))

# ── 6. rank ──
hdr("[6] rank_evidence")
s6 = jl(f"{PFX}rank_evidence.jsonl")
print("총(후보≥2):", len(s6))
print("gold_best_index 도출(채점가능):", sum(1 for r in s6 if r.get("gold_best_index") is not None))
print("미도출(보강필요):", sum(1 for r in s6 if r.get("gold_best_index") is None))
print("evidences<2 인 행(오류):", sum(1 for r in s6 if len(r.get("evidences", [])) < 2))

# ── 7. calculate_metric ──
hdr("[7] calculate_metric")
s7 = jl(f"{PFX}calculate_metric.jsonl")
sample = s7[0]
print("행 키:", list(sample.keys()), "| evidence 키:", list((sample.get("evidence") or {}).keys()))
miss_period = not any("period" in str(r.get("claim", {})) for r in s7[:5])
print("claim.period 필드 존재?:", any("period" in (r.get("claim") or {}) for r in s7))
print("evidence.period 필드 존재?:", any("period" in (r.get("evidence") or {}) for r in s7 if r.get("evidence")))
print("has_evidence:", sum(1 for r in s7 if r.get("has_evidence")), "/", len(s7))
# 채점 유효성: has_evidence=False 인데 gold!=N → 불공정(검색실패를 모듈오류로)
unfair = [r for r in s7 if not r["has_evidence"] and r["gold_verdict_stage7"] != "N"]
print("무증거인데 gold!=N (불공정 채점 위험):", len(unfair),
      dict(Counter(r["label"] for r in unfair)))
print("M행 consistency(=값일치여야 M→T 성립):",
      dict(Counter(r["consistency_flag"] for r in s7 if r["label"] == "M")))

# ── 8. check_alignment ──
hdr("[8] check_alignment")
s8 = jl(f"{PFX}check_alignment.jsonl")
req_claim = ["sentence", "subject", "population", "unit", "aggregation", "period_llm"]
req_ev = ["table_name", "subject", "population", "unit", "period"]
miss = sum(1 for r in s8 if any(not (r["claim"].get(k) not in (None, "")) for k in req_claim))
print("총:", len(s8), "| label:", dict(Counter(r["label"] for r in s8)))
print("claim 필수필드 일부 빈 행:", miss)
print("evidence.table_name 빈:", sum(1 for r in s8 if not r["evidence"].get("table_name")))
print("gold.dimension 주석된 행:", sum(1 for r in s8 if r["gold"].get("dimension")))
print("population_fallback=True evidence:", sum(1 for r in s8 if r["evidence"].get("population_fallback")))

# ── 9. decide_verdict (산식 독립 재계산) ──
hdr("[9] decide_verdict — gold 산식 독립 검증")
s9 = jl(f"{PFX}decide_verdict.jsonl")
bad = 0
for r in s9:
    vs = [c["verdict"] for c in r["claim_results"]]
    cnt = {k: sum(1 for v in vs if (v if v in ("T", "F", "M", "N") else "N") == k) for k in ("T", "F", "M", "N")}
    res = cnt["T"] + cnt["F"] + cnt["M"]
    conf = cnt["T"] / res if res else 0.0
    cov = res / len(vs) if vs else 0.0
    g = r["gold"]
    if g["verdict_counts"] != cnt or abs(g["overall_confidence"] - conf) > 1e-6 or abs(g["coverage"] - cov) > 1e-6:
        bad += 1
print("총 시나리오:", len(s9), "| gold 산식 불일치:", bad, "(0이면 정확)")

# ── 10. generate_explanation ──
hdr("[10] generate_explanation")
s10 = jl(f"{PFX}generate_explanation.jsonl")
fm = [r for r in s10 if r["claim_result"]["verdict"] in ("F", "M")]
fm_null_kv = [r for r in fm if r["claim_result"]["kosis_value"] is None]
print("총:", len(s10), "| verdict:", dict(Counter(r["claim_result"]["verdict"] for r in s10)))
print("F/M 행:", len(fm), "| 그중 kosis_value=null (템플릿 깨짐/입력 비현실):", len(fm_null_kv))
print("gold_template 보유:", sum(1 for r in s10 if r.get("gold_template")))
print("claim_value 빈:", sum(1 for r in s10 if not r["claim_result"].get("claim_value")))
