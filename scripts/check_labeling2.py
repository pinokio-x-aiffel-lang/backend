"""labeling_sheet.csv에서 cited_source 분포 및 통계청 관련 행 확인."""
import csv
from collections import Counter

with open('data/eval/labeling_sheet.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

# cited_source 분포
cited_counter = Counter(r.get('gold_cited_source','').strip() for r in rows)
print('=== gold_cited_source 상위 20개 ===')
for src, cnt in cited_counter.most_common(20):
    print(f'  {cnt:>4}건  {repr(src)}')

print()
# source_sentence에서 통계청 언급 확인
stat_keywords = ['통계청', '고용노동부', '국토교통부', '기획재정부', '행정안전부',
                 '한국은행', '보건복지부', '교육부', '금융감독원', '공정거래위원회']

keyword_counter = Counter()
for r in rows:
    sent = r.get('source_sentence','')
    for kw in stat_keywords:
        if kw in sent:
            keyword_counter[kw] += 1

print('=== source_sentence 기관 언급 빈도 ===')
for kw, cnt in keyword_counter.most_common():
    print(f'  {cnt:>4}건  {kw}')

print()
# is_keep 값 분포
keep_counter = Counter(r.get('is_keep','') for r in rows)
print('=== is_keep 분포 ===')
for k, v in keep_counter.items():
    print(f'  {repr(k)}: {v}건')
