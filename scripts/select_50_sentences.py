"""클라비 엑셀에서 통계청 언급 + 수치 있는 문장 50개 추출 → JSON 저장."""
import json
import re
import openpyxl

EXCEL_PATH = r'D:\Cursor\Project\AIFFEL thon\Data\클라비 제공 뉴스 기사 데이터.xlsx'
OUT_PATH = 'scripts/recall_50_sentences.json'
TARGET = 50

STAT_KEYWORDS = ['통계청에 따르면', '통계청은', '통계청이', '통계청 발표', '통계청 조사']
NUMBER_RE = re.compile(r'\d')
NOISE_RE = re.compile(r'입력\s*\d{4}|\d{4}\.\d{2}\.\d{2}.*?:\d{2}|^\[|\bhttp')


def extract_stat_sentences(body: str) -> list[str]:
    """통계청 언급 기준으로 문장 추출 (마침표 경계)."""
    results = []
    for kw in STAT_KEYWORDS:
        pos = 0
        while True:
            idx = body.find(kw, pos)
            if idx == -1:
                break
            # 이전 마침표(문장 시작) 찾기
            start = body.rfind('.', max(0, idx - 200), idx)
            start = start + 1 if start != -1 else max(0, idx - 150)
            # 다음 마침표(문장 끝) 찾기
            end = body.find('.', idx)
            if end == -1:
                end = min(len(body), idx + 200)
            else:
                end = min(end + 1, len(body))
            sent = body[start:end].strip()
            pos = idx + len(kw)
            if sent:
                results.append(sent)
    return results


wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
ws = wb.active
TITLE_COL, URL_COL, BODY_COL = 0, 2, 3

collected = []
seen = set()

for row in ws.iter_rows(min_row=2, values_only=True):
    body = row[BODY_COL]
    if not body or not isinstance(body, str):
        continue

    for sent in extract_stat_sentences(body):
        # 기본 품질 필터
        if len(sent) < 25 or len(sent) > 300:
            continue
        if not NUMBER_RE.search(sent):
            continue
        if NOISE_RE.search(sent):
            continue
        sent_norm = re.sub(r'\s+', ' ', sent)
        if sent_norm in seen:
            continue
        seen.add(sent_norm)
        collected.append({
            'idx': len(collected) + 1,
            'title': str(row[TITLE_COL] or ''),
            'url': str(row[URL_COL] or ''),
            'sentence': sent_norm,
        })
        if len(collected) >= TARGET:
            break
    if len(collected) >= TARGET:
        break

print(f'수집된 문장: {len(collected)}개')
print()
for item in collected:
    print(f'[{item["idx"]:>2}] {item["sentence"][:130]}')

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(collected, f, ensure_ascii=False, indent=2)
print(f'\n저장 완료 → {OUT_PATH}')
