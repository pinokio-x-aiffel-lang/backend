"""실패한 79개 표의 ITM/PRD 메타를 관대한 파서로 재처리.

원래 크롤러는 httpx 의 resp.json() (표준 json) 을 써서 KOSIS 의 비표준
escape 문자가 든 응답을 파싱 못 했다(Invalid \escape 등).

여기서는:
1. resp.text 를 받아
2. json.loads → 실패 시 json5.loads → 실패 시 escape 수선 후 재시도
순으로 관대하게 파싱한다.

결과는 patch JSONL 로 저장. CSV 생성 시 원본 JSONL 위에 덮어쓴다.

실행:
    uv run --with json5 python kosis/innnn/_meta_reprocess.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

import httpx
from dotenv import load_dotenv

try:
    import json5
except ImportError:
    json5 = None

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()
API_KEY = os.getenv("KOSIS_API_KEY")
META_URL = "https://kosis.kr/openapi/statisticsData.do"

FAIL_KEYS = "kosis/innnn/_meta_fail_keys.json"
PATCH_OUT = "kosis/innnn/kosis_meta_patch.jsonl"
TYPES = ["ITM", "PRD"]


def robust_parse(text: str):
    """표준 json → json5 → escape 수선 순으로 파싱 시도."""
    # 1. 표준
    try:
        return json.loads(text), "json"
    except Exception:
        pass
    # 2. json5
    if json5 is not None:
        try:
            return json5.loads(text), "json5"
        except Exception:
            pass
    # 3. 잘못된 escape 수선: 유효 escape(\" \\ \/ \b \f \n \r \t \uXXXX) 가
    #    아닌 백슬래시를 \\ 로 치환
    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
    try:
        return json.loads(fixed), "escape-fixed"
    except Exception:
        pass
    # 4. KOSIS 특유: 값 끝 백슬래시를 escape 안 함 → \" 가 닫는 따옴표를 깸.
    #    구조문자(, } ]) 앞의 \" 는 "값끝 백슬래시 + 닫는따옴표" 로 보고 백슬래시 이중화.
    fixed2 = re.sub(r'\\"(?=\s*[,}\]])', r'\\\\"', text)
    try:
        return json.loads(fixed2), "trailing-bs-fixed"
    except Exception as e:
        return None, f"failed: {e}"


def fetch(client: httpx.Client, org_id: str, tbl_id: str, meta_type: str):
    params = {
        "method": "getMeta",
        "apiKey": API_KEY,
        "format": "json",
        "jsonVD": "Y",
        "orgId": org_id,
        "tblId": tbl_id,
        "type": meta_type,
    }
    for attempt in range(3):
        try:
            r = client.get(META_URL, params=params, timeout=30)
            r.raise_for_status()
            data, method = robust_parse(r.text)
            return data, method
        except Exception as e:
            time.sleep(0.5 * (attempt + 1))
            last = e
    return None, f"http-failed: {last}"


def main() -> None:
    if not API_KEY:
        raise SystemExit("KOSIS_API_KEY 없음")

    with open(FAIL_KEYS, encoding="utf-8") as f:
        keys = json.load(f)
    print(f"재처리 대상: {len(keys)}건\n")

    parse_methods: dict[str, int] = {}
    still_failed = []

    with open(PATCH_OUT, "w", encoding="utf-8") as out, httpx.Client() as client:
        for i, (org_id, tbl_id) in enumerate(keys, 1):
            items, errors = {}, {}
            for t in TYPES:
                data, method = fetch(client, org_id, tbl_id, t)
                parse_methods[method.split(":")[0]] = (
                    parse_methods.get(method.split(":")[0], 0) + 1
                )
                if data is None:
                    errors[t] = method
                elif isinstance(data, dict) and ("err" in data or "errMsg" in data):
                    errors[t] = f"{data.get('err')}: {data.get('errMsg')}"
                else:
                    items[t] = data
            rec = {"orgId": org_id, "tblId": tbl_id, "items": items, "errors": errors}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

            itm_ok = "ITM" in items and items["ITM"]
            if not itm_ok:
                still_failed.append((org_id, tbl_id, errors.get("ITM", "")))
            print(f"  [{i}/{len(keys)}] org={org_id} tbl={tbl_id} "
                  f"ITM={'O' if itm_ok else 'X'} PRD={'O' if 'PRD' in items else 'X'}")

    print(f"\n=== 파싱 방법 분포 ===")
    for m, c in parse_methods.items():
        print(f"  {m}: {c}")
    print(f"\n=== 여전히 실패 ITM: {len(still_failed)}건 ===")
    for o, t, e in still_failed:
        print(f"  org={o} tbl={t}: {e[:60]}")
    print(f"\npatch 저장: {PATCH_OUT}")


if __name__ == "__main__":
    main()
