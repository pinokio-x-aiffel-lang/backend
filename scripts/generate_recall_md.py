"""recall_50_results.json → recall_50_report.md 생성."""
import json
from datetime import date

with open('scripts/recall_50_results.json', encoding='utf-8') as f:
    results = json.load(f)

lines = []

lines.append(f'# KOSIS Recall 테스트 보고서')
lines.append(f'')
lines.append(f'> 생성일: {date.today()}  ')
lines.append(f'> 클라비 제공 기사 중 통계청 언급 문장 50건 — extractor → KOSIS search 파이프라인')
lines.append(f'')

# 요약
total = len(results)
no_claim = [r for r in results if not r['claims']]
has_claim = [r for r in results if r['claims']]
no_hits = [
    r for r in has_claim
    if r['kosis'] and all(
        hits and hits[0].get('error') for hits in r['kosis'].values()
    )
]
hit_ok = [r for r in has_claim if r['kosis'] and any(
    hits and not hits[0].get('error') for hits in r['kosis'].values()
)]

lines.append(f'## 요약')
lines.append(f'')
lines.append(f'| 항목 | 건수 |')
lines.append(f'|---|---|')
lines.append(f'| 전체 문장 | {total}건 |')
lines.append(f'| claim 추출 성공 | {len(has_claim)}건 |')
lines.append(f'| claim 추출 실패 | {len(no_claim)}건 |')
lines.append(f'| KOSIS 표 반환 성공 | {len(hit_ok)}건 |')
lines.append(f'| KOSIS 표 없음/오류 | {total - len(hit_ok)}건 |')
lines.append(f'')

# claim 추출 실패 목록
lines.append(f'### claim 추출 실패 문장')
lines.append(f'')
for r in no_claim:
    lines.append(f'- `[{r["idx"]:02d}]` {r["sentence"]}')
lines.append(f'')

lines.append('---')
lines.append(f'')
lines.append(f'## 전체 결과')
lines.append(f'')

CLAIM_TYPE_KO = {
    'point': '시점값',
    'change': '변화량',
    'ratio': '비율',
    'rank': '순위',
    'comparison': '비교',
    'none': '없음',
    '': '없음',
}

for r in results:
    idx = r['idx']
    sentence = r['sentence']
    claims = r['claims']
    kosis = r['kosis']

    lines.append(f'### [{idx:02d}] {sentence}')
    lines.append(f'')

    if not claims:
        lines.append(f'> **claim 추출 실패** — 검증 가능한 수치 없음')
        lines.append(f'')
        lines.append('---')
        lines.append(f'')
        continue

    # Extractor 출력 (claim schema)
    lines.append(f'#### Extractor 출력 (claim schema)')
    lines.append(f'')
    for c in claims:
        ct = CLAIM_TYPE_KO.get(c.get('claim_type', ''), c.get('claim_type', ''))
        lines.append(f'| 필드 | 값 |')
        lines.append(f'|---|---|')
        lines.append(f'| claim_type | {ct} |')
        lines.append(f'| subject | **{c["subject"]}** |')
        lines.append(f'| value_raw | `{c["value_raw"]}` |')
        lines.append(f'| unit | {c["unit"]} |')
        lines.append(f'| period_type | {c["period_type"]} |')
        lines.append(f'| period_raw | {c["period_raw"]} |')
        lines.append(f'| population | {c["population"]} |')
        lines.append(f'| cited_source | {c["cited_source"]} |')
        lines.append(f'')

    # KOSIS 검색 결과
    lines.append(f'#### KOSIS 검색 결과')
    lines.append(f'')
    if not kosis:
        lines.append(f'> subject 없어서 검색 미실시')
    else:
        for subj, hits in kosis.items():
            lines.append(f'**검색어: `{subj}`**')
            lines.append(f'')
            if not hits:
                lines.append(f'> 결과 없음')
            elif hits[0].get('error'):
                lines.append(f'> 오류: {hits[0]["error"]}')
            else:
                lines.append(f'| 순위 | tbl_id | 표명 | 통계명 |')
                lines.append(f'|---|---|---|---|')
                for h in hits:
                    if h.get('error'):
                        lines.append(f'| - | - | 오류: {h["error"]} | - |')
                    else:
                        lines.append(
                            f'| {h["rank"]} | `{h["tbl_id"]}` '
                            f'| {h["tbl_nm"]} | {h["stat_nm"]} |'
                        )
            lines.append(f'')

    lines.append('---')
    lines.append(f'')

md = '\n'.join(lines)
out_path = 'scripts/recall_50_report.md'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(md)

print(f'저장 완료 → {out_path}  ({len(results)}건)')
