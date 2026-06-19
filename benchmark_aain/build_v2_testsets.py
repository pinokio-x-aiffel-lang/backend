"""v2 테스트셋 빌드 — input=현재 파이프라인 캡처 슬라이스, gold=독립 출처 재부착.

비순환: input 만 현재 모듈로 갱신, gold 는 SSOT figure·병인님·KOSIS·사람 normalize gold 에서
row_id+값 기준 재부착(claim_id 는 바뀌어 못 씀). 10단계 gold_template 은 스냅샷(회귀).
→ memory: testset-regen-input-not-gold

대상: 3·5·6·7·8·10 (2·4·9 제외). 파일명 시리얼 02.
실행: uv run x python benchmark_aain/build_v2_testsets.py  (KOSIS 불필요 — 캡처 슬라이스만 사용)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAP = ROOT / "benchmark_aain/data/260619_capture_v2_snapshots.jsonl"
SSOT = ROOT / "benchmark/data/ssot/260614_master_eval_213_parsed_human_checked_SSOT.jsonl"
BYUNGIN = ROOT / "benchmark_aain/data/byungin_gold_map.jsonl"
S4_GOLD = ROOT / "benchmark/data/4_retrieve/4_source_2.jsonl"  # 병인님 gold_tbl_id
S3_HUMAN = ROOT / "benchmark/data/3_normalize/3_source_1.jsonl"  # 사람 normalize gold (raw→expected)
DATA = ROOT / "benchmark/data"

OPINION_RUBRIC = ["분포 반영", "verdict와 모순 없음", "환각 없음"]


def load(p):
    return [json.loads(s) for ln in p.read_text(encoding="utf-8").splitlines() if (s := ln.strip())]


def dump(p, rows):
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


# ── 독립 gold 매칭 헬퍼 ──
def to_num(x):
    try:
        return float(re.sub(r"[^\d.\-]", "", str(x)))
    except (TypeError, ValueError):
        return None


def close(a, b, rel=0.01):
    a, b = to_num(a), to_num(b)
    if a is None or b is None:
        return False
    return abs(a - b) <= max(0.05, abs(b) * rel)


# 템플릿 스냅샷 (generate_explanation._build_explanation 복제)
def has_batchim(t):
    for ch in reversed(t):
        c = ord(ch)
        if 0xAC00 <= c <= 0xD7A3:
            return (c - 0xAC00) % 28 != 0
    return False


def eun_neun(t):
    return "은" if has_batchim(t) else "는"


def fmt_period(pt, p):
    p = (p or "").strip()
    if pt == "Y":
        y = p[:4] if len(p) >= 4 and p[:4].isdigit() else p
        return f"{y}년 "
    if pt == "M":
        m = re.match(r"(\d{4})-(\d{2})", p)
        if m:
            return f"{m.group(1)}년 {int(m.group(2))}월 "
        if len(p) == 6 and p.isdigit():
            return f"{p[:4]}년 {int(p[4:])}월 "
    if pt == "Q":
        m = re.match(r"(\d{4})-Q([1-4])", p)
        if m:
            return f"{m.group(1)}년 {m.group(2)}분기 "
    return ""


def build_template(cr, claim):
    subject = (claim.get("subject") if claim else None) or "해당 지표"
    unit = (claim.get("unit") if claim else "") or ""
    pv = (claim.get("period_value") or {}) if claim else {}
    period_str = fmt_period(claim.get("period_type", "") if claim else "", pv.get("llm_value", ""))
    ev = (cr.get("evidence") or [None])[0]
    src = f" (출처: {ev['table_name']})" if ev and ev.get("table_name") else ""
    cv = f"{cr.get('claim_value')}{unit}"
    kv = cr.get("kosis_value")
    kd = f"{kv}{unit}" if kv is not None else ""
    v = cr.get("verdict")
    if v == "T":
        return f"기사의 {period_str}{subject} {cv}{eun_neun(cv)} KOSIS 공식 수치와 일치합니다.{src}"
    if v == "F":
        mm = f" 불일치 유형: {cr.get('mismatch_type')}." if cr.get("mismatch_type") else ""
        return f"기사의 {period_str}{subject} {cv}{eun_neun(cv)} KOSIS 공식 수치({kd})와 다릅니다.{mm}{src}"
    if v == "M":
        return f"기사의 {period_str}{subject} {cv}{eun_neun(cv)} KOSIS 공식 수치({kd})와 부분적으로 일치합니다.{src}"
    return f"{period_str}{subject}에 대한 KOSIS 공식 통계를 찾지 못해 검증할 수 없습니다."


def claim_slim(c):
    return {
        "subject": c.get("subject"), "unit": c.get("unit"),
        "claim_type": c.get("claim_type"),
        "value_raw": (c.get("value") or {}).get("raw"),
        "value_llm": (c.get("value") or {}).get("llm_value"),
        "period_type": c.get("period_type"),
        "period_value": c.get("period_value"),
        "population": c.get("population"),
    }


def main():
    cap = {r["row_id"]: r for r in load(CAP)}
    ssot = {r["row_id"]: r for r in load(SSOT)}
    byungin = {r["row_id"]: r for r in load(BYUNGIN)}
    s4g_by_row = {}
    for r in load(S4_GOLD):
        if r.get("gold_tbl_id"):
            s4g_by_row.setdefault(r["row_id"], r["gold_tbl_id"])
    # 사람 normalize gold: raw 문자열(공백 제거 정규화) → gold
    def nraw(s):
        return re.sub(r"\s+", "", str(s or ""))
    s3_by_raw = {}
    for r in load(S3_HUMAN):
        raw = (r.get("value") or {}).get("raw")
        if raw:
            s3_by_raw[nraw(raw)] = r.get("gold")

    rec3, rec5, rec6, rec7, rec8, rec10 = [], [], [], [], [], []

    for rid, r in cap.items():
        if r.get("failed_step"):  # 파이프라인 실패행은 input 미완 → 스킵(별도 보고)
            continue
        label = r["label"]
        snaps = r["snapshots"]
        s2 = snaps.get("after2", {})
        s5 = snaps.get("after5", {})
        s6 = snaps.get("after6", {})
        s9 = snaps.get("after9", {})
        claims2 = {c["claim_id"]: c for c in (s2.get("claims") or [])}  # 정규화 前(raw용)
        claims6 = s6.get("claims") or []  # 정규화 後(value_llm 채워짐, 표준 claim 데이터)
        ana6 = {a["claim_id"]: a for a in (s6.get("analysis") or [])}  # 랭킹 後 evidences
        ana5 = {a["claim_id"]: a for a in (s5.get("analysis") or [])}  # 랭킹 前 evidences + candidates
        crs = {cr["claim_id"]: cr for cr in ((s9.get("verifications") or {}).get("claim_results") or [])}
        sfig = ssot[rid].get("gold_figures") or []
        bg = byungin.get(rid)
        gold_tbl = s4g_by_row.get(rid)

        for c in claims6:
            cid = c["claim_id"]
            cl = claim_slim(c)
            c2 = claims2.get(cid, c)
            raw = (c2.get("value") or {}).get("raw")
            vllm = (c.get("value") or {}).get("llm_value")  # 정규화값(매칭 앵커)
            ev_list = (ana6.get(cid) or {}).get("evidences") or []   # 랭킹 後(7/8용)
            ev_pre = (ana5.get(cid) or {}).get("evidences") or []    # 랭킹 前(6 rank input)
            cand_list = (ana5.get(cid) or {}).get("candidates") or []
            has_ev = bool(ev_list)

            # ── 3 normalize: 사람 gold(raw→expected) 재부착, input=정규화前 c2 ──
            g3 = s3_by_raw.get(nraw(raw))
            rec3.append({
                "row_id": rid, "label": label, "claim_id": cid,
                "value": c2.get("value"), "period_value": c2.get("period_value"),
                "compare_period_value": c2.get("compare_period_value"),
                "src_text": c2.get("sentence"),
                "gold": g3, "scorable": g3 is not None,
                "scorable_reason": "ok" if g3 is not None else "raw 사람 normalize gold 미보유",
                "provenance": "v2_capture260619",
            })

            # ── 5 fetch: gold figure 값(독립) ──
            gold5 = None
            if label == "T":
                m = next((f for f in sfig if close(vllm or raw, f.get("value"))
                          or close(raw, f.get("value"))), None)
                if m:
                    gold5 = {"value": m.get("value"), "value_source": "SSOT_figure", "period": m.get("period")}
            elif bg and bg.get("official_value") is not None:
                gold5 = {"value": bg["official_value"], "value_source": "byungin_official"}
            rec5.append({
                "row_id": rid, "label": label, "claim_id": cid, "claim": cl,
                "candidates": cand_list, "gold": gold5,
                "scorable": gold5 is not None,
                "scorable_reason": "ok" if gold5 else "독립 figure gold 미매칭",
                "provenance": "v2_capture260619",
            })

            # ── 6 rank: gold_best_index = 병인님 gold_tbl_id 매칭 ──
            gbi, sc6, rsn6 = None, False, "gold_tbl_id(병인님) 미보유"
            if gold_tbl:
                idx = next((i for i, e in enumerate(ev_pre) if e.get("kosis_tbl_id") == gold_tbl), None)
                if idx is not None:
                    gbi, sc6, rsn6 = idx, True, "ok"
                else:
                    rsn6 = "정답표 후보 evidences 미포함(검색단계 책임)"
            rec6.append({
                "row_id": rid, "label": label, "claim_id": cid, "claim": cl,
                "evidences": ev_pre, "gold_best_index": gbi, "gold_tbl_id": gold_tbl,
                "scorable": sc6, "scorable_reason": rsn6, "provenance": "v2_capture260619",
            })

            # ── 7 metric: gold_verdict (독립 라벨·값 앵커) ──
            gv, sc7, rsn7 = None, False, ""
            if label == "NEI":
                gv, sc7, rsn7 = "N", True, "NEI 라벨"
            elif label == "T":
                m = next((f for f in sfig if close(vllm or raw, f.get("value"))), None)
                if m and has_ev:
                    gv, sc7, rsn7 = "T", True, "SSOT figure 일치 claim"
                else:
                    rsn7 = "T이나 figure 미매칭/무증거 → 채점제외"
            elif label == "F":
                # F 거짓 figure claim 판정은 값 앵커 필요 → 보수적으로 무증거시 제외
                if has_ev:
                    gv, sc7, rsn7 = "F", True, "F 라벨(거짓 수치 인용)"
                else:
                    rsn7 = "F이나 무증거 → 채점제외"
            else:  # M → 7단계는 T로 초기, 8단계서 재판정 → 7 채점 제외
                rsn7 = "M 라벨(8단계 영역) → 7 채점제외"
            rec7.append({
                "row_id": rid, "label": label, "claim_id": cid,
                "gold_verdict_stage7": gv, "has_evidence": has_ev, "claim": cl,
                "scorable": sc7, "scorable_reason": rsn7, "provenance": "v2_capture260619",
            })

            # ── 8 alignment: gold M(독립 라벨) + dimension(병인님) ──
            ev0 = ev_list[0] if ev_list else None
            gold8 = {"is_M": label == "M"}
            if label == "M" and bg and bg.get("distortion"):
                gold8["dimension"] = bg["distortion"]
                gold8["dimension_provenance"] = "byungin"
            rec8.append({
                "row_id": rid, "label": label, "claim_id": cid, "claim": cl,
                "evidence": ev0, "gold": gold8,
                "scorable": has_ev, "scorable_reason": "ok" if has_ev else "무증거 → 정합 판정 불가",
                "provenance": "v2_capture260619",
            })

        # ── 10 explanation: claim_result 별 스냅샷 ──
        cmap = {c["claim_id"]: c for c in claims6}
        for cid, cr in crs.items():
            c = cmap.get(cid, {})
            rec10.append({
                "row_id": rid, "label": label, "claim_id": cid,
                "claim": claim_slim(c), "claim_result": cr,
                "gold_template": build_template(cr, c),
                "gold_template_provenance": "template_snapshot",
                "opinion_rubric": OPINION_RUBRIC,
                "scorable": True, "scorable_reason": "ok", "provenance": "v2_capture260619",
            })

    out = {
        "3_normalize/3_source_2.jsonl": rec3,
        "5_fetch/5_source_3.jsonl": rec5,     # 5_source_2=병인님 이미 점유 → 03
        "6_rank/6_source_2.jsonl": rec6,
        "7_metric/7_source_2.jsonl": rec7,
        "8_alignment/8_source_2.jsonl": rec8,
        "10_explanation/10_source_2.jsonl": rec10,
    }
    print(f"캡처 {len(cap)}행 (실패제외 빌드)")
    for rel, rows in out.items():
        dump(DATA / rel, rows)
        sc = sum(1 for r in rows if r.get("scorable"))
        print(f"  {rel:34} {len(rows):>4} records | scorable {sc}")


if __name__ == "__main__":
    main()
