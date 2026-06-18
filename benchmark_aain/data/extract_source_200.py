"""85MB CSV 스트리밍 → claim extractor 통과형(통계 claim) 문장 200개 추출.

예시형: "19일 국가데이터처(옛 통계청)에 따르면, 지난 달 청년층 고용률은 45.1%로 ... 낮아졌다."
점수 = value(필수) + 출처인용(가중2) + 시점 + 증감 + 비교시점.
전망·예상·견해(단일컷 비-claim)는 배제. 문장은 원문 그대로(무수정) 기록.
기사당 best 1문장 → 데이터셋 전 구간 균등 분산 200개 → txt.
"""
import csv
import re
from pathlib import Path

csv.field_size_limit(10 ** 7)
SRC = Path("benchmark/data/[AI 기반 뉴스 사실검증 시스템] 프로젝트 데이터.csv")
OUT = Path("benchmark/data/source_200_from_origin.txt")
N_TARGET = 200

NOISE = re.compile(r"기자\s|입력 20\d\d\.|업데이트 20\d\d\.|\d\d:\d\d|◇|@|无|http")
VALUE = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:%|％|퍼센트|포인트|명|원|건|개|배|가구|달러|톤|㎏|kg|조|억|만)")
SOURCE = re.compile(r"에 따르면|발표한|발표했다|조사 결과|집계됐다|집계 결과|통계청|국가데이터처|한국은행|국토교통부|고용노동부|보건복지부")
CHANGE = re.compile(r"증가|감소|상승|하락|늘었|늘어|줄었|줄어|올랐|내렸|낮아졌|높아졌|급증|급감|확대|축소|차지했")
TIME = re.compile(r"지난달|지난해|지난\s?\d{1,2}월|전년|작년|올해|전월|전분기|동월|동분기|\d{4}년|\d\s?분기|상반기|하반기|이달|1년 전")
COMPARE = re.compile(r"전년\s?동월|전년\s?동분기|1년\s?전|전\s?분기|전월\s?대비|전년 대비|작년보다|지난해보다|동월 대비")
# 단일컷: 전망·예상·견해·기록추세는 비-claim → 배제
EXCLUDE = re.compile(r"전망|예상|예측|관측|추정|것으로 보|것이라고|만에 가장|만에 최|이후 최대|이후 최저|이후 가장|역대 최")

CLOSERS = "”’\"')"
def split_sentences(s):
    s = s.strip(); out = []; start = i = 0; n = len(s)
    while i < n:
        c = s[i]
        if c in ".?!":
            prev = s[i-1] if i > 0 else ""; j = i + 1
            while j < n and s[j] in CLOSERS: j += 1
            if ((j >= n) or s[j].isspace()) and not prev.isdigit():
                seg = s[start:j].strip()
                if seg: out.append(seg)
                while j < n and s[j].isspace(): j += 1
                start = i = j; continue
        i += 1
    if s[start:].strip(): out.append(s[start:].strip())
    return out

def score(sent):
    if not VALUE.search(sent): return 0
    if EXCLUDE.search(sent): return 0
    sc = 1
    if SOURCE.search(sent): sc += 2
    if TIME.search(sent): sc += 1
    if CHANGE.search(sent): sc += 1
    if COMPARE.search(sent): sc += 1
    return sc

best = []          # (aidx, score, sent) — 기사당 best 1
seen = set()
n_art = 0
with open(SRC, encoding="utf-8", errors="replace", newline="") as fh:
    r = csv.reader(fh)
    next(r)  # header
    for row in r:
        if len(row) < 5: continue
        n_art += 1
        body = row[3]
        bsc, bsent = 0, None
        for sent in split_sentences(body):
            if not (30 <= len(sent) <= 180): continue
            if NOISE.search(sent): continue
            if sent in seen: continue
            sc = score(sent)
            if sc > bsc:
                bsc, bsent = sc, sent
        if bsent and bsc >= 3:
            seen.add(bsent)
            best.append((n_art, bsc, bsent))

# 고득점 우선 풀 구성 후 전 구간 균등 분산
pool = [b for b in best if b[1] >= 5]
if len(pool) < N_TARGET:
    pool = [b for b in best if b[1] >= 4]
if len(pool) < N_TARGET:
    pool = best
pool.sort(key=lambda b: b[0])

# 근사-중복 제거(같은 사실의 타기사 재보도) — 유사도 0.8 초과면 뒤 문장 폐기
from difflib import SequenceMatcher
deduped = []
for b in pool:
    if all(SequenceMatcher(None, b[2], k[2]).ratio() <= 0.8 for k in deduped):
        deduped.append(b)
pool = deduped
N = min(N_TARGET, len(pool))
idxs = sorted({round(i * (len(pool) - 1) / (N - 1)) for i in range(N)}) if N > 1 else [0]
k = 0
while len(idxs) < N:
    if k not in idxs: idxs.append(k)
    k += 1
idxs = sorted(idxs)[:N]
picked = [pool[i] for i in idxs]

OUT.write_text("\n".join(p[2] for p in picked) + "\n", encoding="utf-8")

from collections import Counter
print(f"기사 스캔: {n_art:,}  |  후보(기사당 best, score>=3): {len(best):,}  |  풀: {len(pool):,}")
print(f"선정: {len(picked)}개 → {OUT}")
print(f"score 분포: {dict(sorted(Counter(p[1] for p in picked).items()))}")
print("\n[샘플 5]")
for p in picked[:5]:
    print(f"  [s{p[1]}] {p[2][:90]}")
