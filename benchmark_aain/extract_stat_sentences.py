"""85MB CSV 스트리밍 → 통계수치(특히 3단계 정규화 거리) 풍부한 문장 100개 분산 추출.

컬럼: 기사제목 / 작성일 / URL / 기사 본문 전체 / 레이블
점수 = value(필수) + 증감 + 시점 + 비교시점 + 값 2개이상.  점수 높을수록 normalize 테스트가치↑.
기사당 best 1문장 → 데이터셋 전 구간에 균등 분산 100개 → txt(+date tsv).
"""
import csv
import re
import sys
from pathlib import Path

csv.field_size_limit(10 ** 7)
SRC = Path("benchmark/data/[AI 기반 뉴스 사실검증 시스템] 프로젝트 데이터.csv")
OUT_TXT = Path("benchmark/data/3_normalize_candidates_100.txt")
OUT_TSV = Path("benchmark/data/3_normalize_candidates_100.tsv")

NOISE = re.compile(r"기자\s|입력 20\d\d\.|업데이트 20\d\d\.|\d\d:\d\d|◇|@|无|http")
VALUE = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:%|％|퍼센트|명|원|건|개|배|시간|가구|달러|톤|㎏|kg|포인트|조|억)")
CHANGE = re.compile(r"증가|감소|상승|하락|늘|줄|올라|올랐|내려|내렸|낮춰|낮아|높아|급증|급감|뛰|불어|확대|축소|반등")
TIME = re.compile(r"지난달|지난해|지난\s?\d{1,2}월|전년|작년|올해|올\s?\d\s?분기|전월|전분기|동월|동분기|\d{4}년|\d\s?분기|상반기|하반기|이달")
COMPARE = re.compile(r"전년\s?동월|전년\s?동분기|작년\s?\d{1,2}월|1년\s?전|전\s?분기|전분기|전월|전년 대비|작년보다|지난해보다")

CLOSERS = "”’\"')"
def split_sentences(s):
    s = s.strip(); out=[]; start=i=0; n=len(s)
    while i < n:
        c=s[i]
        if c in ".?!":
            prev=s[i-1] if i>0 else ""; j=i+1
            while j<n and s[j] in CLOSERS: j+=1
            if ((j>=n) or s[j].isspace()) and not prev.isdigit():
                seg=s[start:j].strip()
                if seg: out.append(seg)
                while j<n and s[j].isspace(): j+=1
                start=i=j; continue
        i+=1
    if s[start:].strip(): out.append(s[start:].strip())
    return out

def score(sent):
    if not VALUE.search(sent): return 0
    sc = 1
    if CHANGE.search(sent): sc += 1
    if TIME.search(sent): sc += 1
    if COMPARE.search(sent): sc += 1
    if len(VALUE.findall(sent)) >= 2: sc += 1
    return sc

best = []          # (aidx, date, score, sent) — 기사당 best 1
seen = set()
n_art = 0
with open(SRC, encoding="utf-8", errors="replace", newline="") as fh:
    r = csv.reader(fh)
    next(r)  # header
    for row in r:
        if len(row) < 5: continue
        n_art += 1
        date, body = row[1].strip(), row[3]
        bsc, bsent = 0, None
        for sent in split_sentences(body):
            if not (20 <= len(sent) <= 180): continue
            if NOISE.search(sent): continue
            if sent in seen: continue
            sc = score(sent)
            if sc > bsc:
                bsc, bsent = sc, sent
        if bsent and bsc >= 2:
            seen.add(bsent)
            best.append((n_art, date, bsc, bsent))

# score>=3 우선, 부족하면 2 보충 → 전 구간 균등 100개
pool = [b for b in best if b[2] >= 3] or best
if len(pool) < 100:
    pool = best
pool.sort(key=lambda b: b[0])
N = min(100, len(pool))
idxs = sorted({round(i * (len(pool) - 1) / (N - 1)) for i in range(N)}) if N > 1 else [0]
# 균등 후 부족분 채우기
k = 0
while len(idxs) < N:
    if k not in idxs: idxs.append(k)
    k += 1
idxs = sorted(idxs)[:N]
picked = [pool[i] for i in idxs]

OUT_TXT.write_text("\n".join(p[3] for p in picked) + "\n", encoding="utf-8")
with OUT_TSV.open("w", encoding="utf-8") as f:
    f.write("date\tscore\tsentence\n")
    for aidx, date, sc, sent in picked:
        f.write(f"{date}\t{sc}\t{sent}\n")

from collections import Counter
print(f"기사 스캔: {n_art:,}  |  후보(기사당 best, score>=2): {len(best):,}")
print(f"선정: {len(picked)}개  → {OUT_TXT}  (+ {OUT_TSV.name})")
print(f"score 분포: {dict(sorted(Counter(p[2] for p in picked).items()))}")
print(f"날짜 범위: {min(p[1] for p in picked)} ~ {max(p[1] for p in picked)}")
print("\n[샘플 5]")
for p in picked[:5]:
    print(f"  [{p[1]} s{p[2]}] {p[3][:75]}")
