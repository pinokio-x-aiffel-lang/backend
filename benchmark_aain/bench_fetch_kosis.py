"""한 claim 후보 통계표를 3방식으로 조회 — 네이티브 async(aiohttp), src.kosis 미사용.

case1: 후보 1개 / case2: 후보 전체 순차 / case3: 후보 전체 동시(gather).
기존 동기 모듈(requests+to_thread) 대신 aiohttp 코루틴으로 직접 비동기 호출한다.
한 표 조회 = getMeta(ITM) + getList (메타+데이터 2콜).
실행: uv run python benchmark/bench_fetch_kosis.py [--claim "subject:pop:period:unit"]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time

import aiohttp
from dotenv import load_dotenv

SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
META_URL = "https://kosis.kr/openapi/statisticsData.do"  # getMeta
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"  # getList

DEFAULT_CLAIM = ("총인구수", "전국", "2023", "명")  # subject, population, period, unit
_TOTAL_NAMES = {"계", "전체", "합계", "전국", "소계", "총계"}


def _api_key() -> str:
    load_dotenv()
    key = os.getenv("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 없음 (.env 확인)")
    return key


async def _get(session: aiohttp.ClientSession, url: str, params: dict) -> list[dict]:
    """KOSIS GET (format=json, jsonVD=Y) → list[dict]. err 응답이면 RuntimeError."""
    p = {"format": "json", "jsonVD": "Y", **params}
    async with session.get(url, params=p) as resp:
        resp.raise_for_status()
        data = json.loads(await resp.text())  # KOSIS content-type 회피
    if isinstance(data, dict):
        if "err" in data or "errMsg" in data:
            raise RuntimeError(f"{data.get('err')}: {data.get('errMsg')}")
        return [data]
    return data if isinstance(data, list) else []


async def _search(session, key, keyword, top_n=10) -> list[tuple[str, str]]:
    """statisticsSearch.do → [(org_id, tbl_id), ...] 상위 top_n."""
    rows = await _get(session, SEARCH_URL, {
        "method": "getList", "apiKey": key, "searchNm": keyword,
        "startCount": "1", "resultCount": str(top_n), "sort": "RANK",
    })
    return [(str(r.get("ORG_ID", "")), str(r.get("TBL_ID", ""))) for r in rows][:top_n]


def _norm(s) -> str:
    return "".join(str(s or "").split())


def _match_code(rows, target):
    """ITM_NM 이 target 과 일치(정확>부분)하는 행의 ITM_ID. 없으면 None."""
    t = _norm(target)
    if not t:
        return None
    for r in rows:
        if _norm(r.get("ITM_NM")) == t:
            return r.get("ITM_ID")
    cands = [r for r in rows if t in _norm(r.get("ITM_NM")) or _norm(r.get("ITM_NM")) in t]
    if cands:
        cands.sort(key=lambda r: len(_norm(r.get("ITM_NM"))))
        return cands[0].get("ITM_ID")
    return None


def _total_code(rows):
    for r in rows:
        if _norm(r.get("ITM_NM")) in _TOTAL_NAMES:
            return r.get("ITM_ID")
    return None


async def _query_one(session, key, org_id, tbl_id, subject, population, period):
    """후보 표 1개: getMeta(ITM)→이름매칭→getList→셀값. 실패 None. (메타+데이터 2콜)"""
    try:
        itm = await _get(session, META_URL, {
            "method": "getMeta", "apiKey": key, "type": "ITM",
            "orgId": org_id, "tblId": tbl_id,
        })
        items = [r for r in itm if isinstance(r, dict) and r.get("OBJ_ID") == "ITEM"]
        axes: dict[str, list] = {}
        for r in itm:
            if isinstance(r, dict) and r.get("OBJ_ID") and r["OBJ_ID"] != "ITEM":
                axes.setdefault(r["OBJ_ID"], []).append(r)

        itm_id = _match_code(items, subject)
        if itm_id is None:
            return None
        axis_ids = sorted(axes)
        if len(axis_ids) > 2:
            return None
        codes = []
        for oid in axis_ids:
            c = _match_code(axes[oid], population) or _total_code(axes[oid])
            if c is None:
                return None
            codes.append(c)

        rows = await _get(session, DATA_URL, {
            "method": "getList", "apiKey": key, "itmId": itm_id,
            "objL1": codes[0] if codes else "",
            "objL2": codes[1] if len(codes) > 1 else "",
            "objL3": "", "objL4": "", "objL5": "", "objL6": "", "objL7": "", "objL8": "",
            "prdSe": "Y", "startPrdDe": period, "endPrdDe": period,
            "orgId": org_id, "tblId": tbl_id,
        })
        match = {f"C{i + 1}": c for i, c in enumerate(codes)}
        for row in rows:
            if row.get("PRD_DE") == period and all(row.get(k) == v for k, v in match.items()):
                try:
                    return float(row.get("DT"))
                except (TypeError, ValueError):
                    return None
        return None
    except (aiohttp.ClientError, RuntimeError, json.JSONDecodeError):
        return None


async def _run(spec: tuple[str, str, str, str]) -> None:
    subject, population, period_raw, unit = spec
    period = re.sub(r"\D", "", period_raw)[:4]
    key = _api_key()
    label = f"{subject}/{population}/{period_raw}"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        cands = await _search(s, key, subject, top_n=10)  # 후보 수집 (측정 제외)
        n = len(cands)
        print(f"claim: subject={subject} population={population} period={period_raw} unit={unit}")
        print(f"후보 {n}개: {[t for _, t in cands]}\n")

        # case1 — 후보 1개만
        t0 = time.perf_counter()
        r1 = await _query_one(s, key, cands[0][0], cands[0][1], subject, population, period)
        print(f"[case1] claim={label} | 후보 1개({cands[0][1]}) 호출      "
              f"| {time.perf_counter() - t0:.2f}s (값={r1})")
        
        # case2 — 후보 전체 순차
        t0 = time.perf_counter()
        r2 = []
        for org, tbl in cands:
            r2.append(await _query_one(s, key, org, tbl, subject, population, period))
        print(f"[case2] claim={label} | 후보 {n}개 순차 호출   "
              f"| {time.perf_counter() - t0:.2f}s (성공 {sum(x is not None for x in r2)}/{n})")

        # case3 — 후보 전체 동시(gather)
        t0 = time.perf_counter()
        r3 = await asyncio.gather(*(
            _query_one(s, key, org, tbl, subject, population, period) for org, tbl in cands
        ))
        print(f"[case3] claim={label} | 후보 {n}개 비동기 호출 "
              f"| {time.perf_counter() - t0:.2f}s (성공 {sum(x is not None for x in r3)}/{n})")


def main() -> None:
    ap = argparse.ArgumentParser(description="후보 통계표 조회 방식별 시간 비교 (aiohttp)")
    ap.add_argument(
        "--claim", type=lambda s: tuple(p.strip() for p in s.split(":")),
        default=DEFAULT_CLAIM, help="단일 claim 'subject:pop:period:unit'",  # 단일 claim
    )
    asyncio.run(_run(ap.parse_args().claim))


if __name__ == "__main__":
    main()
