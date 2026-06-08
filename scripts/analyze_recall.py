"""recall_50_results.json 분석 출력."""
import json

with open('scripts/recall_50_results.json', encoding='utf-8') as f:
    results = json.load(f)

no_subject = [r for r in results if not r['subjects']]
has_subject = [r for r in results if r['subjects']]
no_hits = [r for r in has_subject if any(
    hits and hits[0].get('error') for hits in r['kosis'].values()
)]

print(f'=== 50건 Recall 테스트 요약 ===')
print(f'subject 추출 성공: {len(has_subject)}건 / 50건')
print(f'subject 추출 실패: {len(no_subject)}건')
print(f'KOSIS 검색 오류:   {len(no_hits)}건')
print()

print('─' * 70)
print('【subject 추출 실패 문장】')
for r in no_subject:
    print(f'  [{r["idx"]:>2}] {r["sentence"][:100]}')

print()
print('─' * 70)
print('【전체 결과 (subject → top3 표)】')
for r in results:
    print(f'\n[{r["idx"]:>2}] {r["sentence"][:90]}')
    if not r['subjects']:
        print('     [X] subject 없음')
        continue
    for subj, hits in r['kosis'].items():
        print(f'     subject: {subj}')
        for h in hits[:3]:
            if 'error' in h:
                print(f'       [!] {h["error"]}')
            else:
                print(f'       [{h["rank"]}] {h["tbl_nm"]}  ({h["tbl_id"]})')
