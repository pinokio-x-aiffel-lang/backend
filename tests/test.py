import asyncio, json
from src.schemas.runtime import MasterSchema
from src.modules.retrieve_kosis_candidates import retrieve_kosis_candidates
from src.modules.fetch_kosis_data import fetch_kosis_data

data =   {
    "claims": [
      {
        "claim_id": "clm-0001",
        "article_id": "art-0001",
        "sentence": "(4~5단계는 안 읽음)",
        "claim_type": "absolute",
        "subject": "취업자 수",
        "value": {"raw": "2858만9000명", "llm_value": "28589000", "is_inferred": False},
        "unit": "명",
        "aggregation": "값",
        "period_type": "M",
        "period_value": {"raw": "지난 3월", "llm_value": "2025-03", "is_inferred": False},
        "compare_period_value": None,
        "population": "전체",
        "cited_source": "통계청"
      }
    ]
  }

ms = MasterSchema.model_validate(data)

async def run():
    await retrieve_kosis_candidates(ms)   # [4] → ms.analysis[*].candidates
    await fetch_kosis_data(ms)            # [5] → ms.analysis[*].evidences
asyncio.run(run())

an = ms.analysis[0]

for ev in an.evidences:
    print(ev.value, ev.unit, ev.period, ev.kosis_tbl_id, ev.population_fallback)
    
    
an = ms.analysis[1]

for ev in an.evidences:
    print(ev.value, ev.unit, ev.period, ev.kosis_tbl_id, ev.population_fallback)
