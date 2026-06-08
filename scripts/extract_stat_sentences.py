"""articles.md에서 통계청 언급 + 수치 있는 문장 50개 추출."""
import re

with open('data/eval/articles.md', encoding='utf-8') as f:
    text = f.read()

# 기사별로 분리
article_blocks = re.split(r'\n---\n', text)

stat_pattern = re.compile(
    r'통계청|국토교통부에 따르면|고용노동부에 따르면|기획재정부에 따르면|'
    r'통계청에 따르면|국가통계|통계에 따르면|행정안전부에 따르면'
)
number_pattern = re.compile(r'\d')

results = []
for block in article_blocks:
    # article_id 추출
    id_match = re.search(r'^## ([A-Z0-9]+)', block, re.MULTILINE)
    article_id = id_match.group(1) if id_match else 'unknown'

    # 문장 단위로 분리
    sentences = re.split(r'(?<=[.。])\s+|(?<=다\.)\s+|(?<=다\.\n)', block)
    for sent in sentences:
        sent = sent.strip()
        if (len(sent) > 20
                and stat_pattern.search(sent)
                and number_pattern.search(sent)):
            results.append({'article_id': article_id, 'sentence': sent})

print(f'총 후보 문장: {len(results)}개')
print()
for i, r in enumerate(results[:60], 1):
    print(f'[{i:>2}] {r["article_id"]}')
    print(f'     {r["sentence"][:150]}')
    print()
