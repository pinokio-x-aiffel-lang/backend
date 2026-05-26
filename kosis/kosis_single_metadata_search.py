"""
수집 항목 (getMeta의 type):
    - TBL    : 통계표명칭
    - ORG    : 기관명칭
    - PRD    : 수록정보 (수록기간 등)
    - ITM    : 분류/항목 정보
    - CMMT   : 주석
    - UNIT   : 단위
    - SOURCE : 출처
    - WGT    : 가중치

API 키는 프로젝트 루트의 .env 파일에서 읽는다.
    KOSIS_API_KEY=발급받은_인증키
"""
import json
from kosis_metadata import KosisMetadataCollector

c = KosisMetadataCollector()


data = c.fetch_meta_item("101", "DT_1YL20581", "TBL")
print("=== type=TBL ===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])

data = c.fetch_meta_item("101", "DT_1YL20581", "ORG")
print("\n=== type=ORG ===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])

data = c.fetch_meta_item("101", "DT_1YL20581", "PRD")
print("\n=== type=PRD ===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])

data = c.fetch_meta_item("101", "DT_1YL20581", "ITM")
print("\n=== type=ITM ===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])

data = c.fetch_meta_item("101", "DT_1YL20581", "CMMT")
print("\n=== type=CMMT ===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])

data = c.fetch_meta_item("101", "DT_1YL20581", "UNIT")
print("\n=== type=UNIT ===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])

data = c.fetch_meta_item("101", "DT_1YL20581", "SOURCE")
print("\n=== type=SOURCE ===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])

