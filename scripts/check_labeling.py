import csv

with open('data/eval/labeling_sheet.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

stat_keywords = ['통계청', '국가통계', '국가데이터처', '통계에 따르면', '통계청에 따르면']

filtered = []
for r in rows:
    sentence = r.get('source_sentence', '')
    tbl_id = r.get('gold_kosis_tbl_id', '').strip()
    cited = r.get('gold_cited_source', '').strip()
    if tbl_id and any(k in sentence or k in cited for k in stat_keywords):
        filtered.append(r)

print(f'전체 행: {len(rows)}')
print(f'통계청 언급 + gold tbl_id 있는 행: {len(filtered)}')
print()
for r in filtered[:5]:
    print(f'  tbl_id={r["gold_kosis_tbl_id"]}  subject={r["gold_subject"]}')
    print(f'  cited={r["gold_cited_source"]}')
    print(f'  sentence: {r["source_sentence"][:120]}')
    print()

# gold_kosis_tbl_id가 있는 전체 행도 확인
has_tbl = [r for r in rows if r.get('gold_kosis_tbl_id','').strip()]
print(f'\ngold_kosis_tbl_id 있는 전체 행: {len(has_tbl)}')
