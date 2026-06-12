"""normalize_claim(3단계) gold — 실문장에서 value/period/compare 3슬롯 추출 (verbatim).

2_single_sentence_for_claim_extractor.txt 의 실제 문장에서
 value(증감·절대값 번갈아) / period_value / compare_period_value 의 raw 를 그대로 뽑고,
 base(2025 추정) + 정규화 정답(expected) 을 붙인다.
환각 방지: 각 항목의 3개 raw 가 같은 실제 문장에 동시 등장하는지 검증.

행: {id, base, value{raw,kind,expected,match}, period_value{...}, compare_period_value{...}|null, src}
정답 규약: % 안 나눔, period YYYY/YYYY-MM/YYYY-Qn, 상대시점=base 추정 계산.
"""
import json
import re
from pathlib import Path

SRC = "benchmark/data/2_single_sentence_for_claim_extractor.txt"
text = open(SRC, encoding="utf-8").read()

# 문장 분리(소수점/날짜 오분리 방지) ─ 검증용
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

SENTS = [snt for para in text.splitlines() if para.strip() for snt in split_sentences(para)]

# (vk, v_raw, v_exp, p_raw, p_exp, c_raw, c_exp, base)  — c_raw/c_exp None 가능
ITEMS = [
    ("절대값", "2858만9000명", "28589000", "지난 3월", "2025-03", "전년 동월", "2024-03", "2025-04"),
    ("증감",  "2.2% 상승",   "+2.2",     "지난달",   "2025-01", "전년 동월", "2024-01", "2025-02"),
    ("절대값", "2888만7000명", "28887000", "지난달",   "2025-04", "작년 4월",  "2024-04", "2025-05"),
    ("증감",  "7.3% 증가",   "+7.3",     "지난달",   "2025-01", None,        None,      "2025-02"),
    ("절대값", "323만4000명",  "3234000",  "지난달",   "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("증감",  "21만6000명 증가", "+216000", "지난달",   "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("절대값", "441만4000명",  "4414000",  "지난달",   "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("증감",  "8만3000명 줄었다", "-83000",  "지난달",   "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("절대값", "196만명",     "1960000",  "지난달",   "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("증감",  "9만7000명 감소", "-97000",  "지난달",   "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("절대값", "115.71",      "115.71",   "지난달",   "2025-01", "전년 동월", "2024-01", "2025-02"),
    ("증감",  "2.9% 올랐",   "+2.9",     "지난달",   "2025-02", "전년 동월", "2024-02", "2025-03"),
    ("절대값", "28만9000명",   "289000",   "지난달",   "2025-03", None,        None,      "2025-04"),
    ("증감",  "1.7%포인트 감소", "-1.7",    "지난달",   "2025-02", "전년 같은 달", "2024-02", "2025-03"),
    ("절대값", "2909만1000명", "29091000", "지난달",   "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("증감",  "18만3000명 늘었다", "+183000", "지난달",  "2025-06", "전년 동월", "2024-06", "2025-07"),
    ("절대값", "2804만1000명", "28041000", "지난달",   "2024-12", "전년 동월", "2023-12", "2025-01"),
    ("증감",  "5만2000명 감소", "-52000",  "지난달",   "2024-12", "전년 동월", "2023-12", "2025-01"),
    ("절대값", "2787만8000명", "27878000", "지난달",   "2025-01", "1년 전",   "2024-01", "2025-02"),
    ("증감",  "13만5000명 늘었다", "+135000", "지난달",  "2025-01", "1년 전",   "2024-01", "2025-02"),
    ("절대값", "116.08",      "116.08",   "지난달",   "2025-02", "전년 동월", "2024-02", "2025-03"),
    ("증감",  "6.3% 올라",   "+6.3",     "지난달",   "2025-02", "전년 동월", "2024-02", "2025-03"),
    ("절대값", "0.82명",      "0.82",     "지난 1분기", "2025-Q1", "1년 전",   "2024",    "2025-04"),
    ("증감",  "0.05명 증가",  "+0.05",    "지난 1분기", "2025-Q1", "1년 전",   "2024",    "2025-04"),
    ("절대값", "6만5022명",    "65022",    "1분기",    "2025-Q1", "1년 전",   "2024",    "2025-04"),
    ("증감",  "7.4% 늘었다",  "+7.4",     "1분기",    "2025-Q1", "1년 전",   "2024",    "2025-04"),
    ("절대값", "856만8000명",  "8568000",  "지난 8월", "2025-08", "전년 동월", "2024-08", "2025-09"),
    ("증감",  "11만 명 증가",  "+110000",  "지난 8월", "2025-08", "전년 동월", "2024-08", "2025-09"),
    ("절대값", "630만2000명",  "6302000",  "지난해",   "2024",    "전년",      "2023",    "2025-10"),
    ("증감",  "19만3000명 줄었다", "-193000", "지난해",  "2024",    "전년",      "2023",    "2025-10"),
]


def _find_src(raws):
    hits = [s for s in SENTS if all(r in s for r in raws if r)]
    return hits


rows = []
for i, (vk, v, ve, p, pe, c, ce, base) in enumerate(ITEMS, 1):
    raws = [v, p] + ([c] if c else [])
    hits = _find_src(raws)
    assert hits, f"item {i}: raws 동시 등장 문장 없음 — {raws}"
    row = {
        "id": i, "base": base,
        "value": {"raw": v, "kind": vk, "expected": ve, "match": "num"},
        "period_value": {"raw": p, "expected": pe, "match": "exact"},
        "compare_period_value": ({"raw": c, "expected": ce, "match": "exact"} if c else None),
        "src": hits[0],
    }
    rows.append(row)

out = Path("benchmark/data/3_normalize_claim_gold.jsonl")
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

from collections import Counter
nc = sum(1 for r in rows if r["compare_period_value"])
print(f"작성: {out}  ({len(rows)}건, 전부 실문장 검증 통과)")
print(f"value kind: {dict(Counter(r['value']['kind'] for r in rows))}")
print(f"compare 포함: {nc}건 / 미포함: {len(rows)-nc}건")
print("\n[샘플 3건]")
for r in rows[:3]:
    print(json.dumps(r, ensure_ascii=False))
