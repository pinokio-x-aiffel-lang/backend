"""1~5단계 파이프라인 결과 JSON → 마크다운 표 리포트."""
import json
from collections import Counter
from pathlib import Path

J = Path("tests/results/260612_1-5_pipeline_leeaain.json")
OUT = Path("tests/results/260612_1-5_pipeline_leeaain.md")
d = json.loads(J.read_text(encoding="utf-8"))
res = d["results"]


def cell(s, n=40):
    s = str(s).replace("|", "/").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def attempt_meta(att):
    """실제 표 메타 (items · axes) 압축 문자열."""
    items = "·".join(att.get("items", [])[:4]) or "—"
    axes = att.get("axes", {})
    axs = "; ".join(f"{k}:[{'/'.join(v[:3])}]" for k, v in list(axes.items())[:2]) or "—"
    return f"items: {cell(items,30)}<br>axes: {cell(axs,55)}"


def used_meta(c):
    """조회에 쓴 메타 (itmId·objL·기간)."""
    ev = c.get("evidence")
    if ev:
        cls = ev.get("classification") or {}
        clsv = ",".join(f"{k}={v}" for k, v in cls.items()) or "—"
        return f"itmId={ev.get('itm_id') or '—'}<br>objL={cell(clsv,30)}<br>기간={ev.get('period') or '—'}"
    # 미발견: best attempt itm_id
    a = next((a for a in c.get("attempts", [])), None)
    return f"itmId={(a or {}).get('itm_id') or '미해소'}<br>기간={c.get('period') or '—'}"


L = []
L.append("# 1~5단계 파이프라인 — KOSIS 값 조회 결과\n")
L.append("| 항목 | 내용 |")
L.append("|---|---|")
L.append(f"| 입력 | `{d['input']}` ({d['n_sentences']}문장) |")
L.append("| 단계 | [1]load [2]extract [3]normalize [4]retrieve(표검색) [5]fetch(메타+값) |")
L.append("| base | load_article 더미 `2025-04` (상대시점 계산용) |")
L.append(f"| 실행 | {d['duration_s']}s |\n")

claims = [(r, c) for r in res for c in r["claims"]]
n_true = sum(1 for _, c in claims if c["found"])
n_sfail = sum(1 for r in res if r["stage_fail"])
blocks = Counter(c["stage_block"].split(":")[0] for _, c in claims if c["stage_block"])
L.append("## 요약\n")
L.append(f"- 문장 {len(res)} · 추출 claim {len(claims)} · **값 발견(TRUE) {n_true} / FALSE {len(claims)-n_true}**")
L.append(f"- 문장 단위 단계 미통과(2단계 등): {n_sfail}건")
L.append(f"- claim 단위 미통과 단계: " + (", ".join(f"{k} {v}건" for k, v in blocks.most_common()) or "없음") + "\n")

# 메인 표
L.append("## claim별 결과\n")
L.append("| # | claim (subject / value / 기간 / 모집단) | 결과 | 대상 통계표(후보 상위) | 조회에 쓴 메타 | 실제 표 메타 (items · axes) | 미통과 |")
L.append("|--|--|--|--|--|--|--|")
i = 0
for r in res:
    for c in r["claims"]:
        i += 1
        ident = f"{cell(c['subject'],14)} / {cell(c['value_raw'],14)} / {cell(c['period'],10)} / {cell(c['population'],8)}"
        tf = "✅TRUE" if c["found"] else "❌FALSE"
        cands = cell("·".join(c["candidates"][:3]) or "—", 40)
        # 실제 표 메타: 발견이면 evidence 표, 아니면 첫 attempt
        ev = c.get("evidence")
        att = None
        if ev:
            att = next((a for a in c["attempts"] if a.get("tbl_nm") and ev.get("table_name") and a["tbl_nm"] in ev["table_name"]), None)
        att = att or next((a for a in c["attempts"]), None)
        meta_actual = attempt_meta(att) if att else "—"
        block = cell(c["stage_block"] or "—", 28)
        L.append(f"| {i} | {ident} | {tf} | {cands} | {used_meta(c)} | {meta_actual} | {block} |")

# 단계 미통과 문장
sfails = [r for r in res if r["stage_fail"]]
if sfails:
    L.append("\n## 단계 미통과 문장 (모듈 요건 불충족)\n")
    L.append("| # | 사유 | 문장 |\n|--|--|--|")
    for r in sfails:
        L.append(f"| {r['n']} | {cell(r['stage_fail'],40)} | {cell(r['sentence'],50)} |")

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"작성: {OUT}  (claim {len(claims)}행)")
print(f"TRUE {n_true} / FALSE {len(claims)-n_true} | 문장 단계미통과 {n_sfail}")
