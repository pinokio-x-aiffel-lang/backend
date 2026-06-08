"""50개 문장 → extractor로 subject 추출 → KOSIS search → recall 결과 출력.

실행:
    uv run python scripts/run_recall_50.py
"""
import asyncio
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()

from src.kosis.search import search_tables
from src.modules.extract_statistical_claims import extract_statistical_claims
from src.schemas.runtime import Article, MasterSchema

SENTENCES_PATH = 'scripts/recall_50_sentences.json'
OUT_PATH = 'scripts/recall_50_results.json'
TOP_N = 10


async def extract_claims_full(sentence: str, idx: int) -> list[dict]:
    """문장 1개 → extract_statistical_claims → 전체 claim 필드 리스트."""
    ms = MasterSchema(
        article=Article(
            article_id=f'recall-{idx:03d}',
            title='',
            content=sentence,
        )
    )
    await extract_statistical_claims(ms)
    result = []
    for c in ms.claims:
        result.append({
            'claim_id':     c.claim_id,
            'claim_type':   c.claim_type.value if c.claim_type else '',
            'subject':      c.subject,
            'value_raw':    c.value.raw if c.value else '',
            'unit':         c.unit,
            'period_type':  c.period_type,
            'period_raw':   c.period_value.raw if c.period_value else '',
            'population':   c.population,
            'cited_source': c.cited_source,
        })
    return result


def search_kosis(subject: str) -> list[dict]:
    """subject → KOSIS top-10 후보표 리스트."""
    try:
        hits = search_tables(subject, top_n=TOP_N)
        return [
            {'rank': i + 1, 'tbl_id': h.tbl_id, 'tbl_nm': h.tbl_nm,
             'stat_nm': h.stat_nm, 'org_nm': h.org_nm}
            for i, h in enumerate(hits)
        ]
    except Exception as e:
        return [{'error': str(e)}]


async def process_one(item: dict) -> dict:
    idx = item['idx']
    sentence = item['sentence']

    print(f'[{idx:>2}/50] 처리 중...')
    t0 = time.perf_counter()

    claims = await extract_claims_full(sentence, idx)
    subjects = [c['subject'] for c in claims if c['subject'] and c['subject'] != '불명']
    kosis_results = {}
    for subj in subjects:
        kosis_results[subj] = search_kosis(subj)

    elapsed = int((time.perf_counter() - t0) * 1000)
    result = {
        'idx': idx,
        'sentence': sentence,
        'claims': claims,
        'kosis': kosis_results,
        'elapsed_ms': elapsed,
    }

    # 즉시 콘솔 출력
    print(f'     claims: {[c["subject"] for c in claims]}')
    for subj, hits in kosis_results.items():
        top3 = [f"{h.get('tbl_nm','?')} ({h.get('tbl_id','?')})" for h in hits[:3]]
        print(f'     [{subj}] top3: {top3}')
    print()

    return result


async def main():
    if not os.getenv('KOSIS_API_KEY'):
        raise SystemExit('KOSIS_API_KEY 가 .env 에 없습니다.')

    with open(SENTENCES_PATH, encoding='utf-8') as f:
        sentences = json.load(f)

    print(f'총 {len(sentences)}개 문장 처리 시작\n{"=" * 60}')
    results = []
    for item in sentences:
        result = await process_one(item)
        results.append(result)

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 요약
    total = len(results)
    no_subject = sum(1 for r in results if not r['claims'])
    no_hits = sum(
        1 for r in results
        if r['kosis'] and all(not v for v in r['kosis'].values())
    )
    print(f'{"=" * 60}')
    print(f'완료: {total}건')
    print(f'  subject 못 찾음: {no_subject}건')
    print(f'  KOSIS 결과 없음: {no_hits}건')
    print(f'결과 저장 → {OUT_PATH}')


if __name__ == '__main__':
    asyncio.run(main())
