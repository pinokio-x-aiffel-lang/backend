import sys, urllib.request, json, re
sys.path.insert(0, r"C:\Users\innnn\AppData\Local\uv\cache\archive-v0\FNlgdzvxzNzdvOr_\Lib\site-packages")
import json5

KEY = "MTlkYjE3YjFjY2RlZDUzMzA2MTZjMjIwMmFmNzNmMGU="

# format=json (no jsonVD=Y) - MCP가 실제로 보내는 것
url = (
    "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    "?method=getList&apiKey=" + KEY +
    "&itmId=ALL&objL=ALL&objL1=ALL&objL2=ALL&objL3=ALL&objL4=&objL5=&objL6=&objL7=&objL8="
    "&format=json&prdSe=H&startPrdDe=202401&endPrdDe=202502&orgId=301&tblId=DT_105Y001"
)

with urllib.request.urlopen(url, timeout=10) as r:
    text = r.read().decode("utf-8")

print(f"응답 길이: {len(text)} bytes")
print(f"앞 200자: {text[:200]}")
print()

# json5로 파싱 시도
try:
    data = json5.loads(text)
    print(f"json5.loads: {type(data).__name__} {len(data) if isinstance(data, list) else data}")
except Exception as e:
    print(f"json5.loads 실패: {e}")
