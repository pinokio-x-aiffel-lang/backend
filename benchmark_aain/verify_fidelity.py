"""생성 소스 ↔ origin 글자·수치 대조(읽기 전용).

origin = ①마스터 xlsx(텍스트/공식값) ②기존 gold(2_claim_extractor_output / 3_normalize_gold).
- verbatim 이어야 하는 필드(2·3단계 텍스트, gold 공식값)는 '완전 일치' 검사.
- 캡처 파생 필드(claim.sentence/value.raw 등)는 LLM 처리라 원문과 다를 수 있어 '구분 보고'.
검출: 실제 글자 변경 / 공백만 차이 / 수치(자릿수) 변경.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "benchmark_aain/data"
XLSX = DATA / "260605_평가셋_T_F_M_NEI_모음.xlsx"
EXTRACT100 = ROOT / "benchmark/data/2_claim_extractor_output.jsonl"
NORM100 = ROOT / "benchmark/data/3_normalize_claim_100_gold.jsonl"


def jl(p, skip_comments=False):
    out = []
    for l in Path(p).read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        if skip_comments and l.lstrip().startswith(("#", "//")):
            continue
        out.append(json.loads(l))
    return out


def digits(s):
    """숫자 토막 추출. 콤마(천단위)는 제거 후 추출('28,589'→['28589'])."""
    return re.findall(r"\d+", str(s or "").replace(",", ""))


def hdr(t):
    print(f"\n{'='*68}\n{t}\n{'='*68}")


# origin 로드(READ-ONLY)
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws = wb["labelled"]
xrows = list(ws.iter_rows(values_only=True))[1:]
xtext = {i + 1: (r[0] or "") for i, r in enumerate(xrows)}      # row_id → 원문 텍스트(strip 안 함)
xfig = {i + 1: (r[2] if len(r) > 2 and r[2] else "") for i, r in enumerate(xrows)}

spine = {r["row_id"]: r for r in jl(DATA / "260614_master_eval_213_parsed.jsonl")}

# ── A. 마스터 텍스트: spine ↔ xlsx ──
hdr("[A] 마스터 텍스트  spine ↔ xlsx 원문")
exact = ws_only = charsdiff = 0
ws_examples = []
for rid, xt in xtext.items():
    st = spine[rid]["text"]
    if st == xt:
        exact += 1
    elif st == xt.strip() or st.strip() == xt.strip():
        ws_only += 1
        if len(ws_examples) < 3:
            ws_examples.append((rid, repr(xt[:25]), repr(st[:25])))
    else:
        charsdiff += 1
        print(f"  ⚠ row {rid} 글자 차이: xlsx={xt[:40]!r} / spine={st[:40]!r}")
print(f"완전일치 {exact} / 공백만차이 {ws_only} / 글자차이 {charsdiff}")
if ws_examples:
    print("  공백차이 예(앞/뒤 공백 strip):", ws_examples)

# ── B. 2단계 master 행: src_text ↔ xlsx ──
hdr("[B] 2단계 source(master 행) ↔ xlsx 원문")
s2 = jl(DATA / "260614_source_from_origin_for_extract_statistical_claims.jsonl")
m = [r for r in s2 if r["provenance"] == "master"]
bad = sum(1 for r in m if r["src_text"] != xtext.get(r["row_id"], "").strip())
print(f"master 행 {len(m)}개: strip 기준 불일치 {bad} (0이어야 정상)")

# ── C. 2단계 100셋: src_text ↔ 기존 gold sentence ──
hdr("[C] 2단계 source(100셋) ↔ 2_claim_extractor_output.sentence")
ext = jl(EXTRACT100)
ext_by_id = {e["id"]: e for e in ext}
g100 = [r for r in s2 if r["provenance"] == "claim_extractor_100"]
mism = [r for r in g100 if r["src_text"] != ext_by_id.get(r["src_id"], {}).get("sentence")]
print(f"100셋 {len(g100)}개: 원본 sentence 불일치 {len(mism)} (0이어야 정상)")

# ── D. 3단계: raw·expected ↔ 3_normalize_gold ──
hdr("[D] 3단계 source ↔ 3_normalize_claim_100_gold (verbatim)")
norm = jl(NORM100, skip_comments=True)
norm_by_id = {g["id"]: g for g in norm}
s3 = jl(DATA / "260614_source_from_origin_for_normalize_claim.jsonl")
draw = dexp = 0
for r in s3:
    g = norm_by_id.get(r["src_id"], {})
    if r["value"]["raw"] != (g.get("value") or {}).get("raw"):
        draw += 1
    if r["gold"]["value"]["expected"] != (g.get("value") or {}).get("expected"):
        dexp += 1
    if r["period_value"]["raw"] != (g.get("period_value") or {}).get("raw"):
        draw += 1
print(f"3단계 {len(s3)}개: raw 불일치 {draw}, expected 불일치 {dexp} (0이어야 정상)")

# ── E. gold 공식값 수치: spine.gold_figures ↔ xlsx figure 셀 ──
hdr("[E] gold 공식값 수치  spine.gold_figures ↔ xlsx '원래 통계표 수치'")
num_bad = 0
checked = 0
for rid, sp in spine.items():
    if sp["label"] != "T" or not sp["gold_figures"]:
        continue
    cell_digits = set(digits(xfig.get(rid, "")))
    for f in sp["gold_figures"]:
        checked += 1
        for vv in (f["value"] if isinstance(f["value"], list) else [f["value"]]):
            ds = digits(vv)
            # gold 값의 모든 숫자 토막이 xlsx 셀 숫자 집합에 존재해야(콤마/공백 무시)
            if not all(d in cell_digits for d in ds):
                num_bad += 1
                if num_bad <= 5:
                    print(f"  ⚠ row {rid} 수치 불일치: gold={vv} / xlsx셀숫자={sorted(cell_digits)}")
                break
print(f"True행 figure {checked}개 검사: 수치 불일치 {num_bad} (0이어야 정상)")

# ── F. 캡처 파생 필드의 원문 차이(참고 — LLM 처리라 정상 가능) ──
hdr("[F] (참고) 캡처 파생 value.raw 가 원문과 다른 예 — LLM 추출/정규화 결과")
cap = json.load(open(DATA / "260614_capture_master_stage1to8.json", encoding="utf-8"))
diff_ex = []
for e in cap:
    xt = xtext.get(e["row_id"], "")
    for c in (e.get("result") or {}).get("claims", []):
        vr = (c.get("value") or {}).get("raw") or ""
        # 원문에서 공백 제거 후에도 value.raw(공백제거)가 안 나타나면 = 표기 변형
        if vr and re.sub(r"\s", "", vr) not in re.sub(r"\s", "", xt):
            diff_ex.append((e["row_id"], vr, xt[:35]))
print(f"value.raw 가 원문 부분문자열이 아닌 건수: {len(diff_ex)} (LLM 변형, 캡처 산출이라 무생성 위반 아님)")
for rid, vr, xt in diff_ex[:6]:
    print(f"  row {rid}: value.raw={vr!r}  ← 원문 {xt!r}…")

# ── G. 캡처 수치 충실도: value.raw 의 '숫자'가 원문에 존재하는가(환각 검출) ──
hdr("[G] 캡처 value.raw 숫자 ⊆ 원문 숫자  (수치 환각 검출 — 핵심)")
halluc = []
total_v = 0
for e in cap:
    od = set(digits(xtext.get(e["row_id"], "")))
    for c in (e.get("result") or {}).get("claims", []):
        vr = (c.get("value") or {}).get("raw") or ""
        ds = digits(vr)
        if not ds:
            continue
        total_v += 1
        missing = [d for d in ds if d not in od]
        if missing:
            halluc.append((e["row_id"], vr, missing))
print(f"value.raw {total_v}개 중 원문에 없는 숫자 포함(환각 의심): {len(halluc)}")
for rid, vr, miss in halluc[:8]:
    print(f"  row {rid}: value.raw={vr!r} 원문에 없는 숫자={miss} | 원문={xtext.get(rid,'')[:45]!r}")
