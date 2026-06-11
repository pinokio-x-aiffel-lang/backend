"""KOSIS statisticsSearch.do 통합검색 테스트 (수동 스크립트).

대상 모듈: KOSIS Open API (statisticsSearch.do — 통계표 메타 검색)
작성자: leeaain2027 <leeaain2027@gmail.com>
작성일: 2026-06-08
"""
# 통계표의 메타 데이터를 받아옴
# 통계표 ID(TBL_ID)
# 통계표 명칭(TBL_NM)
# 통계 조사명 / 기관명 (ORG_ID, ORG_NM)
# 통계표가 속한 분류 경로 등

# KOSIS 검색 엔진의 자체 알고리즘에 의해 계산된 정확도(랭킹 점수)가 높은 순서대로 정렬되어 상위 n개가 반환

import os
import re
import json
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("KOSIS_API_KEY")

url = "https://kosis.kr/openapi/statisticsSearch.do"

params = {
    "method": "getList",
    "format": "json",
    "apiKey": API_KEY,
    "searchNm": "취업자",
    "resultCount": 10,      # 최대 n개
}

response = requests.get(url, params=params, timeout=10)

response.raise_for_status()

# KOSIS 검색 응답은 키가 따옴표 없이 오는 비표준 JSON이라 response.json()으로 못 읽음.
# 키만 따옴표로 감싸 표준 JSON으로 보정 후 파싱한다.
fixed_text = re.sub(
    r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', response.text
)
parsed = json.loads(fixed_text)

result = {
    "status_code": response.status_code,
    "content_type": response.headers.get("Content-Type"),
    # API Key가 포함된 전체 URL을 그대로 담지 않도록 주의 (URL 인코딩된 형태까지 마스킹)
    "request_url": re.sub(r"(apiKey=)[^&]+", r"\1[API_KEY_HIDDEN]", response.url),
    "response": parsed,
}

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "260608_4_kosis-search-table_leeaain.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(json.dumps(result, ensure_ascii=False, indent=2))
print(f"\nsaved to: {out_path}")
